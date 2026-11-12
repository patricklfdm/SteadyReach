"""Prepare pinned public inputs and compare real output with independent references.

Published reference values never enter the solver input or the site result tables.
An exact public-input match is required before a run can claim benchmark agreement.
"""
import copy
import csv
import hashlib
import re
import urllib.request
import zipfile
import uuid
from pathlib import Path, PurePosixPath

from .common import ROOT, finite, intact, item, read, rel, safe_path, save, sha, utc
from .qa import number, verified_profiles

COM_METRICS = {
    'headwater_wse_ft': ('W.S. Elev', 'ft'),
    'inlet_control_egl_ft': ('E.G. IC', 'ft'),
    'outlet_control_egl_ft': ('E.G. OC', 'ft'),
    'culvert_group_flow_cfs': ('Q Culv Group', 'cfs'),
    'representative_barrel_flow_cfs': ('Q Barrel', 'cfs'),
    'roadway_flow_software_cfs': ('Q Weir', 'cfs'),
}


def obtain(entry, fetch=False):
    """Reuse only exact bytes; optional bounded HTTPS fetch, never overwrite a mismatch."""
    target = safe_path(ROOT, entry['path'])
    if target.exists():
        if not intact([entry]):
            raise ValueError('Source hash mismatch: ' + rel(target))
        return target
    if not fetch:
        raise ValueError('Source unavailable; use --fetch or restore verified file: ' + rel(target))
    if not entry.get('url', '').startswith('https://'):
        raise ValueError('Public source requires HTTPS')
    limit = entry['size_bytes']
    if not isinstance(limit, int) or not 0 < limit <= 600_000_000:
        raise ValueError('Public source size exceeds bounded download budget')
    target.parent.mkdir(parents=True, exist_ok=True)
    # A retry preserves a failed partial and starts a separately identifiable download.
    partial = target.with_name(target.name + '.' + uuid.uuid4().hex + '.partial')
    req = urllib.request.Request(entry['url'], headers={'User-Agent': 'Local-HEC-RAS-Validation/2.0'})
    total = 0
    with urllib.request.urlopen(req, timeout=45) as response, partial.open('xb') as f:
        if not response.url.startswith('https://'):
            raise ValueError('Source redirected outside HTTPS')
        size = int(response.headers.get('Content-Length', 0))
        if size and size != limit:
            raise ValueError('Public source size changed; review new source')
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > limit:
                raise ValueError('Source exceeded declared download size')
            f.write(chunk)
        url, headers = response.url, dict(response.headers)
    if total != limit or sha(partial) != entry['sha256']:
        raise ValueError('Downloaded source differs from pinned bytes; partial retained')
    partial.rename(target)
    save(target.with_name(target.name + '.request.json'), dict(requested_url=entry['url'],
         final_url=url, headers=headers, received_utc=utc(), file=item(target)))
    return target


def selected_members(archive, members):
    """Read only named small native inputs. No archive-controlled destination paths."""
    result = {}
    with zipfile.ZipFile(archive) as z:
        for record in members:
            name = record['destination']
            if PurePosixPath(name).name != name or '\\' in name or ':' in name or name in result:
                raise ValueError('Unsafe or duplicate native destination')
            if Path(name).suffix.lower() not in ['.prj', '.g01', '.p01', '.f01']:
                raise ValueError('Only baseline native input extensions are supported')
            if z.namelist().count(record['member']) != 1:
                raise ValueError('Missing or ambiguous archive member')
            info = z.getinfo(record['member'])
            if info.file_size != record['size_bytes'] or info.file_size > 1_000_000:
                raise ValueError('Unexpected native member size')
            data = z.read(info)
            if hashlib.sha256(data).hexdigest() != record['sha256']:
                raise ValueError('Native archive member hash mismatch')
            result[name] = data
    return result


def load_recipe(recipe_path):
    path = safe_path(ROOT, recipe_path); recipe = read(path)
    if recipe.get('schema_version') != '1.0' or recipe.get('preparation') != 'single_baseline_plan':
        raise ValueError('Unsupported public benchmark recipe')
    for key in ['project_template', 'comparison_seed']:
        if not intact([recipe[key]]):
            raise ValueError('Benchmark recipe dependency changed: ' + key)
    seed = read(ROOT / recipe['comparison_seed']['path'])
    if seed.get('status') != 'REFERENCE_ONLY_NOT_A_COMPUTED_RESULT':
        raise ValueError('Published expectations must be separate reference-only data')
    rows = seed.get('rows', [])
    if not rows or len({(r['profile'], r['metric'], r.get('group_id')) for r in rows}) != len(rows):
        raise ValueError('Reference metrics are missing or duplicated')
    for row in rows:
        if 'group_id' in row and (type(row['group_id']) is not int or row['group_id'] != 0 or row['metric']=='headwater_wse_ft'):
            raise ValueError('Only the independently observed first COM group is supported')
        if row['metric'] not in COM_METRICS or row['unit'] != COM_METRICS[row['metric']][1]:
            raise ValueError('Unsupported reference metric/unit')
        if not all(finite(row.get(k)) for k in ['published', 'tolerance']) or not 0 < row['tolerance'] <= .00501:
            raise ValueError('Reference tolerance exceeds displayed precision')
        if not isinstance(row.get('source_pdf_page'), int) or row['source_pdf_page'] < 1 or not row.get('source_printed_page'):
            raise ValueError('Published source page required')
    return path, recipe, seed


