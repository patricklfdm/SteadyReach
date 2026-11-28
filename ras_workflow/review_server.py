"""Token-bound loopback project/QA UI. Serves only enumerated, hashed artifacts."""
import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from pathlib import Path
from .common import ROOT, intact, lock, read, safe_path, save, utc
from . import qa_session, project_home


def create(project=None, session=None):
    project=safe_path(ROOT,project) if project else None
    session=safe_path(ROOT,session) if session else None
    if not project and not session:raise ValueError('Project or QA session required')
    token=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def setup(self):super().setup();self.connection.settimeout(20)
        def log_message(self,*args):pass
        def send(self,code,data,mime='application/json; charset=utf-8',attachment=None):
            raw=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8')
            self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if attachment:
                import urllib.parse
                self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+urllib.parse.quote(attachment,safe=''))
            self.end_headers();self.wfile.write(raw)
        def route(self):
            url=urlsplit(self.path)
            if self.headers.get('Host')!=self.server.address or url.query:raise ValueError('Invalid local host/query')
            prefix='/'+token+'/'
            if not url.path.startswith(prefix):raise ValueError('Invalid local session')
            return url.path[len(prefix):]
        def state(self):
            qa=None;error=None
            if self.server.session:
                try:qa=qa_session.view(self.server.session)
                except (ValueError,OSError,KeyError) as e:error=str(e)
            return dict(home=project_home.inspect(project) if project else None,qa=qa,qa_error=error,launcher_url=getattr(self.server,'launcher_url',None),
                action=self.server.actions.view() if self.server.actions else None)
        def do_GET(self):
            try:
                route=self.route()
                if route=='state':return self.send(200,self.state())
                if route=='action-status':return self.send(200,self.server.actions.view() if self.server.actions else None)
                if route.startswith('artifact/'):
                    state=self.state();allowed=[]
                    for key in ['home','qa']:
                        if state[key]:allowed+=state[key]['artifacts']
                    e=next((e for e in allowed if e['id']==route[9:]),None)
                    if not e or not intact([e]):raise ValueError('Artifact is unavailable or changed')
                    p=safe_path(ROOT,e['path']);suffix=p.suffix.lower()
                    mimes={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.pdf':'application/pdf'}
                    return self.send(200,p.read_bytes(),mimes.get(suffix,'application/octet-stream'),p.name if suffix not in mimes else None)
                assets={'report_options.js':('report_options.js','application/javascript; charset=utf-8'),'':('review.html','text/html; charset=utf-8'),'project_actions.js':('project_actions.js','application/javascript; charset=utf-8'),'review.js':('review.js','application/javascript; charset=utf-8'),'review.css':('review.css','text/css; charset=utf-8')}
                assets['interface.css'] = ('interface.css', 'text/css; charset=utf-8')
                if route not in assets:return self.send(404,dict(error='Not found'))
                filename,mime=assets[route];self.send(200,(ROOT/'ras_workflow/templates'/filename).read_bytes(),mime)
            except (ValueError,KeyError,TypeError,OSError,RuntimeError) as e:self.send(409,dict(error=str(e)))
        def do_POST(self):
            try:
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=15_000_000:raise ValueError('Request exceeds local limit')
                raw=self.rfile.read(n)
                route=self.route()
                if self.headers.get('Origin')!=self.server.origin or self.headers.get('X-Review-Token')!=token:
                    return self.send(403,dict(error='Only the current local browser session can edit this review'))
                if self.headers.get('Content-Type')!='application/json':raise ValueError('JSON required')
                body=json.loads(raw.decode('utf-8'))
                if not isinstance(body,dict):raise ValueError('Object required')
                sp=self.server.session
                if route=='close':result=dict(status='SAVED_ON_DISK')
                elif route=='project-action':
                    if not self.server.actions:raise ValueError('Project action requires a project')
                    if body.get('action')=='QA':
                        home=project_home.inspect(project)
                        if home['project_sha256']!=body.get('project_sha256'):raise ValueError('Project changed; refresh')
                        baseline=None
                        if body.get('previous_run_id'):
                            matches=[r for r in home['previous_runs'] if r['run_id']==body['previous_run_id']]
                            if len(matches)!=1:raise ValueError('Previous run is unavailable or ambiguous')
                            baseline=matches[0]['summary']['path']
                        result=project_home.prepare(project,baseline=baseline);self.server.session=ROOT/result['qa_session'] if result.get('qa_session') else None
                    else:result=self.server.actions.start(body)
                elif not sp:raise ValueError('No computed QA session yet; complete the next project action')
                elif route=='save':result=qa_session.save_draft(sp,body)
                elif route=='upload':result=qa_session.upload(sp,body['revision'],body['name'],body['content'])
                elif route=='investigation':result=qa_session.prepare_investigation(sp,body)
                elif route=='submit':result=qa_session.submit(sp,body['revision'])
                elif route=='cancel':result=qa_session.cancel(sp,body['revision'],body.get('reviewer'),body.get('reason'),body.get('confirmed'))
                elif route=='resume':result=qa_session.resume(sp,body['revision'])
                elif route=='warnings':
                    result=qa_session.import_warnings(sp,body);self.server.session=ROOT/result['session']
                else:return self.send(404,dict(error='Not found'))
                self.send(200,result)
                if route=='close':self.server.outcome=result;self.server.finished.set()
            except (ValueError,KeyError,TypeError,OSError,RuntimeError) as e:self.send(409,dict(error=str(e)))
    class Server(ThreadingHTTPServer):
        daemon_threads=True
        allow_reuse_address=False
    s=Server(('127.0.0.1',0),Handler);s.address='127.0.0.1:'+str(s.server_port);s.origin='http://'+s.address
    s.url=s.origin+'/'+token+'/';s.token=token;s.finished=threading.Event();s.outcome=None;s.session=session
    from .project_actions import Actions
    s.actions=Actions(project) if project else None
    return s


def serve(project=None, session=None, open_browser=True):
    base=safe_path(ROOT,session).parent if session else safe_path(ROOT,project).parent/'portal'
    base.mkdir(parents=True,exist_ok=True)
    with lock(base/'browser.lock'):
        server=create(project,session);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        print('Project / QA review: '+server.url,flush=True)
        print('Use Save and close, or Ctrl+C. Only saved changes persist.',flush=True)
        save(base/'local_server.json',dict(url=server.url,started_utc=utc(),pid=__import__('os').getpid()))
        try:
            if open_browser:webbrowser.open(server.url)
            while not server.finished.wait(.25):pass
            return server.outcome
        except KeyboardInterrupt:return dict(status='SAVED_CHANGES_PRESERVED')
        finally:
            server.shutdown();server.server_close();thread.join(timeout=5)
            if server.actions:server.actions.close()
            save(base/'local_server_stopped.json',dict(stopped_utc=utc(),outcome=server.outcome or 'INTERRUPTED'))
