"""Decision support for two calculated editions of a steady reach."""
GUIDANCE = {
    'FEWER_WARNINGS_OTHER_CHANGES': ('Native warnings fell, but another hydraulic check changed. Review the items below before choosing an edition.',
                                     '原生警告减少，但其他水力检查发生变化。选用版本前，请逐项核对以下变化。'),
    'CHECK_WARNING_COVERAGE': ('Obtain native warning tables for both runs covering the same profiles before comparing warning totals.',
                               '请取得两次计算覆盖相同工况的完整原生警告表，再比较警告总数。'),
    'CHECK_SECTION_CORRESPONDENCE': ('Inspect moved, added or missing sections on the map. Interpret local stage differences at verified common centers.',
                                     '在地图核对移动、新增或缺失的断面。请在位置已核验的共同中心解释局部水位差。'),
    'CHECK_WATER_LEVEL_CHANGE': ('Inspect the largest stage change at a common center against the edited geometry, resistance and boundary conditions.',
                                 '请在共同中心最大水位变化处，对照几何、糙率及边界条件的改动。'),
    'MORE_NATIVE_ERRORS': ('Open the current native errors and locate the affected station and profile.',
                           '请打开本次原生错误表，定位受影响的断面和工况。'),
    'CHECK_WET_ENDS': ('Inspect inundated endpoints on the terrain and check for connected floodplain or bypass flow.',
                       '请在地形上核对过水端点，检查连通漫滩或绕流通道。'),
    'CHECK_NUMERICAL_CONTROLS': ('Inspect the increased numerical checks in the profile plot and native output at the affected sections.',
                                 '请在纵剖面及原生结果中检查数值问题增加的断面。'),
}


METRIC_LABELS = {
    'headwater_wse_ft': ('Headwater (ft)', '涵前水位（ft）'),
    'tailwater_wse_ft': ('Tailwater (ft)', '涵后水位（ft）'),
    'roadway_flow_software_cfs': ('Roadway discharge (cfs)', '路面越流量（cfs）'),
    'upstream_wse_ft': ('Upstream water level (ft)', '上游水位（ft）'),
    'downstream_wse_ft': ('Downstream water level (ft)', '下游水位（ft）'),
    'max_channel_velocity_fts': ('Maximum channel velocity (ft/s)', '主槽最大流速（ft/s）'),
    'max_channel_froude': ('Maximum channel Froude number', '主槽最大弗劳德数'),
}


def investigation(review, overbanks):
    """Describe a specific comparison and its stopping condition from paired native evidence."""
    result=[]
    for r in review['endpoints'].get('rows',[]):
        if r['state'] not in ('still_wet','new_wet'):
            continue
        rs,side=r['station'],r['side']
        values=f"{r['previous_depth_ft']:.3f} → {r['current_depth_ft']:.3f} ft"
        result.append(dict(profile=r['profile'],station=rs,side=side,
            en=f"{r['profile']} · RS {rs} {side} end. Did the edit contain the flow? Endpoint depths {values}, each at its own cutline end. Check the continuous floodplain path on terrain and imagery. If unresolved, request a surveyed bank-to-high-ground section on this side before extending again.",
            zh=f"{r['profile']} · RS {rs} {'左' if side=='left' else '右'}端。修改后断面是否包住水流？两版各自端点的水深为 {values}。请在地形与航片核对连续过流路径。仍有疑义时，先补测该侧从河岸到高地的横断面，再决定是否延伸。"))
    shares=[(abs(change),r,i) for r in (overbanks or {}).get('rows',[])
            for i,change in enumerate(r['delta_points']) if change]
    if shares:
        _,r,i=max(shares,key=lambda v:v[0])
        side=['left','right'][i]
        facts=f"{r['previous_percent'][i]:.2f}% → {r['current_percent'][i]:.2f}%"
        delta=review.get('warning_delta')
        note_en=f" Native warning count fell by {-delta}." if delta is not None and delta<0 else ''
        note_zh=f"原生警告减少 {-delta} 条。" if note_en else ''
        result.append(dict(profile='Q100',station=r['station'],side=side,
            en=f"Q100 · RS {r['station']} {side} overbank share {facts}."+note_en+" Verify the flow path between adjacent sections and check bank locations against field evidence before selecting an edition.",
            zh=f"Q100 · RS {r['station']} {'左' if i==0 else '右'}滩流量占比 {facts}。"+note_zh+"选版前请检查相邻断面间的过流连通性，并对照现场资料复核岸站。"))
    return result


def metric_rows(rows):
    return [dict(r,en=METRIC_LABELS[r['metric']][0],zh=METRIC_LABELS[r['metric']][1])
            for r in rows if r['metric'] in METRIC_LABELS]


def interpret(diagnostics, profiles, all_profiles_matched, threshold):
    old, new = diagnostics['previous'], diagnostics['current']
    comparable = bool(all_profiles_matched and old.get('severity') is not None and new.get('severity') is not None)
    flags = []
    if not comparable:
        flags.append('CHECK_WARNING_COVERAGE')
    if not all_profiles_matched or any(p['verified_center_count'] < p['matched_sections'] or
            p['added_stations'] or p['removed_stations'] or not p['verified_center_count'] for p in profiles):
        flags.append('CHECK_SECTION_CORRESPONDENCE')
    peaks = [p['maximum_at_verified_centers'] for p in profiles if p['maximum_at_verified_centers']]
    peak = max(peaks,key=lambda row:abs(row['change']),default=None)
    if peak and abs(peak['change']) > threshold:
        flags.append('CHECK_WATER_LEVEL_CHANGE')
    if comparable and new['severity']['ERROR'] > old['severity']['ERROR']:
        flags.append('MORE_NATIVE_ERRORS')
    verified = old.get('status') == new.get('status') == 'VERIFIED'
    wet = [len(d['wet_ends']) for d in (old,new)] if verified else None
    if new.get('wet_ends'):
        flags.append('CHECK_WET_ENDS')
    controls = ('CRITICAL_DEPTH_FALLBACK','ENERGY_BALANCE_ERROR','DOWNSTREAM_EGL_RISE','MINIMUM_ERROR_SOLUTION','STRUCTURE_FLOW_IMBALANCE','RIVER_DISCHARGE_MISMATCH')
    increases = [code for code in controls if new['counts'].get(code,0) > old['counts'].get(code,0)] if verified and all_profiles_matched else []
    if increases:
        flags.append('CHECK_NUMERICAL_CONTROLS')
    delta = new['severity']['WARNING']-old['severity']['WARNING'] if comparable else None
    if delta is not None and delta < 0 and (increases or (wet and wet[1]>wet[0]) or
            'MORE_NATIVE_ERRORS' in flags or 'CHECK_WATER_LEVEL_CHANGE' in flags):
        flags.insert(0,'FEWER_WARNINGS_OTHER_CHANGES')
    return dict(warning_delta=delta,wet_end_counts=wet,maximum_at_verified_center=peak,
                increased_control_codes=increases,flags=flags,
                actions=[dict(code=key,en=GUIDANCE[key][0],zh=GUIDANCE[key][1]) for key in flags])
