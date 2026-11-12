"""Operator-observed 7.0.1 Culvert Output clipboard tables, at display precision.

This is a supplementary extraction of an existing solve, never a new solve or
an automatic GUI exporter. The original summary and COM values stay immutable.
"""
import csv
import math
import re
import shutil

import h5py

from .common import ROOT, intact, item, read, rel, safe_path, save, sha, utc
from .qa import number
from .qa_review import load_summary

METHOD = 'HEC-RAS Culvert Output / Copy to Clipboard (Data and Headings)'
LABELS = [
    ('Q Culv Group (cfs)', 'Culv Full Len (ft)'),
    ('# Barrels', 'Culv Vel US (ft/s)'),
    ('Q Barrel (cfs)', 'Culv Vel DS (ft/s)'),
    ('E.G. US. (ft)', 'Culv Inv El Up (ft)'),
    ('W.S. US. (ft)', 'Culv Inv El Dn (ft)'),
    ('E.G. DS (ft)', 'Culv Frctn Ls (ft)'),
    ('W.S. DS (ft)', 'Culv Exit Loss (ft)'),
    ('Delta EG (ft)', 'Culv Entr Loss (ft)'),
    ('Delta WS (ft)', 'Q Weir (cfs)'),
    ('E.G. IC (ft)', 'Weir Sta Lft (ft)'),
    ('E.G. OC (ft)', 'Weir Sta Rgt (ft)'),
    ('Culvert Control', 'Weir Submerg'),
    ('Culv WS Inlet (ft)', 'Weir Max Depth (ft)'),
    ('Culv WS Outlet (ft)', 'Weir Avg Depth (ft)'),
    ('Culv Nml Depth (ft)', 'Weir Flow Area (sq ft)'),
    ('Culv Crt Depth (ft)', 'Min El Weir Flow (ft)'),
]
FIELDS = {
    'flow_cfs': 'Q Culv Group (cfs)',
    'representative_barrel_flow_cfs': 'Q Barrel (cfs)',
    'inlet_velocity_fts': 'Culv Vel US (ft/s)',
    'outlet_velocity_fts': 'Culv Vel DS (ft/s)',
    'inlet_control_egl_ft': 'E.G. IC (ft)',
    'outlet_control_egl_ft': 'E.G. OC (ft)',
    'full_flow_length_ft': 'Culv Full Len (ft)',
    'control': 'Culvert Control',
}


def parse(text):
    lines = text.lstrip('\ufeff').splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) != 17 or not lines[0].startswith('Plan: '):
        raise ValueError('Unsupported Culvert Output clipboard layout')
    values = {}
    for line, labels in zip(lines[1:], LABELS):
        cells = [v.strip() for v in line.split('\t')]
        if len(cells) != 4 or (cells[0], cells[2]) != labels:
            raise ValueError('Unknown, duplicate or reordered native table fields')
        for label, token in zip(cells[::2], cells[1::2]):
            if not token:
                value = None
            elif label == 'Culvert Control':
                # Only this label has been observed in the current native acceptance.
                if token != 'Outlet':
                    raise ValueError('Uninspected native control label: ' + token)
                value = token
            elif label == '# Barrels':
                if not re.fullmatch(r'[1-9][0-9]*', token):
                    raise ValueError('Invalid barrel count')
                value = int(token)
            else:
                if not re.fullmatch(r'-?\d+\.\d{2}', token):
                    raise ValueError('Uninspected numeric format or precision')
                value = float(token)
                if not math.isfinite(value):
                    raise ValueError('Nonfinite native value')
            values[label] = value
    return dict(header=lines[0].strip(), values=values)


def _close(observed, expected, label):
    if (observed is None) != (expected is None):
        raise ValueError('Native blank/value disagrees: ' + label)
    if observed is not None and abs(observed - expected) > .00501:
        raise ValueError('Native value differs beyond display rounding: ' + label)


def _image(entry):
    if not intact([entry]):
        raise ValueError('Missing/changed observed UI evidence')
    with safe_path(ROOT, entry['path']).open('rb') as f:
        magic = f.read(8)
    if not (magic.startswith(b'\xff\xd8\xff') or magic == b'\x89PNG\r\n\x1a\n' or magic.startswith(b'%PDF-')):
        raise ValueError('UI evidence must be an actual PNG, JPEG or PDF')


def _entry(value):
    # Templates use paths for operators; imported bundles seal the actual bytes.
    return item(safe_path(ROOT, value)) if isinstance(value, str) else value


