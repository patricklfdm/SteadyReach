"""Single-user computation orchestration; no named engineering approvals.

All hydraulic operations reuse the inspected engine. Source copies, input
fingerprints, failed attempts and conditional assumptions remain on disk.
"""
import base64
import copy
import math
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from .common import ROOT, digest, finite, intact, item, lock, read, rel, safe_path, save, unique_id, utc

POLICY='local_computation_v1'
BASE=ROOT/'projects'
USER_SOURCE='Entered by the local user for this computation; not independently verified.'

def folder(key):
    from .common import identifier
    return BASE/identifier(key)

def edition_record(record):
    """Older editable revisions sometimes carried result pointers from their parent."""
    if not record.get('parent_revision'):
        return record
    def inherited(ref):
        path = ref.get('path', '') if isinstance(ref, dict) else ''
        parts = Path(path).parts
        return len(parts) > 2 and parts[0] == 'projects' and parts[1] != record['id']
    for field in ('river_observations', 'latest_observed_event', 'latest_geometry_comparison', 'latest_warning_study','extent_review','extent_decision'):
        if inherited(record.get(field)):
            record.pop(field)
    if 'observed_event_history' in record:
        record['observed_event_history'] = [r for r in record['observed_event_history'] if not inherited(r)]
    attempt = record.get('native_export_attempt') or {}
    if inherited(attempt.get('receipt')) or (attempt and not record.get('summary')):
        record.pop('native_export_attempt')
    return record


def model(key):
    return edition_record(read(folder(key)/'app.json'))

def deletion_record(key):
    return ROOT/'status/app/deleted_projects'/(folder(key).name+'.json')

def set_deleted(key,body,deleted):
    """Keep shared project artifacts and their hashes intact while hiding a project."""
    with lock(ROOT/'status/app/launch.lock'):
        m=model(key);record=deletion_record(key)
        if deleted:
            if body.get('confirmed') is not True:raise ValueError('Confirm deletion / 请确认删除项目')
            if record.exists():return dict(id=key,deleted=True)
            require_task_finished(m)
            if body.get('revision')!=m['revision']:raise ValueError('Project changed; refresh the list / 项目已变更，请刷新列表')
            save(record,dict(project_id=key,title=m['title'],deleted_utc=utc(),revision=m['revision']))
        else:
            record.unlink(missing_ok=True)
    return dict(id=key,deleted=deleted)

def persist(m,action=None,details=None):
    m['updated_utc']=utc()
    save(folder(m['id'])/'app.json',m)
    if action:save(folder(m['id'])/'events'/(unique_id()+'.json'),dict(action=action,created_utc=utc(),revision=m['revision'],details=details or {},engineering_acceptance='NOT_ASSESSED'))

def number(value,label,low=None,high=None):
    if value in (None,''):return None
    if isinstance(value,bool):raise ValueError(label+': enter a number')
    value=float(value)
    if not math.isfinite(value) or low is not None and value<=low or high is not None and value>=high:raise ValueError(label+': value outside valid range')
    return value

def create(body):
    from .inputs import template
    from .feasibility import scope
    project_scope = scope(body.get('production_scope', {}))
    title=str(body.get('title','')).strip()
    if not title or len(title)>160:raise ValueError('Enter a project name / 请填写项目名称')
    route=body.get('route','coordinates')
    survey=None
    if route == 'survey':
        from . import survey_import
        survey=survey_import.parse(body.get('survey_files'))
        body=dict(body,model_type='river',latitude=survey[0]['location']['latitude'],longitude=survey[0]['location']['longitude'],
                  flow_cfs=None,channel_n=None,overbank_n=None)
    if route not in ('coordinates','native','survey'):raise ValueError('Choose coordinates, surveyed river inputs, or an existing steady model')
    lat=number(body.get('latitude'),'Latitude',-90,90);lon=number(body.get('longitude'),'Longitude',-180,180)
    if (lat is None)!=(lon is None) or route=='coordinates' and lat is None:raise ValueError('Supply latitude and longitude / 请填写经纬度')
    model_type=body.get('model_type','culvert')
    if model_type not in ('culvert','river'):raise ValueError('Choose river or culvert analysis')
    if model_type=='river' and route=='native':raise ValueError('River mode currently starts from coordinates and reviewed sections')
    key='site_'+unique_id().lower();f=folder(key)
    c=template(key,lat if lat is not None else 0.,lon if lon is not None else 0.);c['title']=title;c['model_type']=model_type
    if lat is None:c['location']=None;c['terrain']={'mode':'not_applicable'}
    p=c['scenarios'][0]['profiles'][0]
    p['flow_cfs']=number(body.get('flow_cfs'),'Discharge',0)
    if p['flow_cfs'] is not None:p['source']=USER_SOURCE
    for k in ['channel_n','overbank_n']:
        c['scenarios'][0][k]=number(body.get(k),k,0,1)
    if any(c['scenarios'][0].get(k) is not None for k in ['channel_n','overbank_n']):c['scenarios'][0]['parameter_source']=USER_SOURCE
    archive=None
    if body.get('local_rasters'):
        from . import local_rasters
        if route not in ('coordinates','survey'):
            raise ValueError('Archived site rasters require a site location.')
        archive=local_rasters.validate(body['local_rasters'],body.get('dem_vertical_unit'),body.get('dem_vertical_datum'),lon,lat,imagery_only=route=='survey')
    f.mkdir(parents=True)
    if archive:
        local_rasters.install(f,c,archive,body.get('dem_vertical_unit'),body.get('dem_vertical_datum'))
    evidence=survey_import.install(f,c,survey) if survey else []
    save(f/'project.json',c);save(f/'initial.json',c)
    m=dict(id=key,title=title,model_type=model_type,route=route,revision=0,status='NEW',phase='CREATED',project=rel(f/'project.json'),
        scenario=c['scenarios'][0]['id'],created_utc=utc(),gis=bool(body.get('gis',lat is not None)),metadata={},attachments=evidence,
        engineering_acceptance='NOT_ASSESSED',policy=POLICY,errors=[], production_scope=project_scope)
    for k in ['native_length_unit','vertical_datum','horizontal_crs','dem_vertical_unit','dem_vertical_datum']:
        if body.get(k):m['metadata'][k]=str(body[k])
    persist(m,'CREATE',dict(initial_information=copy.deepcopy(c),route=route))
    return m

