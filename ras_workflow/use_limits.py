"""Station-specific limits from matched native sections and verified sensitivity studies."""
from .common import finite
from .revision_inputs import station_key
from .river_review import response


def comparison_coverage(comparison, profile):
    """Compare the union of stations. A common identifier alone cannot establish co-location."""
    c = comparison or {}
    group = next((p for p in c.get('profiles', []) if p['profile'] == profile), None)
    if c.get('status') != 'COMPARISON_NOT_ACCEPTANCE' or not group:
        return dict(state='missing', en=f'{profile} · Supply a computed baseline and comparable revised profile.',
                    zh=f'{profile} · 请补已计算基准版及可比修订版工况。', verified=[], excluded=[])
    rows = [r for r in c.get('cross_sections', []) if r['profile'] == profile]
    verified = [str(r['station']) for r in rows if r.get('location_status') == 'SAME_CENTER']
    unavailable = [str(r['station']) for r in rows if r.get('location_status') != 'SAME_CENTER']
    added = group.get('added_stations', [])
    removed = group.get('removed_stations', [])
    excluded = list(dict.fromkeys(unavailable + list(map(str, added)) + list(map(str, removed))))
    matched = group.get('matched_sections')
    try:
        stations = [station_key(r['station']) for r in rows] + [station_key(rs) for rs in [*added, *removed]]
    except (TypeError, ValueError):
        return dict(state='missing', en=f'{profile} · Resolve ambiguous station identifiers before comparing editions.',
                    zh=f'{profile} · 请先核实有歧义的断面编号，再比较两版。', verified=[], excluded=excluded)
    complete = (bool(rows) and matched == len(rows) and len(verified) == group.get('verified_center_count')
                and len(set(stations)) == len(stations))
    total = matched + len(added) + len(removed) if isinstance(matched, int) else None
    if not complete:
        return dict(state='missing', en=f'{profile} · Restore station-level correspondence before quoting revision differences.',
                    zh=f'{profile} · 请先恢复逐断面位置对应记录，再引用修订差值。', verified=[], excluded=excluded)
    if len(verified) == total and not excluded:
        return dict(state='met',en=f'{profile} · Both editions have verified centers at all {total} sections.',
                    zh=f'{profile} · 两版全部 {total} 条断面均已核实同位置。',verified=verified,excluded=[])
    kept = ', '.join(verified) or '—'
    gaps = ', '.join(excluded) or '—'
    return dict(state='missing',en=f'{profile} · Local comparison only. Verified {len(verified)}/{total} sections. Comparable RS: {kept}. Unmatched, moved or unverified RS: {gaps}.',
                zh=f'{profile} · 仅可局部比较，已核实 {len(verified)}/{total} 条断面。可比 RS：{kept}。缺配对、移动或未核实的 RS：{gaps}。',
                verified=verified,excluded=excluded)


def control_changes(comparison, profile):
    labels = {'upstream_wse_ft':('upstream stage','上游水位'), 'downstream_wse_ft':('downstream stage','下游水位'),
              'headwater_wse_ft':('headwater','涵前水位'), 'tailwater_wse_ft':('tailwater','尾水水位')}
    for r in (comparison or {}).get('rows', []):
        metric = r.get('metric')
        if (r.get('profile') != profile or metric not in labels or r.get('location_status') == 'SAME_CENTER'
                or not any(finite(r.get(k)) for k in ('previous','current'))):
            continue
        stations = list(dict.fromkeys(str(r[k]) for k in ('previous_station','current_station') if r.get(k) is not None))
        where = ', '.join(stations) or '—'
        en, zh = labels[metric]
        yield dict(heading=dict(en='Unmatched hydraulic control', zh='控制位置尚未配对'), profile=profile,
                   control_stations=stations, en=f'{profile} · {en}, RS {where}. Verify the same control location before citing a change.',
                   zh=f'{profile} · {zh}，RS {where}。引用该指标的变化前须核实两版控制位置一致。')


def boundary_limits(studies, inventory=None):
    """Keep single-factor evidence and its tested locations separate for each end and flow."""
    result = {}
    for study in studies or ():
        if not study.get('comparisons') or study.get('coverage') or study.get('convergence'):
            continue
        cases = {c['id']: c for c in study['cases']}
        variants = {c['case']: c for c in study['comparisons']}
        for row in response([study]):
            if len(row['paths']) != 1:
                continue
            path = row['paths'][0]
            parts = path.split('.')
            if len(parts) < 2 or parts[0] not in ('boundaries', 'boundary_slopes') or parts[1] not in ('upstream','downstream'):
                continue
            changes = [c for c in cases[row['case']].get('changes', []) if c['path'] == path]
            if len(changes) != 1:
                continue
            before, after = changes[0].get('before'), changes[0].get('after')
            if before is None or after is None or before == after:
                continue
            key = (row['profile'],parts[1])
            limit = result.setdefault(key, dict(profile=key[0], side=key[1], affected={}, complete=False, threshold_ft=row['threshold_ft']))
            if inventory and key[0] in inventory:
                samples = [station_key(v['station']) for v in variants[row['case']].get('cross_section_differences', [])
                           if v.get('profile') == key[0] and finite(v.get('delta_wse_ft'))]
                expected = {station_key(rs) for rs in inventory[key[0]]}
                if expected and len(samples) == len(expected) and set(samples) == expected:
                    limit['complete'] = True
            for sample in row['affected']:
                rs = str(sample['rs'])
                if abs(sample['delta_ft']) > abs(limit['affected'].get(rs, 0)):
                    limit['affected'][rs] = sample['delta_ft']
    return result


def boundary_rows(limits):
    for (profile,side), limit in sorted(limits.items()):
        affected = limit['affected']
        if not affected:
            continue
        stations = sorted(affected, key=float, reverse=True)
        names = ', '.join(stations)
        threshold = limit['threshold_ft']
        yield dict(heading=dict(en='Boundary-sensitive stages',zh='受边界影响的水位'),
                   profile=profile,side=side,stations=stations,threshold_ft=threshold,
                   en=f'{profile} · {side} perturbation changed stage by more than {threshold:g} ft at RS {names}. Verify the event boundary before citing these stages.',
                   zh=f"{profile} · {'上游' if side=='upstream' else '下游'}边界试算使以下 RS 的水位变化超过 {threshold:g} ft：{names}。引用这些水位前请核对同期边界。")
