"""Compare a field return with a sealed run and create a separate editable edition."""
import base64
import copy
import csv
import hashlib
import io
import json
from pathlib import Path

from . import app_core as core
from .common import ROOT, digest, finite, intact, item, lock, read, save, unique_id
from .revision_inputs import bound_inputs
from .river_observations import datum

COLUMNS=('field','location','value','unit','datum','evidence_class','source','prior','station_axis_ft','request_summary')


def targets(geom, scenario):
    result={}
    def add(key,location,prior,axis=None,count=None):
        result[key]=dict(location=location,prior=prior,axis=axis,count=count)
    for i,g in enumerate((geom.get('structure') or {}).get('groups',[])):
        for name,side in [('us_invert_ft','inlet'),('ds_invert_ft','outlet')]:
            add(f'g.structure.groups.{i}.{name}',f'Group {i+1} · {side}',g.get(name))
    road=(geom.get('structure') or {}).get('road',{})
    for field,axis in [('elevation_ft','station_ft'),('downstream_elevation_ft','downstream_station_ft')]:
        if road.get(axis) and road.get(field):
            add('g.structure.road.'+field,field,road[field],road[axis],len(road[axis]))
    if geom.get('model_type')=='river':
        for i,s in enumerate(geom['cross_sections']):
            add(f'g.cross_sections.{i}.elevation_ft','RS '+str(s['rs']),s['elevation_ft'],s['station_ft'],len(s['station_ft']))
        if geom['flow_regime'] in ('mixed','subcritical'):
            profiles=[p['id'] for p in scenario['profiles']]
            add('g.boundaries.downstream.stages_ft','Downstream · '+', '.join(profiles),
                geom['boundaries']['downstream'].get('stages_ft'),count=len(profiles))
    return result


def context(key,body):
    m=core.model(key);core.require_idle(m)
    if m.get('native_review') or not m.get('summary') or m['summary']['sha256']!=body.get('summary_hash') or not intact([m['summary']]):
        raise ValueError('Reopen the calculated workflow edition / 请打开对应的已计算版本')
    s=read(ROOT/m['summary']['path'])
    c,g,_=bound_inputs(s)
    scenario=next(v for v in c['scenarios'] if v['id']==m['scenario'])
    return m,s,g,targets(g,scenario)


def worksheet(m,g,fields):
    out=io.StringIO(newline='');writer=csv.DictWriter(out,fieldnames=COLUMNS);writer.writeheader()
    for key,r in fields.items():
        writer.writerow(dict(field=key,location=r['location'],value='',unit='ft',datum=g['vertical_datum'],
            evidence_class='reported',source='',prior=json.dumps(r['prior']),station_axis_ft=json.dumps(r['axis']),request_summary=m['summary']['sha256']))
    return out.getvalue()


def changes(content,fields,g,summary_hash,documented):
    reader=csv.DictReader(io.StringIO(content.lstrip('\ufeff')))
    if tuple(reader.fieldnames or ())!=COLUMNS:
        raise ValueError('Use the field-return worksheet columns / 请使用本页导出的补测表')
    seen=set();result=[]
    for raw in reader:
        if None in raw or None in raw.values():raise ValueError('Malformed worksheet row')
        k=raw['field']
        if k in seen or k not in fields or raw['request_summary']!=summary_hash:
            raise ValueError('Unknown, repeated or stale field / 字段重复或来自其他版本')
        seen.add(k);row=fields[k]
        if json.loads(raw['station_axis_ft'])!=row['axis'] or json.loads(raw['prior'])!=row['prior'] or raw['location']!=row['location']:
            raise ValueError('Location or previous geometry changed / 原断面、站距或原值已改变')
        if not raw['value'].strip():continue
        if raw['unit'].strip()!='ft' or not datum(g['vertical_datum']) or datum(raw['datum'])!=datum(g['vertical_datum']) or datum(raw['datum']) in ('UNKNOWN','LOCAL','UNREVIEWED'):
            raise ValueError(row['location']+' · supply ft in '+g['vertical_datum']+' / 请先核对单位与高程基准')
        kind=raw['evidence_class'].strip()
        if kind not in ('reported','assumed') or not raw['source'].strip() or (kind=='reported' and not documented):
            raise ValueError(row['location']+' · supply a source record or identify the assumption / 请附测量原件或标注假设')
        value=json.loads(raw['value'])
        if row['count'] is None:
            valid=finite(value)
        else:
            valid=isinstance(value,list) and len(value)==row['count'] and all(finite(x) for x in value)
        if not valid:raise ValueError(row['location']+' · values must match the listed station or profile order / 数值须与原站距或工况逐项对应')
        result.append(dict(key=k,location=row['location'],before=row['prior'],after=value,unit='ft',datum=g['vertical_datum'],
                           classification=kind,source=raw['source'].strip()))
    if not result:raise ValueError('The return has no filled values / 回传表没有填写数值')
    return result


def record_bytes(document):
    if not document:return None
    name=Path(document['name'])
    if name.name!=str(name) or name.suffix.lower() not in ('.pdf','.txt','.json','.csv','.tsv','.jpg','.jpeg','.png'):
        raise ValueError('Choose a field PDF, text, JSON, CSV or photograph')
    data=base64.b64decode(document['data'],validate=True)
    if not 0<len(data)<=12_000_000:raise ValueError('Field source must be under 12 MB')
    return data