def native_inputs(key,body):
    from .native_review import prepare,inspect
    m=model(key);require_idle(m)
    selected=body.get('selected_plan') or None
    f=folder(key)/'imports'/unique_id()
    if body.get('files'):
        raw=f/'submitted';raw.mkdir(parents=True)
        for entry in body['files']:
            name=entry['name']
            if Path(name).name!=name or any(s in name for s in '/\\:'):raise ValueError('Plain filenames only')
            import re
            if not re.search(r'\.(prj|p\d\d|g\d\d|f\d\d)$',name,re.I):continue
            content=base64.b64decode(entry['content'],validate=True)
            if len(content)>15_000_000:raise ValueError('Native input file exceeds 15 MB')
            (raw/name).write_bytes(content)
        projects=list(raw.glob('*.prj'))
        if len(projects)!=1:raise ValueError('Select one project and its plan/geometry/steady-flow files')
        source=projects[0]
    else:
        source=Path(str(body.get('native_path',''))).expanduser().resolve()
        if not source.is_file() or source.suffix.lower()!='.prj':raise ValueError('Select an existing HEC-RAS .prj file')
    # Explicit plan supports projects whose saved Current Plan was not supplied.
    packet=prepare(source,f/'review',selected_plan=selected)
    m.update(native_review=rel(packet),revision=m['revision']+1,status='INPUTS_READY',errors=[])
    persist(m,'SELECT_NATIVE_INPUTS',dict(inspection=item(packet),source=str(source),selected_plan=read(packet)['selected_plan']))
    return view(key)

def task_alive(job):
    from .project_actions import process_alive
    pids={job.get('pid'),job.get('worker_pid')} - {None}
    return not pids or any(process_alive(pid) for pid in pids)

def require_task_finished(m):
    if m.get('task'):
        job=read(ROOT/m['task'])
        if job['status']=='RUNNING' and task_alive(job):
            raise ValueError('A task is running; wait for it to finish / 当前任务尚未结束')

def require_idle(m):
    if deletion_record(m['id']).exists():raise ValueError('Restore this project from Deleted projects first / 请先从回收站恢复此项目')
    require_task_finished(m)
    if m['status']=='ABANDONED':raise ValueError('Project abandoned; create a new project or explicitly resume')

def update(key,body):
    m=model(key);require_idle(m)
    if body.get('revision')!=m['revision']:raise ValueError('This page is stale; refresh to retain the saved draft')
    if 'production_scope' in body:
        from .feasibility import scope
        if m.get('active_project') or m.get('summary'):
            raise ValueError('Change the scope on an editable revision / 请在可编辑修订版修改用途')
        m['production_scope'] = scope(body['production_scope'])
    allowed={'native_length_unit','vertical_datum','horizontal_crs','dem_vertical_unit','dem_vertical_datum'}
    values=body.get('metadata',{})
    if set(values)-allowed:raise ValueError('Unknown metadata fields')
    for k,v in values.items():m['metadata'][k]=str(v).strip()
    if 'gis' in body:m['gis']=bool(body['gis'])
    if 'values' in body:
        from . import intake
        if not m.get('session'):raise ValueError('Prepare terrain/inputs before editing')
        sp=ROOT/m['session'];_,_,p,d=intake._load(sp);c,g=intake._objects(p,d)
        allowed_fields={v['key']:v for v in intake.fields(c,g,m['scenario'])}
        classes=body.get('classes',{})
        if set(classes)-set(allowed_fields) or any(v not in ('user_entered','reported','assumed') for v in classes.values()):raise ValueError('Invalid input origin')
        for key0,value in body['values'].items():
            if key0 not in allowed_fields:raise ValueError('Unknown model field: '+key0)
            previous=d['answers'].get(key0,{})
            classification=classes.get(key0,previous.get('evidence_class','user_entered'))
            if key0 not in classes and classification in ('inferred','derived','terrain_derived'):
                classification='assumed'
            if classification not in ('reported','assumed'):classification='user_entered'
            # Editing a candidate never silently turns it into a measurement.
            answer=dict(value=value,evidence_class=classification,basis=USER_SOURCE,confirmed=False)
            if previous:answer['previous_origin']={k:previous[k] for k in ('evidence_class','basis','candidate_record') if k in previous}
            if classification=='assumed':answer['basis']='User-selected conditional assumption; not a measured site value.'
            d['answers'][key0]=answer
        # Provenance strings are generated by the app, never called measurements.
        for f in intake.fields(c,g,m['scenario']):
            if f['key'].endswith(('.source','.parameter_source')) and not d['answers'].get(f['key'],{}).get('value') and not f['value']:
                d['answers'][f['key']]=dict(value=USER_SOURCE,evidence_class='user_entered',basis=USER_SOURCE,confirmed=False)
        d.update(reviewer=None,basis='Local user requested computation using the displayed inputs; no engineering review asserted.')
        # Explicit section edits are allowed, but must stop claiming unmodified DEM samples.
        spatial_keys=('cutline_xy','station_ft','elevation_ft','center_xy')
        affected={int(k.split('.')[2]) for k in body['values'] if k.startswith('g.cross_sections.') and k.split('.')[-1] in spatial_keys}
        with lock(sp.parent/'session.lock'):
            if read(sp.parent/'draft.json')['revision']!=d['revision']:raise ValueError('Draft changed; reload')
            for index in affected:
                row=d['geometry']['cross_sections'][index]
                if row.get('terrain_sampling'):
                    row.setdefault('previous_terrain_sampling',[]).append(row.pop('terrain_sampling'))
                    row['sampling_status']='USER_EDITED_NOT_DEM_MEASUREMENT'
                row.pop('terrain_review',None)
            intake._objects(p,d)
            d['revision']+=1;save(sp.parent/'events'/(unique_id()+'.json'),dict(action='SAVE_INPUTS',draft=d));save(sp.parent/'draft.json',d)
    m['revision']+=1;persist(m,'SAVE_INPUTS',dict(metadata=values,fields=list(body.get('values',{}))))
    return view(m['id'])

