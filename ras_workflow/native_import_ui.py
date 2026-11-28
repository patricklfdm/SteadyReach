"""Local browser review of one already-inspected native input copy."""
import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from .common import ROOT, digest, intact, item, lock, read, rel, safe_path, save, utc
from . import native_review

FIELDS=['project_id','title','source','reviewer','vertical_datum','native_length_unit']

def view(path):
    path=safe_path(ROOT,path);packet=read(path)
    if packet.get('schema_version')!='native_import_review_1.0' or not intact(list(packet['files'].values())):
        raise ValueError('Native source copy changed; prepare a new import / 原件副本变化，请重新导入')
    draftpath=path.parent/'browser_draft.json'
    draft=read(draftpath) if draftpath.exists() else dict(revision=0,status='WAITING_FOR_REVIEW',review={k:'' for k in FIELDS},binding=item(path))
    if draft['binding']!=item(path):raise ValueError('Preview changed; prepare a new import / 预览已变化，请重新导入')
    return dict(packet=packet,draft=draft,review_path=rel(path))

def update(path,body,action):
    path=safe_path(ROOT,path)
    with lock(path.parent/'browser_draft.lock'):
        state=view(path);draft=state['draft']
        if type(body.get('revision'))!=int or body['revision']!=draft['revision']:raise ValueError('Draft changed; reload / 草稿已变化，请刷新')
        if draft['status']=='APPROVED':raise ValueError('Import already approved / 已批准，请打开创建的项目')
        if action=='resume':draft['status']='WAITING_FOR_REVIEW'
        elif draft['status']=='ABANDONED':raise ValueError('Resume explicitly before editing / 请先明确恢复已放弃的导入')
        elif action=='abandon':
            if body.get('confirmed') is not True:raise ValueError('Confirm abandoning this import / 请确认放弃导入')
            draft['status']='ABANDONED'
        else:
            review=body.get('review')
            if not isinstance(review,dict) or set(review)!=set(FIELDS) or any(not isinstance(v,str) or len(v)>5000 for v in review.values()):raise ValueError('Invalid review fields / 审核字段无效')
            draft['review']=review
            if action=='approve':
                if body.get('confirmed') is not True:raise ValueError('Explicit approval required / 需要明确确认')
                project=native_review.approve(path,dict(review,approve=True))
                draft.update(status='APPROVED',project=rel(project))
        draft.update(revision=draft['revision']+1,updated_utc=utc())
        save(path.parent/'browser_draft.json',draft)
    return view(path)

def create(path):
    path=safe_path(ROOT,path);view(path);token=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def setup(self):super().setup();self.connection.settimeout(15)
        def send(self,code,value,mime='application/json; charset=utf-8'):
            if isinstance(value,dict):value=dict(value,launcher_url=getattr(self.server,'launcher_url',None))
            raw=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(code)
            for key,value in {'Content-Type':mime,'Content-Length':str(len(raw)),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}.items():self.send_header(key,value)
            self.end_headers();self.wfile.write(raw)
        def route(self):
            url=urlsplit(self.path);prefix='/'+token+'/'
            if self.headers.get('Host')!=self.server.address or url.query or not url.path.startswith(prefix):raise ValueError('Invalid local session')
            return url.path[len(prefix):]
        def do_GET(self):
            try:
                route=self.route()
                if route=='state':return self.send(200,view(path))
                assets={'':('native_import.html','text/html'),'native_import.js':('native_import.js','application/javascript'),'intake.css':('intake.css','text/css')}
                assets['interface.css'] = ('interface.css', 'text/css')
                if route not in assets:return self.send(404,dict(error='Not found'))
                filename,mime=assets[route];self.send(200,(ROOT/'ras_workflow/templates'/filename).read_bytes(),mime+'; charset=utf-8')
            except (ValueError,OSError,KeyError) as e:self.send(409,dict(error=str(e)))
        def do_POST(self):
            try:
                action=self.route();n=int(self.headers.get('Content-Length','0'))
                if self.headers.get('Content-Type')!='application/json' or not 0<n<=50000:raise ValueError('Invalid request')
                raw=self.rfile.read(n)
                if self.headers.get('Origin')!=self.server.origin or self.headers.get('X-Import-Token')!=token:return self.send(403,dict(error='Invalid browser session'))
                if action not in ['save','pause','approve','abandon','resume']:return self.send(404,dict(error='Not found'))
                body=json.loads(raw)
                if not isinstance(body,dict):raise ValueError('Object required')
                result=update(path,body,action);self.send(200,result)
                if action in ['approve','pause','abandon']:self.server.outcome=result['draft'];self.server.finished.set()
            except (ValueError,OSError,KeyError,TypeError) as e:self.send(409,dict(error=str(e)))
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    server.address='127.0.0.1:'+str(server.server_port);server.origin='http://'+server.address
    server.url=server.origin+'/'+token+'/';server.token=token;server.finished=threading.Event();server.outcome=None
    return server

def serve(path,open_browser=True):
    path=safe_path(ROOT,path)
    current=view(path)['draft']
    if current['status']=='APPROVED':return ROOT/current['project']
    with lock(path.parent/'browser.lock'):
        server=create(path);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        print('Native import review / 原生导入审核: '+server.url,flush=True)
        save(path.parent/'local_server.json',dict(url=server.url,started_utc=utc(),pid=__import__('os').getpid()))
        try:
            if open_browser:webbrowser.open(server.url)
            while not server.finished.wait(.25):pass
            return ROOT/server.outcome['project'] if server.outcome.get('status')=='APPROVED' else None
        except KeyboardInterrupt:return None
        finally:
            server.shutdown();server.server_close();thread.join(timeout=5)
            save(path.parent/'local_server_stopped.json',dict(stopped_utc=utc(),outcome=server.outcome or 'SAVED_DRAFT_RETAINED'))
