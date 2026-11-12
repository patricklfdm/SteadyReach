"""Traceable diagnostics and comparisons; never certifies engineering acceptance.

Numerical checks are workflow checks, not a substitute for HEC-RAS's complete
Errors/Warnings/Notes table. Every review is tied to the actual output hash.
"""
import csv
import math
from collections import Counter

import h5py

from .common import ROOT, digest, intact, item, read, rel, safe_path, save, utc

BASE = 'Results/Steady/Output/Output Blocks/Base Output/Steady Profiles'
THRESHOLDS = dict(min_error_ft=.3, egl_rise_ft=.05,
                  flow_balance_relative=.005, sensitivity_hw_ft=.10)


def number(v):
    if isinstance(v, (list, tuple)):
        v = v[0] if v else None
    if v is None:
        return None
    v = float(v)
    return v if math.isfinite(v) and abs(v) < 1e30 else None


def standard_step_issue(metrics):
    """Codes are described by the installed Output_Variables metadata."""
    case = number(metrics.get('Std Stp Case'))
    if case == 2:
        return 'MINIMUM_ERROR_SOLUTION'
    if case == 3:
        return 'CRITICAL_DEPTH_FALLBACK'
    if case not in (None, 0, 1):
        return 'UNRECOGNIZED_STANDARD_STEP_CODE'
    return None


def verified_profiles(hydraulics):
    """Read comparison values from the verified raw result, not editable summaries."""
    if not intact([hydraulics['raw_hdf'], hydraulics['raw_controller']]):
        raise ValueError('Raw result hashes no longer match')
    if hydraulics.get('native_log'):
        if not intact([hydraulics['native_log']]):raise ValueError('Native log extraction identity changed')
        log=read(ROOT/hydraulics['native_log']['path'])
        if log.get('source') and not intact([log['source']]):raise ValueError('Native log source identity changed')
    controller = read(safe_path(ROOT, hydraulics['raw_controller']['path']))
    if controller['hdf_sha256'] != hydraulics['raw_hdf']['sha256']:
        raise ValueError('Controller/HDF identity mismatch')
    with h5py.File(safe_path(ROOT, hydraulics['raw_hdf']['path'])) as h:
        stations = [r['Station'].decode().strip() for r in h['Results/Steady/Output/Geometry Info/Cross Section Attributes'][:]]
        names = [v.decode().strip() for v in h[BASE + '/Profile Names'][:]]
        if names != [p['profile_id'] for p in hydraulics['profiles']]:
            raise ValueError('Summary profile identities differ from raw HDF')
        result = {}
        for i, p in enumerate(hydraulics['profiles']):
            flow = h[BASE + '/Cross Sections/Flow'][i]
            if any(abs(float(v) - p['flow_cfs']) > .002 for v in flow):
                raise ValueError('Summary flows differ from raw HDF')
            wse = {rs: float(v) for rs, v in zip(stations, h[BASE + '/Cross Sections/Water Surface'][i])}
            for key, rs in [('headwater_wse_ft', p['headwater_rs']), ('tailwater_wse_ft', p['tailwater_rs'])]:
                if abs(wse[rs] - p['metrics'][key]) > .001:
                    raise ValueError('Summary water surface differs from raw HDF')
            result[p['profile_id']] = wse
    return result


