"""Ephemeral loopback-only form server. No remote hosting, shell or solver endpoints."""
import json
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from .common import ROOT, item, lock, read, rel, safe_path, save, utc
from . import intake


class Server(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=False


def create(session_path):
    session_path=safe_path(ROOT,session_path)
    token=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup();self.connection.settimeout(15)
        def log_message(self,*args):pass  # Do not put the session token into logs.
        def send(self,code,data,mime='application/json; charset=utf-8'):
            if isinstance(data,dict):data=dict(data,launcher_url=getattr(self.server,'launcher_url',None))
            raw=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers();self.wfile.write(raw)
        def route(self):
            if self.headers.get('Host')!=self.server.address or urlsplit(self.path).query:
                raise ValueError('Invalid local request host/query')
            prefix='/'+token+'/'
            path=urlsplit(self.path).path
            if not path.startswith(prefix):raise ValueError('Invalid local session')
            return path[len(prefix):]
        def do_GET(self):
            try:
                route=self.route()
                if route=='state':return self.send(200,intake.view(session_path))
                if route=='intake_native.js':return self.send(200,(ROOT/'ras_workflow/templates/intake_native.js').read_bytes(),'application/javascript; charset=utf-8')
                assets={'geometry_setup.js':('geometry_setup.js','application/javascript; charset=utf-8'),'':('intake.html','text/html; charset=utf-8'),'intake.js':('intake.js','application/javascript; charset=utf-8'),'intake.css':('intake.css','text/css; charset=utf-8'),'geometry_review.js':('geometry_review.js','application/javascript; charset=utf-8')}
                assets['interface.css'] = ('interface.css', 'text/css; charset=utf-8')
                if route not in assets:return self.send(404,dict(error='Not found'))
                filename,mime=assets[route];return self.send(200,(ROOT/'ras_workflow/templates'/filename).read_bytes(),mime)
            except Exception as e:self.send(400,dict(error=str(e)))
        def do_POST(self):
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=21_000_000:raise ValueError('Request exceeds local input limit')
                raw=self.rfile.read(length)
                route=self.route()
                if self.headers.get('Origin')!=self.server.origin or self.headers.get('X-Intake-Token')!=token:
                    return self.send(403,dict(error='This form accepts only its own local browser session'))
                if self.headers.get('Content-Type')!='application/json':raise ValueError('JSON required')
                body=json.loads(raw.decode('utf-8'))
                if not isinstance(body,dict):raise ValueError('Object required')
                if route=='save':result=intake.save_draft(session_path,body)
                elif route=='validate':
                    # Save first so validation and any following approval share one revision.
                    result=intake.save_draft(session_path,body)
                    result['check']=intake.validate(session_path)
                elif route=='upload':result=intake.upload(session_path,body['revision'],body['name'],body['content'],body['kind'],body['basis'],body['evidence_class'])
                elif route in ['native-upload','native-workspace','native-approve']:
                    from . import intake_native
                    action={'native-upload':intake_native.upload,'native-workspace':intake_native.from_workspace,'native-approve':intake_native.approve}[route]
                    result=action(session_path,body)
                elif route=='add':result=intake.edit_structure(session_path,body['revision'],body['kind'])
                elif route=='section-review':
                    from .geometry_workflow import review
                    result=review(session_path,body['revision'],body['index'],body.get('bank_indices'),body.get('reviewer'),body.get('basis'),body.get('action','ACCEPT'),body.get('fingerprint'))
                elif route.startswith('geometry-'):
                    from . import geometry_editor as editor
                    if route=='geometry-map':result=editor.map_view(session_path,body.get('bounds'))
                    elif route=='geometry-generate':result=editor.configure(session_path,body['revision'],body['configuration'])
                    elif route=='geometry-preview':result=editor.preview(session_path,body['revision'],body['index'],body['fingerprint'],body['parameters'])
                    elif route=='geometry-apply':result=editor.apply_preview(session_path,body['revision'],body['preview_id'],body.get('reviewer'),body.get('basis'))
                    elif route=='geometry-alternatives':result=editor.alternatives(session_path,body['index'])
                    else:return self.send(404,dict(error='Not found'))
                elif route=='apply':result=intake.apply(session_path,body['revision'])
                elif route=='cancel':result=intake.cancel(session_path,body['revision'],body.get('reviewer',''),body.get('reason',''),body.get('confirmed',False))
                elif route=='pause':
                    intake.save_draft(session_path,body);result=dict(status=intake.WAITING,saved=True)
                else:return self.send(404,dict(error='Not found'))
                self.send(200,result)
                if route=='pause' or result.get('status') in ['APPLIED','CANCELLED']:
                    self.server.outcome=result;self.server.finished.set()
            except (ValueError,KeyError,TypeError,OSError,RuntimeError) as e:self.send(409,dict(error=str(e)))
    server=Server(('127.0.0.1',0),Handler)
    server.address='127.0.0.1:'+str(server.server_port);server.origin='http://'+server.address
    server.url=server.origin+'/'+token+'/';server.token=token;server.finished=threading.Event();server.outcome=None
    return server


def serve(session_path,open_browser=True):
    sp=safe_path(ROOT,session_path)
    with lock(sp.parent/'browser.lock'):
        s=read(sp)
        if s['status']!='WAITING_FOR_INPUT':return dict(status=s['status'],project=s.get('approved_project'))
        server=create(sp)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        print('Input wizard / 资料填报向导: '+server.url,flush=True)
        print('Close with Save for later, or Ctrl+C. Saved drafts persist. / 保存后可稍后继续。',flush=True)
        save(sp.parent/'local_server.json',dict(url=server.url,host='127.0.0.1',started_utc=utc(),pid=__import__('os').getpid()))
        try:
            if open_browser:webbrowser.open(server.url)
            while not server.finished.wait(.25):pass
            return server.outcome
        except KeyboardInterrupt:return dict(status=intake.WAITING,saved=True)
        finally:
            server.shutdown();server.server_close();thread.join(timeout=5)
            save(sp.parent/'local_server_stopped.json',dict(stopped_utc=utc(),outcome=server.outcome or intake.WAITING))
