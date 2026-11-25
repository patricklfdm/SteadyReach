"""Same-workstation P6 acceptance through normal intake and confirmation paths."""
from contextlib import contextmanager
from pathlib import Path
import os
import shutil
import socket
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ras_workflow import app_core as core,intake_freeze as freeze
from ras_workflow.common import ROOT,digest,intact,read,rel,save,sha
from ras_workflow.intake_register import context
from midway_release import need,page_action


@contextmanager
def isolated_sources(source,key):
    """Stage one historical sealed input edition. Remove only files created here."""
    project=source/'projects'/key
    m=read(project/'app.json');created=[]
    def copy(name):
        src=(source/name).resolve();dst=(ROOT/name).resolve()
        if not src.is_relative_to(source) or not dst.is_relative_to(ROOT) or dst.relative_to(ROOT).parts[0] not in ('projects','data','status','examples'):
            raise ValueError('Invalid retained source path')
        if dst.exists():
            need(sha(src)==sha(dst),'Isolation path already has different content: '+name);return
        dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);created.append(dst)
    try:
        for name in ('projects/'+key+'/app.json',m['pending_review']['path'],(m.get('source_analysis') or {}).get('path'),m.get('task')):
            if name:copy(name)
        config=read(ROOT/m['pending_review']['path'])['inputs']['configuration'];settings=config.get('delivery',{})
        raster=(settings.get('imagery') or {}).get('raster')
        for name in ([raster,*settings.get('additional_sources',[])] if raster else []):
            src=((source/m['project']).parent/name).resolve()
            if src.is_file():copy(src.relative_to(source).as_posix())
        ctx=context(core.model(key))
        for r in ctx['sources']:copy(r['path'])
        yield core.model(key)
    finally:
        for path in reversed(created):path.unlink(missing_ok=True)
        for parent in sorted({p for f in created for p in f.parents if p!=ROOT and p.is_relative_to(ROOT)},key=lambda p:-len(p.parts)):
            if parent.is_dir() and not any(parent.iterdir()):parent.rmdir()


@contextmanager
def offline_providers(folder):
    """Block public DNS and network sockets in the app and its Python workers."""
    from contextlib import ExitStack
    from unittest.mock import patch
    hooks=folder/'offline';hooks.mkdir();log=hooks/'connections.log'
    guard="""import os,sys
from ipaddress import ip_address
from pathlib import Path
log=Path(os.environ['STEADYREACH_P6_NETWORK_LOG'])
def write(msg):
    with log.open('a',encoding='utf-8') as f: f.write(str(os.getpid())+' '+msg+'\\n')
def verify(host):
    if isinstance(host,bytes):host=host.decode()
    if host is None or host in ('localhost',''):return
    try:
        if ip_address(host).is_loopback:return
    except ValueError:pass
    write('DENIED '+str(host))
    raise OSError('Frozen replay disallows public provider access')
def hook(event,args):
    if event=='socket.getaddrinfo':verify(args[0])
    if event=='socket.connect' and isinstance(args[1],tuple):verify(args[1][0])
write('ACTIVE')
"""
    (hooks/'sitecustomize.py').write_text(guard+'sys.addaudithook(hook)\n',encoding='utf-8')
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ,{'PYTHONPATH':str(hooks)+os.pathsep+os.environ.get('PYTHONPATH',''),
            'PROJ_NETWORK':'OFF','STEADYREACH_P6_NETWORK_LOG':str(log)}))
        namespace={};exec(guard,namespace);verify=namespace['verify']
        connect=socket.socket.connect;resolve=socket.getaddrinfo
        def checked(sock,address):
            if isinstance(address,tuple):verify(address[0])
            return connect(sock,address)
        def checked_dns(host,*args,**kwargs):
            verify(host);return resolve(host,*args,**kwargs)
        stack.enter_context(patch.object(socket.socket,'connect',checked))
        stack.enter_context(patch.object(socket,'getaddrinfo',checked_dns))
        yield log