def use_native_values(key,body):
    """An explicit conflict resolution; old coordinates/values remain preserved."""
    m=model(key);require_idle(m)
    if body.get('revision')!=m['revision'] or body.get('use_native') is not True:raise ValueError('Confirm using the displayed native parameters')
    if not m.get('native_review'):raise ValueError('Read a native model first')
    old=ROOT/m['project'];c=read(old)
    before=copy.deepcopy(c['scenarios'])
    for scenario in c['scenarios']:
        for p in scenario['profiles']:p.update(flow_cfs=None,source=None)
        for k in ['channel_n','overbank_n','culvert_n','parameter_source']:scenario[k]=None
    target=folder(key)/'parameter_choices'/unique_id()/'project.json';save(target,c)
    receipt=target.parent/'choice.json';save(receipt,dict(action='USE_NATIVE_VALUES',previous=item(old),previous_values=before,
        native_inspection=item(ROOT/m['native_review']),new_configuration=item(target),created_utc=utc(),engineering_review='NOT_PERFORMED'))
    m.setdefault('input_choices',[]).append(item(receipt));m.update(project=rel(target),revision=m['revision']+1)
    persist(m,'RESOLVE_NATIVE_CONFLICT',dict(choice=item(receipt)));return view(key)

def use_candidate(key,body):
    from . import app_parameters
    m=model(key);require_idle(m)
    if body.get('revision')!=m['revision']:raise ValueError('Inputs changed; refresh before selecting a candidate')
    return app_parameters.choose(m,body.get('selections') or [dict(field=body.get('field'),candidate=body.get('candidate'))],body.get('missing_only',False))

def prepare(key):
    from . import intake,inputs,terrain,terrain_metadata
    m=model(key);f=folder(key);cp=ROOT/m['project'];c=read(cp)
    if not m.get('session'):
        s=intake.prepare(cp,m['scenario']);m['session']=s['session'];persist(m)
    # A download retry must not replace a partly completed engineering draft.
    sp=ROOT/m['session'];_,_,packet,draft=intake._load(sp,active=False)
    if read(sp).get('status')!='APPLIED':
        config,geometry=intake._objects(packet,draft)
        changed=False
        for field in intake.fields(config,geometry,m['scenario']):
            if field['key'].endswith(('.source','.parameter_source')) and not field['value']:
                draft['answers'][field['key']]=dict(value=USER_SOURCE,evidence_class='user_entered',basis=USER_SOURCE,confirmed=False);changed=True
        if changed:
            draft.update(reviewer=None,basis='Local computation inputs; no engineering review asserted.')
            intake.save_draft(sp,draft)
    if not c.get('location'):
        m.update(status='INPUTS_READY',phase='SUPPLY_MISSING_INPUTS',errors=[]);persist(m);return
    # One checkpoint; transient failures can retry without losing the draft.
    old=m.get('terrain')
    if old and old.get('raster') and intact([old['raster']]):
        m.update(status='INPUTS_READY',phase='SUPPLY_MISSING_INPUTS',errors=[]);persist(m);return
    dest=f/'preparation'/unique_id();dest.mkdir(parents=True)
    if m.get('model_type') == 'river' and c['terrain'].get('mode') == 'usgs' and not m.get('map_picks', {}).get('river'):
        from .public_reach import discover
        m['phase']='Finding river bends and crossing limits / 正在查询河道弯点及道路交叉位置'
        persist(m)
        entry=discover(c['location'], dest/'public_reach')
        candidate=read(ROOT/entry['path'])
        m['public_reach']=entry
        if candidate['status'] in ('CANDIDATE','CHOOSE_REACH'):
            c=copy.deepcopy(c)
            c['terrain']['buffer_m']=max(c['terrain']['buffer_m'],candidate['buffer_m'])
        persist(m,'PUBLIC_REACH_SEARCH',dict(candidate=entry,status=candidate['status']))
    from .app_acquisition import progress
    t=terrain.acquire(cp,c,dest/'terrain',progress=lambda label:progress(m,label));m['terrain']=t
    records=[]
    try:
        if t.get('products'):records=terrain_metadata.fetch_products(dest/'terrain/terrain.json',dest/'metadata')
    except Exception as e:m['metadata_error']=str(e)
    checkpoint=dict(terrain=t,metadata=dict(products=records,review_status='NOT_ENGINEERING_REVIEWED'),created_utc=utc())
    save((ROOT/m['session']).parent/'terrain_checkpoint.json',checkpoint)
    candidate=terrain_metadata.review_candidate(records) if records else {}
    m['terrain_metadata']=candidate
    if candidate.get('status')=='CANDIDATE_REQUIRES_REVIEW':
        m['metadata'].setdefault('dem_vertical_unit',candidate['unit']);m['metadata'].setdefault('dem_vertical_datum',candidate['datum'])
    m.update(status='INPUTS_READY',phase='SUPPLY_MISSING_INPUTS',errors=[]);persist(m,'TERRAIN_READY',dict(raster=t.get('raster'),metadata_candidate=candidate))