def perform(key,body,action):
    m,s,g,fields=context(key,body)
    if action=='request':return dict(csv=worksheet(m,g,fields))
    content=body.get('csv')
    if not isinstance(content,str) or not 0<len(content)<=2_000_000:raise ValueError('Choose a UTF-8 CSV under 2 MB')
    document=body.get('document');data=record_bytes(document);mode=body.get('mode')
    summary_hash=m['summary']['sha256']
    if mode=='geometry':
        rows=changes(content,fields,g,summary_hash,data is not None)
        if any(r['key']=='g.boundaries.downstream.stages_ft' for r in rows) and g['boundaries']['downstream']['type']!='known_stage':
            rows.append(dict(key='g.boundaries.downstream.type',location='Downstream boundary',before=g['boundaries']['downstream']['type'],
                after='known_stage',unit='',datum='',classification='model_setting',source='Apply the returned downstream stage for each listed profile.'))
        from .inputs import geometry_errors
        from .intake import _set
        prospective=copy.deepcopy(g)
        for change in rows:
            _set(prospective,change['key'].split('.')[1:],change['after'])
        introduced=set(geometry_errors(prospective))-set(geometry_errors(g))
        if introduced:
            raise ValueError('Returned geometry / 回传几何：'+' · '.join(sorted(introduced)))
    elif mode=='observation' and g.get('model_type')=='river' and data is not None:
        from .survey_events import merge_holdouts,profile_rows,records
        existing=records(s)[0]
        observed=profile_rows(content,s)
        identities={(r['profile'],r['event'],(r.get('location') or {}).get('rs')) for r in observed}
        if len(identities)!=len(observed) or not observed or any(r['issues'] or r['role']!='holdout' or r['kind'] not in ('stage','gage_height') or
                               r['residual_ft'] is None for r in observed):
            raise ValueError('Check event, profile, station, discharge, independent role and datum / 请核对事件、断面、流量、独立性与基准')
        merge_holdouts(existing,observed)
        prior={(r['profile'],(r.get('location') or {}).get('rs')):r for r in existing}
        rows=[]
        for r in observed:
            old=prior.get((r['profile'],r['location']['rs']),{})
            rows.append(dict(key=r['profile'],location=r['event']+' · RS '+r['location']['rs'],
                        before=old.get('observed_ft'),after=r['observed_ft'],prior_uncertainty_ft=old.get('uncertainty_ft'),
                        uncertainty_ft=r['uncertainty_ft'],unit='ft',datum=r['observed_datum'],classification='reported',source=r['source']))
    else:raise ValueError('Choose a supported return and attach the field original / 请选回传类型并附原件')
    token=digest(dict(project=key,revision=m['revision'],summary=summary_hash,mode=mode,rows=rows,csv=content,
                      document=hashlib.sha256(data).hexdigest() if data else None,filename=document['name'] if document else None))
    untouched=[v['location'] for k,v in fields.items() if k not in {r['key'] for r in rows}]
    preview=dict(rows=rows,token=token,other_fields=untouched if mode=='geometry' else [],run=s['hydraulics']['run_id'])
    if action=='preview':return preview
    if action!='apply' or body.get('token')!=token or body.get('confirmed') is not True:
        raise ValueError('Review the current return before creating a revision / 请复核当前回传预览')
    directory=core.folder(key)/'field_returns'/token[:24]
    with lock(directory/'apply.lock'):
        if core.model(key)['revision']!=m['revision']:raise ValueError('Project changed; preview again')
        pointer=directory/'child.json'
        if pointer.exists():
            child=read(pointer)['id']
            if (core.folder(child)/'app.json').is_file():return dict(id=child)
        path=directory/('observed_profiles.csv' if mode=='observation' else 'Field_values.csv')
        path.write_bytes(content.encode('utf-8-sig'))
        source=item(path,'returned_observations' if mode=='observation' else 'field_worksheet')
        sources=[source]
        if data:
            record=directory/('Original'+Path(document['name']).suffix.lower());record.write_bytes(data)
            sources.append(item(record,'field_original'))
        child='site_'+unique_id().lower();save(pointer,dict(id=child))
        from .app_revision import create_draft
        return dict(id=create_draft(m,{},field_return=dict(id=child,mode=mode,rows=rows,sources=sources))['id'])


def apply_to_draft(config,draft,returned):
    refs=returned['sources']
    draft['uploads']=list(draft.get('uploads',[]))+refs
    config['field_return_sources']=list({r['path']:r for r in [*config.get('field_return_sources',[]),*refs]}.values())
    if returned['mode']=='observation':
        config['returned_observations']=[*config.get('returned_observations',[]),refs[0]]
        config['returned_observation_originals']=[*config.get('returned_observation_originals',[]),*refs[1:]]
        return
    for r in returned['rows']:
        source=refs[-1];basis=r['source']
        candidate=dict(value=r['after'],evidence_class=r['classification'],source=source,datum=r['datum'],basis=basis,sources=refs)
        draft['answers'][r['key']]=dict(value=r['after'],evidence_class=r['classification'],basis=basis,confirmed=False,candidate_record=candidate)
