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
