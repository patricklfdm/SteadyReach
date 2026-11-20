"""Pre-construction decisions for a single steady reach. No solver or downloads."""
from .common import finite
from .river import boundary_errors


PURPOSES = {'screening', 'comparison', 'review'}
PATHS = {'unknown', 'single', 'parallel', 'unsteady', 'bridge'}
OUTSIDE = {'parallel', 'unsteady', 'bridge'}


def scope(data):
    if not isinstance(data,dict):
        raise ValueError('Invalid project scope / 项目范围格式有误')
    purpose = data.get('purpose', 'screening')
    paths = data.get('flow_paths', 'unknown')
    if purpose not in PURPOSES or paths not in PATHS:
        raise ValueError('Choose a listed project purpose and flow path / 请选择列表中的用途和过流条件')
    return {'purpose': purpose, 'flow_paths': paths}


def assess(model, config, geometry, answers, acquisition=None, native=None, reach=None):
    from .river_observations import datum as normalize_datum
    intent = scope(model.get('production_scope', {}))
    scenario = next((s for s in config.get('scenarios', []) if s['id'] == model['scenario']), {})
    river = model.get('model_type') == 'river'
    reach = reach or {}
    if reach.get('status')=='CHOOSE_REACH':
        index=model.get('reach_option')
        reach=reach['options'][index] if type(index) is int and 0<=index<len(reach['options']) else {}
    rows = []

    def add(key, status, en, zh, **facts):
        rows.append(dict(key=key, status=status, en=en, zh=zh, facts=facts))

    mapped = (reach or {}).get('mapped_junctions')
    add('scope', 'outside' if intent['flow_paths'] in OUTSIDE else
        'review' if intent['flow_paths'] == 'unknown' or mapped else 'available',
        'Inspect imagery for bypass channels, controlling bridges and lateral exchange.',
        '用航片核对旁路、控制性桥梁和横向交换。', mapped_junctions=mapped, **intent)
    profiles = (native or {}).get('profiles') or scenario.get('profiles', [])
    has_flow = bool(profiles) and all(finite(p.get('flow_cfs')) and p['flow_cfs'] > 0 for p in profiles)
    add('flow', 'review' if has_flow else 'missing',
        'Check the event, reach and discharge against its cited hydrology table or gage record.',
        '用水文报告表格或测站记录核对事件、河段和流量。',
        profiles=[{k:p.get(k) for k in ('id','flow_cfs','source')} for p in profiles])
    if river:
        bed = geometry.get('channel_geometry_basis')
        survey = bed in ('surveyed_channel', 'combined_survey_and_dem')
        add('bed', 'review' if survey else 'conditional',
            'Check survey dates, submerged coverage, vertical datum and the tie to the terrain.',
            '核对测量年代、水下覆盖、垂直基准和与地形的衔接。', basis=bed)
    else:
        groups = ((native or {}).get('structure') or geometry.get('structure') or {}).get('groups', [])
        for key, names, en, zh in [
            ('openings', ('shape','count','span_ft','rise_ft'), 'Verify each opening against the drawing or scaled photos.',
             '用图纸或带尺度照片逐组核对开口。'),
            ('inverts', ('length_ft','us_invert_ft','ds_invert_ft'), 'Use surveyed inverts and barrel length on the model datum.',
             '用测量或竣工图核对涵长及模型基准下的两端涵底。')]:
            values = []
            for i, group in enumerate(groups):
                for name in names:
                    answer = answers.get(f'g.structure.groups.{i}.{name}', {})
                    values.append(dict(group=i+1, field=name, value=group.get(name),
                                       origin=answer.get('evidence_class') or ('native_input' if native else 'unverified'),
                                       basis=answer.get('basis')))
            status = 'review'
            if not values or any(r['value'] is None for r in values):
                status = 'missing'
            elif any(r['origin'] in ('assumed','terrain_derived','inferred','derived') for r in values):
                status = 'conditional'
            add(key,status,en,zh,values=values)
    datum = geometry.get('vertical_datum') or model.get('metadata', {}).get('vertical_datum')
    dem_datum = model.get('metadata', {}).get('dem_vertical_datum') or (config.get('terrain') or {}).get('vertical_datum')
    mismatch = datum and dem_datum and normalize_datum(datum) != normalize_datum(dem_datum)
    add('datum', 'conflict' if mismatch else 'review' if datum else 'missing',
        'Match model, survey, terrain and observation datums; a gage height needs its dated gage zero.',
        '核对模型、测量、地形和观测基准；水尺读数还需同期零点。', model_datum=datum, terrain_datum=dem_datum)
    boundaries = (native or {}).get('boundaries') or geometry.get('boundaries', {})
    slopes = geometry.get('boundary_slopes') or {}
    required = ['downstream'] if geometry.get('flow_regime') == 'subcritical' else ['upstream','downstream']
    if native:
        complete = bool(boundaries)
    elif river:
        complete = not boundary_errors(geometry, len(profiles))
    else:
        complete = all(finite(slopes.get(side)) and slopes[side] > 0 for side in required)
    nearby = [dict(station=s.get('station'),distance_to_project_m=s.get('distance_m'))
              for attempt in (acquisition or {}).get('attempts', []) if attempt.get('route') == 'CA_USGS_gage_frequency'
              for s in attempt.get('matches', [])]
    from .early_gages import screen
    search = next((a for a in (acquisition or {}).get('attempts',[]) if a.get('route')=='USGS_boundary_records'),{})
    stations = screen(search, geometry, model, reach, profiles) if search.get('stations') else []
    add('boundary','review' if complete else 'missing',
        'Check each required reach end. For an off-site stage, obtain a dated transfer, common datum and uncertainty; test normal-depth alternatives.',
        '核对适用的河段边界。异地测站水位需同期传递关系、共同基准与不确定度；正常水深需做敏感性检查。',
        boundaries=boundaries, slopes=slopes, nearby_frequency_stations=nearby, stations=stations,
        search_status=search.get('status'), search_failures=search.get('failures',[]))
    if intent['purpose'] == 'review':
        add('independent_event','review','Reserve a separate event and non-boundary measurements before tuning.',
            '调参前留出独立事件及非边界实测点，用于校核。')
    state = 'outside' if intent['flow_paths'] in OUTSIDE else 'missing' if any(r['status'] in ('missing','conflict') for r in rows) else 'review'
    conditional=[r['key'] for r in rows if r['status']=='conditional']
    if stations and all(r['transfer_required'] is True for r in stations):conditional.append('offsite_boundary')
    use=('outside_scope' if state=='outside' else 'resolve_inputs' if state=='missing' else
         'conditional_screening' if conditional else 'parameter_review')
    return dict(state=state,use=use,scope=intent,conditional_basis=conditional,rows=rows)
