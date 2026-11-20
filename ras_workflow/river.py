"""Explicit river-only scope and steady boundary contracts.

The downstream known-WSE card is taken from the inspected USACE MULTCULV
example. No bridge, submerged channel or boundary stage is inferred here.
"""
from .common import finite


def is_river(obj):
    return obj.get('model_type', 'culvert') == 'river'


def check_known_stages(profiles, station, requested, actual, critical=None):
    failures=[]
    for i,(profile,target,value) in enumerate(zip(profiles,requested,actual,strict=True)):
        if finite(value) and abs(value-target)<=.002:continue
        message=f"{profile['id']} at downstream RS {station}: requested {target:.4f} ft, native {value:.4f} ft"
        if critical is not None and finite(critical[i]) and abs(critical[i]-value)<=.002 and target<critical[i]-.002:
            message+=f", computed critical elevation {critical[i]:.4f} ft; review the outlet survey, stage transfer and regime"
        failures.append(message)
    if failures:raise ValueError('Known downstream water level readback mismatch: '+' | '.join(failures))


def boundary_errors(g, profile_count=None):
    errors = []
    sides = ['downstream'] if g.get('flow_regime') == 'subcritical' else ['upstream', 'downstream']
    for side in sides:
        b = g.get('boundaries', {}).get(side, {})
        kind = b.get('type')
        if kind == 'normal_depth':
            if not finite(g.get('boundary_slopes', {}).get(side)) or g['boundary_slopes'][side] <= 0:
                errors.append('Positive normal-depth slope required: ' + side)
        elif kind == 'known_stage' and side == 'downstream':
            values = b.get('stages_ft')
            if not isinstance(values, list) or not values or not all(finite(v) for v in values):
                errors.append('Known downstream WSE requires finite elevations in profile order')
            elif profile_count is not None and len(values) != profile_count:
                errors.append('Known downstream WSE count must equal flow profile count')
        else:
            errors.append('Choose a supported boundary type: ' + side)
    return errors


def boundary_cards(g, index):
    text = ''
    for side, prefix in [('upstream', 'Up'), ('downstream', 'Dn')]:
        if side == 'upstream' and g.get('flow_regime') == 'subcritical':
            text += 'Up Type= 0\n'
        elif g['boundaries'][side]['type'] == 'known_stage':
            text += f"Dn Type= 1\nDn Known WS={g['boundaries'][side]['stages_ft'][index]:.6f}\n"
        else:
            text += f"{prefix} Type= 3\n{prefix} Slope={g['boundary_slopes'][side]:.8f}\n"
    return text


def add_fields(add, g):
    add('g.channel_geometry_basis', 'Channel bed representation', '水下河槽表示方式', 'choice',
        options=['surveyed_channel', 'combined_survey_and_dem', 'conditional_surface_dem'],
        help_en='Surface DEM may represent water surface, not bed. Conditional DEM-only results require channel survey before engineering acceptance.',
        help_cn='地表 DEM 可能表示水面而非河底。仅用地表 DEM 的结果属于条件性结果，工程验收前需补充河槽测量。')
    for side, cn in [('upstream', '上游'), ('downstream', '下游')]:
        if side == 'upstream' and g.get('flow_regime') == 'subcritical':
            continue
        add('g.boundaries.' + side + '.type', side.title() + ' boundary type', cn + '边界类型', 'choice',
            options=['normal_depth', 'known_stage'] if side == 'downstream' else ['normal_depth'])
        kind = g.get('boundaries', {}).get(side, {}).get('type')
        if kind == 'known_stage':
            add('g.boundaries.' + side + '.stages_ft', 'Downstream water-surface elevations in profile order',
                '下游已知水位（按流量工况顺序）', 'array', 'ft',
                help_en='Absolute WSE in the model vertical datum, not gauge height. One value for each flow profile.',
                help_cn='填写模型高程基准下的绝对水位，不是水尺读数。每个流量工况对应一个值。')
        elif kind == 'normal_depth':
            add('g.boundary_slopes.' + side, side.title() + ' normal-depth slope', cn + '正常水深坡降', unit='ft/ft',
                help_en='Representative energy slope at the boundary; check sensitivity and possible bridge backwater.',
                help_cn='边界附近代表性能量坡降；需检查边界敏感性和桥梁壅水影响。')
