"""Run same-machine release regressions, including the mandatory fresh Midway lifecycle."""
import argparse
import os
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
    if getattr(args,'p10',False):
        from pilot_metrics import sample_storage,storage_summary,write_summary
        with sample_storage(REPO,root):
            status=run_checks(args,root)
        state=read(root/'release.json')
        state['storage']=storage_summary(root/'storage_samples.jsonl')
        state['pilot_reports']=write_summary(root,state['storage'])
        save(root/'release.json',state)
        return status
    return run_checks(args,root)


def run_checks(args,root):
    result=dict(scope='same-machine',release_gate='P2' if args.p2 else 'standard',tests={},projects=[],field_packet=None,engineering_approval='PENDING')
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
            if passed and getattr(args,'p3',False):
                result['release_gate']='P3'
                from p3_release import run as journeys
                fixture=Path(args.midway_fixture or os.environ['STEADYREACH_MIDWAY_FIXTURE']).resolve()
                journeys(packet,fixture,args.transfer_survey.resolve(),root/'p3',args.transfer_imagery)
                result['p3']=dict(status='PASSED',receipt='p3/journeys.json',sha256=sha(root/'p3/journeys.json'))
            if passed and args.fresh_benchmark:
                from release_benchmark import replay
                result['fresh_benchmark']=replay(packet,matching[0],hashes,root,p2=args.p2)
        elif args.fresh_benchmark:raise ValueError('--fresh-benchmark requires --packet with the frozen source inventory')
    except (OSError,ValueError,KeyError,TypeError,RuntimeError,subprocess.SubprocessError) as exc:
        result['error']=str(exc);passed=False
    fixture = args.midway_fixture or os.environ.get('STEADYREACH_MIDWAY_FIXTURE')
    if not fixture:
        result['midway'] = dict(status='REQUIRED',reason='Set --midway-fixture to the private source manifest to exercise all three native calculations and the detached handoff.')
        passed=False
    elif passed:
        try:
            from midway_release import replay
            replay(Path(fixture),root/'midway.json')
            result['midway'] = dict(status='PASSED',receipt='midway.json',sha256=sha(root/'midway.json'))
        except (OSError,ValueError,KeyError,RuntimeError,TypeError,subprocess.SubprocessError) as exc:
            result['midway'] = dict(status='FAILED',error=str(exc))
            passed=False
    else:
        result['midway'] = dict(status='NOT_RUN',reason='Fix preceding release checks first.')
    if getattr(args,'p3',False) and 'p3' not in result:
        result['release_gate']='P3'
        evidence=root/'p3/journeys.json'
        result['p3']=dict(status='FAILED' if evidence.exists() else 'NOT_RUN',error=result.get('error'),
                          receipt='p3/journeys.json' if evidence.exists() else None)
    if getattr(args,'p4',False):
        result['release_gate']='P4'
        result['p4']=dict(status='NOT_RUN')
        if passed:
            from p4_release import run as holdout,midway_returns
            try:
                output=root/'p4'
                holdout(args.dexter_survey.resolve(),args.dexter_observation.resolve(),args.dexter_imagery.resolve(),output)
                prev=read(root/'p3/journeys.json')['cases']
                midway_returns(prev['Midway']['revised']['project'],output)
                from midway_release import page_action,need
                priorities=page_action(prev['Siletz']['revision']['project'],'priority-read')
                need('44056' in priorities or '0.524' in priorities,'Missing Siletz event priority')
                historic=subprocess.check_output([sys.executable,'-B',str(REPO/'scripts/p4_archived.py'),str(args.historical_root.resolve())],cwd=REPO)
                import json
                save(output/'historical.json',dict(archives=json.loads(historic),siletz_priorities=priorities))
                result['p4']=dict(status='PASSED',receipts={n:sha(output/n) for n in ('release.json','midway_returns.json','historical.json')})
            except (OSError,ValueError,KeyError,TypeError,RuntimeError,subprocess.SubprocessError) as exc:
                result['p4']=dict(status='FAILED',error=str(exc))
                passed=False
    if getattr(args,'p5',False):
        result['release_gate']='P5';result['p5']=dict(status='NOT_RUN')
        if passed:
            from p5_release import run as storage_recovery
            try:
                receipt=storage_recovery(root,args.p5_archive_dir.resolve())
                result['p5']=dict(status='PASSED',receipt='p5/release.json',sha256=sha(receipt))
            except (OSError,ValueError,KeyError,RuntimeError,TypeError,subprocess.SubprocessError) as exc:
                result['p5']=dict(status='FAILED',error=str(exc));passed=False
    if getattr(args,'p6',False):
        result['release_gate']='P6';result['p6']=dict(status='NOT_RUN')
        if passed:
            from p6_release import run as intake_acceptance
            try:
                receipt=intake_acceptance(root,args.historical_root.resolve())
                result['p6']=dict(status='PASSED',receipt='p6/release.json',sha256=sha(receipt))
            except (OSError,ValueError,KeyError,RuntimeError,TypeError,subprocess.SubprocessError) as exc:
                result['p6']=dict(status='FAILED',error=str(exc));passed=False
    if getattr(args,'p7',False):
        result['release_gate']='P7';result['p7']=dict(status='NOT_RUN')
        if passed:
            from p7_release import run as confidence
            try:
                receipt=confidence(root,args.historical_root.resolve(),args.p7_visits.resolve())
                result['p7']=dict(status='PASSED',receipt='p7/release.json',sha256=sha(receipt))
            except (OSError,ValueError,KeyError,TypeError,RuntimeError,subprocess.SubprocessError) as exc:
                result['p7']=dict(status='FAILED',error=str(exc));passed=False
    if getattr(args,'p8',False):
        result['release_gate']='P8';result['p8']=dict(status='NOT_RUN')
        if passed:
            from p8_release import run as controlled_review
            try:
                receipt=controlled_review(root)
                result['p8']=dict(status='PASSED',receipt='p8/release.json',sha256=sha(receipt))
            except (OSError,ValueError,KeyError,TypeError,RuntimeError,subprocess.SubprocessError) as exc:
                result['p8']=dict(status='FAILED',error=str(exc));passed=False
    if getattr(args,'p9',False):
        result['release_gate']='P9';result['p9']=dict(status='NOT_RUN')
        if passed:
            from p9_release import run as operations_check
            try:
                receipt=operations_check(root,args.p9_fixture.resolve())
                result['p9']=dict(status='PASSED',receipt='p9/release.json',sha256=sha(receipt))
            except (OSError,ValueError,KeyError,TypeError,RuntimeError,subprocess.SubprocessError) as exc:
                result['p9']=dict(status='FAILED',error=str(exc));passed=False
    if getattr(args,'p10',False):
        result['release_gate']='P10'
        result['p10']=dict(status='NOT_RUN')
        if passed:
            from p10_release import run as pilot
            try:
                evidence=pilot(root,args.p10_sources.resolve(),args.p10_baseline.resolve())
                result['p10']=dict(status='PASSED',receipt='p10/release.json',sha256=sha(evidence))
            except (OSError,ValueError,KeyError,TypeError,RuntimeError,subprocess.SubprocessError) as exc:
                result['p10']=dict(status='FAILED',error=str(exc))
                passed=False
    result['status']='SOFTWARE_CHECKS_PASSED' if passed else 'NEEDS_ATTENTION'
    save(root/'release.json',result);print(root/'release.json');return 0 if passed else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--packet',type=Path)
    p.add_argument('--project',action='append',default=[]);p.add_argument('--session',type=Path)
    p.add_argument('--cohort',type=Path,help='JSON object mapping pilot site names to their project IDs')
    p.add_argument('--p2',action='store_true',help='Require the measured river replay, independent river revision and Midway recipient checks')
    p.add_argument('--fresh-benchmark',action='store_true',help='Create an isolated project and repeat the native solve and mapped exports from the verified packet')
    p.add_argument('--midway-fixture',type=Path,help='Private Midway originals, terrain and operator choices for the mandatory fresh lifecycle replay')
    p.add_argument('--p3',action='store_true',help='Require P2 plus fresh browser journeys and observed recipient decisions')
    p.add_argument('--transfer-survey',type=Path,help='Separate complete surveyed site reserved for the transfer test')
    p.add_argument('--transfer-imagery',type=Path,help='Optional dated NAIP Aerial.tif and acquisition.json for the transfer site')
    p.add_argument('--p4',action='store_true',help='Require P3 plus the frozen Dexter holdout, Midway field returns and archived diagnostic cases')
    for flag in ('dexter-survey','dexter-observation','dexter-imagery','historical-root'):
        p.add_argument('--'+flag,type=Path)
    p.add_argument('--p5',action='store_true',help='Require P4 plus edition storage, offline packages and native restore replay')
    p.add_argument('--p5-archive-dir',type=Path,help='Existing local archive folder outside this isolated checkout')
    p.add_argument('--p6',action='store_true',help='Require P5 and the three-site frozen intake and return checks')
    p.add_argument('--p7',action='store_true',help='Require P6 and local hydraulic confidence checks')
    p.add_argument('--p7-visits',type=Path,help='Frozen preregistered USGS field visit folder')
    p.add_argument('--p8',action='store_true',help='Require P7 plus formal station review, offline return and audience-scoped handoff')
    p.add_argument('--p9',action='store_true',help='Require the P8 checks, signed offline installs, migration and queue recovery')
    p.add_argument('--p9-fixture',type=Path,help='Local admin distribution and legacy-edition fixture JSON')
    p.add_argument('--p10',action='store_true',help='Require P9 and the fixed 26-job pilot on the same host')
    p.add_argument('--p10-sources',type=Path,help='Directory of frozen pilot originals')
    p.add_argument('--p10-baseline',type=Path,help='Original P5 same-host timing receipt')
    args=p.parse_args()
    if args.p10:
        if not args.p10_sources or not args.p10_baseline:p.error('--p10 requires --p10-sources and --p10-baseline')
        args.p9=True
    if args.p9:
        if not args.p9_fixture:p.error('--p9 requires --p9-fixture')
        args.p8=True
    if args.p8:args.p7=True
    if args.p7:
        if not args.p7_visits:p.error('--p7 requires --p7-visits')
        args.p6=True
    if args.p6:args.p5=True
    if args.p5:
        if not args.p5_archive_dir or not args.p5_archive_dir.is_dir() or args.p5_archive_dir.resolve().is_relative_to(REPO):
            p.error('--p5 requires an existing external --p5-archive-dir')
        args.p4=True
    if args.p4:
        if not all((args.dexter_survey,args.dexter_observation,args.dexter_imagery,args.historical_root)):
            p.error('--p4 requires --dexter-survey, --dexter-observation, --dexter-imagery and --historical-root')
        args.p3=True
    if args.p3:
        if not args.transfer_survey:p.error('--p3 requires --transfer-survey')
        args.p2=True
    if args.p2:
        if not args.packet or not (args.midway_fixture or os.environ.get('STEADYREACH_MIDWAY_FIXTURE')):
            p.error('--p2 requires --packet and --midway-fixture (or STEADYREACH_MIDWAY_FIXTURE)')
        args.fresh_benchmark=True
    raise SystemExit(run(args))
