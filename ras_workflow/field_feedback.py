"""Collect field feedback for one solved river edition without editing its source model."""
import base64
import csv
import io
from pathlib import Path

from . import app_core as core
from .common import ROOT, digest, finite, intact, item, read, rel, save, unique_id
from .river_observations import current as observation_table

CONTEXT = ('point_id','event','date','rs','role','stage_ft','datum','flow_cfs','original_source')
EDIT = ('point_type','basis','uncertainty_ft','reference')
POINTS = ('unknown','measured','interpolated')
BASES = ('unknown','documented','assumed')


def model_for(key, body):
    m=core.model(key)
    if (m.get('model_type')!='river' or m.get('native_review') or not m.get('summary')
            or m['summary']['sha256']!=body.get('summary_hash') or not intact([m['summary']])):
        raise ValueError('Reopen the current workflow-built river result')
    return m


def rows_for(m):
    packet=observation_table(m)
    if not packet:
        if m.get('river_observations'):raise ValueError('Restore the bound observation table')
        return []
    rows=[]
    for r in packet['rows']:
        if not r['event_eligible'] or r['kind'] not in ('stage','boundary_stage','gage_height'):continue
        identity=digest([packet['source']['sha256'],r['line']])[:16]
        recorded=r.get('uncertainty_ft')
        rows.append(dict(point_id=identity,event=r['event'],date=r['date'],rs=r['location']['rs'],role=r['role'],
                         stage_ft=r['observed_ft'],datum=r['model_datum'],flow_cfs=r['flow_cfs'],original_source=r['source'],
                         point_type='unknown',basis='documented' if recorded and recorded>0 else 'unknown',
                         uncertainty_ft=recorded if recorded and recorded>0 else '',reference=r['source'] if recorded and recorded>0 else ''))
    return rows


def csv_text(rows):
    stream=io.StringIO(newline='')
    writer=csv.DictWriter(stream,fieldnames=CONTEXT+EDIT)
    writer.writeheader();writer.writerows(rows)
    return stream.getvalue()


def merge_feedback(template, text):
    if not isinstance(text,str) or len(text)>2_000_000:raise ValueError('Use a CSV under 2 MB')
    reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    if tuple(reader.fieldnames or ())!=CONTEXT+EDIT:raise ValueError('Use the downloaded field feedback template')
    by_id={r['point_id']:dict(r) for r in template}
    seen=set()
    for row in reader:
        pid=row.get('point_id')
        if pid not in by_id or pid in seen or None in row or None in row.values():raise ValueError('Unknown, duplicate or incomplete feedback row')
        seen.add(pid);original=by_id[pid]
        if any((float(row[k])!=original[k] if k in ('flow_cfs','stage_ft') else row[k]!=str(original[k])) for k in CONTEXT):raise ValueError('Event, station or source changed. Edit the last four columns only.')
        point,origin=row['point_type'].strip(),row['basis'].strip()
        ref=row['reference'].strip()
        if point not in POINTS or origin not in BASES:raise ValueError('Unknown point type or evidence class')
        u=float(row['uncertainty_ft']) if row['uncertainty_ft'].strip() else None
        if u is not None and (not finite(u) or u<=0):raise ValueError('Report uncertainty as a positive number in feet')
        if (origin=='unknown' and (u is not None or point!='unknown')) or (origin!='unknown' and not ref):
            raise ValueError('Classify the field information and supply its reference or assumption')
        original.update(point_type=point,basis=origin,uncertainty_ft=u,reference=ref)
    if not seen:raise ValueError('The feedback file is empty')
    return list(by_id.values())


def observation_uses(rows):
    missing=[];usable=[];assumed=[]
    for r in rows:
        if r['point_type']=='interpolated' or r['point_type']=='unknown' or not r['uncertainty_ft']:
            missing.append(r['point_id'])
        elif r['basis']=='documented':
            usable.append(r['point_id'])
        elif r['basis']=='assumed':
            assumed.append(r['point_id'])
    return dict(documented=usable,assumed=assumed,unresolved=missing)


