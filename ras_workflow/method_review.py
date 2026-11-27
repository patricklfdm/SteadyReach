"""Scope of a steady-flow calculation given a hydrograph and native sensitivity evidence."""
import base64
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from statistics import median

from .common import ROOT, finite, intact, item, safe_path


def series(raw, day, profile, flow):
    day=date.fromisoformat(day)
    if not profile or len(profile)>100 or not finite(flow) or flow<=0:
        raise ValueError('Identify the modeled event profile and positive discharge in cfs / 请指定事件工况和正流量（cfs）')
    dataset=json.loads(raw)
    if not isinstance(dataset,dict) or not isinstance(dataset.get('features'),list):
        raise ValueError('Choose a USGS continuous discharge feature collection / 请选择 USGS 连续流量要素集合')
    if any(link.get('rel')=='next' for link in dataset.get('links',[])):
        raise ValueError('Supply the complete event series, including subsequent pages / 请提供包含所有分页的事件时序')
    values={}
    identity=set()
    for feature in dataset['features']:
        row=feature['properties']
        if row.get('parameter_code')!='00060' or row.get('approval_status')!='Approved' or row.get('value') is None:
            continue
        if row.get('unit_of_measure') not in ('ft^3/s','ft3/s','cfs'):
            raise ValueError('Expected published discharge in cfs / 原始流量单位应为 cfs')
        identity.add((row.get('monitoring_location_id'),row.get('time_series_id')))
        stamp=datetime.fromisoformat(row['time'])
        value=float(row['value'])
        if stamp.tzinfo is None or not finite(value) or value<0:
            raise ValueError('Check discharge and timestamp timezone / 请核对流量和时间的时区')
        stamp=stamp.astimezone(timezone.utc)
        if stamp in values and values[stamp]!=value:
            raise ValueError('Conflicting simultaneous measurements / 同一时间有冲突流量')
        values[stamp]=value
    if len(identity)!=1 or len(values)<3:
        raise ValueError('Choose one approved USGS continuous discharge series / 请选一条已批准的 USGS 连续流量过程')
    station,series_id=identity.pop()
    if not re.fullmatch('USGS-[0-9]+',station or '') or not series_id:
        raise ValueError('Missing USGS series identity / 缺少测站或时序编号')
    start=datetime.combine(day,datetime.min.time(),tzinfo=timezone.utc)
    end=start+timedelta(days=1)
    times=sorted(values)
    if times[-1]<start or times[0]>=end:
        raise ValueError('Event date is outside this record / 事件日位于原件范围以外')
    intervals=[(b-a).total_seconds()/60 for a,b in zip(times,times[1:])]
    cadence=median(intervals)
    # Examine intervals touching the event day, including a gap spanning the whole day.
    intervals_on_day=[(a,b) for a,b in zip(times,times[1:]) if b>start and a<end]
    gaps=[(a,b) for a,b in intervals_on_day if (b-a).total_seconds()/60>1.5*cadence]
    if times[0]>start:gaps.append((start,min(times[0],end)))
    if times[-1]<end:gaps.append((max(start,times[-1]),end))
    longest=max(gaps,key=lambda pair:pair[1]-pair[0],default=None)
    usable=[(a,b) for a,b in intervals_on_day if (b-a).total_seconds()/60<=1.5*cadence and min(values[a],values[b])>=.95*flow]
    span=best=0.
    previous=None
    for a,b in usable:
        span=span if a==previous else 0.
        span+=(min(end,b)-max(start,a)).total_seconds()/60
        previous=b
        best=max(best,span)
    same_day=[q for t,q in values.items() if start<=t<end]
    return dict(profile=profile,day=day.isoformat(),flow_cfs=flow,station=station,series=series_id,
                source_sha256=hashlib.sha256(raw).hexdigest(),sample_interval_minutes=cadence,
                max_on_day_cfs=max(same_day,default=None),near_peak_continuous_minutes=best,
                gap_hours=(longest[1]-longest[0]).total_seconds()/3600 if longest else 0.,
                gap_utc=[t.isoformat() for t in longest] if longest else [])


