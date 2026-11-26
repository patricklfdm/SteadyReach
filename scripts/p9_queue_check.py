"""Exercise the production queue in an isolated checkout with three explicit test faults."""
import argparse
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import subprocess
import sys
import threading
import time
from unittest.mock import patch
from zipfile import ZipFile
import json

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ras_workflow import app_core as core, queue, queue_operations as ops
from ras_workflow.common import digest, item, read, rel, save, sha, unique_id
from ras_workflow.delivery_pair import check
from ras_workflow.qa import verified_profiles


def require(value,message):
    if not value:raise ValueError(message)


def fault_worker(path,kind):
    """These hooks exist only in this test process. Normal CLI jobs load no fault code."""
    from ras_workflow import queue_worker, qgis_runtime, site_delivery
    marker=path.parent/'injected.json'
    original=site_delivery.copy_file
    def locked_copy(source,destination):
        if Path(source).suffix.lower()!='.docx' or marker.exists():
            return original(source,destination)
        import win32file,win32con
        handle=win32file.CreateFile(str(source),win32con.GENERIC_READ,0,None,win32con.OPEN_EXISTING,0,None)
        try:
            save(marker,dict(point='actual required DOCX open with zero sharing',source=item_path(source)))
            return original(source,destination)
        finally:handle.Close()
    def export_failure(*args,**kwargs):
        save(marker,dict(point='controlled QGIS process timeout during actual delivery'))
        raise TimeoutError('P9 acceptance: simulated renderer timeout')
    sys.argv=[sys.argv[0],str(path)]
    if kind=='locked':
        with patch.object(site_delivery,'copy_file',locked_copy):return queue_worker.main()
    with patch.object(qgis_runtime,'run',export_failure):return queue_worker.main()


def item_path(source):
    # File contents cannot be opened while the injected Windows sharing lock is held.
    return rel(Path(source))


@contextmanager
def faults_enabled():
    original=subprocess.Popen
    def start(command,*args,**kwargs):
        if isinstance(command,list) and command[1:3]==['-m','ras_workflow.queue_worker']:
            path=Path(command[3]);spec=read(path)
            kind=spec['job']['id']
            if spec['fresh'] and kind in ('locked','export'):
                command=[command[0],str(Path(__file__).resolve()),'--worker',str(path),'--fault',kind]
        return original(command,*args,**kwargs)
    with patch.object(subprocess,'Popen',start):yield


def interrupt_started(work,active_config,outcome,stop):
    deadline=time.monotonic()+150
    known=set((active_config.parent/'jobs').glob('*'))
    while not stop.is_set() and time.monotonic()<deadline:
        for new in set((active_config.parent/'jobs').glob('*'))-known:
            for record in new.glob('solver__*/execution.json'):
                data=read(record)
                if data.get('owned_app_pid') and not data['compute_completed']:
                    outcome.update(run=data['run_id'],native_process_started=True,stage=data['stages'][-1]['stage'])
                    ops.control(rel(work),'interrupt','cancel')
                    return
        stop.wait(.05)


def verify_pair(attempt):
    receipt,summary=queue.validate_receipt(attempt['receipt'])
    native=summary['hydraulics'];profiles=verified_profiles(native)
    pair=check(*(ROOT/receipt['delivery'][k]['path'] for k in ('complete','minimal')))
    require(pair['run_id']==native['run_id'] and pair['native_hdf_sha256']==native['raw_hdf']['sha256'],'Package/native mismatch')
    return dict(run=native['run_id'],sha256=native['raw_hdf']['sha256'],sections={k:len(v) for k,v in profiles.items()},
                packages={k:receipt['delivery'][k]['path'] for k in ('complete','minimal')},timing=attempt['stage_seconds'])