def prepare(summary_path, output):
    _, summary, hyd = load_summary(summary_path)
    original_hdf = safe_path(ROOT, hyd['raw_hdf']['path'])
    if not original_hdf.name.lower().endswith('.p01.hdf'):
        raise ValueError('Unsupported native plan suffix')
    with h5py.File(original_hdf) as h:
        groups = h['Geometry/Structures/Culvert Groups/Attributes'][:]
        structures = h['Geometry/Structures/Attributes'][:]
        if (len(groups) != 2 or len(structures) != 1 or
                not h.attrs['File Version'].decode().startswith('HEC-RAS 7.0.1 ') or
                h.attrs['Units System'].decode() != 'US Customary'):
            raise ValueError('Prepare supports the inspected 7.0.1 two-group crossing only')
    original = original_hdf.with_name(original_hdf.name[:-8] + '.prj')
    folder = safe_path(ROOT, output)
    folder.mkdir(parents=True, exist_ok=False)
    for suffix in ('.prj', '.p01', '.g01', '.f01', '.p01.hdf', '.g01.hdf', '.O01'):
        source = original.with_suffix(suffix)
        if source.exists():
            shutil.copyfile(source, folder / source.name)
    tables = []
    for pi, profile in enumerate(hyd['profiles']):
        for gi, group in enumerate(groups):
            stem = f'profile_{pi+1}_group_{gi+1}'
            tables.append(dict(profile=profile['profile_id'], group=group['Name'].decode().strip(),
                               export=rel(folder / (stem + '.txt')),
                               ui_evidence=[rel(folder / (stem + '.jpg'))]))
    selection = dict(schema_version='culvert_detail_selection_1.0', run_id=hyd['run_id'],
                     engine_version='7.0.1', method=METHOD, project=rel(folder / original.name),
                     observer=None, scope_observed=False,
                     project_ui_evidence=[rel(folder / 'project_observed.jpg')], tables=tables)
    save(folder / 'selection.template.json', selection)
    save(folder / 'source_summary.json', item(summary_path))
    return selection