def diagnostics(hydraulics, folder, native_bundle=None):
    sources = [hydraulics['raw_hdf'], hydraulics['raw_controller']]
    if hydraulics.get('native_log'):sources.append(hydraulics['native_log'])
    if not intact(sources):
        raise ValueError('Diagnostic source hashes no longer match')
    verified_profiles(hydraulics)
    controller = read(ROOT / hydraulics['raw_controller']['path'])
    issues = []

    def add(code, profile, station, severity, evidence, action):
        identity = dict(code=code, profile=profile, station=station,
                        output_sha256=hydraulics['raw_hdf']['sha256'], evidence=evidence)
        issues.append(dict(id=digest(identity)[:20], **identity, severity=severity,
                           review_status='OPEN', recommended_action=action))

    with h5py.File(ROOT / hydraulics['raw_hdf']['path']) as h:
        stations = [v['Station'].decode().strip() for v in h['Results/Steady/Output/Geometry Info/Cross Section Attributes'][:]]
        info = h['Geometry/Cross Sections/Station Elevation Info'][:]
        points = h['Geometry/Cross Sections/Station Elevation Values'][:]
        for pi, profile in enumerate(hydraulics['profiles']):
            name = profile['profile_id']
            w = h[BASE + '/Cross Sections/Water Surface'][pi]
            eg = h[BASE + '/Cross Sections/Energy Grade'][pi]
            for i, (start, count) in enumerate(info):
                for side, z in [('left', points[start, 1]), ('right', points[start + count - 1, 1])]:
                    excess = float(w[i] - z)
                    if excess > 0:
                        add('WET_SECTION_EDGE', name, stations[i], 'WARNING',
                            dict(side=side, edge_elevation_ft=float(z), wse_ft=float(w[i]), exceedance_ft=excess,
                                 raw_fields=['Station Elevation Values', BASE + '/Cross Sections/Water Surface']),
                            'Extend the section using terrain/survey; review actual bypass paths. Do not raise the edge artificially.')
                if i + 1 < len(stations) and eg[i + 1] - eg[i] > THRESHOLDS['egl_rise_ft']:
                    add('DOWNSTREAM_EGL_RISE', name, stations[i], 'WARNING',
                        dict(downstream_station=stations[i + 1], rise_ft=float(eg[i + 1] - eg[i]),
                             raw_field=BASE + '/Cross Sections/Energy Grade'),
                        'Review flow direction, hydraulic jumps, control changes and numerical convergence.')
            for row in controller['rows']:
                if row['profile'] != name or row['node_type']:
                    continue
                m = row['metrics']; code = standard_step_issue(m)
                if code:
                    add(code, name, row['station'], 'WARNING',
                        dict(standard_step_case=number(m.get('Std Stp Case')), min_error_ft=number(m.get('Min Error')),
                             raw_fields=['controller_output / Std Stp Case', 'controller_output / Min Error']),
                        'Check geometry, section spacing, ineffective areas and flow regime; compare a defensible refined model.')
                error = number(m.get('Min Error'))
                if error is not None and error > THRESHOLDS['min_error_ft']:
                    add('ENERGY_BALANCE_ERROR', name, row['station'], 'WARNING',
                        dict(min_error_ft=error, threshold_ft=THRESHOLDS['min_error_ft'], raw_field='controller_output / Min Error'),
                        'Review the local energy solution; do not increase the solver tolerance to suppress this warning.')
            q = profile['qa']; residual = q['flow_balance_residual_cfs']
            for group in profile.get('culvert_groups',[]):
                if group['detail_coverage']!='FIRST_GROUP_COM_FIELDS':
                    add('CULVERT_GROUP_DETAIL_NOT_EXTRACTED',name,None,'EVIDENCE_GAP',
                        dict(group_id=group['group_id'],group_name=group['name'],coverage=group['detail_coverage']),
                        'Review the native group detail table. Derived remainder flow does not supply velocities or control-state details.')
            if residual is None:
                add('FLOW_SPLIT_NOT_FULLY_OBSERVED', name, None, 'EVIDENCE_GAP',
                    dict(residual_cfs=None, reason='A required structure-flow output is undefined or not extracted'),
                    'Obtain all culvert/roadway/other-path outputs at the same structure. Missing is not zero.')
            elif abs(residual) / profile['flow_cfs'] > THRESHOLDS['flow_balance_relative']:
                add('STRUCTURE_FLOW_IMBALANCE', name, None, 'WARNING',
                    dict(residual_cfs=residual, relative_error=abs(residual) / profile['flow_cfs']),
                    'Check structure group aggregation, overflow and any other represented paths.')

    coverage = 'PARTIAL'
    if native_bundle:
        from .native_warnings import validate_bundle
        bundle_path = safe_path(ROOT, native_bundle)
        bundle = validate_bundle(read(bundle_path), hydraulics)
        sources += [item(bundle_path)] + bundle['sources']
        coverage = bundle['coverage']
        for row in bundle['parsed']['records']:
            add(row['code'], row['profile'], row['station'], row['severity'],
                dict(native_message=row['text'], river=row['river'], reach=row['reach'],
                     culvert=row['culvert'], export=bundle['export'],
                     first_line=row['first_line'], last_line=row['last_line']),
                'Review native message in context of the computed profile and geometry; retain an explicit disposition.')
    else:
        add('NATIVE_WARNING_TABLE_INCOMPLETE', None, None, 'EVIDENCE_GAP',
            dict(coverage='COMPUTE_MESSAGES_AND_NUMERICAL_FIELDS_ONLY'),
            'Export the complete native Summary Errors, Warnings and Notes for all profiles, then bind it to this output.')
    result = dict(schema_version='1.0', created_utc=utc(), run_id=hydraulics['run_id'],
                  sources=sources, thresholds=THRESHOLDS, issues=issues,
                  counts=dict(Counter(i['code'] for i in issues)),
                  warning_coverage=coverage, hydraulic_qa_status='REVIEW_REQUIRED',
                  engineering_acceptance='NOT_ASSESSED',
                  reference='https://www.hec.usace.army.mil/confluence/rasdocs/rasum/7.0/troubleshooting-with-hec-ras')
    folder.mkdir(parents=True, exist_ok=True)
    save(folder / 'diagnostics.json', result)
    with (folder / 'issues.csv').open('w', newline='', encoding='utf-8-sig') as f:
        fields = ['id', 'code', 'profile', 'station', 'severity', 'review_status', 'recommended_action']
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); writer.writeheader(); writer.writerows(issues)
    return result


