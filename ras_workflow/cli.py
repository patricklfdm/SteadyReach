import argparse, shutil, sys, traceback
from pathlib import Path
from .common import *
from . import inputs, native, terrain, results, report, ras_terrain

def stage(state,path,name,key,action,fresh=False):
    old=state['stages'].get(name)
    if not fresh and old and old.get('key')==key and old.get('status')=='READY' and intact(old['artifacts']):
        print(name+': REUSED_VERIFIED '+old['evidence_dir'],flush=True)
        return old['result']
    dest=path/name;dest.mkdir(parents=True,exist_ok=False)
    record=dict(status='IN_PROGRESS',started_at_utc=utc(),key=key,evidence_dir=rel(dest))
    if old:
        state.setdefault('stage_history',[]).append(dict(stage=name,**old))
    state['stages'][name]=record;save(path.parent.parent/'state.json',state)
    try:
        record['result']=action(dest);record['status']='READY'
    except Exception as e:
        record.update(status='FAILED',error=str(e));(dest/'traceback.txt').write_text(traceback.format_exc(),encoding='utf-8');raise
    finally:
        record['finished_at_utc']=utc();record['artifacts']=[item(p) for p in sorted(dest.rglob('*')) if p.is_file()]
        save(path.parent.parent/'state.json',state)
        print(name+': '+record['status'],flush=True)
    return record['result']

