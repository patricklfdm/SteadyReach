"""Small local start page joining the existing input, calculation and review tools."""
import base64
import json
import math
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import webbrowser
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .common import ROOT, digest, intact, item, lock, read, rel, safe_path, save, unique_id, utc

BASE=ROOT/'status/launcher'
EXAMPLES={'phelps':('Phelps Brook', 'benchmarks/phelps_brook/recipe.json'),
          'queen':('Queen Gutter', 'benchmarks/queen_gutter/recipe.json')}


def text(value,label,limit=500):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:
        raise ValueError('Please enter '+label+' / 请填写'+label)
    return value.strip()


def coordinates(body,required=True):
    values=[body.get('latitude'),body.get('longitude')]
    if not required and all(v in ('',None) for v in values):return None
    if any(isinstance(v,bool) for v in values):raise ValueError('Coordinates must be numbers, not booleans')
    try:lat,lon=[float(v) for v in values]
    except (ValueError,TypeError):raise ValueError('Enter latitude and longitude as decimal degrees / 请填写十进制度纬度和经度')
    if not all(math.isfinite(v) for v in (lat,lon)) or not (-90<=lat<=90 and -180<=lon<=180):
        raise ValueError('Latitude must be -90…90 and longitude -180…180 / 经纬度超出范围')
    return lat,lon


def catalog():
    path=BASE/'projects.json'
    data=read(path) if path.is_file() else {'schema_version':'launcher_1.0','projects':[]}
    if data.get('schema_version')!='launcher_1.0':raise ValueError('Unsupported launcher catalog')
    return data


def remember(entry):
    with lock(BASE/'catalog.lock'):
        data=catalog();entries=[e for e in data['projects'] if e['id']!=entry['id']]
        data['projects']=([dict(entry,updated_utc=utc())]+entries)[:200];save(BASE/'projects.json',data)
    return entry


def find(key):
    matches=[e for e in catalog()['projects'] if e['id']==key]
    if len(matches)!=1:raise ValueError('Project is unavailable; refresh / 项目不可用，请刷新')
    return matches[0]


def native_copy(body,folder):
    """Only the four browser-selected inputs; plan changes are explicit and preserved."""
    files=body.get('files');selected=body.get('selected_plan')
    if not isinstance(files,list) or len(files)!=4:raise ValueError('Choose one project and its selected steady plan / 请选择工程及对应恒定流计划')
    if not isinstance(selected,str) or not re.fullmatch(r'p\d{2}',selected,re.I):raise ValueError('Choose a saved steady plan / 请选择已保存的恒定流计划')
    decoded={};total=0
    for f in files:
        if not isinstance(f,dict):raise ValueError('Invalid native file record')
        name=f.get('name','')
        if not re.fullmatch(r'[A-Za-z0-9_ .-]+\.(?:prj|[pgf]\d{2})',name,re.I):raise ValueError('Unsupported native filename / 原生文件名不受支持')
        if name.casefold() in {k.casefold() for k in decoded}:raise ValueError('Duplicate input filename')
        raw=base64.b64decode(f.get('content',''),validate=True);total+=len(raw)
        if total>15_000_000:raise ValueError('Selected native inputs exceed 15 MB / 输入超过 15 MB')
        decoded[name]=raw
    projects=[n for n in decoded if n.lower().endswith('.prj')]
    if len(projects)!=1:raise ValueError('Select exactly one HEC-RAS project')
    if Path(projects[0]).with_suffix('.'+selected).name.casefold() not in {n.casefold() for n in decoded}:
        raise ValueError('Selected plan is missing from the uploaded inputs')
    original=folder/'source';original.mkdir(parents=True,exist_ok=False)
    work=folder/'selected_inputs';work.mkdir()
    for name,raw in decoded.items():(original/name).write_bytes(raw);(work/name).write_bytes(raw)
    project=work/projects[0]
    from .native_review import text as native_text, inspect
    value=native_text(project);matches=re.findall(r'^Current Plan=(.*)$',value,re.M)
    if len(matches)!=1:raise ValueError('Original project has no unique current plan')
    old=matches[0].strip();selected=selected.lower()
    if old.lower()!=selected:
        value=re.sub(r'^Current Plan=.*$',lambda _: 'Current Plan='+selected,value,flags=re.M)
        project.write_text(value,encoding='ascii')
    result=inspect(project)
    selected_paths={Path(v).resolve() for v in result['files'].values()}
    if selected_paths!={p.resolve() for p in work.iterdir()}:raise ValueError('Uploaded files do not match selected plan references')
    save(folder/'selection_receipt.json',dict(created_utc=utc(),source_files=[item(p) for p in sorted(original.iterdir())],
        selected_files=[item(p) for p in sorted(work.iterdir())],previous_plan=old,selected_plan=selected,
        change='Only the working copy Current Plan card was changed' if old.lower()!=selected else 'No source changes',
        source=body['source'],approval='NOT_APPROVED'))
    return project


