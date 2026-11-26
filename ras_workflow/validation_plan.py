"""Precalculation station/event roles and independent-stage scoring for one run."""
from datetime import date
from .common import finite
from .revision_inputs import station_key

ROLES={'holdout','calibration','boundary'}
STATES={
    'EXCEEDED':('Investigate stage error','调查水位偏差'),
    'PENDING':('Obtain comparable evidence','补充可比证据'),
    'WITHIN':('Within the specified error at this station and flow','该断面和流量的误差在约定范围内'),
    'CALIBRATION':('Used for calibration; obtain a replacement holdout','已用于率定，需另取独立事件'),
    'BOUNDARY':('Boundary control excluded','边界控制已从评分排除')}


def normalize(rows):
    if not isinstance(rows,list) or len(rows)>100:raise ValueError('Specify up to 100 station events / 最多登记 100 项断面事件')
    result=[];seen=set()
    for row in rows:
        if not isinstance(row,dict):raise ValueError('Invalid event record')
        event={}
        for k in ('event','profile','date','rs','basis','role'):
            val=row.get(k)
            if not isinstance(val,str) or not val.strip() or len(val)>500:raise ValueError('Supply event field / 请填写事件字段 '+k)
            event[k]=val.strip()
        event['date']=date.fromisoformat(event['date']).isoformat()
        event['rs']=station_key(event['rs'])
        limit=row.get('tolerance_ft')
        if event['role'] not in ROLES or not finite(limit) or limit<0:raise ValueError('Invalid role or station tolerance / 用途或水位容差无效')
        event['tolerance_ft']=limit
        key=(event['profile'],event['date'],event['rs'])
        if key in seen:raise ValueError('Duplicate event at the same station, profile and date / 同一工况、日期和断面存在重复事件')
        seen.add(key);result.append(event)
    return result


def scope_update(old,new):
    retired=set(old.get('calibration_dates',[]))
    retired.update(r['date'] for r in old.get('validation_plan',[]) if r['role']=='calibration')
    retired.update(r['date'] for r in new.get('validation_plan',[]) if r['role']=='calibration')
    if any(r['role']=='holdout' and r['date'] in retired for r in new.get('validation_plan',[])):
        raise ValueError('This event date was used for calibration. Reserve a different independent event / 该日期的事件已用于率定，需另选独立事件')
    if old.get('validation_protocol_active') or old.get('validation_plan') or new.get('validation_plan'):
        new=dict(new,validation_protocol_active=True)
    if retired:new=dict(new,calibration_dates=sorted(retired))
    return new


def station_flows(hyd):
    from .common import ROOT,intact
    from .qa import BASE,number
    import h5py
    source=hyd.get('raw_hdf')
    if not source or not intact([source]):
        return {}
    with h5py.File(ROOT/source['path']) as f:
        attrs=f['Results/Steady/Output/Geometry Info/Cross Section Attributes'][:]
        stations=[station_key(row['Station'].decode().strip()) for row in attrs]
        if len(set(stations))!=len(stations):
            return {}
        names=[raw.decode().strip() for raw in f[BASE+'/Profile Names'][:]]
        values=f[BASE+'/Cross Sections/Flow']
        if values.shape!=(len(names),len(stations)):
            return {}
        return {(name,rs):number(q) for name,row in zip(names,values) for rs,q in zip(stations,row)}


