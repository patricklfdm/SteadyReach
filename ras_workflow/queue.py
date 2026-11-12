"""Serial local queue with immutable attempts and evidence-checked recovery.

No daemon or database. Queue, project and solver locks are Windows kernel locks.
The parent owns each worker's process tree and never attaches to existing RAS.
"""
import os
import subprocess
import sys
import traceback
from .common import ROOT, code_identity, digest, identifier, intact, item, lock, read, rel, safe_path, save, unique_id, utc
from . import inputs, native, report_tools


def load(path):
    path=safe_path(ROOT,path);spec=read(path)
    if spec.get('schema_version')!='1.0':raise ValueError('Unsupported queue schema')
    identifier(spec['queue_id'])
    jobs=spec.get('jobs',[])
    if not jobs:raise ValueError('Queue needs at least one job')
    ids=[]
    for job in jobs:
        ids.append(identifier(job['id']));identifier(job['scenario'])
        safe_path(ROOT,job['project'])
        if job.get('tools'):safe_path(ROOT,job['tools'])
        if not 5<=job.get('solver_timeout_seconds',180)<=3600:raise ValueError('Solver timeout must be 5..3600 seconds')
        if not 1<=job.get('job_timeout_seconds',900)<=7200:raise ValueError('Job timeout must be 1..7200 seconds')
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate queue job id')
    return path,spec


def identity(job):
    from .intake import resolve, control
    path,c=inputs.load(resolve(job['project']))
    session=control(path)
    try:deps=inputs.dependencies(path,c);missing=None
    except (ValueError,OSError) as e:deps=[item(path)];missing=str(e)
    engine=native.discover()
    report=report_tools.discover(job.get('tools'))
    report.pop('checked_at_utc',None)
    value=dict(job=job,inputs=deps,input_inventory_error=missing,code=code_identity(),cancelled=bool(session and session['status']=='CANCELLED'),
        engine={k:engine.get(k) for k in ['status','selected','executables','runtime','blocking_items']},report_tools=report)
    return dict(key=digest(value),evidence=value)


def validate_receipt(entry,expected=None):
    if not intact([entry]):raise ValueError('Attempt receipt changed or is missing')
    receipt=read(ROOT/entry['path'])
    if not intact(receipt['artifacts']+[receipt['summary']]):raise ValueError('Attempt artifact changed or is missing')
    if expected and (receipt.get('requested_project',receipt['project'])!=rel(safe_path(ROOT,expected['project'])) or receipt['scenario_id']!=expected['scenario']):
        raise ValueError('Receipt belongs to a different queue job')
    summary=read(ROOT/receipt['summary']['path'])
    if summary['attempt_id']!=receipt['attempt_id'] or summary['calculation_status']!=receipt['calculation_status']:
        raise ValueError('Receipt/summary identity mismatch')
    if summary.get('hydraulics'):
        from .qa import verified_profiles
        verified_profiles(summary['hydraulics'])
        if not intact([summary['hydraulic_results']]) or read(ROOT/summary['hydraulic_results']['path'])!=summary['hydraulics']:
            raise ValueError('Summary differs from sealed hydraulic results')
    elif summary['calculation_status']=='COMPUTED':raise ValueError('Computed receipt lacks real hydraulic results')
    return receipt,summary


def reusable(attempt,key,job):
    status=attempt.get('status')
    if status not in ['COMPLETED','WAITING_FOR_INPUT','CANCELLED'] or attempt.get('identity',{}).get('key')!=key:return False
    try:
        from .intake import resolve, control
        session=control(resolve(job['project']))
        if status=='COMPLETED' and session and session['status'] in ['WAITING_FOR_INPUT','CANCELLED']:return False
        if status!='COMPLETED':
            if not session or session['status']!=status:return False
        receipt,summary=validate_receipt(attempt['receipt'],job)
        if status=='WAITING_FOR_INPUT' and summary.get('intake',{}).get('session')!=session['session']:return False
        return intact(receipt['inputs']) and intact(receipt['code'])
    except (KeyError,ValueError,OSError):return False