def event_spec(rows):
    blocked=[]
    q={r['flow_cfs'] for r in rows}
    boundary=[r for r in rows if r['role']=='boundary']
    if len(q)!=1 or not all(finite(v) and v>0 for v in q):blocked.append('EVENT_FLOW')
    if set(r['role'] for r in rows)>={'holdout','calibration'}:blocked.append('MIXED_EVENT_ROLES')
    if not boundary:blocked.append('BOUNDARY_OBSERVATION')
    controls={(r['stage_ft'],r['datum'],r['uncertainty_ft'],r['point_type'],r['basis']) for r in boundary}
    if len(controls)>1:blocked.append('CONFLICTING_CONTROLS')
    if boundary and (not boundary[0]['uncertainty_ft'] or boundary[0]['point_type']!='measured' or boundary[0]['basis']=='unknown'):
        blocked.append('BOUNDARY_ACCURACY')
    stages=[]
    if not blocked:
        b=boundary[0];z=b['stage_ft'];u=b['uncertainty_ft']
        stages=[dict(profile=name,stage_ft=stage) for name,stage in [('EventBase',z),('TailLow',z-u),('TailHigh',z+u)]]
    return dict(rows=rows,uses=observation_uses(rows),blockers=blocked,stages=stages,
                assumed=any(r['basis']=='assumed' for r in rows),flow_cfs=next(iter(q)) if len(q)==1 else None)


def exports(key,body):
    m=model_for(key,body); rows=rows_for(m)
    root=core.folder(key)/'field_followups'/'requests'/digest([m['summary'],rows])[:24]
    root.mkdir(parents=True,exist_ok=True)
    target=root/'Field_feedback.csv'
    target.write_bytes(csv_text(rows).encode('utf-8-sig'))
    from .revision_inputs import bound_inputs,station_key
    _,geom,_=bound_inputs(read(ROOT/m['summary']['path']))
    end=station_key(geom['cross_sections'][-1]['rs'])
    lines=[m['title'], 'Field records requested / 现场索资清单',
           f'Downstream / 下游 RS {end} · {geom["vertical_datum"]}',
           'Please supply event date, concurrent discharge, located stage, vertical control, uncertainty and its units.',
           '请提供事件日期、同期流量、带坐标的水位、垂直控制和有单位的测量不确定度。',
           'For an offsite gage, provide a dated, independently supported stage transfer to the model boundary.',
           '若使用异地测站，需提供有日期和独立依据的测站至模型边界水位传递关系。',
           'For each listed point identify the original measurement or interpolation and its field-record reference.',
           '请逐点区分实测或插值，并注明原始记录。']
    lines.extend(f"{r['event']} | {r['date']} | RS {r['rs']} | {r['role']} | {r['datum']} | {r['flow_cfs']:.2f} cfs | {r['original_source']}" for r in rows)
    path=root/'Field_request.txt';path.write_text('\n'.join(lines)+'\n',encoding='utf-8-sig')
    return dict(template=item(target),request=item(path),rows=rows)


def store_attachment(folder, attachment):
    name=Path(attachment['name'])
    if name.name!=str(name) or name.suffix.lower() not in ('.pdf','.txt','.csv','.png','.jpg','.jpeg'):
        raise ValueError('Choose a PDF, text, CSV or image field record')
    raw=base64.b64decode(attachment['data'],validate=True)
    if not 0<len(raw)<=12_000_000:raise ValueError('Use a field record up to 12 MB')
    p=folder/('Field_record'+name.suffix.lower());p.write_bytes(raw)
    return item(p)