def create_entry(body):
    route=body.get('route')
    if route not in ('coordinates','native','example'):raise ValueError('Choose a supported route')
    title=text(body.get('title'),'project name / 项目名称') if route!='example' else EXAMPLES.get(body.get('example'),('',''))[0]
    if not title:raise ValueError('Choose a published example')
    point=coordinates(body,required=route=='coordinates') if route!='example' else None
    if route=='native' and body.get('native_only') is True and point is not None:
        raise ValueError('Choose coordinates with GIS, or clear coordinates for native-only output / 请选择带坐标的 GIS 输出，或清空坐标后选择仅原生输出')
    if route=='native':body=dict(body,source=text(body.get('source'),'source and applicable site / 来源及适用地点',5000))
    if route=='native' and point is None and body.get('native_only') is not True:
        raise ValueError('Supply coordinates for GIS, or explicitly choose native-only output / 填写坐标，或明确选择不含 GIS 的原生输出')
    key='site_'+unique_id().lower();folder=ROOT/'projects'/key
    entry=dict(id=key,title=title,route=route,created_utc=utc(),project=rel(folder/'project.json'),scenario='q100')
    if route=='example':
        entry.update(recipe=EXAMPLES[body['example']][1],scenario='baseline')
    elif route=='native':
        project=native_copy(body,folder);entry.update(native_source=rel(project),source=body['source'])
        if point is None:
            from .native_review import prepare
            review=prepare(project,folder/'import_review');entry['review']=rel(review);entry['project']=None;entry['scenario']='baseline'
            # Metadata prefill is not input approval. Units/datum/reviewer stay empty.
            from .native_import_ui import view,update
            draft=view(review)['draft'];values=draft['review'];values.update(project_id=key,title=title,source=body['source'])
            update(review,dict(revision=draft['revision'],review=values),'save')
    if point is not None:
        from .inputs import template
        config=template(key,*point);config['title']=title
        supplied={k:body.get(k) for k in ['flow_cfs','channel_n','overbank_n'] if body.get(k) not in ('',None)}
        if supplied:
            basis=text(body.get('parameter_source'),'parameter source / 参数出处',5000)
            for key0,value in supplied.items():
                if isinstance(value,bool):raise ValueError('Flow and roughness must be numbers')
                number=float(value)
                if not math.isfinite(number) or number<=0 or (key0!='flow_cfs' and number>=1):raise ValueError('Invalid supplied flow/roughness / 已填流量或糙率无效')
                if key0=='flow_cfs':config['scenarios'][0]['profiles'][0].update(flow_cfs=number,source=basis)
                else:config['scenarios'][0][key0]=number;config['scenarios'][0]['parameter_source']=basis
        save(folder/'project.json',config)
    return remember(entry)


def outputs(entry):
    if not entry.get('project') or not (ROOT/entry['project']).is_file():return []
    from .project_home import inspect
    home=inspect(entry['project']);found=[]
    for r in home.get('reports',[]):
        if r.get('verified') and r.get('format')=='pdf':
            found.append(dict(id=digest(r['path']),path=r['path'],label=('Summary' if r.get('detail')=='summary' else 'Report')+' '+str(r.get('language')),kind='pdf',evidence=r))
    for key in ['complete','minimal']:
        value=home.get('delivery',{}).get(key)
        if value:
            path=safe_path(ROOT,value['path'])
            if path.is_dir():found.append(dict(id=digest(rel(path)),path=rel(path),label=key,kind='folder'))
    return found