def supervise(request_path,timeout):
    import win32api,win32job
    folder=request_path.parent
    job=win32job.CreateJobObject(None,'Local\\HecQueue_'+unique_id())
    limits=win32job.QueryInformationJobObject(job,win32job.JobObjectExtendedLimitInformation)
    limits['BasicLimitInformation']['LimitFlags']=win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    win32job.SetInformationJobObject(job,win32job.JobObjectExtendedLimitInformation,limits)
    proc=None;status='FAILED';code=None
    try:
        with (folder/'worker.log').open('wb') as log:
            proc=subprocess.Popen([sys.executable,'-m','ras_workflow.queue_worker',str(request_path)],cwd=ROOT,
                stdin=subprocess.PIPE,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                win32job.AssignProcessToJobObject(job,proc._handle)
                save(folder/'worker_started.json',dict(worker_pid=proc.pid,started_utc=utc(),owned_job=True))
                proc.stdin.write(b'GO\n');proc.stdin.close()
                code=proc.wait(timeout=timeout);status='EXITED'
            except subprocess.TimeoutExpired:status='TIMEOUT'
            except BaseException:
                # Before GO the worker cannot launch native or conversion processes.
                if proc.poll() is None:proc.terminate()
                raise
    finally:
        win32api.CloseHandle(job)
        if proc and proc.poll() is None:proc.wait(timeout=15)
        result=dict(status=status,exit_code=code,worker_pid=proc.pid if proc else None,finished_utc=utc(),
            cleanup='Closed only this queue worker job and its newly owned descendants')
        save(folder/'supervisor.json',result)
    return result


def collect(folder,job):
    result=read(folder/'worker_result.json')
    receipt,summary=validate_receipt(result['receipt'],job)
    status='FAILED'
    if result['exit_code']==0 and receipt['calculation_status']=='COMPUTED' and not receipt['errors'] and receipt['report_status']=='GENERATED_PENDING_VISUAL_REVIEW':
        status='COMPLETED'
    elif result['exit_code']==2 and receipt['calculation_status']=='BLOCKED':status='BLOCKED'
    elif result['exit_code']==3 and receipt.get('workflow_status')=='WAITING_FOR_INPUT':status='WAITING_FOR_INPUT'
    elif result['exit_code']==4 and receipt.get('workflow_status')=='CANCELLED':status='CANCELLED'
    return dict(status=status,receipt=result['receipt'],summary=receipt['summary'],exit_code=result['exit_code'],
        calculation_status=receipt['calculation_status'],report_status=receipt['report_status'],
        solver_reused=summary['solver_reused'],run_id=summary['hydraulics']['run_id'] if summary.get('hydraulics') else None,
        errors=receipt['errors'],blocking_items=summary['gate']['blocking_items'])


def event(output,state,kind,job_id,attempt):
    record=dict(at_utc=utc(),event=kind,job_id=job_id,attempt=attempt)
    save(output/'events'/(unique_id()+'.json'),record)
    save(output/'queue_state.json',state)


def inspect(output):
    state=read(safe_path(ROOT,output)/'queue_state.json')
    latest=[dict(job_id=k,**(v[-1] if v else dict(status='PENDING'))) for k,v in state['jobs'].items()]
    statuses=[a['status'] for a in latest]
    code=1 if any(s not in ['COMPLETED','BLOCKED','WAITING_FOR_INPUT','CANCELLED'] for s in statuses) else 2 if 'BLOCKED' in statuses else 3 if 'WAITING_FOR_INPUT' in statuses else 4 if 'CANCELLED' in statuses else 0
    return dict(queue_id=state['queue_id'],status={0:'COMPLETE',1:'HAS_FAILURES',2:'HAS_BLOCKERS',3:'WAITING_FOR_INPUT',4:'HAS_CANCELLATIONS'}[code],
        exit_code=code,latest=latest,engineering_acceptance='NOT_ASSESSED')


def run(queue_path,output,fresh=False):
    path,spec=load(queue_path);output=safe_path(ROOT,output);output.mkdir(parents=True,exist_ok=True)
    with lock(output/'queue.lock'):
        state_path=output/'queue_state.json'
        if state_path.exists():
            state=read(state_path)
            if state['queue']['sha256']!=item(path)['sha256']:raise ValueError('Queue specification changed; use a new output directory')
        else:
            state=dict(schema_version='1.0',queue_id=spec['queue_id'],queue=item(path),jobs={j['id']:[] for j in spec['jobs']})
            save(output/'queue_specification.json',spec);save(state_path,state)
        for job in spec['jobs']:
            attempts=state['jobs'][job['id']]
            # The acquired kernel lock proves no other parent owns this queue.
            if attempts and attempts[-1]['status']=='IN_PROGRESS':
                previous=attempts[-1];folder=ROOT/previous['folder']
                try:
                    previous.update(collect(folder,job),recovered_after_parent_exit=True)
                except (ValueError,KeyError,OSError):
                    previous.update(status='INTERRUPTED',error='Previous parent exited without a verifiable terminal receipt')
                previous['finished_utc']=utc();event(output,state,'RECOVERY',job['id'],previous)
            try:current=identity(job)
            except Exception as e:
                attempts.append(dict(id=unique_id(),status='BLOCKED',error='Preflight: '+str(e),finished_utc=utc()))
                event(output,state,'PREFLIGHT_BLOCKED',job['id'],attempts[-1]);continue
            if not fresh and attempts and reusable(attempts[-1],current['key'],job):
                event(output,state,'SKIPPED_VERIFIED',job['id'],dict(attempt_id=attempts[-1]['id'],identity_key=current['key']))
                print(job['id']+': '+attempts[-1]['status']+' (unchanged; evidence verified)',flush=True);continue
            aid=unique_id();folder=output/'attempts'/job['id']/aid;folder.mkdir(parents=True)
            attempt=dict(id=aid,status='IN_PROGRESS',started_utc=utc(),folder=rel(folder),identity=current)
            attempts.append(attempt)
            save(folder/'request.json',dict(job=job,identity=current,fresh=fresh,created_utc=utc()))
            event(output,state,'STARTED',job['id'],attempt)
            try:
                supervisor=supervise(folder/'request.json',job.get('job_timeout_seconds',900))
                if supervisor['status']!='EXITED':raise RuntimeError('Queue worker '+supervisor['status'])
                attempt.update(collect(folder,job))
                if identity(job)['key']!=current['key']:
                    attempt.update(status='FAILED',error='Inputs, code or environment changed during the attempt')
            except Exception as e:
                attempt.update(status='FAILED',error=str(e))
                (folder/'parent_error.txt').write_text(traceback.format_exc(),encoding='utf-8')
            attempt['finished_utc']=utc()
            save(folder/'completion.json',attempt);event(output,state,'FINISHED',job['id'],attempt)
            print(job['id']+': '+attempt['status'],flush=True)
        result=inspect(output);save(output/'queue_summary.json',result);return result
