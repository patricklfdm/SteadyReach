"""Station-level next actions shared by the results page and both report languages."""
from collections import defaultdict

from .common import finite
from .revision_inputs import station_key
from .river_observations import datum, holdout_stages
from .river_review import response
from .validation_plan import usable


def step(code, tool, en, zh):
    return dict(code=code, en=en, zh=zh, action=dict(tool=tool, stations=[]))


def residual_regression(previous, current, sections, warning_delta):
    """Compare the identical field reading against each edition's own native profile."""
    if warning_delta is None or warning_delta >= 0:
        return None

    def index(rows):
        indexed = defaultdict(list)
        for r in holdout_stages(rows)[0]:
            rs = (r.get('location') or {}).get('rs')
            identity = (r.get('event'), r.get('date'), r.get('profile'), r.get('source'), datum(r.get('observed_datum')))
            if rs is None or not all(identity) or not all(finite(r.get(k)) for k in ('model_ft','observed_ft','flow_cfs')):
                continue
            indexed[(*identity, station_key(rs))].append(r)
        return indexed

    left, right = index(previous), index(current)
    changes = {(r['profile'],station_key(r['station'])):r for r in sections if r['location_status']=='SAME_CENTER'}
    worst = None
    for key in sorted(left.keys() & right.keys()):
        if len(left[key]) != 1 or len(right[key]) != 1:
            continue
        a, b = left[key][0], right[key][0]
        event, date, profile, source, vertical, rs = key
        change = changes.get((profile,rs))
        if not change or a['observed_ft'] != b['observed_ft'] or a['flow_cfs'] != b['flow_cfs']:
            continue
        if any(abs(r['model_ft']-change[k]) > 1.e-5 for r,k in ((a,'previous'),(b,'current'))):
            continue
        before, after = (r['model_ft']-r['observed_ft'] for r in (a,b))
        increase = abs(after)-abs(before)
        if increase > 1.e-5 and (worst is None or increase > worst[0]):
            facts = f'{date} · {event} · {profile} · RS {rs} · {vertical}'
            worst = (increase,step('FIELD_REGRESSION','comparison',
                f'{facts}. Native warnings fell by {-warning_delta}. Modeled minus observed stage changed from {before:+.3f} to {after:+.3f} ft. Retain the parent as the reference for this observation. Check datum, bed and boundary controls before selecting a revision. After tuning, verify against a new independent event.',
                f'{facts}。原生警告减少 {-warning_delta} 条，同一测点的计算减实测水位差从 {before:+.3f} 变为 {after:+.3f} ft。保留父版作为该测点的比较基准，核对基准面、河床与边界依据后再选版。若据此调参，另取独立事件验证。'))
    return worst[1] if worst else None


def site_steps(scope, events, studies):
    rows = []
    rules = scope.get('criteria') or {}
    flagged = []
    for obs in holdout_stages(usable(events,scope))[0]:
        rs = (obs.get('location') or {}).get('rs')
        if rs is None or not obs.get('date') or not obs.get('event'):
            continue
        limit = None
        if rules.get('event')==obs['event'] and (not rules.get('profile') or rules['profile']==obs.get('profile')) and (
                not rules.get('rs') or station_key(rules['rs'])==station_key(rs)):
            limit = rules.get('max_residual_ft')
        for plan in scope.get('validation_plan',[]):
            if (plan['role'],plan['event'],plan['date'],plan['profile'],plan['rs'])==(
                    'holdout',obs['event'],obs['date'],obs.get('profile'),station_key(rs)):
                limit = min(limit,plan['tolerance_ft']) if finite(limit) else plan['tolerance_ft']
        err = obs['residual_ft']
        uncertainty = obs.get('uncertainty_ft')
        exceeds = finite(limit) and abs(err)>limit
        if exceeds or not finite(uncertainty) or uncertainty<=0 or abs(err)>uncertainty:
            flagged.append((exceeds,abs(err),obs,rs,limit))
    if flagged:
        _,_,obs,rs,limit=max(flagged,key=lambda item:item[:2])
        facts=f"{obs['event']} · {obs['date']} · RS {rs} · {obs['residual_ft']:+.3f} ft"
        en,zh = ('','') if not finite(limit) else (f' Project limit {limit:g} ft.',f' 项目限值 {limit:g} ft。')
        accuracy = obs.get('uncertainty_ft')
        if finite(accuracy) and accuracy>0:
            en+=f' Reported vertical uncertainty ±{accuracy:g} ft.'
            zh+=f' 已记录的高程不确定度为 ±{accuracy:g} ft。'
        else:
            en+=' Vertical uncertainty is undocumented.'
            zh+=' 缺少高程测量精度记录。'
        rows.append(step('FIELD_CHECK','observations',facts+' (modeled minus observed).'+en+
            ' Verify the event discharge, gage zero, vertical uncertainty and outlet transfer, then compare the bed with a surveyed section. Pause fitting until the controlling input has evidence. Reserve a new event if this one informs a revision.',
            facts+'（计算减实测）。'+zh+' 先查同期流量、水尺零点、测量精度与出口水位换算，再对照实测河床。关键输入缺依据时暂停调参。若据此修改模型，另留一次事件验证。'))
    boundaries = {}
    for case in response(studies):
        paths=case['paths']
        if len(paths)!=1 or not paths[0].startswith(('boundaries.','boundary_slopes.')) or not case['affected']:
            continue
        side=paths[0].split('.')[1]
        if side not in ('upstream','downstream'):
            continue
        farthest=(max if side=='downstream' else min)(case['affected'],key=lambda r:float(r['rs']))
        key=(side,case['profile'])
        rank=((1 if side=='downstream' else -1)*float(farthest['rs']),abs(case['signed_peak_ft']))
        if key not in boundaries or rank>boundaries[key][0]:
            boundaries[key]=(rank,case,farthest['rs'])
    for (side,profile),(_,case,rs) in boundaries.items():
        facts=f"{profile} · {case['case']}"
        change=next((c for study in studies if study['analysis']==case['source'] for variant in study['cases']
                     if variant['id']==case['case'] for c in variant.get('changes',[]) if c['path']==case['paths'][0]),{})
        if finite(change.get('before')) and finite(change.get('after')):
            units='ft/ft' if case['paths'][0].startswith('boundary_slopes.') else 'ft'
            facts+=f" ({change['before']:g} → {change['after']:g} {units})"
        facts+=f" · RS {case['peak_rs']} · Δ {case['signed_peak_ft']:+.3f} ft"
        count=f"{len(case['affected'])}/{case['compared']}"
        limit=case['threshold_ft']
        rows.append(step('BOUNDARY_'+side.upper()+'_'+profile,'sensitivity',
            f'{facts}. Perturbing the {side} boundary changed stage by more than {limit:g} ft at {count} compared sections. The farthest tested exceedance was RS {rs}. Obtain event-matched boundary control before repeating the range or using those levels.',
            f"{facts}。改变{'下游' if side=='downstream' else '上游'}边界后，{count} 条可比断面的水位变化超过 {limit:g} ft。离该边界最远的超限断面为 RS {rs}。先取得同期边界控制资料，再重复试算或引用这些水位。"))
    return rows