def capture(key):
    model=core.model(key);ctx,register=freeze.build(model)
    frozen=freeze.perform(key,'freeze',dict(token=digest(ctx)))
    with patch.object(socket.socket,'connect',side_effect=AssertionError('Network used during replay')),patch('socket.getaddrinfo',side_effect=AssertionError('DNS used during replay')):
        verified=freeze.perform(key,'replay',{})
    need(verified['register']==register and verified['register_hash']==digest(register),'Frozen register differs')
    return register,dict(id=key,frozen=frozen['archive'],register_hash=verified['register_hash'],objects=verified['objects'],searches=register['searches'],
        evidence={r['category']:dict(status=r['status'],dates=r['dates'],sources=len(r['sources']),
            requested_fields=r['requested_fields'],request=r['request'],datum=r['datum'],unit=r['unit']) for r in register['records']},
        boundary=register['boundary'])


def soquel_source(source):
    items=read(source/'status/soquel_native_warnings_20261120/source_receipts.json')
    ref=next(r for r in items if r['path'].endswith('/app.json'))
    need(sha(source/ref['path'])==ref['sha256'],'Soquel source edition differs')
    return Path(ref['path']).parent.name


def check_case(label,register):
    rec={r['category']:r for r in register['records']};b=register['boundary']
    if label=='Midway':
        invert=[f for f in rec['structure']['fields'] if f['key'].endswith(('us_invert_ft','ds_invert_ft'))]
        need(len(invert)>=2 and all(f['missing'] or f['classification'] in ('assumed','inferred','terrain_derived') for f in invert),'Buried inverts should require measurement')
        need('inlet' in rec['structure']['request'][0],'Missing specific measurement request')
    elif label=='Soquel':
        gage=next(s for s in b['stations'] if s['station']=='11160000')
        need(gage['distance_to_boundary_center_m']>5 and b['status']=='NO_BOUNDARY_OBSERVATION' and gage['datum']=='NGVD29','Unsupported off-site stage passed')
        need({'EMPTY','UNAVAILABLE','FOUND'}.issubset({q['outcome'] for q in register['searches']}),'Soquel search outcomes merged')
    else:
        need(rec['channel']['status']=='DOCUMENTED_BASIS' and any(r.get('visit') for r in rec['flow']['metadata']),'Missing published survey or paired event identity')
        need(any(r['role']=='holdout' and r['status']=='CONTEXT' for r in b['rows']),'Interior Dexter holdout became a boundary')


def run(gate,historical_root):
    """Start with a fresh interpreter so earlier gates cannot supply a cached intake or provider."""
    import subprocess
    subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),str(gate),str(historical_root)],
                   cwd=ROOT,check=True)
    return gate/'p6/release.json'