def inspect(summary_path, selection_path):
    summary_path, summary, hyd = load_summary(summary_path)
    selection_path = safe_path(ROOT, selection_path)
    selection = read(selection_path)
    observer = selection.get('observer')
    if (selection.get('schema_version') != 'culvert_detail_selection_1.0' or
            selection.get('method') != METHOD or not isinstance(observer, str) or not observer.strip() or
            selection.get('scope_observed') is not True or selection.get('engine_version') != '7.0.1' or
            selection.get('run_id') != hyd['run_id']):
        raise ValueError('A matching, explicitly observed 7.0.1 selection is required')
    original_hdf = safe_path(ROOT, hyd['raw_hdf']['path'])
    if not original_hdf.name.lower().endswith('.p01.hdf'):
        raise ValueError('Unsupported native plan suffix')
    original = original_hdf.with_name(original_hdf.name[:-8] + '.prj')
    project = safe_path(ROOT, selection['project'])
    sources = [item(summary_path), summary['hydraulic_results'], hyd['raw_hdf'], hyd['raw_controller'], item(selection_path)]
    for suffix in ('.prj', '.p01', '.g01', '.f01', '.O01', '.p01.hdf'):
        a, b = original.with_suffix(suffix), project.with_suffix(suffix)
        if sha(a) != sha(b):
            raise ValueError('Observed project differs from original solve: ' + suffix)
        sources.extend([item(a), item(b)])
    plan = original.with_suffix('.p01').read_text(encoding='ascii')
    identifiers = [s.split('=', 1)[1].strip() for s in plan.splitlines() if s.startswith('Short Identifier=')]
    if len(identifiers) != 1:
        raise ValueError('Native plan identifier is ambiguous')
    for value in selection.get('project_ui_evidence', []):
        evidence = _entry(value)
        _image(evidence)
        sources.append(evidence)
    if not selection.get('project_ui_evidence'):
        raise ValueError('Observed project path evidence is required')
    with h5py.File(original_hdf) as h:
        if not h.attrs.get('File Version', b'').decode('ascii').startswith('HEC-RAS 7.0.1 ') or h.attrs.get('Units System', b'').decode('ascii') != 'US Customary':
            raise ValueError('Uninspected native output version or units')
        structures = h['Geometry/Structures/Attributes'][:]
        groups = h['Geometry/Structures/Culvert Groups/Attributes'][:]
    if len(structures) != 1 or len(groups) != 2 or int(structures[0]['Culvert Groups']) != 2:
        raise ValueError('Current detailed-table adapter is verified only for one crossing with two groups')
    decode = lambda v: v.decode('ascii').strip()
    river, reach, station = [decode(structures[0][k]) for k in ('River', 'Reach', 'RS')]
    names = [decode(g['Name']) for g in groups]
    if len(set(names)) != len(names) or not all(names):
        raise ValueError('Native group names must be nonempty and unique')
    controller = read(ROOT / hyd['raw_controller']['path'])
    expected = {(p['profile_id'], name) for p in hyd['profiles'] for name in names}
    seen, rows, checks = set(), [], []
    for entry in selection.get('tables', []):
        entry = dict(entry, export=_entry(entry['export']), ui_evidence=[_entry(v) for v in entry.get('ui_evidence', [])])
        profile, group_name = entry['profile'], entry['group']
        key = profile, group_name
        if key not in expected or key in seen:
            raise ValueError('Unknown/duplicate profile and group selection')
        seen.add(key)
        if not intact([entry['export']]):
            raise ValueError('Missing/changed native text export')
        evidence = entry.get('ui_evidence', [])
        if not evidence:
            raise ValueError('Each selected table requires observed UI evidence')
        for image in evidence:
            _image(image)
        sources.extend([entry['export']] + evidence)
        parsed = parse((ROOT / entry['export']['path']).read_text(encoding='utf-8-sig'))
        header = f'Plan: {identifiers[0]}    {river}    {reach}  RS: {station}   Culv Group:  {group_name}   Profile: {profile}'
        if parsed['header'] != header:
            raise ValueError('Native header differs from selected model/profile/group')
        i = names.index(group_name)
        g, v = groups[i], parsed['values']
        if v['# Barrels'] != int(g['Barrels']):
            raise ValueError('Native barrel count mismatch')
        for label, field in [('Culv Inv El Up (ft)', 'US Invert'), ('Culv Inv El Dn (ft)', 'DS Invert')]:
            _close(v[label], float(g[field]), label)
        if v['Q Culv Group (cfs)'] is None or v['Q Barrel (cfs)'] is None:
            raise ValueError('A computed group and representative flow are required')
        if abs(v['Q Culv Group (cfs)'] - v['# Barrels'] * v['Q Barrel (cfs)']) > .00501 * (v['# Barrels'] + 1):
            raise ValueError('Group and representative-barrel flows disagree')
        if i == 0:
            matched = [r for r in controller['rows'] if r['profile'] == profile and r['station'].strip() == station and r['node_type'] == 'Culv' and r['updn_argument'] == 0]
            if len(matched) != 1:
                raise ValueError('Missing/ambiguous independent first-group COM record')
            metrics = matched[0]['metrics']
            for label, field in [('Q Culv Group (cfs)', 'Q Culv Group'), ('Q Barrel (cfs)', 'Q Barrel'), ('Culv Vel US (ft/s)', 'Culv Vel US'), ('Culv Vel DS (ft/s)', 'Culv Vel DS'), ('E.G. IC (ft)', 'E.G. IC'), ('E.G. OC (ft)', 'E.G. OC'), ('Culv Full Len (ft)', 'Culv Full Len'), ('Q Weir (cfs)', 'Q Weir')]:
                _close(v[label], number(metrics[field]), label)
                checks.append(dict(profile=profile, field=field, status='MATCH_AT_DISPLAY_PRECISION'))
        rows.append(dict(profile=profile, group_id=i, native_group=group_name, barrel_count=v['# Barrels'],
                         **{name: v[label] for name, label in FIELDS.items()},
                         raw_fields=v, export=entry['export'], ui_evidence=evidence,
                         numeric_resolution=.01, basis='NATIVE_GUI_CLIPBOARD_DISPLAY_PRECISION'))
    if seen != expected:
        raise ValueError('All computed profiles and both groups must be observed and exported')
    rows.sort(key=lambda r: ([p['profile_id'] for p in hyd['profiles']].index(r['profile']), r['group_id']))
    return dict(schema_version='culvert_details_1.0', status='VERIFIED_OPERATOR_OBSERVED_SUPPLEMENT',
                run_id=hyd['run_id'], summary=item(summary_path), selection=item(selection_path),
                raw_hdf=hyd['raw_hdf'], sources=sources, rows=rows, checks=checks,
                unit=hyd.get('unit'), datum=hyd.get('datum'),
                scope='One crossing, two groups, HEC-RAS 7.0.1 English clipboard layout; observed Outlet control only',
                limitation='Text has no embedded output hash; operator UI attestation binds it. Display precision is 0.01, blanks remain null. Original full-precision COM results are not replaced.',
                solver_rerun=False, hydraulic_qa='REVIEW_REQUIRED', engineering_acceptance='NOT_ASSESSED')


def import_tables(summary_path, selection_path, output):
    bundle = inspect(summary_path, selection_path)
    folder = safe_path(ROOT, output)
    folder.mkdir(parents=True, exist_ok=False)
    save(folder / 'bundle.json', dict(bundle, created_utc=utc()))
    fields = ['run_id', 'profile', 'group_id', 'native_group', 'barrel_count', *FIELDS, 'numeric_resolution', 'basis', 'raw_hdf', 'export_path', 'export_sha256', 'unit', 'datum']
    with (folder / 'culvert_details.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in bundle['rows']:
            record = dict(row, run_id=bundle['run_id'], raw_hdf=bundle['raw_hdf']['path'],
                          export_path=row['export']['path'], export_sha256=row['export']['sha256'],
                          unit=bundle['unit'], datum=bundle['datum'])
            writer.writerow({k: record[k] for k in fields})
    return bundle


def validate(bundle_path, summary_path):
    bundle = read(safe_path(ROOT, bundle_path))
    if bundle.get('summary') != item(summary_path) or not intact(bundle.get('sources', [])):
        raise ValueError('Supplement source identity mismatch')
    rebuilt = inspect(summary_path, bundle['selection']['path'])
    if {k: v for k, v in bundle.items() if k != 'created_utc'} != rebuilt:
        raise ValueError('Supplement differs from reparsed native evidence')
    return bundle