def validate(spec):
    ref=spec['source']
    name=ref.get('path','')
    if not re.fullmatch(r'projects/[^/]+/hydrographs/[a-f0-9]{64}\.json',name) or not intact([ref]):
        raise ValueError('Restore the registered hydrograph / 请恢复相应的流量时序原件')
    result=series(safe_path(ROOT,name).read_bytes(),spec['day'],spec['profile'],spec['flow_cfs'])
    return dict(result,source=ref)


def attach(key,body):
    from . import app_core as core
    m=core.model(key)
    core.require_idle(m)
    if m['revision']!=body.get('revision') or m.get('summary') or m.get('active_project') or m.get('model_type')!='river':
        raise ValueError('Open the current editable river edition / 请打开可编辑的河道版本')
    scope=dict(m.get('production_scope') or {})
    if body.get('remove') is True:
        scope.pop('event_hydrograph',None)
    else:
        raw=base64.b64decode(body['content'],validate=True)
        if not 0<len(raw)<=8_000_000:
            raise ValueError('Choose an event hydrograph under 8 MB / 请选择 8 MB 内的事件过程原件')
        result=series(raw,body['day'],body['profile'],body['flow_cfs'])
        file=core.folder(key)/'hydrographs'/(result['source_sha256']+'.json')
        file.parent.mkdir(exist_ok=True)
        if file.exists() and file.read_bytes()!=raw:
            raise ValueError('Stored hydrograph changed / 已保存的原件被改动')
        if not file.exists():file.write_bytes(raw)
        scope['event_hydrograph']=dict(result,source=item(file,'event_hydrograph'))
    return core.update(key,dict(revision=m['revision'],production_scope=scope))


def timing(spec,profiles):
    ids={p.get('profile_id',p.get('id')):p.get('flow_cfs') for p in profiles}
    if ids.get(spec['profile']) is None or abs(ids[spec['profile']]-spec['flow_cfs'])>1:
        return ('The hydrograph has a different profile or discharge. Re-associate the event before using it.',
                '流量过程与当前工况名或流量不符，请重新关联事件。')
    facts=f"{spec['station']} · {spec['profile']} · {spec['flow_cfs']:g} cfs · {spec['day']} UTC"
    if spec['gap_hours']:
        return (f"{facts}. A {spec['gap_hours']:g} h gap touches the event day. Obtain time-matched flow and stage records before interpreting flood-wave timing.",
                f"{facts}。事件日存在 {spec['gap_hours']:g} 小时空档。需要同期流量和水位过程才能判断洪峰传播。")
    mins=spec['near_peak_continuous_minutes']
    return (f"{facts}. Longest observed interval at ≥95% of modeled discharge: {mins:g} min. Compare this duration with reach travel time and storage before treating the peak as steady.",
            f"{facts}。测站达到计算流量 95% 的最长连续观测时段为 {mins:g} 分钟。请与河段传播时间和蓄滞影响比较，再判断恒定流近似。")


def conclusions(summary,steps,comparison):
    scope=summary.get('configuration',{}).get('production_scope',{})
    result=[]
    def row(en,zh):
        result.append(dict(heading=dict(en='Steady-flow applicability',zh='恒定流适用范围'),en=en,zh=zh))
    if scope.get('event_hydrograph'):
        row(*timing(validate(scope['event_hydrograph']),summary['hydraulics'].get('profiles',[])))
    for step in steps or []:
        if step['code'].startswith('BOUNDARY_'):
            row(step['en']+' Limit interpretation within that span to the tested boundary range.',
                step['zh']+' 这些断面的水位解释应限定在已试算的边界范围。')
    review=(comparison or {}).get('review',{})
    for entry in review.get('investigation',[]):
        if entry.get('kind')=='overbank_share' and 'CHECK_WATER_LEVEL_CHANGE' in review.get('flags',[]):
            row(entry['en']+' If separate floodplain paths carry material flow, assess a divided reach or a 2D model.',
                entry['zh']+' 若存在独立且显著的漫滩分流，应评估分汊河网或二维模型。')
    return result