def compare(baseline_path, candidate_path, output_path):
    paths = [safe_path(ROOT, p) for p in [baseline_path, candidate_path]]
    summaries = [read(p) for p in paths]
    a, b = [s.get('hydraulics') for s in summaries]
    if not a or not b:
        raise ValueError('Both comparison inputs must contain real computed hydraulics')
    raw_a, raw_b = [verified_profiles(hyd) for hyd in [a, b]]
    if a['project_id'] != b['project_id'] or a['datum'] != b['datum'] or a['unit'] != b['unit']:
        raise ValueError('Comparison requires the same site, datum and units')
    right = {p['profile_id']: p for p in b['profiles']}; rows = []; section_rows = []
    for p in a['profiles']:
        other = right.get(p['profile_id'])
        if other is None:
            continue
        if p['flow_cfs'] != other['flow_cfs'] or p['headwater_rs'] != other['headwater_rs'] or p['tailwater_rs'] != other['tailwater_rs']:
            raise ValueError('Matched profiles must have the same flow and comparison locations')
        left_wse, right_wse = raw_a[p['profile_id']], raw_b[p['profile_id']]
        delta = right_wse[p['headwater_rs']] - left_wse[p['headwater_rs']]
        differences = [dict(profile=p['profile_id'], station=rs, baseline_wse_ft=left_wse[rs],
                            candidate_wse_ft=right_wse[rs], delta_wse_ft=right_wse[rs] - left_wse[rs])
                       for rs in left_wse if rs in right_wse]
        section_rows.extend(differences)
        rows.append(dict(profile=p['profile_id'], flow_cfs=p['flow_cfs'], headwater_rs=p['headwater_rs'],
                         baseline_hw_ft=p['metrics']['headwater_wse_ft'], candidate_hw_ft=other['metrics']['headwater_wse_ft'],
                         delta_hw_ft=delta, exceeds_review_threshold=abs(delta) > THRESHOLDS['sensitivity_hw_ft'],
                         max_matched_xs_delta_wse_ft=max(abs(d['delta_wse_ft']) for d in differences),
                         removed_stations=sorted(set(left_wse) - set(right_wse)),
                         added_stations=sorted(set(right_wse) - set(left_wse)),
                         baseline_qa=p['qa'], candidate_qa=other['qa']))
    if not rows:
        raise ValueError('No comparable profiles')
    result = dict(status='COMPARISON_REQUIRES_REVIEW', sources=[item(p) for p in paths],
                  baseline_run_id=a['run_id'], candidate_run_id=b['run_id'], rows=rows, cross_section_differences=section_rows,
                  unmatched_baseline_profiles=sorted(set(p['profile_id'] for p in a['profiles']) - set(right)),
                  unmatched_candidate_profiles=sorted(set(right) - set(p['profile_id'] for p in a['profiles'])),
                  threshold_ft=THRESHOLDS['sensitivity_hw_ft'], engineering_acceptance='NOT_ASSESSED')
    save(safe_path(ROOT, output_path), result)
    return result
