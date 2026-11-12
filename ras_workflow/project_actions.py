"""Fixed local actions. No shell commands, arbitrary paths or silent model approval."""
import os, subprocess, sys, threading
from .common import ROOT, digest, item, lock, read, rel, safe_path, save, unique_id, utc


def process_alive(pid):
    """Read-only Windows process query; uncertainty keeps the action blocked."""
    if not isinstance(pid,int) or pid<=0:return True
    import ctypes
    from ctypes import wintypes
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];api.OpenProcess.restype=wintypes.HANDLE
    api.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    api.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=api.OpenProcess(0x1000,False,pid)
    if not handle:return ctypes.get_last_error()!=87
    try:
        code=wintypes.DWORD()
        return not api.GetExitCodeProcess(handle,ctypes.byref(code)) or code.value==259
    finally:api.CloseHandle(handle)


def worker(record):
    """Persist completion independently of the browser/server lifetime."""
    path=safe_path(ROOT,record);job=read(path)
    if not path.is_relative_to(ROOT/'status/project_actions') or path.name!='action.json':raise ValueError('Invalid action record')
    if job['command'][0]!='workflow.py' or job['command'][1] not in ['run','report','site-delivery']:raise ValueError('Invalid action command')
    job['worker_pid']=os.getpid();save(path,job)
    try:
        code=subprocess.call([sys.executable,str(ROOT/'workflow.py')]+job['command'][1:],cwd=ROOT,stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        job.update(status={0:'COMPLETED',3:'WAITING_FOR_INPUT',4:'CANCELLED'}.get(code,'FAILED'),exit_code=code)
        if code==3 and job.get('action')=='RUN':
            from .project_home import inspect
            if inspect(job['project']['path'])['workflow_status']=='WAITING_FOR_DELIVERY_REVIEW':job['status']='WAITING_FOR_DELIVERY_REVIEW'
    except Exception as e:job.update(status='FAILED',error=str(e))
    job['finished_utc']=utc();save(path,job)


class Actions:
    def __init__(self,project):
        self.project=safe_path(ROOT,project);self.guard=threading.Lock();self.process=None;self.job=None;self.children=[]
        self.base=ROOT/'status/project_actions'/digest(rel(self.project))
        latest=self.base/'latest.json'
        if latest.exists():
            record=safe_path(ROOT,read(latest)['record'])
            if not record.is_relative_to(self.base) or record.name!='action.json':raise ValueError('Action record outside project history')
            self.job=read(record)

    def view(self):
        with self.guard:
            latest=self.base/'latest.json'
            if latest.exists():
                record=safe_path(ROOT,read(latest)['record'])
                if not record.is_relative_to(self.base) or record.name!='action.json':raise ValueError('Invalid project action history')
                self.job=read(record)
            if self.process and self.process.poll() is not None:self.process=None
            if self.job and self.job['status']=='RUNNING' and not self.process and not process_alive(self.job.get('worker_pid')):
                self.job.update(status='INTERRUPTED',error='Action worker stopped without a completion record. Inspect the latest project attempt and action log before retrying.',finished_utc=utc())
                save(ROOT/self.job['record'],self.job)
            return self.job

    def start(self,body):
        from . import intake,inputs
        from .project_home import inspect
        action=body.get('action')
        if action not in ['INPUT','REPORT','RUN','DELIVERY']:raise ValueError('Unknown project action')
        self.view()
        with self.guard,lock(self.base/'launch.lock'):
            latest=self.base/'latest.json'
            if latest.exists():self.job=read(safe_path(ROOT,read(latest)['record']))
            if self.process or (self.job and self.job['status']=='RUNNING'):raise ValueError('A project action is running or has an unclosed record; check its log before restarting')
            path=intake.resolve(self.project);path,c=inputs.load(path)
            if body.get('project_sha256')!=item(path)['sha256']:raise ValueError('Project changed; refresh before continuing')
            scenario=body.get('scenario') or c['scenarios'][0]['id']
            if scenario not in [s['id'] for s in c['scenarios']]:raise ValueError('Unknown scenario')
            if action=='INPUT':
                from .intake_server import create
                control=intake.control(path)
                if control and control['status']=='CANCELLED' and body.get('confirmed') is not True:raise ValueError('Confirm restarting cancelled input review')
                s=intake.prepare(path,scenario,refresh=bool(control and control['status']=='CANCELLED'))
                if s['status']!='WAITING_FOR_INPUT':raise ValueError('Inputs already applied; reopen the active project')
                server=create(s['session']);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();self.children.append((server,thread))
                return dict(status='WAITING_FOR_INPUT',url=server.url)
            home=inspect(self.project);folder=self.base/unique_id();folder.mkdir(parents=True)
            if action=='DELIVERY':
                if not home.get('run_id') or home['issues']:raise ValueError('An intact computed run and current evidence are required for delivery')
                from .site_delivery import review_settings
                if body.get('delivery_settings') is not None:
                    with lock(path.parent/'project.lock'):review_settings(path,body['delivery_settings'],body.get('reviewer'))
                args=['site-delivery','--summary',home['latest_summary']['path'],'--output',rel(path.parent/'deliveries'/unique_id())]
            elif action=='REPORT':
                if not home.get('latest_summary') or home['calculation_status']=='EVIDENCE_CHANGED':raise ValueError('No intact summary to report')
                args=['report','--summary',home['latest_summary']['path'],'--output',rel(folder/'reports')]
                if body.get('report_context'):
                    from .report_context import evaluate
                    context=body['report_context']
                    if not isinstance(context,dict):raise ValueError('Invalid report context')
                    context=dict(context,schema_version='report_context_1.0',summary=home['latest_summary'])
                    valid_editions=[e for e in home.get('report_history',[]) if e.get('verified')]
                    if valid_editions:context['previous_report']=valid_editions[-1]['manifest']
                    if home.get('qa_decisions'):context['qa_decisions']=home['qa_decisions']
                    previous=context.pop('previous_run_id',None)
                    if previous:
                        matched=[r for r in home['previous_runs'] if r['run_id']==previous]
                        if len(matched)!=1:raise ValueError('Previous run is unavailable or ambiguous')
                        context['previous_summary']=matched[0]['summary']
                    evaluate(home['latest_summary']['path'],context)
                    save(folder/'context.json',context);args+=['--context',rel(folder/'context.json')]
            else:
                if body.get('confirmed') is not True or not str(body.get('reviewer','')).strip():raise ValueError('Named confirmation required before running the approved project')
                args=['run','--project',rel(self.project),'--scenario',scenario,'--non-interactive','--no-browser']
                if body.get('recompute') is True:args.append('--fresh')
            self.job=dict(status='RUNNING',action=action,started_utc=utc(),command=['workflow.py']+args,record=rel(folder/'action.json'),
                project=item(path),reviewer=body.get('reviewer'),confirmed=body.get('confirmed',False),log=rel(folder/'action.log'),worker_pid=os.getpid())
            save(folder/'action.json',self.job)
            save(self.base/'latest.json',dict(record=self.job['record']))
            with (folder/'action.log').open('wb') as log:
                try:self.process=subprocess.Popen([sys.executable,'-m','ras_workflow.project_actions',self.job['record']],cwd=ROOT,stdout=log,stderr=log,stdin=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                except OSError as e:
                    self.job.update(status='FAILED',error=str(e));save(folder/'action.json',self.job);raise
            return self.job

    def close(self):
        for server,thread in self.children:
            server.shutdown();server.server_close();thread.join(timeout=3)
        # A user-requested compute/render continues after its browser closes.
        # Record its eventual status without touching any unrelated processes.
        if self.process:
            process=self.process
            def finish():process.wait();self.view()
            threading.Thread(target=finish,daemon=False).start()


if __name__=='__main__':worker(sys.argv[1])