def prepare(recipe_path, output, fetch=False):
    path, recipe, seed = load_recipe(recipe_path)
    archive = obtain(recipe['archive'], fetch)
    reference = obtain(dict(seed['reference'], url=seed['reference_url']), fetch)
    data = selected_members(archive, recipe['members'])
    pname = recipe['project_name']; original = data[pname]
    # Only remove declarations of plans deliberately not copied. Preserve all other bytes.
    for declaration in recipe['remove_declarations']:
        pattern = rb'^' + re.escape(declaration.encode('ascii')) + rb'\r?\n'
        if len(re.findall(pattern, original, re.M)) != 1:
            raise ValueError('Expected unused-plan declaration not found exactly once')
        data[pname] = re.sub(pattern, b'', data[pname], flags=re.M)
    if hashlib.sha256(data[pname]).hexdigest() != recipe['prepared_project_sha256']:
        raise ValueError('Prepared native project differs from reviewed transformation')
    folder = safe_path(ROOT, output); folder.mkdir(parents=True, exist_ok=False)
    inp = folder / 'inputs'; inp.mkdir()
    for name, content in data.items():
        (inp / name).write_bytes(content)
    (inp / (pname + '.original')).write_bytes(original)
    # Snapshots preserve the independently reviewed recipe and expectations.
    for name, source in [('recipe.json', path), ('comparison.seed.json', ROOT / recipe['comparison_seed']['path'])]:
        (folder / name).write_bytes(source.read_bytes())
    configuration = read(ROOT / recipe['project_template']['path'])
    configuration['benchmark_preparation'] = 'preparation.json'
    save(folder / 'project.json', configuration)
    save(folder / 'preparation.json', dict(created_utc=utc(), status='PREPARED_NOT_COMPUTED',
         recipe=item(path), archive=item(archive), reference=item(reference),
         files=[item(p) for p in sorted(inp.iterdir())],
         source_snapshots=[item(folder / n) for n in ['recipe.json', 'comparison.seed.json']],
         transformations=recipe['remove_declarations'],
         limitations=['No geographic coordinates or geodetic datum supplied; not a georeferenced site or DEM validation'],
         engineering_acceptance='NOT_ASSESSED'))
    return folder / 'project.json'


def review_reference(seed, seed_identity, review_path):
    """Apply an explicit source reconciliation; preserve the immutable seed and tolerance."""
    path = safe_path(ROOT, review_path); review = read(path)
    if (review.get('schema_version') != 'benchmark_reference_review_1.0' or
        review.get('seed') != seed_identity or review.get('reference') != seed['reference'] or
        not review.get('reviewer') or not review.get('reason')):
        raise ValueError('Reference review requires matching seed/PDF identity and a stated reviewer/reason')
    revised = copy.deepcopy(seed); seen = set()
    for change in review.get('changes', []):
        index = change.get('row_index')
        if type(index) is not int or not 0 <= index < len(seed['rows']) or index in seen:
            raise ValueError('Invalid or duplicate reference row')
        seen.add(index); old = seed['rows'][index]
        if change.get('original') != old or not change.get('reason'):
            raise ValueError('Reference review must retain the complete original row and reason')
        replacement = change.get('replacement', {})
        if set(replacement) != {'published','source_pdf_page','source_printed_page','source_figure'}:
            raise ValueError('Only the published value and source location can be reconciled')
        if (not finite(replacement['published']) or type(replacement['source_pdf_page']) is not int or
            replacement['source_pdf_page'] < 1 or not replacement['source_printed_page'] or not replacement['source_figure']):
            raise ValueError('Explicit finite value and published table/figure location required')
        revised['rows'][index].update(replacement)
        revised['rows'][index]['original_reference'] = old
        revised['rows'][index]['reference_reconciliation_reason'] = change['reason']
    if not seen:
        raise ValueError('Empty reference review')
    return revised, item(path)


