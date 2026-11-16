"""Token-protected loopback UI. No command execution or remote file access API."""
import json
import mimetypes
import os
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,unquote
from .common import ROOT,read,save,rel,safe_path,utc,lock
from . import app_core as core

def create():
    token=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        # Keep large DEM/proposal responses alive until Content-Length is consumed.
        # HTTP/1.0 close-after-write reset a >255 KiB local preview on Windows.
        protocol_version='HTTP/1.1'
        timeout=30
        def log_message(self,*args):pass
        def route(self):
            if self.headers.get('Host')!=self.server.address:raise ValueError('Invalid local host')
            url=urlsplit(self.path);prefix='/'+token+'/'
            if not url.path.startswith(prefix) or url.query:raise ValueError('Invalid session')
            return unquote(url.path[len(prefix):])
        def send(self,code,value,mime='application/json; charset=utf-8'):
            raw=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(code)
            if code>=400:
                # Rejected requests may have an unread body; never reuse that stream.
                self.close_connection=True;self.send_header('Connection','close')
            for k,v in {'Content-Type':mime,'Content-Length':str(len(raw)),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',
                'Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}.items():self.send_header(k,v)
            self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            try:
                route=self.route()
                if route=='state':return self.send(200,dict(projects=core.listing(),deleted_projects=core.listing(deleted=True),scope='Single reach, one box/circular culvert crossing, 1D steady flow'))
                if route.startswith('project/'):
                    return self.send(200,core.view(route.split('/',1)[1]))
                if route.startswith('file/'):
                    path=safe_path(ROOT,route[5:])
                    if not path.is_relative_to(ROOT/'projects') or path.suffix.lower() not in ('.pdf','.docx','.json','.txt','.csv','.png','.jpg','.jpeg'):raise ValueError('Unsupported artifact')
                    return self.send(200,path.read_bytes(),mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
                assets={'app_geometry_auto.js':('app_geometry_auto.js','application/javascript; charset=utf-8'),'app_results.js':('app_results.js','application/javascript; charset=utf-8'),'app_automation.js':('app_automation.js','application/javascript; charset=utf-8'),'app_map.js':('app_map.js','application/javascript; charset=utf-8'),'app_section_repair.js':('app_section_repair.js','application/javascript; charset=utf-8'),'':('app.html','text/html; charset=utf-8'),'app.js':('app.js','application/javascript; charset=utf-8'),'app_editor.js':('app_editor.js','application/javascript; charset=utf-8'),'app_sources.js':('app_sources.js','application/javascript; charset=utf-8'),'app.css':('app.css','text/css; charset=utf-8')}
                if route not in assets:return self.send(404,dict(error='Not found'))
                file,mime=assets[route];self.send(200,(ROOT/'ras_workflow/templates'/file).read_bytes(),mime)
            except Exception as e:self.send(400,dict(error=str(e)))
        def do_POST(self):
            with self.server.mutation_lock:self.post()
        def post(self):
            try:
                route=self.route()
                if self.headers.get('Origin')!=self.server.origin or self.headers.get('X-Workflow-Token')!=token:return self.send(403,dict(error='Invalid local request origin'))
                length=int(self.headers.get('Content-Length','0'))
                if self.headers.get('Content-Type')!='application/json' or not 0<length<=70_000_000:raise ValueError('Invalid JSON request size')
                body=json.loads(self.rfile.read(length).decode('utf-8'))
                if not isinstance(body,dict):raise ValueError('JSON object required')
                if route=='create':
                    m=core.create(body)
                    if body.get('native_path') or body.get('files'):core.native_inputs(m['id'],body)
                    result=core.launch(m['id'],'prepare')
                else:
                    key=body['id']
                    if route in ('delete-project','restore-project'):result=core.set_deleted(key,body,deleted=route=='delete-project')
                    elif route=='save':result=core.update(key,body)
                    elif route=='native':result=core.native_inputs(key,body)
                    elif route=='use-native-values':result=core.use_native_values(key,body)
                    elif route=='candidate':result=core.use_candidate(key,body)
                    elif route=='prepare':result=core.launch(key,'prepare')
                    elif route=='automatic-prepare':
                        from .app_autoprepare import queue
                        result=queue(key,body)
                    elif route in ('acquire','analyze'):result=core.launch(key,route)
                    elif route.startswith('sources/'):
                        from . import app_acquisition as acquisition
                        actions={'folder':acquisition.import_folder,'survey':acquisition.configure_survey,'points':acquisition.select_points}
                        result=actions[route.split('/')[1]](key,body)
                    elif route=='opening-associations':
                        from .app_automation import perform
                        result=perform(key,body)
                    elif route=='catalog-import':
                        from .app_catalog import queue
                        result=queue(key,body)
                    elif route=='qgis-preview':
                        from .app_desktop import qgis
                        result=qgis(key,body)
                    elif route in ('study-prepare','study-start'):
                        from . import app_study
                        result=(app_study.prepare if route=='study-prepare' else app_study.start)(key,body)
                    elif route=='native-outputs':
                        from .app_outputs import receive
                        result=receive(key,body)
                    elif route=='revision':
                        from .app_revision import create as revise
                        result=revise(key,body)
                    elif route=='start':result=core.start(key,body)
                    elif route=='review':
                        from .app_parameters import review
                        result=review(core.model(key))
                    elif route in ('report','delivery','native-export'):result=core.launch(key,route)
                    elif route=='attach':result=core.attach(key,body['files'])
                    elif route=='abandon':result=core.abandon(key)
                    elif route.startswith('geometry/'):
                        from .app_geometry import perform
                        result=perform(key,route.split('/')[1],body)
                    elif route=='open-folder':
                        m=core.model(key);path=safe_path(ROOT,body['path'])
                        if not path.is_dir() or not path.is_relative_to(core.folder(key)):raise ValueError('Choose this project\'s output folder')
                        os.startfile(path);result={'opened':rel(path)}
                    else:return self.send(404,dict(error='Unknown action'))
                self.send(200,result)
            except Exception as e:self.send(409,dict(error=str(e)))
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    server.mutation_lock=threading.RLock()
    server.address='127.0.0.1:'+str(server.server_port);server.origin='http://'+server.address;server.url=server.origin+'/'+token+'/'
    return server

def serve(open_browser=True):
    with lock(ROOT/'status/app/server.lock'):
        server=create();save(ROOT/'status/app/server.json',dict(url=server.url,pid=os.getpid(),started_utc=utc()))
        print('SteadyReach / 1D 恒定流工作流: '+server.url,flush=True)
        if open_browser:webbrowser.open(server.url)
        try:server.serve_forever(poll_interval=.5)
        except KeyboardInterrupt:pass
        finally:server.server_close()
    return 0