def score(summary,events,flows=None):
    scope=summary.get('configuration',{}).get('production_scope') or {}
    retired=set(scope.get('calibration_dates',[]))
    if not scope.get('validation_plan'):
        return []
    hyd=summary.get('hydraulics') or {}
    if flows is None:
        flows=station_flows(hyd)
    profiles={p['profile_id']:p for p in hyd.get('profiles',[])}
    rows=[]
    for spec in scope.get('validation_plan',[]):
        row=dict(spec,flow_cfs=flows.get((spec['profile'],spec['rs'])),
                 state='PENDING',residual_ft=None,uncertainty_ft=None,count=0)
        matches=[]
        for e in events:
            rs=(e.get('location') or {}).get('rs')
            if rs is None or str(e.get('profile'))!=spec['profile'] or e.get('date')!=spec['date'] or e.get('event')!=spec['event']:continue
            if station_key(rs)==spec['rs']:matches.append(e)
        profile=profiles.get(spec['profile']) or {}
        ends={station_key(profile[k]) for k in ('tailwater_rs','headwater_rs') if profile.get(k) is not None}
        if spec['rs'] in ends or spec['role']=='boundary' or any(e.get('role')=='boundary' for e in matches):row['state']='BOUNDARY'
        elif spec['role']=='calibration' or spec['date'] in retired or any(e.get('role')=='calibration' for e in matches):row['state']='CALIBRATION'
        elif len(matches)==1:
            e=matches[0];z=e.get('observed_ft');modeled=e.get('model_ft');q=e.get('flow_cfs')
            if (e.get('role')=='holdout' and e.get('kind') in ('stage','gage_height') and not e.get('issues') and
                finite(row['flow_cfs']) and finite(q) and abs(q-row['flow_cfs'])<=max(.002,q*1e-7) and
                finite(z) and finite(modeled) and finite(e.get('residual_ft')) and abs((modeled-z)-e['residual_ft'])<1e-5):
                delta=modeled-z;u=e.get('uncertainty_ft');row.update(residual_ft=delta,uncertainty_ft=u,count=1)
                if abs(delta)>spec['tolerance_ft']:row['state']='EXCEEDED'
                elif finite(u) and u>0 and abs(delta)+u<=spec['tolerance_ft']:row['state']='WITHIN'
        rows.append(row)
    return rows


def revision_roles(model,config,geometry):
    """Once evidence is visible, prevent a parameter or tolerance change from validating itself."""
    from .common import ROOT,intact,read
    from .revision_inputs import bound_inputs
    from .river_review_report import collect
    scope=model.get('production_scope') or {};plan=scope.get('validation_plan',[])
    origin=(model.get('parent_revision') or {}).get('summary')
    if not origin or not (scope.get('validation_protocol_active') or plan):return scope
    if not intact([origin]):raise ValueError('Restore the parent evidence before checking event independence / 请先恢复父版证据以核对独立性')
    parent=read(ROOT/origin['path']);old,geom,_=bound_inputs(parent)
    evidence,_=collect(ROOT/origin['path'],parent)
    exposed={r['date'] for r in evidence.get('events',[]) if r.get('role') in ('holdout','calibration') and r.get('observed_ft') is not None}
    if not exposed:return scope
    def hydraulics(c,g):
        scenarios=[{k:v for k,v in s.items() if k in ('id','channel_n','overbank_n','flow_regime')} |
                   {'profiles':[(p['id'],p['flow_cfs']) for p in s.get('profiles',[])]} for s in c.get('scenarios',[])]
        return scenarios,{k:v for k,v in g.items() if k in ('boundaries','boundary_slopes','cross_sections','structure','flowlines','flow_regime','vertical_datum','horizontal_crs')}
    old_plan=old.get('production_scope',{}).get('validation_plan',[])
    adjusted=hydraulics(old,geom)!=hydraulics(config,geometry)
    dates={r['date'] for r in plan if r['role']=='holdout' and r['date'] in exposed and (adjusted or r not in old_plan)}
    dates.update(r['date'] for r in old_plan if r['role']=='holdout' and r['date'] in exposed and (adjusted or r not in plan))
    if not dates:return scope
    updated=[dict(r,role='calibration') if r['date'] in dates and r['role']=='holdout' else r for r in plan]
    return scope_update(dict(scope,calibration_dates=sorted(set(scope.get('calibration_dates',[]))|dates)),dict(scope,validation_plan=updated))


def usable(rows,scope):
    plan=scope.get('validation_plan',[]);retired=scope.get('calibration_dates',[])
    if not plan and not retired and not scope.get('validation_protocol_active'):return rows
    selected=[]
    for e in rows:
        role=e.get('role')
        if role=='holdout':
            key=(e.get('profile'),e.get('event'),e.get('date'),(e.get('location') or {}).get('rs'))
            if key[2] in retired:role='calibration'
            elif (plan or scope.get('validation_protocol_active')) and not any((p['profile'],p['event'],p['date'])==key[:3] and key[3] is not None and
                        station_key(key[3])==p['rs'] and p['role']=='holdout' for p in plan):role='context'
        selected.append(dict(e,role=role))
    return selected