def compare(recipe_path, summary_path, output, reference_review=None):
    recipe_path, recipe, seed = load_recipe(recipe_path)
    review_identity = None
    if reference_review:
        seed, review_identity = review_reference(seed, recipe['comparison_seed'], reference_review)
    if not intact([seed['reference']]):
        raise ValueError('Published reference PDF unavailable or changed')
    summary_path = safe_path(ROOT, summary_path); summary = read(summary_path)
    c = summary['configuration']; hyd = summary.get('hydraulics')
    if not hyd or c['case_kind'] != 'official_benchmark' or c['project_id'] != recipe['benchmark_id']:
        raise ValueError('Result does not identify the selected official benchmark')
    verified_profiles(hyd)
    raw = safe_path(ROOT, hyd['raw_hdf']['path'])
    receipt_path = raw.parent.parent / 'manifest.json'; receipt = read(receipt_path)
    execution = receipt['execution']
    if (receipt['run_id'] != hyd['run_id'] or execution['run_id'] != hyd['run_id'] or
        execution.get('hdf_sha256') != hyd['raw_hdf']['sha256'] or
        not all(execution.get(k) for k in ['solver_invoked', 'compute_completed', 'output_identity_verified', 'output_written_this_run'])):
        raise ValueError('Matching actual solver execution evidence required')
    if not intact(receipt['native_before']) or not intact(receipt['outputs']):
        raise ValueError('Native input/output evidence changed')
    expected = {r['destination']: r['sha256'] for r in recipe['members']}
    expected[recipe['project_name']] = recipe['prepared_project_sha256']
    actual = {Path(r['path']).name: r['sha256'] for r in receipt['native_before']}
    if actual != expected:
        raise ValueError('Run native inputs do not match the published baseline plan')
    baseline = read(ROOT / recipe['project_template']['path'])
    if c['expected_native'] != baseline['expected_native'] or c['scenarios'] != baseline['scenarios']:
        raise ValueError('Benchmark geometry/flow specification differs from reference case')
    controller = read(ROOT / hyd['raw_controller']['path']); rows = []
    for ref in seed['rows']:
        field, unit = COM_METRICS[ref['metric']]
        headwater = ref['metric']=='headwater_wse_ft'
        station = c['expected_native']['us_xs_rs'] if headwater else c['expected_native']['structure_rs']
        matches = [r for r in controller['rows'] if r['profile'] == ref['profile'] and r['node_type'] == ('' if headwater else 'Culv')
                   and r['station'] == station and r['updn_argument'] == 0]
        if len(matches) != 1:
            raise ValueError('Missing or ambiguous raw structure metric')
        value = number(matches[0]['metrics'].get(field))
        profile = next(p for p in hyd['profiles'] if p['profile_id'] == ref['profile'])
        if 'group_id' in ref:
            group = profile['culvert_groups'][ref['group_id']]
            if group['flow_basis']!='COM_FIRST_GROUP':raise ValueError('Benchmark requires directly observed group output')
            summary_value = group.get('flow_cfs' if ref['metric']=='culvert_group_flow_cfs' else ref['metric'])
        else:summary_value = profile['metrics'].get(ref['metric'])
        if value != summary_value:
            raise ValueError('Summary metric differs from raw controller: ' + ref['metric'])
        difference = value - ref['published'] if value is not None else None
        passed = difference is not None and abs(difference) <= ref['tolerance']
        rows.append(dict(ref, actual=value, difference=difference,
                    status='PASS_PRINTED_PRECISION' if passed else ('MISSING' if value is None else 'REVIEW'),
                    raw_field=field, native_station=matches[0]['station']))
    folder = safe_path(ROOT, output); folder.mkdir(parents=True, exist_ok=False)
    result = dict(status='PASS_AT_PUBLISHED_PRECISION' if all(r['status']=='PASS_PRINTED_PRECISION' for r in rows) else 'REVIEW_REQUIRED',
        compared_utc=utc(), run_id=hyd['run_id'], solver_reused=summary['solver_reused'],
        sources=[item(recipe_path), recipe['comparison_seed'], seed['reference'], item(summary_path), item(receipt_path), hyd['raw_hdf'], hyd['raw_controller']],
        reference_url=seed['reference_url'], reference_plan=seed['reference_plan'], rows=rows,
        interpretation=seed['interpretation'], reference_review=review_identity,
        hydraulic_qa='REVIEW_REQUIRED', engineering_acceptance='NOT_ASSESSED')
    if review_identity:
        result['sources'].append(review_identity)
    save(folder / 'comparison.json', result)
    with (folder / 'comparison.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for row in rows for k in row))); writer.writeheader(); writer.writerows(rows)
    text = ['# Public benchmark comparison', '', result['status'], '',
            'Run: ' + hyd['run_id'], '', seed['interpretation'], '',
            '| Profile | Metric | Published | Actual | Difference | Unit | PDF page | Status |',
            '|---|---|---:|---:|---:|---|---:|---|']
    for r in rows:
        text.append('| ' + ' | '.join(str(r[k]) for k in ['profile','metric','published','actual','difference','unit','source_pdf_page','status']) + ' |')
    text += ['', 'Reference: ' + seed['reference_url'], '',
             'Each value was read again from the hash-verified raw controller output, linked to the real HDF and execution receipt. '
             'Native inputs must match the original published plan before comparison. Full warning-table review and engineering acceptance remain separate.']
    if review_identity:
        text += ['', 'Explicit reference reconciliation: '+review_identity['path'], '',
                 'The immutable seed and its original values are retained in comparison.json. No tolerance or native input was changed.']
    (folder / 'COMPARISON.md').write_text('\n'.join(text) + '\n', encoding='utf-8')
    return result
