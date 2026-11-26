"""Project-page preview and explicit adoption of a field book and its source rows."""
import base64
import csv
import hashlib
import io
from pathlib import Path

from . import app_core as core
from . import field_return
from .app_parameters import objects
from .common import ROOT, digest, intact, item, lock, read, save
from .intake_boundary import documents, screen
from .intake_freeze import local
from .intake_register import context
from .raw_measurements import invert_rows, parse, stage_rows, suggestions
from .river_observations import COLUMNS, UNITS


def csv_bytes(columns, rows):
    stream=io.StringIO(newline='')
    writer=csv.DictWriter(stream,fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


def source_row(name, raw_hash, row, boundary):
    m=row['meta']
    return dict(profile=m['profile'],event=m['event'],date=m['date'],role='boundary' if boundary else 'holdout',
                kind='boundary_stage' if boundary else 'stage',x=row['x'],y=row['y'],elevation=row['value'],
                horizontal_crs=m['crs'],vertical_datum=m['datum'],unit=m['unit'],flow=m['flow'],
                flow_unit=m['flow_unit'],vertical_uncertainty=m['uncertainty'],
                source=f'{name} · row {row["line"]} · SHA-256 {raw_hash}')


def describe(model):
    ctx=context(model)
    evidence=screen(ctx,documents(ctx,local))
    return dict(profiles=ctx['profiles'],datum=ctx['geom'].get('vertical_datum'),crs=ctx['geom'].get('horizontal_crs'),
                stations=evidence['stations'],outlet=evidence['end_rs'],computed=bool(model.get('summary')),
                invert_fields=[f for f in ctx['fields'] if f['key'].endswith(('.us_invert_ft','.ds_invert_ft'))])


def action(key, body, operation):
    model=core.model(key)
    core.require_idle(model)
    if model['revision']!=body.get('revision') or model.get('native_review') or not model.get('session'):
        raise ValueError('Open the current workflow model with located geometry / 请打开有已定位几何的当前工作流模型')
    if operation=='inspect':return describe(model)
    sp,packet,draft,config,geom=objects(model)
    if model.get('summary'):
        from .revision_inputs import bound_inputs
        if not intact([model['summary']]):raise ValueError('Restore the original calculation / 请先恢复原始计算')
        config,geom,_=bound_inputs(read(ROOT/model['summary']['path']))
    elif model.get('active_project'):raise ValueError('Open an editable revision / 请打开可编辑修订版')
    profiles=next(s['profiles'] for s in config['scenarios'] if s['id']==model['scenario'])
    mode=body.get('mode')
    if mode not in ('stage','gage','invert') or (mode=='invert')!=(geom.get('model_type')!='river'):
        raise ValueError('Select the measurement type for this reach / 请选择与河段相符的测量类型')
    name=body.get('name','')
    if not isinstance(name,str) or not name or Path(name).name!=name or len(name)>220 or any(ord(ch)<32 for ch in name):
        raise ValueError('Invalid source name / 原始文件名无效')
    data=base64.b64decode(body.get('content',''),validate=True)
    gage_json=Path(name).suffix.lower() in ('.json','.geojson')
    if gage_json and mode=='invert':raise ValueError('Use a culvert invert table / 涵底请使用测量表')
    if gage_json:mode='gage'
    headers,mapping,raw=parse(data,name,body.get('columns',{}))
    defaults=suggestions(raw,mapping,name,profiles)
    from .raw_source_metadata import companion
    references=companion(model,name,mapping['level']) if mapping['level'] else []
    values={k:{r['values'][k] for r in references if k in r['values']} for k in ('unit','crs','datum')}
    for k,v in values.items():
        if len(v)==1 and not mapping[k]:defaults[k]=next(iter(v))
    if operation=='columns':return dict(headers=headers,mapping=mapping,suggestions=defaults,count=len(raw),references=references,gage_json=gage_json)
    settings=body.get('settings',{})
    if not isinstance(settings,dict) or not all(isinstance(v,(str,int,float)) for v in settings.values()):
        raise ValueError('Invalid survey metadata')
    if mode=='invert':
        rows,missing=invert_rows(raw,settings,geom,profiles);outside=[]
    else:
        rows,outside=stage_rows(raw,settings,geom,profiles,mapping,mode);missing=[]
    for r in rows:
        meta=r.get('meta') or r
        if any(v and (len(v)>1 or meta.get(k) not in v) for k,v in values.items()):r['issues'].append('SOURCE_METADATA_CONFLICT')
    role='invert' if mode=='invert' else 'interior' if model.get('summary') else 'outlet'
    selectable=[r for r in rows if r['role']==role and not r['issues'] and mode!='gage']
    raw_hash=hashlib.sha256(data).hexdigest()
    token=digest(dict(raw=raw_hash,name=name,edition=key,revision=model['revision'],draft=draft['revision'],
                      geometry=digest(geom),summary=model.get('summary'),mode=mode,settings=settings,
                      columns=mapping,companions=references,rows=selectable))
    cuts=[dict(rs=s['rs'],xy=s['cutline_xy']) for s in geom.get('cross_sections',[]) if s.get('cutline_xy')]
    if operation=='preview':
        display=[dict(r,value=None) if role=='outlet' and r['role']=='interior' else r for r in rows]
        return dict(rows=display,missing=missing,role=role,selectable=[r['line'] for r in selectable],
                    outside_count=len(outside),outside_sample=[r['line'] for r in outside[:10]],raw_count=len(raw),
                    cuts=cuts,token=token,sha256=raw_hash)
    if operation!='apply' or body.get('token')!=token or body.get('confirmed') is not True:
        raise ValueError('Refresh and confirm this preview / 请刷新并确认本次预览')
    selected=body.get('lines')
    if not isinstance(selected,list) or not selected or any(type(n)!=int for n in selected) or set(selected)-{r['line'] for r in selectable}:
        raise ValueError('Choose supported source rows / 请选择本次预览中可采用的原始行')
    used=[r for r in selectable if r['line'] in selected]
    if role!='invert' and len({r['rs'] for r in used})!=len(used):
        raise ValueError('Select one event and one observation per section / 每次仅采用一个事件，每断面一项')
    if role=='interior' and (body.get('independent') is not True or len({(r['meta']['event'],r['meta']['date'],r['meta']['profile']) for r in used})!=1):
        raise ValueError('Confirm these points were held out for one event / 请确认同一事件的这些内点未参与设边界或调参')
    if model.get('summary'):
        args=dict(id=key,revision=model['revision'],summary_hash=model['summary']['sha256'],
                  document=dict(name=name,data=body['content']))
        if mode=='invert':
            template=field_return.perform(key,args,'request')['csv']
            keyed={r['target']:r for r in used}
            output=[]
            for row in csv.DictReader(io.StringIO(template)):
                if row['field'] in keyed:
                    r=keyed[row['field']]
                    row.update(value=str(r['value_ft']),source=f'{name} · row {r["line"]}',evidence_class='reported')
                    output.append(row)
            args.update(mode='geometry',csv=csv_bytes(field_return.COLUMNS,output).decode())
        else:
            args.update(mode='observation',csv=csv_bytes(('profile',*COLUMNS),[source_row(name,raw_hash,r,False) for r in used]).decode())
        validated=field_return.perform(key,args,'preview')
        return field_return.perform(key,dict(args,token=validated['token'],confirmed=True),'apply')

    if role=='outlet':
        m=used[0]['meta']
        if len(profiles)!=1 or geom.get('flow_regime') not in ('mixed','subcritical'):
            raise ValueError('Direct outlet adoption requires one profile with an active downstream boundary / 出口采用需要单工况及有效下游边界')
        if m['uncertainty'] in (None,'') and (body.get('conditional') is not True or (model.get('production_scope') or {}).get('purpose') not in ('screening','review')):
            raise ValueError('Confirm screening use or supply survey uncertainty / 请明确确认初筛用途或补充实测精度')
        # Keep competing observations available for review on the original edition.
        ctx=context(model)
        if any(row.get('role')=='boundary' and row.get('profile')==m['profile']
               for row,ref in documents(ctx,local)['observations']):
            raise ValueError('This profile already has documented boundary observations. Compare them in the evidence register before replacing a control. / 已有边界观测，请在资料清单核对现用控制。')
    dest=core.folder(key)/'raw_measurements'/token
    dest.mkdir(parents=True,exist_ok=True)
    def member(filename,content):
        path=dest/filename
        if path.exists() and path.read_bytes()!=content:raise ValueError('Stored evidence changed')
        if not path.exists():path.write_bytes(content)
        return item(path,'raw_survey_evidence')
    original=member('FieldBook'+Path(name).suffix.lower(),data)
    refs=[original]
    changes={}
    if role=='outlet':
        r=used[0];obs=source_row(name,raw_hash,r,True);label=obs['source']
        point=member('SurveyedOutlet.csv',csv_bytes(('x','y','elevation'),[{k:obs[k] for k in ('x','y','elevation')}]))
        from json import dumps
        event=dict(profile=m['profile'],event=m['event'],date=m['date'],method='direct_outlet_survey',
                   point_source=label,source_sha256=point['sha256'],dataset_sha256=raw_hash,
                   horizontal_crs=m['crs'],vertical_datum=m['datum'],unit=m['unit'],
                   vertical_uncertainty=m['uncertainty'],accept_unquantified_for_screening=body.get('conditional') is True)
        refs.extend([point,member('intake_evidence.json',dumps(dict(schema='intake_evidence_1',events=[event])).encode()),
                     member('observed_profiles.csv',csv_bytes(('profile',*COLUMNS),[obs]))])
        changes={'g.boundaries.downstream.type':('known_stage',label),
                 'g.boundaries.downstream.stages_ft':([r['value']*UNITS[m['unit']]],label)}
    else:
        changes={r['target']:(r['value_ft'],f'{name} · row {r["line"]}') for r in used}
    with lock(sp.parent/'session.lock'):
        from . import intake
        _,_,_,fresh=intake._load(sp)
        if fresh['revision']!=draft['revision']:raise ValueError('Draft changed; preview again / 草稿有变，请重新预览')
        fresh['uploads'].extend(refs)
        for field,(value,basis) in changes.items():
            fresh['answers'][field]=dict(value=value,basis=basis,evidence_class='reported',confirmed=False,
                candidate_record=dict(value=value,basis=basis,sources=refs,source=original,evidence_class='reported'))
        fresh.update(consent=False,revision=fresh['revision']+1)
        intake._objects(packet,fresh)
        save(sp.parent/'draft.json',fresh)
    model.pop('pending_review',None)
    model['revision']+=1
    core.persist(model,'ADOPT_RAW_MEASUREMENTS',dict(source=original,fields=list(changes),lines=selected))
    return dict(id=key,fields=list(changes))