def solve(dest,path,c,s,g,engine,attempt,timeout,native_terrain=None):
    from .run_source import freeze
    code=code_identity()
    code_archive=freeze(code)
    snapshots=dest/'inputs_before';snapshots.mkdir()
    dep=inputs.dependencies(path,c)
    for d in dep:
        p=ROOT/d['path'];target=snapshots/d['path'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    project,expected=native.import_native(dest/'project',path,c) if c.get('native_project') else native.build(dest/'project',c,s,g)
    native_before=[]
    for p in project.parent.iterdir():
        target=dest/'native_before'/p.name;target.parent.mkdir(exist_ok=True);shutil.copyfile(p,target);native_before.append(item(target,'native_input_before'))
    request=dict(run_id=attempt,case_kind=c['case_kind'],project=rel(project),engine=engine,expected=expected,profiles=s['profiles'])
    if native_terrain:
        nt=dest/'Terrain';nt.mkdir()
        for entry in native_terrain['files']:shutil.copyfile(ROOT/entry['path'],nt/Path(entry['path']).name)
        request['native_terrain']=rel(nt/Path(native_terrain['hdf']).name)
    save(dest/'request.json',request)
    rec=native.run_isolated(dest/'request.json',timeout)
    hyd=results.extract(project,expected,c,s,attempt,dest)
    if code!=code_identity():raise ValueError('Workflow code changed while calculating. Run the frozen inputs again with a consistent version.')
    receipt=dict(run_id=attempt,source_inputs=dep,native_before=native_before,
        input_snapshots=[item(p,'input_snapshot') for p in snapshots.rglob('*') if p.is_file()],
        native_after=[item(p,'native_after') for p in project.parent.iterdir() if p.suffix.lower() in ['.prj','.g01','.f01','.p01']],
        outputs=[item(p,'raw_solver_output') for p in project.parent.iterdir() if p.suffix.lower() in ['.hdf','.o01','.r01','.txt','.json','.log']],
        code=code,code_archive=code_archive,engine=engine,execution=rec,engineering_acceptance='NOT_ASSESSED')
    save(dest/'manifest.json',receipt)
    return hyd

def execute(path,scenario_id,fresh=False,timeout=180,receipt_path=None):
    from . import intake
    requested=safe_path(ROOT,path);path=intake.resolve(requested)
    path,c=inputs.load(path);base=path.parent
    s=next((v for v in c['scenarios'] if v['id']==scenario_id),None)
    if s is None:raise ValueError('Unknown scenario: '+scenario_id)
    with lock(base/'project.lock'):
        state=read(base/'state.json') if (base/'state.json').exists() else dict(project_id=c['project_id'],stages={})
        attempt=unique_id();folder=base/'jobs'/attempt;folder.mkdir(parents=True)
        save(folder/'configuration.json',c)
        state['latest_attempt']=rel(folder);state['status']='IN_PROGRESS';save(base/'state.json',state)
        errors=[];hyd=None;t={};engine={};nt=None;session=None
        active=intake.control(path);cancelled=bool(active and active['status']=='CANCELLED')
        gate,g=inputs.gate(path,c,s)
        try:inputs.dependencies(path,c)
        except (OSError,ValueError) as e:
            gate.update(status='BLOCKED',input_adequacy_status='INCOMPLETE');gate['blocking_items'].append(str(e))
        if cancelled:gate.update(status='BLOCKED',blocking_items=['User cancelled this workflow; use intake --refresh to begin another review.'])
        elif active and active['status']==intake.WAITING:
            session=intake.prepare(path,active['scenario'])
            gate.update(status='BLOCKED');gate['blocking_items'].append('Input review is pending; complete it or explicitly cancel before calculation.')
        elif gate['status']=='BLOCKED':session=intake.prepare(path,scenario_id)
        save(folder/'input_gate.json',gate)
        try:
            engine=native.discover() if not cancelled else dict(status='NOT_STARTED');save(folder/'environment.json',engine)
        except Exception as e:engine=dict(status='BLOCKED',error=str(e));save(folder/'environment.json',engine)
        # Terrain remains independent of missing structure and solver capabilities.
        try:
            missing_terrain=[k for k in ['raster','provenance'] if c['terrain'].get('mode')=='local' and (not c['terrain'].get(k) or not safe_path(base,c['terrain'][k]).is_file())]
            if cancelled:t=dict(status='NOT_STARTED')
            elif missing_terrain:t=dict(status='WAITING_FOR_INPUT',missing_files=missing_terrain)
            else:
                terrain_key=digest(dict(terrain=c['terrain'],location=c.get('location'),code=sha(ROOT/'ras_workflow/terrain.py'),
                    local_inputs=[item(safe_path(base,c['terrain'][k])) for k in ['raster','provenance'] if c['terrain'].get(k)]))
                t=stage(state,folder,'terrain',terrain_key,lambda d:terrain.acquire(path,c,d))
        except Exception as e:t=dict(status='FAILED',error=str(e));errors.append('Terrain: '+str(e))
        metadata={}
        if t.get('products') and not cancelled:
            try:
                from .terrain_metadata import fetch_products
                terrain_record=ROOT/state['stages']['terrain']['evidence_dir']/'terrain.json'
                metadata=stage(state,folder,'terrain_metadata',digest([item(terrain_record),sha(ROOT/'ras_workflow/terrain_metadata.py')]),
                    lambda d:dict(products=fetch_products(terrain_record,d/'products'),review_status='UNREVIEWED'))
            except Exception as e:
                metadata=dict(status='MANUAL_METADATA_REVIEW_REQUIRED',error=str(e))
                print('Metadata: review required / 元数据需复核: '+str(e),flush=True)
        if session and not cancelled:
            save((ROOT/session['session']).parent/'terrain_checkpoint.json',dict(terrain=t,metadata=metadata,created_utc=utc()))
        if c.get('section_workflow') and session and not cancelled:
            try:
                from .geometry_workflow import seed
                geometry_checkpoint=seed(session['session'],path,c,t,folder/'section_workflow')
                save(folder/'geometry_checkpoint.json',geometry_checkpoint)
                save((ROOT/session['session']).parent/'geometry_checkpoint.json',geometry_checkpoint)
                print('Geometry: '+geometry_checkpoint['status'],flush=True)
            except Exception as e:
                # Candidate-generation problems remain actionable at the intake
                # checkpoint, with the exact error retained, never a fake pass.
                save(folder/'geometry_checkpoint.json',dict(status='WAITING_FOR_INPUT',error=str(e)))
                save((ROOT/session['session']).parent/'geometry_checkpoint.json',dict(status='WAITING_FOR_INPUT',error=str(e)))
                print('Geometry: WAITING_FOR_INPUT '+str(e),flush=True)
        terrain_metadata_ready=c['terrain'].get('vertical_unit') in ['m','US survey foot','international foot'] and c['terrain'].get('vertical_datum') not in [None,'','unknown','unreviewed']
        if c['terrain'].get('create_native') and terrain_metadata_ready and t.get('status')=='READY_WITH_LIMITATIONS' and engine.get('status')=='READY':
            try:nt=stage(state,folder,'native_terrain',digest([terrain_key,sha(ROOT/'ras_workflow/ras_terrain.py'),engine['selected']]),lambda d:ras_terrain.create(path,c,engine,d))
            except Exception as e:errors.append('Native terrain: '+str(e))
        if gate['status']=='READY_CONDITIONAL' and engine.get('status')=='READY':
            try:
                # DEM download failure does not block a reviewed native benchmark or explicit XS data.
                identity=dict(configuration=c,scenario=s,dependencies=inputs.dependencies(path,c),code=code_identity(),
                    engine=engine['selected'],engine_dependencies=engine['executables'],runtime=engine['runtime'])
                hyd=stage(state,folder,'solver__'+s['id'],digest(identity),lambda d:solve(d,path,c,s,g,engine,attempt,timeout,nt),fresh)
            except Exception as e:errors.append('Solver: '+str(e))
        elif engine.get('status')!='READY' and not cancelled:errors.extend(engine.get('blocking_items',[engine.get('error','Engine unavailable')]))
        summary=dict(schema_version='1.0',attempt_id=attempt,finished_at_utc=utc(),configuration=c,gate=gate,
            calculation_status='COMPUTED' if hyd else ('BLOCKED' if gate['status']=='BLOCKED' or engine.get('status')!='READY' else 'FAILED'),
            terrain=t,terrain_metadata=metadata,native_terrain=nt,hydraulics=hyd,errors=list(errors),
            solver_reused=bool(hyd and hyd['run_id']!=attempt),engineering_acceptance_status='NOT_ASSESSED')
        summary['workflow_status']='CANCELLED' if cancelled else intake.WAITING if session else 'COMPLETED' if hyd and not errors else 'FAILED'
        summary['review_status']='WAITING_FOR_QA_REVIEW' if hyd else 'NOT_STARTED'
        target_status=summary['workflow_status']
        summary['status_scope']='CALCULATION_CHECKPOINT_BEFORE_REPORT; final workflow status is in attempt_receipt.json'
        if target_status=='COMPLETED':summary['workflow_status']='REPORT_PENDING'
        if session:summary['intake']=dict(session=session['session'],packet=session['packet'],resume_project=rel(requested),scenario=session['scenario'])
        if hyd:summary['hydraulic_results']=item((ROOT/hyd['raw_hdf']['path']).parent.parent/'hydraulic_results.json')
        if hyd:
            from .app_outputs import attach_automatic
            execution=read((ROOT/hyd['raw_hdf']['path']).parent.parent/'execution.json')
            attach_automatic(summary,folder/'native_outputs',execution.get('native_export'),execution.get('native_export_error'))
            print('Native outputs: '+summary['automatic_native_outputs']['status'],flush=True)
        save(folder/'summary.json',summary)
        try:report.generate(folder/'summary.json',folder/'reports')
        except Exception as e:errors.append('Report: '+str(e));save(folder/'report_error.json',dict(error=str(e),traceback=traceback.format_exc()))
        delivery_result=None
        if hyd and (folder/'reports/report_manifest.json').exists() and c.get('delivery',{}).get('enabled',True):
            from .site_delivery import generate as generate_delivery
            try:delivery_result=generate_delivery(folder/'summary.json',folder/'delivery')
            except Exception as e:
                delivery_result=dict(status='INCOMPLETE',error=str(e),output=rel(folder/'delivery'))
                save(folder/'delivery_error.json',dict(**delivery_result,traceback=traceback.format_exc()))
            print('Delivery: '+delivery_result['status'],flush=True)
        # Summary is immutable after report authoring; report failure lives in state.
        try:current_inputs=inputs.dependencies(path,c)
        except Exception as e:
            current_inputs=[item(path)]
            if gate['status']!='BLOCKED':errors.append('Incomplete input inventory: '+str(e))
        terminal=target_status if not errors or session or cancelled else 'FAILED'
        if terminal=='COMPLETED' and delivery_result and delivery_result['status']=='INCOMPLETE':terminal='WAITING_FOR_DELIVERY_REVIEW'
        state.update(status=terminal,workflow_status=terminal,calculation_status=summary['calculation_status'],errors=errors,latest_summary=item(folder/'summary.json'),latest_attempt=rel(folder),updated_at_utc=utc(),
            review_status=summary['review_status'],
            current_input_manifest=current_inputs,current_code_manifest=code_identity())
        state['delivery']=delivery_result
        save(base/'state.json',state)
        # A per-attempt receipt survives later runs of the same project/scenario.
        # Reports and the solver stage are hashed before another queue job can run.
        artifacts=[item(p) for p in sorted(folder.rglob('*')) if p.is_file()]
        if hyd:
            solver_folder=(ROOT/hyd['raw_hdf']['path']).parent.parent
            if not solver_folder.is_relative_to(folder):
                artifacts.extend(item(p) for p in sorted(solver_folder.rglob('*')) if p.is_file())
        receipt=dict(schema_version='1.0',attempt_id=attempt,project=rel(path),requested_project=rel(requested),scenario_id=scenario_id,
            summary=item(folder/'summary.json'),artifacts=artifacts,
            inputs=current_inputs,code=code_identity(),errors=errors,
            calculation_status=summary['calculation_status'],workflow_status=terminal,solver_reused=summary['solver_reused'],
            report_status='GENERATED_PENDING_VISUAL_REVIEW' if (folder/'reports/report_manifest.json').exists() else 'FAILED',
            delivery=delivery_result,
            created_utc=utc(),engineering_acceptance='NOT_ASSESSED')
        save(folder/'attempt_receipt.json',receipt)
        if receipt_path:save(safe_path(ROOT,receipt_path),receipt)
        if requested!=path:save(requested.parent/'state.json',dict(**state,active_project=rel(path)))
        if hyd:
            from .project_home import register
            register(path,folder/'summary.json')
        (base/'STATUS.md').write_text('# '+c['title']+'\n\n'+state['status']+'\n\nSummary: '+rel(folder/'summary.json')+'\n\n'+('\n'.join(gate['blocking_items']+errors))+'\n\nEngineering acceptance: NOT_ASSESSED.\n',encoding='utf-8')
        print(json.dumps(dict(status=state['status'],summary=rel(folder/'summary.json'),reports=rel(folder/'reports'),errors=errors),ensure_ascii=False,indent=2))
        if hyd:print('WAITING_FOR_QA_REVIEW: workflow.py project-open --project "'+rel(requested)+'"',flush=True)
        if cancelled:return 4
        return 3 if terminal=='WAITING_FOR_DELIVERY_REVIEW' else 0 if hyd and not errors else 3 if session and not errors else 1


def run_with_intake(project,scenario,fresh=False,timeout=180,interactive=False,no_browser=False):
    from . import intake
    path=intake.resolve(project);session=intake.control(path)
    if session and session['status']=='CANCELLED':
        print('CANCELLED: use intake --refresh for an explicit new review.');return 4
    code=execute(project,scenario,fresh,timeout)
    path=intake.resolve(project);session=intake.control(path)
    if not session or session['status']!=intake.WAITING:return code
    print('WAITING_FOR_INPUT: .\\.venv\\Scripts\\python.exe workflow.py intake --project "'+rel(path)+'" --scenario '+session['scenario'],flush=True)
    if not interactive:return code
    from .intake_server import serve
    outcome=serve(session['session'],not no_browser)
    if outcome['status']=='APPLIED':return execute(project,scenario,fresh,timeout)
    return 4 if outcome['status']=='CANCELLED' else 3

def verify(path):
    path,c=inputs.load(path);state=read(path.parent/'state.json');checks=[]
    checks.append(dict(check='latest_summary',passed=intact([state['latest_summary']])))
    checks.append(dict(check='current_inputs_still_match',passed=intact(state.get('current_input_manifest',[]))))
    checks.append(dict(check='current_code_still_matches',passed=intact(state.get('current_code_manifest',[]))))
    for name,s in state['stages'].items():
        checks.append(dict(check=name+'_artifacts',stage_status=s['status'],passed=intact(s.get('artifacts',[]))))
    summary=read(ROOT/state['latest_summary']['path']);hyd=summary.get('hydraulics')
    if hyd:
        checks.extend([dict(check='real_hdf',passed=intact([hyd['raw_hdf']])),dict(check='controller',passed=intact([hyd['raw_controller']]))])
    manifest=ROOT/state['latest_attempt']/'reports/report_manifest.json'
    if manifest.exists():
        m=read(manifest);checks.append(dict(check='report_source',passed=intact([m['summary']])))
        checks.append(dict(check='report_files',passed=intact([x[k] for x in m['reports'] for k in ['docx','pdf']])))
        if m.get('supplementary_sources'):
            checks.append(dict(check='report_supplement_sources',passed=intact(m['supplementary_sources'])))
        visual=m['visual_review']
    else:checks.append(dict(check='report_manifest',passed=False));visual='NOT_AVAILABLE'
    result=dict(status='PASS_INTEGRITY_ONLY' if all(v['passed'] for v in checks) else 'FAILED',checks=checks,
        computation=summary['calculation_status'],visual_review=visual,hydraulic_qa='REVIEW_REQUIRED' if hyd else 'NOT_STARTED',engineering_acceptance='NOT_ASSESSED')
    save(path.parent/'verification.json',result);print(json.dumps(result,indent=2));return 0 if result['status']=='PASS_INTEGRITY_ONLY' else 1

def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser(description='Windows native HEC-RAS evidence workflow')
    sub=p.add_subparsers(dest='command',required=True)
    z=sub.add_parser('start',help='Local start page: new site, imported model, example or saved projects');z.add_argument('--terminal',action='store_true');z.add_argument('--no-browser',action='store_true')
    z=sub.add_parser('native-import',help='Inspect native steady inputs and review without writing configuration JSON')
    selection=z.add_mutually_exclusive_group(required=True);selection.add_argument('--source');selection.add_argument('--review')
    z.add_argument('--output');z.add_argument('--prepare-only',action='store_true')
    z.add_argument('--browser',action='store_true');z.add_argument('--no-browser',action='store_true')
    z=sub.add_parser('native-import-approve',help='Apply an explicit decision to a saved native import preview')
    z.add_argument('--review',required=True);z.add_argument('--decision',required=True)
    ini=sub.add_parser('init');ini.add_argument('--id',required=True);ini.add_argument('--lat',type=float,required=True);ini.add_argument('--lon',type=float,required=True)
    run=sub.add_parser('run');run.add_argument('--project',required=True);run.add_argument('--scenario',default='q100');run.add_argument('--fresh',action='store_true');run.add_argument('--timeout',type=int,default=180)
    mode=run.add_mutually_exclusive_group();mode.add_argument('--interactive',action='store_true');mode.add_argument('--non-interactive',action='store_true')
    run.add_argument('--no-browser',action='store_true')
    run.add_argument('--review',action='store_true',help='After successful calculation/report, open the local QA checkpoint')
    z=sub.add_parser('intake',help='Open/save/resume the missing-input wizard');z.add_argument('--project',required=True);z.add_argument('--scenario',default='q100');z.add_argument('--refresh',action='store_true');z.add_argument('--no-browser',action='store_true');z.add_argument('--prepare-only',action='store_true');z.add_argument('--no-resume',action='store_true')
    for name in ['status','verify']:
        z=sub.add_parser(name);z.add_argument('--project',required=True)
    z=sub.add_parser('sections');z.add_argument('--project',required=True);z.add_argument('--alignment',required=True)
    z=sub.add_parser('compare');z.add_argument('--baseline',required=True);z.add_argument('--candidate',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('qa');z.add_argument('--summary',required=True);z.add_argument('--warnings');z.add_argument('--output',required=True)
    z=sub.add_parser('warnings-import');z.add_argument('--summary',required=True);z.add_argument('--export',required=True);z.add_argument('--selection',required=True);z.add_argument('--output',required=True);z.add_argument('--encoding',default='utf-8-sig')
    z=sub.add_parser('culvert-details-import');z.add_argument('--summary',required=True);z.add_argument('--selection',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('culvert-details-prepare');z.add_argument('--summary',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('variant');z.add_argument('--project',required=True);z.add_argument('--spec',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('benchmark-prepare');z.add_argument('--recipe',required=True);z.add_argument('--output',required=True);z.add_argument('--fetch',action='store_true')
    z=sub.add_parser('public-case-prepare');z.add_argument('--recipe',required=True);z.add_argument('--output',required=True);z.add_argument('--fetch',action='store_true')
    z=sub.add_parser('public-case-compare');z.add_argument('--recipe',required=True);z.add_argument('--summary',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('benchmark-compare');z.add_argument('--recipe',required=True);z.add_argument('--summary',required=True);z.add_argument('--output',required=True);z.add_argument('--reference-review')
    z=sub.add_parser('terrain-metadata');z.add_argument('--raster',required=True);z.add_argument('--xml',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('geometry-screen');z.add_argument('--geometry',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('terrain-reference',help='Compare DEM samples against source section elevations without editing either');z.add_argument('--project',required=True);z.add_argument('--geometry',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('banks-evaluate');z.add_argument('--geometry',required=True);z.add_argument('--reference',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('investigation-prepare');z.add_argument('--packet',required=True);z.add_argument('--project',required=True);z.add_argument('--scenario',required=True);z.add_argument('--spec',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('investigation-analyze');z.add_argument('--investigation',required=True);z.add_argument('--review',required=True)
    z=sub.add_parser('metadata-fetch');z.add_argument('--terrain-result',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('evidence-extract');z.add_argument('--source',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('parameter-candidates');z.add_argument('--evidence',required=True);z.add_argument('--spec',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('hydrology-import');z.add_argument('--evidence',required=True);z.add_argument('--project',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('alignment-candidates');z.add_argument('--project',required=True);z.add_argument('--spec',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('review-template');z.add_argument('--candidates',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('source-review');z.add_argument('--candidates',required=True);z.add_argument('--spec',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('study-prepare');z.add_argument('--project',required=True);z.add_argument('--scenario',required=True);z.add_argument('--spec',required=True);z.add_argument('--output',required=True)
    for name in ['study-run','study-analyze']:
        z=sub.add_parser(name);z.add_argument('--study',required=True);z.add_argument('--review',required=True)
        if name=='study-run':z.add_argument('--timeout',type=int,default=180)
    z=sub.add_parser('doctor');z.add_argument('--tools');z.add_argument('--output');z.add_argument('--brief',action='store_true');z.add_argument('--full',action='store_true');z.add_argument('--require-delivery',action='store_true')
    z=sub.add_parser('site-delivery',help='Export complete and minimal review folders from one verified actual run');z.add_argument('--summary',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('site-delivery-verify',help='Verify a complete or minimal review folder');z.add_argument('--folder',required=True)
    z=sub.add_parser('report');z.add_argument('--summary',required=True);z.add_argument('--output',required=True);z.add_argument('--culvert-details');z.add_argument('--comparison',action='append',default=[],help='Verified same-site sensitivity or public-case comparison; may be repeated');z.add_argument('--context',help='Bound report purpose, criteria, previous summary and QA decisions')
    z=sub.add_parser('queue-run');z.add_argument('--queue',required=True);z.add_argument('--output',required=True);z.add_argument('--fresh',action='store_true')
    z=sub.add_parser('queue-status');z.add_argument('--output',required=True)
    z=sub.add_parser('batch-report');z.add_argument('--queue-output',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('batch-verify');z.add_argument('--output',required=True)
    z=sub.add_parser('qa-review');z.add_argument('--summary',required=True);z.add_argument('--output',required=True);z.add_argument('--baseline');z.add_argument('--warnings');z.add_argument('--baseline-warnings')
    z=sub.add_parser('qa-disposition');z.add_argument('--packet',required=True);z.add_argument('--spec',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('qa-closure');z.add_argument('--packet',required=True);z.add_argument('--spec',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('qa-series');z.add_argument('--summary',required=True,action='append');z.add_argument('--output',required=True)
    z=sub.add_parser('project-status',help='Inspect computation, inputs, reports and QA separately');z.add_argument('--project',required=True);z.add_argument('--output')
    z=sub.add_parser('project-open',help='Open the local project and QA entry');z.add_argument('--project',required=True);z.add_argument('--warnings');z.add_argument('--baseline');z.add_argument('--baseline-warnings');z.add_argument('--prepare-only',action='store_true');z.add_argument('--no-browser',action='store_true')
    z=sub.add_parser('qa-wizard',help='Open or resume a sealed QA packet');z.add_argument('--packet',required=True);z.add_argument('--output',required=True);z.add_argument('--prepare-only',action='store_true');z.add_argument('--no-browser',action='store_true')
    z=sub.add_parser('site-review');z.add_argument('--project',required=True);z.add_argument('--output',required=True);z.add_argument('--alignment');z.add_argument('--parameters');z.add_argument('--hydrology')
    z=sub.add_parser('site-review-import');z.add_argument('--packet',required=True);z.add_argument('--spec',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('review-open');z.add_argument('--packet',required=True);z.add_argument('--output',required=True)
    sub.add_parser('review-index')
    z=sub.add_parser('model-mapping-template');z.add_argument('--project',required=True);z.add_argument('--reviewed',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('model-propose');z.add_argument('--project',required=True);z.add_argument('--reviewed',required=True);z.add_argument('--mapping',required=True);z.add_argument('--output',required=True)
    z=sub.add_parser('model-approve');z.add_argument('--proposal',required=True);z.add_argument('--approval',required=True);z.add_argument('--output',required=True)
    a=p.parse_args()
    try:
        if a.command=='site-delivery':
            from .site_delivery import generate
            print(json.dumps(generate(a.summary,a.output),ensure_ascii=False,indent=2));return 0
        if a.command=='site-delivery-verify':
            from .site_delivery import verify
            print(json.dumps(verify(a.folder),ensure_ascii=False,indent=2));return 0
        if a.command=='start':
            from .onboarding import start
            return start(a.terminal,a.no_browser)
        if a.command=='native-import':
            from .onboarding import native_import
            return 0 if native_import(a.source,a.output,a.prepare_only,a.review,a.browser,not a.no_browser) else 3
        if a.command=='native-import-approve':
            from .native_review import approve
            print(rel(approve(a.review,read(safe_path(ROOT,a.decision)))));return 0
        if a.command=='investigation-prepare':
            from .investigations import prepare
            print(prepare(a.packet,a.project,a.scenario,a.spec,a.output)['status']);return 0
        if a.command=='investigation-analyze':
            from .investigations import analyze
            print(analyze(a.investigation,a.review)['status']);return 0
        if a.command=='geometry-screen':
            from .physical_geometry import screen
            source=safe_path(ROOT,a.geometry);dest=safe_path(ROOT,a.output)
            if dest.exists():raise ValueError('Use a new screening output')
            result=screen(read(source));result['source']=item(source);save(dest,result);print(result['status']);return 0
        if a.command=='banks-evaluate':
            from .physical_geometry import evaluate_banks
            print(evaluate_banks(a.geometry,a.reference,a.output)['status']);return 0
        if a.command=='public-case-prepare':
            from .public_case import prepare
            print(rel(prepare(a.recipe,a.output,a.fetch)));return 0
        if a.command=='public-case-compare':
            from .public_case import compare
            r=compare(a.recipe,a.summary,a.output);print(r['status']);return 0 if r['status']=='PASS_AT_PUBLISHED_PRECISION' else 1
        if a.command=='project-status':
            from .project_home import inspect
            result=inspect(a.project)
            if a.output:save(safe_path(ROOT,a.output),result)
            print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if not result['issues'] else 2
        if a.command=='project-open':
            from .project_home import prepare
            from .review_server import serve
            result=prepare(a.project,a.warnings,a.baseline,a.baseline_warnings)
            if a.prepare_only:print(json.dumps(result,ensure_ascii=False,indent=2));return 0
            serve(a.project,result.get('qa_session'),not a.no_browser);return 0
        if a.command=='qa-wizard':
            from .qa_session import prepare
            from .review_server import serve
            result=prepare(a.packet,a.output)
            if a.prepare_only:print(json.dumps(dict(session=result['session'],status=result['status'],issues=len(result['issues'])),ensure_ascii=False));return 0
            serve(session=result['session'],open_browser=not a.no_browser);return 0
        if a.command=='intake':
            from . import intake
            from .intake_server import serve
            path=safe_path(ROOT,a.project) if a.refresh else intake.resolve(a.project)
            if not a.refresh and path!=safe_path(ROOT,a.project) and intake.control(path) is None:
                print('APPLIED: '+rel(path))
                return 0 if a.no_resume or a.prepare_only else execute(a.project,a.scenario)
            session=intake.prepare(path,a.scenario,a.refresh)
            if a.prepare_only:print(json.dumps(session,ensure_ascii=False,indent=2));return 3 if session['status']==intake.WAITING else 4 if session['status']=='CANCELLED' else 0
            outcome=serve(session['session'],not a.no_browser)
            if outcome['status']=='APPLIED' and not a.no_resume:return execute(a.project,a.scenario)
            return 4 if outcome['status']=='CANCELLED' else 3 if outcome['status']==intake.WAITING else 0
        if a.command=='model-mapping-template':
            from .model_proposal import mapping_template
            mapping_template(a.project,a.reviewed,a.output);print('MAPPING_REQUIRES_REVIEW');return 0
        if a.command=='model-propose':
            from .model_proposal import prepare
            r=prepare(a.project,a.reviewed,a.mapping,a.output);print(r['status']);return 2 if r['blocking_items'] else 0
        if a.command=='model-approve':
            from .model_proposal import approve
            print(rel(approve(a.proposal,a.approval,a.output)));return 0
        if a.command=='review-index':
            from .site_review import write_index
            print(rel(write_index()));return 0
        if a.command=='review-open':
            from .site_review import refresh_view
            print(rel(refresh_view(a.packet,a.output)));return 0
        if a.command=='qa-review':
            from .qa_review import prepare
            r=prepare(a.summary,a.output,a.baseline,a.warnings,a.baseline_warnings);print(json.dumps(dict(run_id=r['run_id'],issues=len(r['issues']),status=r['hydraulic_qa_status'])));return 0
        if a.command=='qa-disposition':
            from .qa_review import disposition
            r=disposition(a.packet,a.spec,a.output);print(r['status']);return 0
        if a.command=='qa-closure':
            from .qa_review import closure
            r=closure(a.packet,a.spec,a.output);print(r['status']);return 3 if r['blockers'] else 0
        if a.command=='qa-series':
            from .convergence import series
            r=series(a.summary,a.output);print(r['status']);return 0 if r['status']=='STABLE_AT_REVIEW_THRESHOLD' else 3
        if a.command=='site-review':
            from .site_review import prepare,register_view
            r=prepare(a.project,a.output,a.alignment,a.parameters,a.hydrology)
            folder=safe_path(ROOT,a.output);register_view(r['project_id'],folder/'index.html',folder/'site_packet.json')
            print(json.dumps(dict(project=r['project_id'],gaps=len(r['gaps']),status=r['status'],entry='REVIEW.html')));return 0
        if a.command=='site-review-import':
            from .site_review import apply_review
            r=apply_review(a.packet,a.spec,a.output);print(r['status']);return 0
        if a.command=='batch-verify':
            from .batch_report import verify as batch_verify
            print(json.dumps(batch_verify(a.output)));return 0
        if a.command=='batch-report':
            from .batch_report import generate
            result=generate(a.queue_output,a.output);print(result['status']);return 0
        if a.command=='queue-run':
            from .queue import run
            result=run(a.queue,a.output,a.fresh);print(json.dumps(result,ensure_ascii=False,indent=2))
            return result['exit_code']
        if a.command=='queue-status':
            from .queue import inspect
            print(json.dumps(inspect(a.output),ensure_ascii=False,indent=2));return 0
        if a.command=='study-prepare':
            from .study import prepare
            print(rel(prepare(a.project,a.scenario,a.spec,a.output)));return 0
        if a.command in ['study-run','study-analyze']:
            from .study import run as study_run, analyze
            if a.command=='study-run':
                if not 5<=a.timeout<=3600:raise ValueError('timeout must be 5..3600 seconds')
                result=study_run(a.study,a.review,a.timeout)
            else:result=analyze(a.study,a.review)
            print(result['status']);return 0 if result['status']=='COMPARISON_REQUIRES_REVIEW' else 1
        if a.command=='review-template':
            from .source_review import template
            template(a.candidates,a.output);print('REVIEW_SPECIFICATION_PENDING');return 0
        if a.command=='source-review':
            from .source_review import review
            result=review(a.candidates,a.spec,a.output);print(result['status']);return 0
        if a.command=='alignment-candidates':
            from .alignment import draft
            result=draft(a.project,a.spec,a.output);print(json.dumps(dict(status=result['status'],section_count=len(result['cross_sections']),intersections=result['intersecting_cutlines'])));return 0
        if a.command=='terrain-metadata':
            from .terrain_metadata import inspect
            result=inspect(a.raster,a.xml,a.output);print(result['status']);return 0
        if a.command=='metadata-fetch':
            from .terrain_metadata import fetch_products
            result=fetch_products(a.terrain_result,a.output);print(json.dumps(result));return 1 if any(r['status']=='FAILED' for r in result) else 0
        if a.command=='evidence-extract':
            from .evidence import extract
            result=extract(a.source,a.output);print(result['status']);return 0
        if a.command=='parameter-candidates':
            from .evidence import parameters
            result=parameters(a.evidence,a.spec,a.output);print(result['status']);return 0
        if a.command=='hydrology-import':
            from .hydrology import import_report
            result=import_report(a.evidence,a.project,a.output);print(result['status']);return 0
        if a.command=='benchmark-prepare':
            from .benchmark import prepare
            print(rel(prepare(a.recipe,a.output,a.fetch)));return 0
        if a.command=='benchmark-compare':
            from .benchmark import compare
            result=compare(a.recipe,a.summary,a.output,a.reference_review);print(result['status']);return 0 if result['status']=='PASS_AT_PUBLISHED_PRECISION' else 1
        if a.command=='variant':
            from .sensitivity import prepare
            print(rel(prepare(a.project,a.spec,a.output)));return 0
        if a.command=='warnings-import':
            from .native_warnings import import_export
            result=import_export(a.summary,a.export,a.selection,a.output,a.encoding);print(json.dumps(result['parsed']['counts']));return 0
        if a.command=='culvert-details-import':
            from .culvert_details import import_tables
            result=import_tables(a.summary,a.selection,a.output);print(result['status']);return 0
        if a.command=='culvert-details-prepare':
            from .culvert_details import prepare
            prepare(a.summary,a.output);print('WAITING_FOR_OBSERVED_NATIVE_TABLES');return 0
        if a.command=='qa':
            from .qa import diagnostics
            summary=read(safe_path(ROOT,a.summary));hyd=summary.get('hydraulics')
            if not hyd:raise ValueError('QA requires computed hydraulics')
            result=diagnostics(hyd,safe_path(ROOT,a.output),a.warnings);print(json.dumps(dict(coverage=result['warning_coverage'],counts=result['counts'])));return 0
        if a.command=='compare':
            from .qa import compare
            result=compare(a.baseline,a.candidate,a.output);print('Compared '+str(len(result['rows']))+' profile(s); review required');return 0
        if a.command=='init':
            c=inputs.template(a.id,a.lat,a.lon);dest=ROOT/'projects'/a.id;dest.mkdir(parents=True,exist_ok=False);save(dest/'project.json',c);print(rel(dest/'project.json'));return 0
        if a.command=='doctor':
            from .doctor import main as doctor_main
            arguments=[]
            for key in ['tools','output']:
                if getattr(a,key):arguments.extend(['--'+key,getattr(a,key)])
            for key in ['brief','full','require_delivery']:
                if getattr(a,key):arguments.append('--'+key.replace('_','-'))
            return doctor_main(arguments)
        if a.command=='terrain-reference':
            from .terrain_reference import compare
            result=compare(a.project,a.geometry,a.output);print(result['status']);return 0
        if a.command=='report':
            report.generate(safe_path(ROOT,a.summary),safe_path(ROOT,a.output),a.culvert_details,a.comparison,a.context);print('RENDERED_PENDING_VISUAL_REVIEW');return 0
        if a.command=='sections':
            from .sections import draft
            draft(a.project,a.alignment);return 0
        if a.command=='run':
            if not 5<=a.timeout<=3600:raise ValueError('timeout must be 5..3600 seconds')
            interactive=a.interactive or (not a.non_interactive and sys.stdin.isatty())
            result=run_with_intake(a.project,a.scenario,a.fresh,a.timeout,interactive,a.no_browser)
            if result==0 and a.review:
                from .project_home import prepare,inspect
                from .review_server import serve
                home=prepare(a.project);serve(a.project,home.get('qa_session'),not a.no_browser)
                review_state=inspect(a.project)['review_status'];print(review_state)
                return 4 if review_state=='REVIEW_CANCELLED' else 0 if review_state=='TECHNICAL_REVIEW_RECORDED_CONDITIONAL' else 3
            return result
        if a.command=='verify':return verify(a.project)
        path,c=inputs.load(a.project);print(json.dumps(read(path.parent/'state.json'),ensure_ascii=False,indent=2));return 0
    except Exception as e:print(type(e).__name__+': '+str(e),file=sys.stderr);return 1
