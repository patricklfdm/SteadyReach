"""Import HEC-RAS's real English Summary Errors, Warnings and Notes export.

The text format has no embedded output hash. A separate observed UI selection
record is mandatory; hash verification binds the inspected project copy to the
solver evidence. This is an operator-attested export, not a COM export API.
"""
import re
from collections import Counter

from .common import ROOT, intact, item, read, safe_path, save, sha, utc

LOCATION = re.compile(
    r'^Location:\s+River:\s*(.*?)\s+Reach:\s*(.*?)\s+RS:\s*(.*?)\s+'
    r'Profile:\s*(.*?)(?:\s{2,}Culv:\s*(.*?))?\s*$')
MESSAGE = re.compile(r'^(Error|Warning|Note):\s*(.*)$')
CLASSIFICATIONS = [
    ('cross-section end points', 'NATIVE_WET_SECTION_EDGE'),
    ('energy equation could not be balanced', 'NATIVE_ENERGY_NOT_BALANCED'),
    ('program defaulted to critical depth', 'NATIVE_CRITICAL_DEPTH_FALLBACK'),
    ('conveyance ratio', 'NATIVE_CONVEYANCE_CHANGE'),
    ('energy loss was greater', 'NATIVE_LARGE_ENERGY_LOSS'),
    ('velocity head has changed', 'NATIVE_VELOCITY_HEAD_CHANGE'),
    ('divided flow', 'NATIVE_DIVIDED_FLOW'),
    ('hydraulic jump', 'NATIVE_HYDRAULIC_JUMP'),
    ('supercritical flow starting', 'NATIVE_SUPERCRITICAL_START'),
]


def parse(text, clipboard_plan_label=None):
    """Fail closed on unrecognised layout; retain every message and line number."""
    lines = text.lstrip('\ufeff').splitlines()
    if lines and lines[0].startswith('Errors Warnings and Notes for Plan : '):
        plan_label=lines[0].split(' : ',1)[1].strip(); body=lines[1:];first_line=2
    elif lines and clipboard_plan_label and lines[0].startswith('Location:'):
        # Observed 7.0.1 Clipboard export omits the File export's title line.
        plan_label=clipboard_plan_label;body=lines;first_line=1
    else:
        raise ValueError('Not a native English Summary Errors, Warnings and Notes export')
    nonempty=[line.strip() for line in body if line.strip()]
    if nonempty==['No Errors, Warnings or Notes in Computations']:
        return dict(plan_label=plan_label,records=[],counts={})
    location = None
    current = None
    rows = []
    for n, line in enumerate(body, first_line):
        if not line.strip():
            continue
        loc = LOCATION.fullmatch(line)
        msg = MESSAGE.fullmatch(line)
        if loc:
            river, reach, station, profile, culvert = loc.groups()
            if not all([river, reach, station, profile]):
                raise ValueError(f'Incomplete native location at line {n}')
            location = dict(river=river, reach=reach, station=station, profile=profile,
                            culvert=culvert or None, location_line=n)
            current = None
        elif msg:
            if location is None:
                raise ValueError(f'Native message without location at line {n}')
            current = dict(**location, severity=msg[1].upper(), text=msg[2],
                           first_line=n, last_line=n)
            rows.append(current)
        elif line[0].isspace() and current is not None:
            current['text'] += ' ' + line.strip()
            current['last_line'] = n
        else:
            raise ValueError(f'Unrecognised native export content at line {n}: {line[:100]}')
    for row in rows:
        row['code'] = next((code for phrase, code in CLASSIFICATIONS
                            if phrase in row['text'].lower()), 'NATIVE_UNCLASSIFIED_MESSAGE')
    return dict(plan_label=plan_label, records=rows,
                counts=dict(Counter(r['severity'] for r in rows)))


def validate_bundle(bundle, hydraulics):
    if bundle['run_id'] != hydraulics['run_id'] or bundle['output_sha256'] != hydraulics['raw_hdf']['sha256']:
        raise ValueError('Native warning bundle belongs to another run/output')
    if not intact(bundle['sources']):
        raise ValueError('Native warning source identity mismatch')
    if bundle['export'] not in bundle['sources'] or not intact([bundle['export']]):
        raise ValueError('Warning export is not part of the bound source set')
    if bundle.get('coverage') not in [None,'EXPORTED_SCOPE_OPERATOR_ATTESTED']:
        raise ValueError('Native export coverage cannot exceed operator-attested scope')
    if bundle.get('clipboard_plan_label'):
        selection=read(safe_path(ROOT,bundle['sources'][2]['path']))
        if selection.get('method')!='HEC-RAS Summary Errors Warnings Notes / Clipboard' or selection.get('plan_label')!=bundle['clipboard_plan_label']:
            raise ValueError('Clipboard plan label differs from the observed selection')
    if set(bundle['selected_profiles']) != {p['profile_id'] for p in hydraulics['profiles']}:
        raise ValueError('Native warning selection does not cover all requested profiles')
    # Parsed rows are derived data. Reparse the hashed text, do not trust editable JSON.
    parsed = parse(safe_path(ROOT, bundle['export']['path']).read_text(encoding=bundle['encoding']),bundle.get('clipboard_plan_label'))
    if parsed != bundle['parsed']:
        raise ValueError('Native warning records differ from the hashed export')
    return bundle