def prepare(key,body):
    m=model_for(key,body);core.require_idle(m)
    if body.get('revision')!=m['revision']:raise ValueError('Reopen the current result')
    folder=core.folder(key)/'field_followups'/unique_id()
    from .survey_import import verified_sources
    identity=m['summary'];evidence=[identity,*verified_sources(m)];summary=read(ROOT/identity['path'])
    mode=body.get('mode')
    if mode=='event':
        all_rows=rows_for(m)
        if not all_rows:raise ValueError('Import located observations first. A nearby rating alone cannot provide a boundary.')
        previous=latest(m,'event',body.get('event'),body.get('date'))
        if previous and (previous['review']['event'],previous['review']['date'])==(body.get('event'),body.get('date')):
            retained={r['point_id']:r for r in previous['review']['rows']}
            all_rows=[retained.get(r['point_id'],r) for r in all_rows]
        rows=merge_feedback(all_rows,body['csv'])
        selected=[r for r in rows if (r['event'],r['date'])==(body.get('event'),body.get('date'))]
        if not selected:raise ValueError('Choose an event present in the template')
        packet=observation_table(m);evidence.extend([m['river_observations'],packet['source']])
        spec=event_spec(selected)
        from .revision_inputs import bound_inputs
        _,geometry,_=bound_inputs(summary)
        from .revision_inputs import station_key
        downstream=station_key(geometry['cross_sections'][-1]['rs'])
        if any(station_key(r['rs'])!=downstream for r in selected if r['role']=='boundary'):
            spec['blockers'].append('BOUNDARY_LOCATION')
        regime=geometry.get('flow_regime')
        if regime=='supercritical' or (regime=='mixed' and geometry.get('boundaries',{}).get('upstream',{}).get('type')=='known_stage'):
            spec['blockers'].append('UPSTREAM_EVENT_CONTROL')
        folder.mkdir(parents=True)
        document=None
        if body.get('attachment'):
            document=store_attachment(folder,body['attachment'])
        elif body.get('reuse_document'):
            prior=latest(m,'event',body['event'],body['date'])
            if prior and prior['token']==body['reuse_document'] and (prior['review']['event'],prior['review']['date'])==(body['event'],body['date']):
                document=prior['review'].get('supporting_record')
        if document:
            if not intact([document]):raise ValueError('Field document changed')
            evidence.append(document)
        if any(r['basis']=='documented' and r['point_type']!='unknown' for r in selected) and not document:
            raise ValueError('Attach the field record for the documented point identity or accuracy')
        spec['supporting_record']=document
        csv_path=folder/'Feedback.csv';csv_path.write_bytes(body['csv'].encode('utf-8-sig'));evidence.append(item(csv_path))
        spec.update(event=body['event'],date=body['date'])
    elif mode=='geometry':
        from .field_paths import decision
        spec,identity,refs=decision(key,body);evidence.extend(refs)
        folder.mkdir(parents=True)
    else:raise ValueError('Unknown field review type')
    from .assessment_area import current
    from .qa import verified_profiles
    area=current(m,verified_profiles(summary['hydraulics']))['selected']
    spec.update(mode=mode,parent=key,parent_summary=m['summary'],geometry_summary=identity,area=area,
                parent_observations=m.get('river_observations'),parent_comparison=m.get('latest_geometry_comparison'),area_record=m.get('assessment_area'),
                child='field_'+unique_id().lower(),sources=evidence,engineering_acceptance='NOT_ASSESSED')
    save(folder/'review.json',spec)
    ref=item(folder/'review.json')
    if mode=='event':save(folder.parent/'events'/(digest([spec['event'],spec['date']])+'.json'),ref)
    save(folder.parent/('latest_'+mode+'.json'),ref)
    return dict(review=spec,token=ref['sha256'])


def latest(m,mode,event=None,date=None):
    root=core.folder(m['id'])/'field_followups'
    path=root/('latest_'+mode+'.json')
    if mode=='event' and event and date:
        saved=root/'events'/(digest([event,date])+'.json')
        if saved.is_file():path=saved
    if not path.is_file():return None
    ref=read(path)
    if not intact([ref]):raise ValueError('Saved field review changed')
    spec=read(ROOT/ref['path'])
    if mode=='event' and event and (spec['event'],spec['date'])!=(event,date):return None
    if spec['parent_summary']!=m['summary'] or ('area_record' in spec and spec['area_record']!=m.get('assessment_area')):
        return None
    link='river_observations' if mode=='event' else 'latest_geometry_comparison'
    source_key='parent_observations' if mode=='event' else 'parent_comparison'
    if source_key in spec and spec[source_key]!=m.get(link):return None
    return dict(review=spec,token=ref['sha256'],source=ref)