class Controller:
    def __init__(self,discover=True):
        BASE.mkdir(parents=True,exist_ok=True);self.guard=threading.RLock();self.children={};self.threads=[];self.busy=None;self.closing=False
        self.instance=secrets.token_urlsafe(24)
        if not discover:return
        # Discover conventional existing projects without scanning sources or run trees.
        known={e.get('project') for e in catalog()['projects']}
        from .inputs import load
        for p in sorted((ROOT/'projects').glob('*/project.json'))[:200]:
            if rel(p) in known:continue
            # A shipped configuration is not the user's saved working project.
            if not any((p.parent/name).is_file() for name in ['state.json','intake_state.json']):continue
            try:
                _,c=load(p);remember(dict(id='existing_'+digest(rel(p))[:16],title=c['title'],project=rel(p),scenario=c['scenarios'][0]['id'],route='existing'))
            except (ValueError,OSError,KeyError,IndexError):continue

    def state(self):
        rows=[]
        from . import intake
        for entry in catalog()['projects']:
            row=dict(entry,status='NOT_STARTED',url=None,outputs=[])
            try:
                if entry.get('project') and (ROOT/entry['project']).is_file():
                    p=intake.resolve(entry['project']);control=intake.control(p)
                    state=read(p.parent/'state.json') if (p.parent/'state.json').is_file() else {}
                    row['status']=control['status'] if control and control['status'] in ('WAITING_FOR_INPUT','CANCELLED') else state.get('workflow_status',state.get('status','NOT_STARTED'))
                    row['calculation_status']=state.get('calculation_status','NOT_STARTED')
                elif entry.get('review'):
                    from .native_import_ui import view
                    row['status']=view(entry['review'])['draft']['status']
                jobfile=BASE/'jobs'/entry['id']/'latest.json'
                if jobfile.is_file():
                    job=read(safe_path(ROOT,read(jobfile)['path']));row['job']=job
                    if job['status']=='RUNNING' and self.busy!=entry['id']:
                        from .project_actions import process_alive
                        if not process_alive(job.get('pid')):row['job']=dict(job,status='INTERRUPTED')
                    log=safe_path(ROOT,job['log'])
                    if log.is_file():
                        with log.open('rb') as f:f.seek(max(0,log.stat().st_size-12000));row['log_tail']=f.read().decode('utf-8',errors='replace')
                errorfile=BASE/'jobs'/entry['id']/'continuation_error.json'
                if errorfile.is_file():row['continuation_error']=read(errorfile)['error']
                child=self.children.get(entry['id'])
                if child and not child.finished.is_set():row['url']=child.url;row['view_kind']=child.view_kind
            except (ValueError,OSError,KeyError) as e:row.update(status='NEEDS_ATTENTION',error=str(e))
            rows.append(row)
        return dict(projects=rows,busy=self.busy,launcher_instance=self.instance,scope='1D steady flow; engineering approval remains with the reviewer')

    def _attach_native(self,entry,session):
        if not entry.get('native_source'):return
        from . import intake_native
        if intake_native.preview(session):return
        draft=read(safe_path(ROOT,session).parent/'draft.json')
        intake_native.from_workspace(session,dict(revision=draft['revision'],project=entry['native_source'],source=entry['source']))

    def _child(self,entry,kind,server):
        old=self.children.get(entry['id'])
        if old and not old.finished.is_set():server.server_close();return old.url
        server.view_kind=kind;server.launcher_url=getattr(self,'url',None);self.children[entry['id']]=server
        t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
        def completed():
            while not self.closing and not server.finished.wait(.25):pass
            if self.closing:return
            outcome=server.outcome or {}
            server.shutdown();server.server_close();t.join(timeout=3)
            if hasattr(server,'actions'):server.actions.close()
            if outcome.get('status') in ('APPLIED','APPROVED'):
                if kind=='native':entry['project']=outcome['project'];remember(entry)
                try:self.run(entry)
                except (ValueError,OSError,RuntimeError) as e:save(BASE/'jobs'/entry['id']/'continuation_error.json',dict(project=entry['id'],error=str(e),created_utc=utc()))
        watcher=threading.Thread(target=completed,daemon=True);watcher.start()
        return server.url

    def open(self,entry):
        with self.guard:
            old=self.children.get(entry['id'])
            if old and not old.finished.is_set():return dict(url=old.url)
            from . import intake
            if entry.get('review') and not entry.get('project'):
                from .native_import_ui import create,view
                draft=view(entry['review'])['draft']
                if draft['status']=='APPROVED':entry['project']=draft['project'];remember(entry)
                else:return dict(url=self._child(entry,'native',create(entry['review'])))
            if not entry.get('project') or not (ROOT/entry['project']).is_file():return self.run(entry)
            p=intake.resolve(entry['project']);session=intake.control(p)
            if session and session['status']=='WAITING_FOR_INPUT':
                self._attach_native(entry,session['session'])
                from .intake_server import create
                return dict(url=self._child(entry,'input',create(session['session'])))
            from .project_home import prepare
            from .review_server import create
            home=prepare(entry['project'])
            return dict(url=self._child(entry,'review',create(entry['project'],home.get('qa_session'))))

    def run(self,entry):
        with self.guard:
            if self.closing:raise ValueError('Start page is closing; resume from saved projects')
            if self.busy:raise ValueError('A task is already running; wait for completion / 已有任务运行，请等待完成')
            errorfile=BASE/'jobs'/entry['id']/'continuation_error.json'
            if errorfile.is_file():errorfile.unlink()
            self.busy=entry['id'];folder=BASE/'jobs'/entry['id']/unique_id();folder.mkdir(parents=True)
            record=folder/'job.json';job=dict(status='RUNNING',entry=entry,phase='PREPARING',created_utc=utc(),log=rel(folder/'job.log'),pid=os.getpid())
            save(record,job);save(folder.parent/'latest.json',{'path':rel(record)})
            def work():
                try:
                    env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONUNBUFFERED='1')
                    with (folder/'job.log').open('wb') as log:
                        proc=subprocess.Popen([sys.executable,'-m','ras_workflow.launcher_worker',rel(record)],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                        code=proc.wait()
                    finished=read(record)
                    if finished.get('status')=='RUNNING':save(record,dict(finished,status='FAILED',error='Worker stopped; inspect the retained log',exit_code=code))
                except Exception as e:save(record,dict(job,status='FAILED',error=str(e),finished_utc=utc()))
                finally:
                    with self.guard:self.busy=None
                # Failed preparation has no project to open. Opening it would start
                # another worker indefinitely; retries must be an explicit user action.
                if not self.closing and read(record).get('exit_code') in (0,3):
                    try:self.open(find(entry['id']))
                    except Exception as e:
                        finished=read(record);save(record,dict(finished,next_step_error=str(e)))
            thread=threading.Thread(target=work,daemon=False);self.threads.append(thread);thread.start()
            return {'status':'RUNNING','project_id':entry['id']}

    def close(self):
        self.closing=True
        for child in list(self.children.values()):
            child.shutdown();child.server_close()
            if hasattr(child,'actions'):child.actions.close()
        # Requested computations finish and keep their receipts; never terminate user apps.


def create():
    controller=Controller();token=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def setup(self):super().setup();self.connection.settimeout(30)
        def log_message(self,*args):pass
        def send(self,code,data,mime='application/json; charset=utf-8'):
            raw=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8')
            self.send_response(code)
            for k,v in {'Content-Type':mime,'Content-Length':str(len(raw)),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}.items():self.send_header(k,v)
            self.end_headers();self.wfile.write(raw)
        def route(self):
            url=urlsplit(self.path);prefix='/'+token+'/'
            if self.headers.get('Host')!=self.server.address or url.query or not url.path.startswith(prefix):raise ValueError('Invalid local session')
            return url.path[len(prefix):]
        def do_GET(self):
            try:
                route=self.route()
                if route=='state':return self.send(200,controller.state())
                assets={'':('launcher.html','text/html'),'launcher.js':('launcher.js','application/javascript'),'launcher.css':('launcher.css','text/css')}
                if route not in assets:return self.send(404,{'error':'Not found'})
                name,mime=assets[route];self.send(200,(ROOT/'ras_workflow/templates'/name).read_bytes(),mime+'; charset=utf-8')
            except (ValueError,OSError,KeyError,TypeError) as e:self.send(409,{'error':str(e)})
        def do_POST(self):
            try:
                route=self.route()
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=21_000_000:raise ValueError('Invalid request size')
                # Consume the bounded body before a 403. Unread TCP bytes can reset
                # the Windows connection and hide the useful rejection response.
                raw=self.rfile.read(n)
                if self.headers.get('Origin')!=self.server.origin or self.headers.get('X-Launcher-Token')!=token:return self.send(403,{'error':'Use this local start page'})
                if self.headers.get('Content-Type')!='application/json':raise ValueError('Invalid request')
                body=json.loads(raw)
                if not isinstance(body,dict):raise ValueError('Object required')
                if route=='create':
                    if controller.busy:raise ValueError('Wait for the current task to finish')
                    entry=create_entry(body)
                    result=controller.open(entry) if entry.get('review') else controller.run(entry)
                elif route in ('open','run','outputs','open-output'):
                    entry=find(body.get('id'))
                    if route=='open':result=controller.open(entry)
                    elif route=='run':result=controller.run(entry)
                    else:
                        allowed=outputs(entry)
                        if route=='outputs':result={'outputs':[{k:v for k,v in r.items() if k!='evidence'} for r in allowed]}
                        else:
                            target=next((v for v in allowed if v['id']==body.get('output_id')),None)
                            if not target or (target.get('evidence') and not intact([target['evidence']])):raise ValueError('Output changed or unavailable; refresh')
                            path=safe_path(ROOT,target['path'])
                            if target['kind']=='pdf' and path.suffix.lower()!='.pdf':raise ValueError('Only PDF reports can open here')
                            os.startfile(str(path));result={'status':'OPENED'}
                elif route=='close':result={'status':'SAVED_ON_DISK'};self.server.finished.set()
                else:return self.send(404,{'error':'Not found'})
                self.send(200,result)
            except (ValueError,OSError,KeyError,TypeError,RuntimeError) as e:self.send(409,{'error':str(e)})
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    server.address='127.0.0.1:'+str(server.server_port);server.origin='http://'+server.address
    server.url=server.origin+'/'+token+'/';server.token=token;server.finished=threading.Event();server.controller=controller
    controller.url=server.url
    return server


def existing_server():
    """Reuse only a live, token-bound loopback launcher; never trust arbitrary URLs."""
    record=BASE/'local_server.json'
    if not record.is_file():return None
    try:
        saved=read(record);url=urlsplit(saved['url'])
        if url.scheme!='http' or url.hostname!='127.0.0.1' or not url.port or url.query or url.fragment or url.username:return None
        if not re.fullmatch(r'/[A-Za-z0-9_-]{43}/',url.path):return None
        connection=http.client.HTTPConnection('127.0.0.1',url.port,timeout=2)
        try:
            connection.request('GET',url.path+'state');response=connection.getresponse()
            data=json.loads(response.read(2_000_000))
            if response.status==200 and data.get('launcher_instance')==saved.get('instance') and saved.get('instance'):return saved['url']
        finally:connection.close()
    except (ValueError,OSError,KeyError,http.client.HTTPException):pass
    return None


def serve(open_browser=True):
    BASE.mkdir(parents=True,exist_ok=True)
    existing=existing_server()
    if existing:
        print('Existing start page / 已打开的工作流首页: '+existing,flush=True)
        if open_browser:webbrowser.open(existing)
        return 0
    with lock(BASE/'browser.lock'):
        server=create();thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        save(BASE/'local_server.json',dict(url=server.url,pid=os.getpid(),instance=server.controller.instance,started_utc=utc()))
        print('Workflow start page / 工作流首页: '+server.url,flush=True)
        print('Keep this window open. Use Save and close on the page. / 请保持本窗口打开，用网页的保存并关闭退出。',flush=True)
        try:
            if open_browser:webbrowser.open(server.url)
            while not server.finished.wait(.25):pass
        except KeyboardInterrupt:pass
        finally:server.controller.close();server.shutdown();server.server_close();thread.join(timeout=3)
    return 0
