"""Resume only the interrupted edition's approved inputs, or reconnect its saved native results."""
from . import app_core as core, inputs
from .common import ROOT, intact, item, read, rel, safe_path, save


def seal(model, project):
    content=dict(project_id=model['id'],project=rel(project),scenario=model['run_scenario'],revision=model['revision'],
                 confirmation=model['run_confirmation'],inputs=inputs.dependencies(project,read(project)))
    record=project.parent/'resume_inputs.json'
    save(record,content)
    return item(record)


def inspect(model):
    cp=model.get('active_project')
    if not cp and model.get('session'):
        session=read(safe_path(ROOT,model['session']))
        if session.get('status')=='APPLIED':
            cp=session.get('approved_project')
    if not cp:
        return dict(mode='REVIEW_INPUTS')
    try:
        project=safe_path(ROOT,cp)
        if not project.is_relative_to(core.folder(model['id'])):
            raise ValueError('Approved project lies outside this edition')
        config=read(project)
        state_path=project.parent/'state.json'
        state=read(state_path) if state_path.is_file() else {}
        scenario=model.get('run_scenario') or model['scenario']
        folder=safe_path(ROOT,state['latest_attempt']) if state.get('latest_attempt') else None
        if folder and folder.parent!=project.parent/'jobs':
            raise ValueError('Solver attempt path differs from the approved project')
        path=folder/'summary.json' if folder else None
        if path and path.is_file() and read(path).get('calculation_status')=='COMPUTED':
            from .qa_review import load_summary
            _,summary,hyd=load_summary(path)
            native=safe_path(ROOT,hyd['raw_hdf']['path'])
            if (summary['configuration']!=config or summary['attempt_id']!=folder.name or
                    not native.is_relative_to(project.parent/'jobs'/hyd['run_id']) or hyd['scenario_id']!=scenario):
                raise ValueError('Saved calculation belongs to another project, attempt or profile set')
            ref=item(path)
            registered=state.get('latest_summary') or {}
            if registered.get('path')==ref['path'] and not intact([registered]):
                raise ValueError('Saved calculation summary changed')
            manifest=read(safe_path(ROOT,hyd['raw_hdf']['path']).parent.parent/'manifest.json')
            if (manifest['run_id']!=hyd['run_id'] or not intact(manifest['source_inputs']) or
                    inputs.dependencies(project,config)!=manifest['source_inputs']):
                raise ValueError('Solver inputs differ from this approved edition')
            return dict(mode='RESTORE_RESULT',project=rel(project),summary=ref,run_id=hyd['run_id'])
        ref=model.get('compiled_checkpoint')
        if not ref or not intact([ref]):
            raise ValueError('The approved input checkpoint is unavailable. Restore the original approved inputs and records before continuing.')
        saved=read(safe_path(ROOT,ref['path']))
        if (saved['project_id']!=model['id'] or saved['revision']!=model['revision'] or saved['project']!=rel(project)
                or saved['scenario']!=scenario or saved['confirmation']!=model.get('run_confirmation') or
                not intact([saved['confirmation']]) or saved['inputs']!=inputs.dependencies(project,config)):
            raise ValueError('Confirmed inputs changed. Restore the approved edition before retrying.')
        return dict(mode='RESUME_COMPUTATION',project=rel(project),scenario=scenario)
    except (ValueError,OSError,TypeError,KeyError) as exc:
        return dict(mode='RESTORE_EVIDENCE',error=str(exc))


def request(key,body):
    model=core.model(key)
    if (body.get('mode')=='RESTORE_RESULT' and model.get('recovered_task') and model['recovered_task']==body.get('task') and
            model.get('summary') and intact([model['summary']]) and model['revision']==body.get('revision')):
        return dict(status=model['status'],run_id=read(ROOT/model['summary']['path'])['hydraulics']['run_id'],new_solver_calls=0)
    job=read(safe_path(ROOT,model['task'])) if model.get('task') else {}
    if (body.get('mode')=='RESUME_COMPUTATION' and body.get('confirmed') is True and body.get('task')
            and job.get('action')=='resume-run' and job.get('resume_of')==body['task'] and model['revision']==body.get('revision')
            and (job.get('status')=='FINISHED' or job.get('status')=='RUNNING' and core.task_alive(job))):
        return dict(status=model['status'],task=model['task'],reused_request=True)
    if (job.get('action') not in ('run','resume-run') or model.get('task')!=body.get('task')
            or model['revision']!=body.get('revision')):
        raise ValueError('Reopen the interrupted calculation')
    core.require_idle(model)
    if model['status'] not in ('PROCESSING','NEEDS_ATTENTION','INTERRUPTED') and job.get('status') not in ('FAILED','INTERRUPTED'):
        raise ValueError('No interrupted calculation to resume')
    plan=inspect(model)
    if body.get('mode')!=plan['mode'] or plan['mode'] not in ('RESTORE_RESULT','RESUME_COMPUTATION'):
        raise ValueError(plan.get('error') or 'The saved calculation changed. Reopen the project.')
    if plan['mode']=='RESUME_COMPUTATION' and body.get('confirmed') is not True:
        raise ValueError('Explicitly confirm resuming the approved native calculation')
    if plan['mode']=='RESTORE_RESULT':
        project=safe_path(ROOT,plan['project'])
        state=read(project.parent/'state.json')
        delivery=state.get('delivery') if state.get('latest_summary')==plan['summary'] else None
        model.update(active_project=plan['project'],engine_state=rel(project.parent/'state.json'),summary=plan['summary'],
                     phase='DONE',errors=[],status='RESULTS_READY' if delivery and delivery.get('status','').startswith('READY') else 'RESULTS_READY_MAP_PENDING')
        if state.get('latest_summary')!=plan['summary']:
            model['exports_need_refresh']=True
        model['recovered_task']=model.pop('task')
        core.persist(model,'RECOVER_SAVED_RESULT',dict(summary=plan['summary'],new_solver_calls=0))
        return dict(status=model['status'],run_id=plan['run_id'],new_solver_calls=0)
    return core.launch(key,'resume-run')


def execute(key):
    model=core.model(key)
    plan=inspect(model)
    if plan['mode']!='RESUME_COMPUTATION':
        raise ValueError(plan.get('error') or 'A calculation checkpoint is available. Reopen the project before continuing.')
    core.execute_approved(model,safe_path(ROOT,plan['project']),fresh=False)
