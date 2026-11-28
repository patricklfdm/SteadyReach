"""Versioned scope descriptions used at intake and carried into the issued edition."""
TEMPLATES = {
    'between_bridges_v1': {
        'model': 'river',
        'title': ['River between two bridges', '两桥间纯河道'],
        'inputs': ['Identify the upstream bridge’s downstream face and the downstream bridge’s upstream face. Confirm flow direction, event discharge, DEM units and datum, bed representation, floodplain connectivity, roughness and the applicable end controls.',
                   '定位上游桥的下游侧和下游桥的上游侧。核对流向、事件流量、DEM 单位和基准、河床代表性、漫滩连通、糙率及适用端点边界。'],
        'screening': ['Deliver a conditional reach profile and section tables. Include available terrain, Mapper layers and exhibits in a mapped delivery. Label DEM bed and normal-depth assumptions. Check for bridge backwater at the project limits.',
                      '可交付条件性河段水面线和断面表，启用制图时附地形、Mapper 图层和展示图。标明 DEM 河床及正常水深假设，核查桥梁壅水是否影响边界。'],
        'comparison': ['Reuse the confirmed reach, flow, datum and baseline. Identify the changed input and compare the same profiles at matching sections, including outlet sensitivity and wet ends.',
                       '沿用已确认河段、流量、基准和基准版。注明改动项，在匹配断面对照同工况结果，核查出口影响和湿端。'],
        'review': ['For engineering review add source-backed submerged sections and an independent interior stage with agreed tolerance. Test the controlling boundary in a single-factor sensitivity run. Building impacts require separate site elevations and flow-path review.',
                   '提交工程复核需补有原件的水下断面，及有约定容差的独立内点水位。以单因素试算量化控制边界影响。评价建筑影响还需场地高程和过流路径复核。'],
    },
    'single_culvert_v1': {
        'model': 'culvert',
        'title': ['One culvert crossing', '单处涵洞'],
        'inputs': ['Identify each barrel group, opening, length, both inverts, entrance, blockage and road crest. Confirm the approach sections, tailwater, event flow, datum and roughness.',
                   '逐组核对涵孔数与净尺寸、涵长、两端涵底、入口、堵塞及道路控制高程。核对进出口断面、尾水、事件流量、高程基准和糙率。'],
        'screening': ['Deliver conditional headwater, tailwater and available native flow tables. Identify estimated inverts and road elevations. Missing roadway or group discharge stays unknown.',
                      '可交付条件性涵前及尾水水位与可用原生流量表。标明估算的涵底和路面高程，缺失的路面或分组流量保留未知。'],
        'comparison': ['Reuse the baseline crossing, event flow and datum. Identify the changed barrel, blockage or outlet condition and compare common profiles, headwater and flow distribution.',
                       '沿用基准涵址、事件流量和基准面。注明改变的涵孔、堵塞或出口条件，对比共同工况的涵前水位和流量分配。'],
        'review': ['For engineering review supply sourced opening sizes, length and both inverts for every group, a surveyed road crest and native roadway flow. If a road margin is contractual enter its value and basis. Check bypass paths before issue.',
                   '提交工程复核需逐组提供有原件的净尺寸、涵长与两端涵底，提供道路控制线测量和原生路面越流量。若合同约定余高，另填数值与依据。签发前核查旁路。'],
    },
}


def validate(template, model=None):
    if template not in TEMPLATES or (model and TEMPLATES[template]['model'] != model):
        raise ValueError('Choose the delivery template for this model type / 请选择与模型类型一致的交付模板')
    return template


def crossing_records(geometry, answers, sources):
    """Record which confirmed crossing controls have matching, intact source records."""
    from .common import intact
    from .river_observations import datum
    structure = geometry.get('structure') or {}
    model_datum = datum(geometry.get('vertical_datum'))
    missing = []
    checked = set()

    def check(key, value, elevation=False):
        answer = answers.get(key) or {}
        record = answer.get('candidate_record') or {}
        ref = record.get('source')
        declared = answer.get('evidence_class') in ('reported', 'user_reported_measurement', 'as_built')
        tied = model_datum not in ('', 'UNKNOWN', 'UNSPECIFIED', 'NONE', 'LOCAL') and datum(record.get('datum')) == model_datum
        if not (declared and value is not None and record.get('value') == value and ref and ref in sources and (not elevation or tied)):
            missing.append(key)
        elif ref.get('sha256') not in checked:
            if intact([ref]):
                checked.add(ref['sha256'])
            else:
                missing.append(key)

    groups = structure.get('groups') or []
    for index, group in enumerate(groups):
        for name in ('shape', 'count', 'span_ft', 'rise_ft', 'length_ft', 'us_invert_ft', 'ds_invert_ft'):
            check(f'g.structure.groups.{index}.{name}', group.get(name), name.endswith('invert_ft'))
    road = structure.get('road') or {}
    for name in ['station_ft', 'elevation_ft'] + (['downstream_station_ft', 'downstream_elevation_ft'] if road.get('profile_mode') == 'distinct' else []):
        check('g.structure.road.' + name, road.get(name), 'elevation' in name)
    return dict(groups=len(groups), missing=missing, documented=bool(groups) and not missing)


def delivery_row(scope):
    key = scope.get('delivery_template')
    if key not in TEMPLATES:
        return None
    template = TEMPLATES[key]
    use = template[scope['purpose']]
    return dict(heading=dict(en='Agreed delivery scope', zh='约定交付范围'),
                en=template['title'][0]+'. '+use[0]+' '+template['inputs'][0],
                zh=template['title'][1]+'。'+use[1]+template['inputs'][1])