def import_export(summary_path, export_path, selection_path, output_path, encoding='utf-8-sig'):
    summary_path, export_path, selection_path, output_path = [
        safe_path(ROOT, p) for p in [summary_path, export_path, selection_path, output_path]]
    hyd = read(summary_path).get('hydraulics')
    if not hyd or not intact([hyd['raw_hdf'], hyd['raw_controller']]):
        raise ValueError('A verified real solver result is required')
    selection = read(selection_path)
    if selection.get('run_id') != hyd['run_id']:
        raise ValueError('UI selection record belongs to another run')
    if not selection.get('observer') or selection.get('method') not in [
            'HEC-RAS Summary Errors Warnings Notes / File',
            'HEC-RAS Summary Errors Warnings Notes / Clipboard']:
        raise ValueError('Observed native File or Clipboard export method and observer are required')
    evidence = selection.get('ui_evidence', [])
    if not intact(evidence):
        raise ValueError('Observed UI selection evidence is missing or changed')
    project = safe_path(ROOT, selection['project'])
    # The adapter's explicit p01 naming is verified in the worker. No guessed HDF fields.
    original_hdf = safe_path(ROOT, hyd['raw_hdf']['path'])
    if not original_hdf.name.lower().endswith('.p01.hdf'):
        raise ValueError('Unsupported warning adapter plan')
    original = original_hdf.with_name(original_hdf.name[:-8] + '.prj')
    sources = [item(summary_path), item(export_path), item(selection_path),
               hyd['raw_hdf'], hyd['raw_controller'], item(project)] + evidence
    for suffix in ['.p01.hdf', '.O01', '.g01', '.f01', '.p01']:
        source, inspected = original.with_suffix(suffix), project.with_suffix(suffix)
        if sha(source) != sha(inspected):
            raise ValueError('Inspected warning project differs from solver evidence: ' + suffix)
        sources.extend([item(source), item(inspected)])
    controller = read(safe_path(ROOT, hyd['raw_controller']['path']))
    # Worker v1 supports one river/reach. Their names are read from actual native input.
    native_geometry = original.with_suffix('.g01').read_text(encoding='ascii')
    reaches = [tuple(v.strip() for v in line.split('=', 1)[1].split(','))
               for line in native_geometry.splitlines() if line.startswith('River Reach=')]
    selected_reaches = [tuple(v) for v in selection.get('river_reaches', [])]
    if set(reaches) != set(selected_reaches):
        raise ValueError('Native warning selection must cover every model river/reach')
    clipboard_plan=None
    if selection['method'].endswith('/ Clipboard'):
        title=next((line.split('=',1)[1].strip() for line in original.with_suffix('.p01').read_text(encoding='ascii').splitlines() if line.startswith('Plan Title=')),None)
        if not title or selection.get('plan_label')!=title:
            raise ValueError('Clipboard export requires the observed plan title matching the native plan')
        clipboard_plan=title
    parsed = parse(export_path.read_text(encoding=encoding),clipboard_plan)
    profiles = {p['profile_id'] for p in hyd['profiles']}
    stations = {r['station'].strip() for r in controller['rows']}
    for row in parsed['records']:
        if row['profile'] not in profiles or row['station'] not in stations or (row['river'], row['reach']) not in reaches:
            raise ValueError('Native warning references a different profile/node/reach')
    if not parsed['records'] and selection.get('empty_table_observed') is not True:
        raise ValueError('An empty export needs explicit observed-empty-table evidence')
    bundle = dict(schema_version='1.0', created_utc=utc(), run_id=hyd['run_id'],
                  output_sha256=hyd['raw_hdf']['sha256'], sources=sources,
                  export=item(export_path), encoding=encoding, parsed=parsed,clipboard_plan_label=clipboard_plan,
                  selected_profiles=selection.get('profiles', []), river_reaches=reaches,
                  coverage='EXPORTED_SCOPE_OPERATOR_ATTESTED',
                  limitation='Native text has no embedded output hash; origin/scope depend on the recorded UI observation.',
                  engineering_acceptance='NOT_ASSESSED')
    validate_bundle(bundle, hyd)
    save(output_path, bundle)
    return bundle