def native_preview(m):
    if not m.get('native_review'):return None
    from .native_context import reconcile
    p=read(ROOT/m['native_review']);c=read(ROOT/m['project']);errors=[]
    try:matches=reconcile(p,c,m['scenario'])
    except ValueError as e:matches=[];errors.append(str(e))
    return dict(plan=p['selected_plan'],saved_plan=p.get('previous_current_plan'),title=p['plan_title'],regime=p['regime'],
        profiles=p['profiles'],sections=p['sections'],structure=p['expected_native'],boundaries=p['boundaries'],
        source_files=p['files'],prior_flow_matches=matches,conflicts=errors)

def check(m):
    errors=[];meta=m['metadata']
    if m.get('native_review'):
        p=native_preview(m);errors.extend(p['conflicts'])
        if meta.get('native_length_unit') not in ('international ft','US survey foot'):errors.append('Choose the native foot convention / 请选择原生英尺定义')
        if not meta.get('vertical_datum'):errors.append('Supply model elevation datum / 请补充模型高程基准')
        if m['gis']:
            if not m.get('terrain',{}).get('raster'):errors.append('GIS needs available DEM; retry terrain or disable GIS / GIS 需有效地形')
            try:
                from pyproj import CRS
                if not CRS.from_user_input(meta.get('horizontal_crs')).is_projected:raise ValueError()
            except Exception:errors.append('Supply the native projected CRS / 请补充原生模型投影坐标系')
            if meta.get('dem_vertical_unit') not in ('m','US survey foot','international foot'):errors.append('Supply DEM elevation unit / 请补充 DEM 高程单位')
            if not meta.get('dem_vertical_datum') or meta.get('dem_vertical_datum','').casefold()!=meta.get('vertical_datum','').casefold():errors.append('Model and DEM elevation datums must match / 模型与 DEM 高程基准须一致')
    elif m.get('session'):
        from . import intake
        sp=ROOT/m['session'];_,_,p,d=intake._load(sp,active=False);c,g=intake._objects(p,d)
        labels={f['key']:f['label'] for f in intake.fields(c,g,m['scenario'])}
        for e in intake.validate(sp,require_consent=False,direct_start=True)['errors']:
            label=labels.get(e['field'],{})
            errors.append((label.get('en','')+' / '+label.get('zh','')+': ' if label else '')+e['en']+' / '+e['zh'])
    else:errors.append('Prepare inputs first / 请先准备输入')
    return errors

def start(key,body):
    m=model(key)
    if body.get('start') is not True:raise ValueError('An explicit Start action is required')
    if body.get('confirmed') is not True:raise ValueError('Confirm the complete parameter list / 请确认完整参数清单')
    if body.get('revision')!=m['revision']:raise ValueError('Inputs changed; refresh before starting')
    # A network retry after a lost HTTP response reopens the same attempt,
    # including after completion. A new parameter review issues a new token.
    pointer=m.get('task')
    if pointer and body.get('review_token') and not deletion_record(key).exists():
        last=read(safe_path(ROOT,pointer))
        if (last.get('project_id')==key and last.get('action')=='run' and
            last.get('confirmed_review')==body['review_token'] and last.get('status') in ('RUNNING','FINISHED')):
            if last['status']=='FINISHED' or task_alive(last):
                return dict(id=key,status=m['status'],task=pointer,reused_request=True)
    return launch(key,'run',run_review=body.get('review_token'))

