"""Summarize site decisions and native water-surface effects at identifiable sections."""
from collections import defaultdict

from .common import finite
from .qa import THRESHOLDS
from .revision_inputs import station_key


def key_inputs(fields):
    """Use the adopted record, preserving alternatives as candidates only."""
    result = []
    for field in fields:
        key = field['key']
        if not (key.endswith(('.flow_cfs','.channel_n','.overbank_n','.channel_geometry_basis'))
                or key.startswith(('g.boundary_slopes.', 'g.boundaries.'))):
            continue
        answer = field.get('answer') or {}
        adopted = answer.get('candidate_record') or {}
        options = field.get('parameter_candidates', [])
        alternatives = []
        for option in options:
            value = option.get('value')
            if value is not None and value!=field.get('value') and value not in alternatives:
                alternatives.append(value)
        sources = [s for s in [adopted.get('source'), *adopted.get('sources', [])] if isinstance(s,dict)]
        basis = answer.get('basis') or field.get('basis')
        origin = field.get('evidence_class','unrecorded')
        if field.get('missing') and field.get('required'):
            priority = 'MISSING'
        elif field.get('missing'):
            continue
        elif not basis and not sources and not adopted.get('url'):
            priority = 'BASIS_MISSING'
        elif alternatives:
            priority = 'OTHER_CANDIDATES'
        elif origin in ('assumed','user_entered','source_input_unverified') or field.get('value')=='conditional_surface_dem':
            priority = 'CHECK_APPLICABILITY'
        else:
            priority = 'SOURCE_RECORDED'
        result.append(dict(key=key,label=field.get('label'),value=field.get('value'),unit=field.get('unit'),basis=basis,
            priority=priority,origin=origin,alternatives=alternatives,adopted_range=adopted.get('range'),
            sources=list({s['path']:s for s in sources if 'path' in s}.values()),url=adopted.get('url')))
    return result


def response(studies, threshold=None):
    report = []
    if threshold is None:
        threshold = THRESHOLDS['sensitivity_hw_ft']
    if not finite(threshold) or threshold < 0:
        raise ValueError('Choose a finite nonnegative water-level threshold')
    for study in studies:
        if study.get('coverage') or study.get('convergence'):
            continue
        cases = {c['id']:c for c in study['cases']}
        for comp in study['comparisons']:
            changes = cases[comp['case']].get('changes',[])
            paths = [v['path'] for v in changes if v['path']!='blockage_basis']
            profiles = defaultdict(list)
            for row in comp.get('cross_section_differences',[]):
                if finite(row.get('delta_wse_ft')):
                    profiles[row['profile']].append(row)
            for profile,rows in profiles.items():
                rows = sorted(rows,key=lambda r:float(r['station']),reverse=True)
                peak = max(rows,key=lambda r:abs(r['delta_wse_ft']))
                affected = [r for r in rows if abs(r['delta_wse_ft'])>threshold]
                report.append(dict(case=comp['case'],profile=profile,paths=paths,threshold_ft=threshold,
                    compared=len(rows),peak_rs=peak['station'],signed_peak_ft=peak['delta_wse_ft'],
                    minimum_ft=min(r['delta_wse_ft'] for r in rows), maximum_ft=max(r['delta_wse_ft'] for r in rows),
                    affected=[dict(rs=r['station'],delta_ft=r['delta_wse_ft']) for r in affected],
                    source=study['analysis']))
    return report


def overbank_changes(previous, current, locations):
    from .lateral_coverage import hydraulic_context
    try:
        before, after = hydraulic_context(previous), hydraulic_context(current)
    except (KeyError, OSError, ValueError) as error:
        return dict(status='UNAVAILABLE', reason=str(error), rows=[])
    comparisons = []
    for rs in sorted(before.keys() & after.keys(), reverse=True):
        if locations.get(station_key(rs), {}).get('location_status') != 'SAME_CENTER':
            continue
        old, new = before[rs], after[rs]
        comparisons.append(dict(station=rs, previous_percent=[100*v for v in old[1:]],
            current_percent=[100*v for v in new[1:]], delta_points=[100*(y-x) for x,y in zip(old[1:],new[1:])]))
    return dict(status='AVAILABLE' if comparisons else 'NO_MATCHED_NATIVE_Q100_SHARES', rows=comparisons)


def local_problems(actions, stations):
    """Join records in the same review family/profile at adjacent actual station IDs."""
    order = {station_key(rs):i for i,rs in enumerate(stations)}
    problems = []
    for action in actions:
        if not action.get('issue_ids'):
            continue
        buckets = defaultdict(lambda:defaultdict(list))
        for issue in action.get('issue_records',[]):
            try:
                rs = station_key(issue.get('station'))
            except (TypeError,ValueError):
                rs = None
            buckets[issue.get('profile') or ''][rs if rs in order else None].append(issue)
        for profile,locations in buckets.items():
            groups = []
            for rs in sorted((s for s in locations if s is not None),key=order.get):
                if not groups or order[rs]!=order[groups[-1][-1]]+1:
                    groups.append([])
                groups[-1].append(rs)
            if None in locations:
                groups.append([None])
            for group in groups:
                records = [r for rs in group for r in locations[rs]]
                problems.append(dict(family=action['id'],title=action['title'],target=action['target'],
                    explanation=action['explanation'],profile=profile,stations=[s for s in group if s is not None],
                    records=len(records),issue_ids=[r['id'] for r in records],codes=sorted({r['code'] for r in records})))
    return problems
