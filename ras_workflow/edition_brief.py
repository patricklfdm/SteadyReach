"""A recipient-safe description of the computed edition shared by screen and reports."""
from .common import finite
from .river_observations import holdout_stages
from .validation_plan import usable


def build(summary, decision, events):
    h = summary['hydraulics']
    config = summary.get('configuration') or {}
    scope = config.get('production_scope') or {}
    measured, missing, _ = holdout_stages(usable(events, scope))
    observed = sorted({(str(row['location']['rs']), row['flow_cfs']) for row in measured
                       if (row.get('location') or {}).get('rs') is not None and finite(row.get('flow_cfs'))})
    profiles = [f"{row['profile_id']} ({row['flow_cfs']:g} cfs)" for row in h.get('profiles', [])
                if row.get('profile_id') and finite(row.get('flow_cfs'))]
    profiles_text = ', '.join(profiles[:3])
    if len(profiles) > 3:
        profiles_text += f' (+{len(profiles)-3})'
    if profiles_text:
        flows = (f'Modeled {profiles_text}.', f'已计算 {profiles_text}。')
    else:
        flows = ('Consult the native profile table for discharge.', '流量见原生工况表。')
    if observed:
        locations = ', '.join(f'RS {rs} @ {flow:g} cfs' for rs,flow in observed[:3])
        if len(observed) > 3:
            locations += f' (+{len(observed)-3})'
        field = ('Field comparison at '+locations+'.', '有现场水位对照的位置与流量为 '+locations+'。')
    else:
        field = ('Independent field stage comparison is pending.', '尚缺可比的独立实测水位。')

    if config.get('case_kind') == 'software_validation':
        condition = ('Reference example inputs define the result.', '结果取决于教学或数值算例输入。')
        follow = ('Modeler: compare with the registered reference output.', '建模工程师核对已登记的参考输出。')
    elif h.get('channel_geometry_basis') == 'conditional_surface_dem':
        condition = ('The surface DEM approximates the submerged bed.', '当前以地表 DEM 近似水下河床。')
        follow = ('Survey team: collect dated bed-to-bank sections at the hydraulic controls.', '请测量组补控制断面从河床到岸顶的同期剖面。')
    elif h.get('model_type') == 'culvert':
        condition = ('Opening and invert elevations control headwater and overtopping.', '洞口几何及进出口涵底高程影响涵前水位与漫顶。')
        follow = ('Structure survey team: check the barrel openings, both inverts and road crest against the model.', '请结构测量组核对各孔洞口、两端涵底和路面顶高程。')
    elif missing:
        condition = ('Vertical uncertainty is missing for comparable stage observations.', '部分可比水位缺少高程测量精度。')
        follow = ('Survey lead: supply the vertical uncertainty and datum tie for the observed stages.', '请测量负责人补水位测量精度和高程基准联测记录。')
    else:
        condition = ('Event discharge and outlet stage govern the water-surface profile.', '事件流量与出口水位影响沿程水位。')
        follow = ('Hydrologist: verify event discharge and outlet control. Survey team: confirm interior water levels.', '请水文工程师核对同期流量与出口控制，测量组核查河段内实测水位。')

    if config.get('case_kind')=='software_validation':
        answer=('Reproduces the reference calculation.', '复算给定参考工况。')
    elif h.get('model_type')=='culvert':
        answer=('Calculates water levels at the crossing.', '计算过水设施处的水位。')
    else:
        answer=('Calculates steady-flow water levels along the reach.', '计算该河段的恒定流水面线。')

    def row(en_title, zh_title, en, zh):
        return dict(heading=dict(en=en_title, zh=zh_title), en=en, zh=zh)
    return dict(run_id=h.get('run_id'), rows=[
        row('Edition use', '本版用途', answer[0]+' '+decision['en'], answer[1]+decision['zh']),
        row('Flow and field coverage', '流量和实测范围', ' '.join((flows[0],field[0])), flows[1]+field[1]),
        row('Key assumption or limitation', '关键假设或限制', *condition),
        row('Who should follow up', '下一步由谁补什么', *follow),
    ])