def run(root,edition):
    out=root/'p9_operations';out.mkdir(exist_ok=False)
    model=core.model(edition);config=ROOT/model['active_project'];scenario=model['run_scenario']
    ids=['interrupt','export','locked',*('ordinary_'+str(n) for n in range(1,8))]
    jobs=[dict(id=n,project=rel(config),scenario=scenario) for n in ids]
    spec=out/'spec.json';work=out/'queue'
    save(spec,dict(schema_version='1.0',queue_id='operations',jobs=jobs))
    receipt=dict(status='RUNNING',faults={},project=edition);target=out/'operations.json';save(target,receipt)
    stop=threading.Event();injection={}
    watcher=threading.Thread(target=interrupt_started,args=(work,config,injection,stop),daemon=True)
    watcher.start()
    try:
        with faults_enabled():queue.run(spec,work,fresh=True)
    finally:
        stop.set();watcher.join(5)
    state=read(work/'queue_state.json')['jobs']
    require(injection.get('native_process_started') and state['interrupt'][-1]['status']=='CANCELLED','Owned native job was not interrupted')
    for key in ('locked','export'):
        row=state[key][-1]
        require(row['status']=='NEEDS_EXPORT' and (ROOT/row['folder']/'injected.json').exists(),'Expected export-stage stop: '+key)
        receipt['faults'][key]=dict(run=row['run_id'],fingerprint=read(ROOT/row['summary']['path'])['hydraulics']['raw_hdf']['sha256'])
    require(all(state[key][-1]['status']=='COMPLETED' for key in ids[3:]),'Unexpected failure in ordinary calculation')
    receipt['faults']['interrupt']=injection
    save(target,receipt)
    ops.control(rel(work),'interrupt','resume')
    # A cancelled attempt has no matching completed native output of its own. Request a fresh
    # solver stage for this job only, through normal queue resumption.
    queue.run(spec,work)
    state=read(work/'queue_state.json')['jobs']
    cases={}
    for key,attempts in state.items():
        require(attempts[-1]['status']=='COMPLETED','Pending operation: '+key)
        cases[key]=verify_pair(attempts[-1])
        if key in ('locked','export'):
            require(len(attempts)==2 and attempts[-1]['solver_reused'] and cases[key]['timing']['solver']==0
                    and cases[key]['run']==receipt['faults'][key]['run'] and cases[key]['sha256']==receipt['faults'][key]['fingerprint'],
                    'Export retry repeated or changed hydraulics: '+key)
        elif key=='interrupt':
            require(len(attempts)==2 and not attempts[-1]['solver_reused'] and cases[key]['run']!=injection['run'],
                    'Interrupted native job did not receive a new, verified solve')
        elif key.startswith('ordinary'):
            require(len(attempts)==1,'Verified completed work repeated')
    reservations=[(a['started_utc'],a['finished_utc']) for attempts in state.values() for a in attempts if a.get('started_utc')]
    intervals=sorted((datetime.fromisoformat(a),datetime.fromisoformat(b)) for a,b in reservations)
    require(all(a[1]<=b[0] for a,b in zip(intervals,intervals[1:])),'Queue worker ownership overlapped')
    import shutil
    low=out/'low_space';low.mkdir()
    try:
        with ops.reserve(low,shutil.disk_usage(low).free+1):pass
    except ops.SpaceUnavailable:receipt['low_space']='REJECTED'
    else:raise ValueError('Impossible space reservation accepted')
    preview=ops.support(rel(work));bundle=ops.export_support(rel(work),out/'Support.zip',digest(preview))
    with ZipFile(bundle) as z:
        require(z.namelist()==['Support.json'] and json.loads(z.read('Support.json'))==preview,'Support preview and archive differ')
        raw=z.read('Support.json').decode()
    require(not any(v in raw for v in (str(ROOT),edition,'projects/','.pdf',':\\')),'Unexpected private data in support bundle')
    receipt.update(status='PASSED',cases=cases,operator_context='automated',sequential_attempts=len(intervals),support=item(bundle))
    save(target,receipt);return target


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--worker',type=Path);cli.add_argument('--fault',choices=('locked','export'))
    cli.add_argument('--edition');cli.add_argument('--output',type=Path)
    args=cli.parse_args()
    if args.worker:raise SystemExit(fault_worker(args.worker,args.fault))
    print(run(args.output.resolve(),args.edition))