def accept(gate,historical_root):
    out=gate/'p6';out.mkdir(exist_ok=True);record=dict(status='RUNNING',cases={},human='DEFERRED',cross_machine='DEFERRED')
    dest=out/'release.json';save(dest,record)
    try:
        mid=read(gate/'midway.json')['first']['project'];dex=read(gate/'p4/release.json')['revision']
        def visit(label,key):
            register,case=capture(key);record['cases'][label]=case;check_case(label,register);save(dest,record)
        visit('Midway',mid);visit('Dexter',dex)
        for key in (mid,dex):need(page_action(key,'p6-evidence')=='VERIFIED','Evidence page failed to freeze and replay')
        from ras_workflow.app_revision import create_draft
        annotated=create_draft(core.model(mid),{})['id']
        original=page_action(annotated,'p6-annotate')
        _,updated=freeze.build(core.model(annotated))
        rec=next(r for r in updated['records'] if r['category']=='structure')
        need(any(note.get('source_sha256')==original and note.get('version')=='SHA-256 '+original for note in rec['metadata']),
             'Metadata was not saved against its original')
        record['metadata_entry']=dict(edition=annotated,original_sha256=original)
        key=soquel_source(historical_root)
        with isolated_sources(historical_root,key):visit('Soquel',key)
        case=record['cases']['Soquel'];archive=ROOT/case['frozen']['path']
        with patch.object(socket.socket,'connect',side_effect=AssertionError('Live lookup after detachment')),patch('socket.getaddrinfo',side_effect=AssertionError('Live DNS after detachment')):
            detached=freeze.replay(archive,case['frozen']['sha256'])
        need(detached['register_hash']==case['register_hash'] and not (ROOT/'projects'/key/'app.json').exists(),
             'Detached historical edition still requires its source checkout')
        case['detached_replay']=True;save(dest,record)
        changes={}
        for name,v in read(gate/'p4/midway_returns.json').items():
            if not isinstance(v,dict):continue
            key=v['project'];m=core.model(key)
            if m.get('run_confirmation'):scope=read(ROOT/m['run_confirmation']['path'])['return_scope']
            else:
                from ras_workflow.app_parameters import review
                scope=review(m)['return_scope']
            need(scope['mode']=='CHANGES_ONLY' and scope['retained'],'No inherited hydraulic confirmation')
            direct=[r for r in scope['affected'] if r['reason']=='RETURNED'];need(len(direct)==v['fields'],'Incorrect number of returned values')
            need(all(r['key'].endswith(('us_invert_ft','ds_invert_ft')) for r in scope['affected']),'Unrelated Midway field reopened')
            import json
            metric=out/(name+'_return_page.json')
            browser=json.loads(page_action(key,'p6-review-changes',metrics=str(metric))) if not m.get('run_confirmation') else {'native_confirmation':m['run_confirmation']}
            actual=read(metric if metric.is_file() else gate/'p4/midway_both_solve_page.json')['entries']
            need(not any(k.startswith('input-') for k in actual),'Unchanged parameters were re-entered');browser['dom_inputs']=actual
            changes[name]=dict(affected=scope['affected'],carried=len(scope['retained']),browser=browser)
        dex_scope=read(ROOT/core.model(dex)['run_confirmation']['path'])['return_scope']
        need(dex_scope['mode']=='CHANGES_ONLY' and not dex_scope['affected'],'Observation-only return reopened hydraulic fields')
        record['observation_return']=dict(affected=0,carried=len(dex_scope['retained']))
        from p5_release import hydraulic_outputs,open_packages
        with tempfile.TemporaryDirectory(dir=out,prefix='recovered_survey_') as temp:
            with patch.object(socket.socket,'connect',side_effect=AssertionError('Network used to recover survey')):
                imagery=Path(temp)/'Imagery';folder=freeze.survey_copy(ROOT/record['cases']['Dexter']['frozen']['path'],Path(temp)/'survey',imagery)
            with offline_providers(Path(temp)) as network:
                protocol=read(ROOT/'examples/dexter_or/protocol.json')
                criteria={'accept-profile':'Visit20151001','accept-event':'Visit20151001','accept-rs':'500',
                          'accept-error':protocol['threshold_ft'],'accept-basis':protocol['threshold_basis']}
                child=page_action(None,'home-survey',title='Dexter · frozen source replay',folder=str(folder),criteria=criteria,protocol=False,
                                  rasters=[str(imagery/n) for n in ('Aerial.tif','acquisition.json')])
                page_action(child,'survey-solve')
                network_events=network.read_text(encoding='utf-8').splitlines()
            need(len({s.split()[0] for s in network_events if s.endswith(' ACTIVE')})>=2 and not any(' DENIED ' in s for s in network_events),
                 'A worker missed the provider guard or attempted an external lookup: '+str(network_events))
            old,z,q=hydraulic_outputs(dex);new,z2,q2=hydraulic_outputs(child)
            need(new!=old and z==z2 and q==q2,'Frozen hydraulic replay differs at a station or discharge')
            handoff=ROOT/page_action(child,'transfer-current');pair=open_packages(handoff)
            need(pair['run']==new,'Replayed handoff differs from the fresh native result')
            rows=[dict(profile=name,rs=station,original_stage_ft=value,replayed_stage_ft=z2[name][station],
                       original_flow_cfs=q[name][station],replayed_flow_cfs=q2[name][station])
                  for name,profile in z.items() for station,value in profile.items()]
            record['native_replay']=dict(original=old,new=new,id=child,station_profiles=len(rows),sections=rows,
                max_stage_difference_ft=max(abs(r['replayed_stage_ft']-r['original_stage_ft']) for r in rows),
                max_flow_difference_cfs=max(abs(r['replayed_flow_cfs']-r['original_flow_cfs']) for r in rows),
                handoff=str(handoff),pair=pair,python_network_audit=network_events)
        record.update(status='PASSED',returns=changes)
    except Exception as error:
        record.update(status='FAILED',error=str(error));raise
    finally:save(dest,record)
    return dest


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('gate',type=Path)
    parser.add_argument('historical_root',type=Path)
    args=parser.parse_args()
    folder=args.gate.resolve()
    need(folder.is_relative_to(ROOT/'status/release_checks') and folder.is_dir(),'Use an isolated release cohort')
    accept(folder,args.historical_root.resolve())