def compile_native(m):
    from . import native_review,intake
    p=ROOT/m['native_review'];packet=read(p);meta=m['metadata'];c=read(ROOT/m['project'])
    review=dict(project_id=m['id'],title=m['title'],source='User-selected native input files: '+', '.join(Path(x['path']).name for x in packet['files'].values())+'. Original geometry and flow retained; not independently verified.',
        native_length_unit=meta['native_length_unit'],vertical_datum=meta['vertical_datum'],approve=True,
        run_action='START_CONDITIONAL_COMPUTATION',engineering_review='NOT_PERFORMED')
    context=None
    if m['gis']:
        t=m['terrain'];provenance=(ROOT/t['raster']['path']).parent/'terrain.json'
        if not provenance.exists():raise ValueError('Terrain provenance is missing')
        review['mapping']=dict(confirmed=True,horizontal_crs=meta['horizontal_crs'],dem_vertical_unit=meta['dem_vertical_unit'],
            dem_vertical_datum=meta['dem_vertical_datum'],basis='Metadata displayed with the model and accepted by the local Start action; CRS/realization not independently verified.',contour_interval=2.)
        context=dict(configuration=c,scenario_id=m['scenario'],sources=[item(ROOT/m['project']),item(folder(m['id'])/'initial.json'),item(provenance),t['raster']]+m.get('input_choices',[])+m.get('attachments',[]),
            terrain=dict(raster=t['raster'],provenance=item(provenance)))
    else:
        from .native_context import reconcile
        reconcile(packet,c,m['scenario'])
    # Every run request gets its own normalized working copy and receipt.
    fresh=folder(m['id'])/'compiled'/unique_id()
    copied=native_review.prepare(ROOT/packet['files']['project']['path'],fresh,selected_plan=packet['selected_plan'])
    review['production_scope'] = m.get('production_scope', {})
    cp=native_review.approve(copied,review,context,direct_start=True)
    if not context:
        # Default native scenario is baseline, preserving every original profile.
        m['run_scenario']='baseline'
    else:m['run_scenario']=m['scenario']
    return cp

def run(key):
    from . import intake
    from . import app_parameters
    app_parameters.verify_execution(model(key))
    m=model(key);errors=check(m)
    if errors:raise ValueError('\n'.join(errors))
    if m.get('native_review'):cp=compile_native(m)
    else:
        sp=ROOT/m['session'];d=read(sp.parent/'draft.json')
        # Carry original attachments and the exact final confirmation into the report source chain.
        d['uploads']+=m.get('attachments',[])+[m['run_confirmation'],m['pending_review']]
        if m.get('road_sample'):d['uploads'].append(m['road_sample'])
        if m.get('source_analysis'):d['uploads'].append(m['source_analysis'])
        save(sp.parent/'draft.json',d)
        result=intake.apply(ROOT/m['session'],d['revision'],direct_start=True,mapping_enabled=m['gis'],
                            production_scope=m.get('production_scope'))
        if result['status']!='APPLIED':raise ValueError(str(result['errors']))
        cp=ROOT/result['project'];m['run_scenario']=m['scenario']
    from .calculation_recovery import seal
    m['compiled_checkpoint']=seal(m,cp)
    m['active_project']=rel(cp);m['phase']='HEC_RAS_REPORTS_DELIVERY';persist(m)
    execute_approved(m,cp,fresh=True)

def execute_approved(m,cp,*,fresh):
    from . import cli
    key=m['id']
    code=cli.execute(cp,m['run_scenario'],fresh=fresh,timeout=240)
    state=read(cp.parent/'state.json');m['engine_state']=rel(cp.parent/'state.json');m['summary']=state.get('latest_summary')
    m.pop('exports_need_refresh',None)
    m.pop('native_export_attempt',None)
    m['status']='RESULTS_READY' if state.get('calculation_status')=='COMPUTED' else 'NEEDS_ATTENTION'
    m['errors']=state.get('errors',[]);m['phase']='DONE';m['exit_code']=code
    if (state.get('delivery') or {}).get('status')=='INCOMPLETE':m['status']='RESULTS_READY_MAP_PENDING'
    persist(m,'FINISHED',dict(calculation=state.get('calculation_status'),exit_code=code,summary=m.get('summary')))
    if state.get('calculation_status')=='COMPUTED':
        # Preview only. Additional native computation keeps its separate consent.
        try:
            from .app_next_review import execute
            execute(key)
        except Exception:
            traceback.print_exc()  # Preserve the completed solver/export outcome.

class ActiveProjectJob(ValueError):
    """A project draft may be saved while the local worker is occupied."""


