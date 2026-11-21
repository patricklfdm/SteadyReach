"""Run local software regressions and optionally audit a measured benchmark packet."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from ras_workflow.common import read,save,sha,unique_id
from ras_workflow.delivery_pair import check
from ras_workflow.release_metrics import cohort,metrics


def run(args):
    root=REPO/'status/release_checks'/unique_id();root.mkdir(parents=True)
    result=dict(scope='same-machine',tests={},projects=[],field_packet=None,engineering_approval='PENDING')
    def execute(name,cmd):
        start=time.monotonic()
        with (root/(name+'.log')).open('wb') as log:
            test=subprocess.run(cmd,cwd=REPO,stdout=log,stderr=subprocess.STDOUT,timeout=600)
        result['tests'][name]=dict(code=test.returncode,seconds=round(time.monotonic()-start,2),log=name+'.log')
        return test.returncode==0
    passed=execute('python',[sys.executable,'-B','-m','unittest','discover','-s','tests'])
    node=shutil.which('node')
    if node:
        js=execute('page',[node,'--test',*[str(p) for p in sorted((REPO/'tests').glob('*.cjs'))]])
        passed=passed and js
    else:
        result['tests']['page']=dict(error='Node.js unavailable');passed=False
    try:
        groups=read(args.cohort) if args.cohort else {}
        if not isinstance(groups,dict) or any(not isinstance(keys,list) or not all(isinstance(key,str) for key in keys) for keys in groups.values()):raise ValueError('Each cohort site needs a list of project IDs')
        keys=list(dict.fromkeys([*args.project,*[key for group in groups.values() for key in group]]))
        for key in keys:
            folder=REPO/'projects'/key
            if folder.resolve().parent!=REPO/'projects' or not (folder/'app.json').is_file():raise ValueError('Select an existing project ID')
            session=read(args.session) if args.session else None
            result['projects'].append(metrics(folder,session if session and session.get('project_id')==key else None))
        if groups:result['cohort']=cohort(groups,result['projects'])
        if args.packet:
            packet=Path(args.packet).resolve();data=read(packet/'review.json')
            hashes=read(packet/'SHA256.json')
            if not hashes or {p.relative_to(packet).as_posix() for p in packet.rglob('*') if p.is_file() and p!=packet/'SHA256.json'}!=set(hashes):
                raise ValueError('Field packet inventory differs')
            for name,value in hashes.items():
                p=(packet/name).resolve()
                if not p.is_relative_to(packet) or sha(p)!=value:raise ValueError('Field packet changed: '+name)
            pairing=check(packet/'Packages/Complete',packet/'Packages/Minimal')
            matching=[s for s in data['siletz'] if s['run']==pairing['run_id'] and s['native_hash']==pairing['native_hdf_sha256']]
            if len(matching)!=1:raise ValueError('Measured results do not match delivery')
            from release_benchmark import field_screen,east_fork_screen,write_field_notes
            east=east_fork_screen(packet)
            if abs(east['rmse_m']-data['east_fork']['holdout_rmse_m'])>1e-8:
                raise ValueError('East Fork field result and packet summary disagree')
            result['field_packet']=dict(identity=pairing,records=len(hashes),measured=matching[0]['rows'],
                   holdout_rmse_m=data['east_fork']['holdout_rmse_m'],native_warnings=matching[0]['warnings'],
                   siletz_field_screen=field_screen(packet,matching[0],hashes),east_fork_field_screen=east)
            write_field_notes(root,result['field_packet']['siletz_field_screen'],east)
            if args.fresh_benchmark:
                from release_benchmark import replay
                result['fresh_benchmark']=replay(packet,matching[0],hashes,root)
        elif args.fresh_benchmark:raise ValueError('--fresh-benchmark requires --packet with the frozen source inventory')
    except (OSError,ValueError,KeyError) as exc:result['error']=str(exc);passed=False
    result['status']='SOFTWARE_CHECKS_PASSED' if passed else 'NEEDS_ATTENTION'
    save(root/'release.json',result);print(root/'release.json');return 0 if passed else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--packet',type=Path)
    p.add_argument('--project',action='append',default=[]);p.add_argument('--session',type=Path)
    p.add_argument('--cohort',type=Path,help='JSON object mapping pilot site names to their project IDs')
    p.add_argument('--fresh-benchmark',action='store_true',help='Create an isolated project and repeat the native solve and mapped exports from the verified packet')
    raise SystemExit(run(p.parse_args()))