def launch(key,action,*,run_review=None):
    if action not in ('prepare','run','resume-run','report','delivery','acquire','analyze','study','catalog','native-export','automatic-prepare','check-batch','next-review','field-run'):raise ValueError('Unknown task')
    global_state=ROOT/'status/app/active.json'
    with lock(ROOT/'status/app/launch.lock'):
        m=model(key);require_idle(m)
        if global_state.exists():
            previous=read(global_state)
            if previous.get('record') and (ROOT/previous['record']).exists():
                prev=read(ROOT/previous['record'])
                if prev['status']=='RUNNING' and task_alive(prev):raise ActiveProjectJob('Another project is processing; keep this draft and wait')
        if action=='run':
            from . import app_parameters
            app_parameters.confirm(m,run_review)
            persist(m,'START_REQUEST',dict(policy=POLICY,metadata=m['metadata'],gis=m['gis'],revision=m['revision'],named_engineering_review=False))
        f=folder(key)/'tasks'/unique_id();f.mkdir(parents=True)
        record=f/'task.json';job=dict(project_id=key,action=action,status='RUNNING',started_utc=utc(),log=rel(f/'task.log'))
        if action=='resume-run':job['resume_of']=m.get('task')
        if action=='run' and m.get('pending_review'):job['confirmed_review']=m['pending_review']['sha256']
        save(record,job)
        with (f/'task.log').open('wb') as log:
            process=subprocess.Popen([sys.executable,str(ROOT/'app.py'),'worker',rel(record)],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        job['pid']=process.pid;save(record,job);save(global_state,dict(record=rel(record)))
        m.update(task=rel(record),status='PROCESSING',phase=action.upper());persist(m)
    return dict(id=key,status='PROCESSING',task=rel(record))

def worker(record):
    path=safe_path(ROOT,record);job=read(path);key=job['project_id'];started=time.monotonic()
    # Parent publishes its PID and model task pointer before the worker proceeds.
    for _ in range(100):
        if model(key).get('task')==rel(path) and read(path).get('pid'):break
        time.sleep(.05)
    else:
        job=read(path)
        job.update(status='INTERRUPTED',finished_utc=utc(),error='Task publication was interrupted. Reopen the saved project and retry. / 任务登记中断，请重新打开已保存项目并重试。')
        save(path,job)
        return 1
    # A Windows virtual-environment launcher may have a different PID from
    # its actual Python worker. Retain both identities for owned substeps.
    job=read(path);job['worker_pid']=os.getpid();save(path,job)
    try:
        with lock(ROOT/'status/app/execution.lock'):
            if job['action']=='prepare':
                try:prepare(key)
                finally:
                    from .app_acquisition import analyze
                    prepared=model(key)
                    if prepared.get('session') and prepared.get('route')!='survey':
                        analyze(key,network=not prepared.get('source_analysis'))
            elif job['action'] in ('acquire','analyze'):
                from .app_acquisition import analyze
                analyze(key,network=job['action']=='acquire')
                updated=model(key)
                if job['action']=='acquire' and updated.get('public_reach') and updated.get('terrain') and not updated.get('map_picks',{}).get('river'):
                    from .terrain_extent_auto import ensure
                    extent=ensure(updated)
                    updated=model(key)
                    updated['reach_terrain_check']=extent
                    persist(updated,'RECHECK_DISCOVERED_REACH_COVERAGE',extent)
            elif job['action']=='catalog':
                from .app_catalog import acquire as acquire_catalog
                acquire_catalog(key)
            elif job['action']=='field-run':
                from .field_followup import execute
                execute(key)
            elif job['action']=='study':
                from .app_study import execute as execute_study
                execute_study(key)
            elif job['action']=='check-batch':
                from .app_check_batch import execute
                execute(key)
            elif job['action']=='automatic-prepare':
                from .app_autoprepare import execute
                execute(key)
            elif job['action']=='next-review':
                from .app_next_review import execute
                execute(key)
            elif job['action']=='run':run(key)
            elif job['action']=='resume-run':
                from .calculation_recovery import execute
                execute(key)
            elif job['action']=='native-export':
                from .app_outputs import retry
                retry(key)
            else:regenerate(key,job['action'])
        job['status']='FINISHED'
    except Exception as e:
        traceback.print_exc();job.update(status='FAILED',error=str(e));m=model(key)
        if job['action']=='delivery':
            from .site_delivery import failure_kind
            job['recovery_kind']=failure_kind(e)
        m.update(status='NEEDS_ATTENTION',errors=[str(e)]);persist(m,'TASK_FAILED',dict(error=str(e)))
    job.update(finished_utc=utc(),elapsed_seconds=round(time.monotonic()-started,3));save(path,job)
    return 0 if job['status']=='FINISHED' else 1

def report_refresh_binding(m):
    binding={key:m.get(key) for key in ('summary','latest_study','latest_spacing','latest_coverage','latest_coverage_exports')}
    for key in ('river_observations','observed_event_history','latest_geometry_comparison','latest_warning_study','extent_review','extent_decision'):
        if m.get(key):binding[key]=m[key]
    return binding


def current_refreshed_reports(m):
    return bool(m.get('latest_reports') and m.get('latest_reports_binding')==report_refresh_binding(m))


def regenerate(key,action):
    if action not in ('report','delivery'):raise ValueError('Unknown report action')
    m=model(key)
    if not m.get('summary') or not intact([m['summary']]):raise ValueError('No intact calculation summary available')
    out=folder(key)/'exports'/unique_id();summary=ROOT/m['summary']['path']
    from .report import generate as report_generate
    # Recollect completed studies and native supplements for every explicit refresh.
    # Persist the report first so a later mapping failure is recoverable.
    report_generate(summary,out/'reports');m['latest_reports']=rel(out/'reports')
    m['latest_reports_binding']=report_refresh_binding(m)
    previous=m.get('latest_delivery') or m.get('previous_delivery') or (read(ROOT/m['engine_state']).get('delivery') if m.get('engine_state') else None)
    m['previous_delivery']=previous
    m['exports_need_refresh']=True;m.pop('latest_delivery',None)
    persist(m,'REPORT_REFRESHED')
    if action=='delivery':
        from .site_delivery import generate
        reuse=(previous or {}).get('complete',{}).get('path') if (previous or {}).get('mapped') else None
        result=generate(summary,out/'delivery',reuse_package=reuse);m['latest_delivery']=result
        if result.get('status') in ('READY_FOR_REVIEW','READY_NATIVE_ONLY','READY'):m['exports_need_refresh']=False
        else:
            message=result.get('error') or 'Delivery is incomplete. The original calculation and refreshed reports remain available.'
            m.update(status='RESULTS_READY_MAP_PENDING',phase='DONE',errors=[message]);persist(m,'DELIVERY_INCOMPLETE')
            return
    m.update(status='RESULTS_READY',phase='DONE',errors=[]);persist(m,'REGENERATE_'+action.upper())

def view(key,detail=True):
    m=model(key);result=copy.deepcopy(m)
    if detail and deletion_record(key).exists():raise ValueError('Restore this project from Deleted projects first / 请先从回收站恢复此项目')
    if m.get('task'):
        task=read(ROOT/m['task']);result['job']=task
        if task['status']=='RUNNING':
            if not task_alive(task):result.update(status='INTERRUPTED',errors=['The worker stopped; saved inputs and outputs remain. Retry the task. / 后台进程已停止。输入与已有结果已保留，可重试。'])
            else:result['status']='PROCESSING'
    if not detail:return result
    parent=result.get('parent_revision') or {}
    if (parent.get('project_id') and 'inherited_sources' not in parent
            and not m.get('active_project') and not m.get('native_review') and m.get('model_type')!='river'):
        parent_file=folder(parent['project_id'])/'app.json'
        if parent_file.is_file():
            parent['inherited_sources']=[r['sha256'] for r in read(parent_file).get('attachments',[])]
    if m.get('public_reach') and intact([m['public_reach']]):
        result['reach_proposal']=read(ROOT/m['public_reach']['path'])
    if m.get('active_check_batch'):
        from .app_check_batch import progress
        result['check_batch_progress']=progress(m)
    if result.get('job',{}).get('action') in ('study','check-batch') and m.get('active_study'):
        active=m['active_study'];plan=read(ROOT/active['study']['path'])
        journal_path=(ROOT/active['study']['path']).parent/'execution.json'
        records={};journal={}
        if journal_path.exists():
            journal=read(journal_path)
            if journal['study']!=active['study'] or journal['review']!=active['review']:raise ValueError('Study progress identity changed')
            records={row['id']:row for row in journal['cases']}
        cases=plan['cases']
        waiting='QUEUED'
        if plan.get('analysis_kind')=='native_warning_review':
            cases=[dict(id=f'trial_{i:02d}') for i in range(1,plan['policy']['maximum_rounds']+1)]
            if journal.get('stop'):waiting='SKIPPED'
        if plan.get('analysis_kind')=='coverage_repair':
            cases=[dict(id='repair_'+str(i)) for i in range(1,plan['policy']['maximum_rounds']+1)]
            prepared={case['id']:case for case in journal.get('prepared_cases',[])}
            cases=[prepared.get(case['id'],case) for case in cases]
            if journal.get('status') not in (None,'IN_PROGRESS'):waiting='SKIPPED'
        result['study_progress']=[dict(id=case['id'],section_count=case.get('section_count'),
            parameter_path=(case.get('changes') or [{}])[0].get('path'),
            parameter_value=(case.get('changes') or [{}])[0].get('after'),
            status=records.get(case['id'],{}).get('status',waiting),error=records.get(case['id'],{}).get('error')) for case in cases]
        if plan.get('coverage_policy'):
            from .spacing_cycle import progress
            result['study_progress'] = progress(ROOT/active['study']['path'], plan, active['review'])
    # Substeps may persist INPUTS_READY while the encompassing task is still
    # running. Keep polling and avoid expensive draft reads during mutations.
    if result['status']=='PROCESSING':
        result.update(missing=[],native=None)
        return result
    if (result.get('job',{}).get('action') in ('run','resume-run') and
            (result['status'] in ('INTERRUPTED','NEEDS_ATTENTION') or result.get('job',{}).get('status') in ('FAILED','INTERRUPTED'))):
        from .calculation_recovery import inspect
        result['calculation_recovery']=inspect(m)
    if m.get('catalog_attempt') and intact([m['catalog_attempt']]):result['catalog_result']=read(ROOT/m['catalog_attempt']['path'])
    if m.get('latest_study') and intact([m['latest_study']]):result['study_result']=read(ROOT/m['latest_study']['path'])
    if m.get('sensitivity_suggestions'):
        from .sensitivity_ranges import current as current_ranges
        result['suggested_sensitivity']=current_ranges(m)
    if m.get('river_observations'):
        from .river_observations import current as current_observations
        result['observation_review']=current_observations(m)
        result['observed_events']=[]
        for ref in m.get('observed_event_history',[]):
            if not intact([ref]):continue
            event=read(ROOT/ref['path'])
            if result['observation_review'] and event.get('baseline')==m['summary'] and event['observations']==result['observation_review']['source'] and intact([event['study'],event['review'],event['execution'],event['summary']]):
                result['observed_events'].append(event)
    if m.get('latest_geometry_comparison') and intact([m['latest_geometry_comparison']]):
        comparison=read(ROOT/m['latest_geometry_comparison']['path'])
        evidence=[comparison['study'],comparison['review']]+list(comparison.get('summaries',{}).values())
        if comparison.get('table'):evidence.append(comparison['table'])
        if comparison.get('summaries',{}).get('baseline')==m.get('summary') and intact(evidence):
            result['geometry_comparison']=comparison
    if m.get('latest_warning_study') and intact([m['latest_warning_study']]):
        warning_study=read(ROOT/m['latest_warning_study']['path'])
        if warning_study['baseline']==m.get('summary') and intact([warning_study['study'],warning_study['review'],warning_study['execution']]+[c['audit'] for c in warning_study['cases']]):
            result['warning_study']=warning_study
    if m.get('latest_spacing') and intact([m['latest_spacing']]):result['spacing_result']=read(ROOT/m['latest_spacing']['path'])
    if m.get('latest_coverage') and intact([m['latest_coverage']]):result['coverage_result']=read(ROOT/m['latest_coverage']['path'])
    if m.get('latest_coverage_exports') and intact([m['latest_coverage_exports']]):
        exports=read(ROOT/m['latest_coverage_exports']['path'])
        if exports['analysis']==m.get('latest_coverage'):result['coverage_exports']=exports
    if m.get('automatic_next_review'):
        from .app_next_review import current as next_review
        result['next_review']=next_review(m)
    if m.get('pending_check_batch'):
        from .app_check_batch import preview
        result['check_batch_preview']=preview(m['pending_check_batch'])
    if m.get('pending_study') and intact([m['pending_study']]):
        plan=read(ROOT/m['pending_study']['path']);result['pending_study_plan']=plan
        if plan.get('analysis_kind')=='coverage_repair' and intact([plan['initial_preview']]):
            result['coverage_preview']=read(ROOT/plan['initial_preview']['path'])
    if m.get('automatic_preparation') and intact([m['automatic_preparation']]):
        result['preparation_result']=read(ROOT/m['automatic_preparation']['path'])
    result['native']=native_preview(m)
    from .app_acquisition import snapshot
    if m.get('source_analysis'):result['acquisition']=snapshot(m)
    feasibility_inputs = None
    if m.get('session') and not m.get('native_review') and not m.get('active_project'):
        from . import intake
        result['intake']=intake.view(ROOT/m['session'])
        from .app_parameters import attention, rows, objects
        context = objects(m)
        result['intake']['fields']=rows(m, context)
        feasibility_inputs = (context[3], context[4], context[2]['answers'])
        if result.get('preparation_result'):
            result['intake']['current_attention'] = attention(m, result['intake']['fields'])
        from .app_automation import view as automation_view
        result['automation']=automation_view(m,context[4])
        result['intake']['check']=intake.validate(ROOT/m['session'],require_consent=False,direct_start=True)
    if not m.get('active_project') and not m.get('summary'):
        from .feasibility import assess
        if feasibility_inputs is None:
            feasibility_inputs = (read(ROOT/m['project']), {}, {})
        result['feasibility'] = assess(m, *feasibility_inputs, result.get('acquisition'), result['native'], result.get('reach_proposal'))
    result['missing']=check(m) if m['status'] not in ('PROCESSING','ABANDONED') and not m.get('active_project') else []
    if m.get('summary') and intact([m['summary']]):
        s=read(ROOT/m['summary']['path']);h=s.get('hydraulics') or {}
        result['automatic_native_outputs']=m.get('native_export_attempt') or s.get('automatic_native_outputs')
        result['results']=dict(calculation=s['calculation_status'],run_id=h.get('run_id'),solver_reused=s['solver_reused'],hydraulic_qa=h.get('hydraulic_qa_status'),
            diagnostics=read(ROOT/h['diagnostics']['path']) if h.get('diagnostics') and intact([h['diagnostics']]) else None,
            metrics=h.get('profiles'),flow_regime=h.get('flow_regime'),boundaries=h.get('boundaries'),engineering_acceptance='NOT_ASSESSED')
        jobdir=(ROOT/m['summary']['path']).parent
        reports=ROOT/m.get('latest_reports',rel(jobdir/'reports'))
        result['report_files']=[dict(name=p.name,path=rel(p)) for p in reports.glob('*') if p.suffix in ('.pdf','.docx')]
        delivery=m.get('latest_delivery') or (read(ROOT/m['engine_state']).get('delivery') if m.get('engine_state') else None)
        result['delivery']=delivery
        from .app_revision import compare
        result['comparison']=compare(m,s)
        from .iteration_choice import latest as iteration_choice
        result['iteration_choice']=iteration_choice(m)
        if s['configuration'].get('field_feedback'):
            from .field_results import collect as field_results
            result['field_response']=field_results(s)[0]
        if s.get('native_supplement'):
            from .app_outputs import validate as validate_outputs,diagnostics as supplemented_qa
            try:
                result['native_supplement']=validate_outputs(s['native_supplement'])
                result['results']['diagnostics']=supplemented_qa(h,result['native_supplement'])
            except (OSError,KeyError,ValueError) as error:
                result['results']['diagnostics']=None
                result['errors']=[*result.get('errors',[]),'Native evidence: '+str(error)]
        if m.get('exports_need_refresh'):
            if not current_refreshed_reports(m):result['report_files']=[]
            result['delivery']=None
            task=result.get('job',{})
            if task.get('action')=='delivery' and task.get('status')=='FAILED':
                result['delivery']=dict(status='INCOMPLETE',error=task.get('error','Delivery export failed'),recovery_kind=task.get('recovery_kind'))

    return result

def listing(deleted=False):
    projects=[]
    paths=[*BASE.glob('site_*/app.json'),*BASE.glob('field_*/app.json')]
    for path in sorted(paths,reverse=True):
        key=path.parent.name
        if deletion_record(key).exists()==deleted:
            projects.append(model(key) if deleted else view(key,False))
    return projects

def attach(key,files):
    from .app_acquisition import add_file
    m=model(key);require_idle(m)
    if len(files)>100:raise ValueError('Choose at most 100 source files')
    for f in files:
        name=f['name']
        if Path(name).name!=name or any(c in name for c in '/\\:'):raise ValueError('Plain filenames only')
        raw=base64.b64decode(f['content'],validate=True)
        add_file(m,name,raw)
    m['revision']+=1;persist(m,'ADD_SOURCE_MATERIALS',dict(count=len(files)))
    return launch(key,'analyze') if m.get('session') and not m.get('native_review') and not m.get('active_project') else view(key)


def abandon(key):
    m=model(key);require_idle(m);m.update(status='ABANDONED',revision=m['revision']+1)
    persist(m,'ABANDON',dict(retained='Inputs, sources, results'));return view(key)
