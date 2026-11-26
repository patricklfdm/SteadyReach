"""Run a frozen workload matrix on one Windows installation and retain job-level evidence."""
from pathlib import Path
import shutil
import time
from zipfile import ZipFile
import hashlib

from ras_workflow import app_core, inputs, intake, queue, queue_operations
from ras_workflow.common import ROOT, item, read, save, sha, utc
from midway_release import need, page_action
from p6_release import offline_providers
from p5_release import hydraulic_outputs
from pilot_cases import FalseRelease, edition_pair, native_input, receipt_pair, run_config
from pilot_metrics import by_route, timing_comparison
import sys
EXAMPLE = ROOT/'examples/enterprise_pilot'
sys.path.insert(0,str(EXAMPLE))
import wsp_survey
import konkapot_trial


def check_originals(source):
    inventory=read(EXAMPLE/'source_hashes.json')
    for name,digest in inventory.items():
        folder=source/'wsp_raw' if (source/'wsp_raw'/name).is_file() else source
        need(sha(folder/name)==digest,'Pilot source fingerprint differs: '+name)
    with ZipFile(source/'USACE_example_projects_702.zip') as archive:
        for local in (source/'twinpipe').iterdir():
            if local.is_file():
                members=[v for v in archive.namelist() if v.split('/')[-1].casefold()==local.name.casefold()]
                need(len(members)==1 and hashlib.sha256(archive.read(members[0])).hexdigest()==sha(local),
                     'Spring Creek input differs from its provider archive: '+local.name)
    return inventory


def missing_site(out):
    config=out/'project.json'
    save(config,inputs.template('monterey_coordinate_only',42.17948,-73.21343))
    session=intake.prepare(config,'q100')
    report=intake.validate(ROOT/session['session'],require_consent=False)
    if report['ready']:raise FalseRelease('Coordinate-only project was marked ready')
    need(len(report['errors'])>1,'Missing hydraulic fields were not explained')
    return dict(outcome='BLOCKED',reason='Hydraulic inputs missing',errors=report['errors'],session=session['session'])


def repeat(key,out):
    """Recompute the sealed edition inputs as a new job, retaining the history on the edition."""
    model=app_core.model(key)
    path=ROOT/model['active_project']
    before=edition_pair(key)
    receipt=read(ROOT/before['receipt']['path'])
    result=run_config(path,receipt['scenario_id'],out,True)
    need(before['run']!=result['run'] and before['profiles']==result['profiles'],'Missing independent native repeat')
    result['replayed_edition']=key
    return result


def offline(out,execute):
    with offline_providers(out) as log:
        value=execute()
    rows=log.read_text(encoding='utf-8').splitlines()
    need(len({r.split()[0] for r in rows if r.endswith(' ACTIVE')})>=2 and not any(' DENIED ' in r for r in rows),
         'A Python worker lacked the offline guard or tried a public provider')
    value['network_guard']=item(log)
    return value


def coordinate_conflict(soquel,datum):
    boundary=soquel['boundary']
    station,=[s for s in boundary['stations'] if s['station']=='11160000']
    if boundary['status']=='ELIGIBLE':raise FalseRelease('Untransferred gauge accepted as the outlet')
    need(boundary['status']=='NO_BOUNDARY_OBSERVATION' and not boundary['rows'],'Unexpected boundary observation')
    if datum:
        need(station['datum']=='NGVD29' and station['datum_check']=='CONVERSION_REQUIRED','Gauge datum conflict missing')
    else:
        need(station['transfer_required'] and station['matched_rs']!=boundary['end_rs'],'Gauge transfer missing')
    return dict(outcome='BLOCKED',reason='Datum conversion required' if datum else 'Site transfer required',
                station=station['station'],diagnostics=station,boundary_rs=boundary['end_rs'])


def run(gate,source,baseline):
    out=gate/'p10';out.mkdir()
    protocol=read(EXAMPLE/'protocol.json')
    jobs=protocol['workloads']
    need(len(jobs)==26 and len({j['id'] for j in jobs})==26,'Workload inventory differs')
    references=check_originals(source)
    issued=read(gate/'p9/release.json')['distribution']
    result=dict(status='RUNNING',candidate=issued,started=utc(),protocol_sha256=sha(EXAMPLE/'protocol.json'),
                source_hashes=references,jobs=[],human='DEFERRED',cross_machine='DEFERRED',independent_engineering='PENDING')
    dest=out/'release.json'
    save(dest,result)
    p3=read(gate/'p3/journeys.json')['cases']
    p4=read(gate/'p4/release.json')
    returns=read(gate/'p4/midway_returns.json')
    p5={r['site']:r for r in read(gate/'p5/release.json')['cases']}
    p6=read(gate/'p6/release.json')
    selected={};blocked={1,2,3,5,15}
    spring=source/'twinpipe/TWINPIPE.prj';phelps=ROOT/'examples/phelps_brook/inputs/Phelps_River.prj'

    def execute(i,folder):
        if i==1:
            missing=p3['Midway']['missing']
            registered=p6['cases']['Midway']['evidence']['structure']
            if registered['status']=='AVAILABLE':raise FalseRelease('Estimated structure stated as fully documented')
            need('invert' in str(missing) and registered['status']=='ASSUMED' and
                 all(any(k.endswith(end) for k in registered['requested_fields']) for end in ('us_invert_ft','ds_invert_ft')),
                 'Missing Midway invert survey request')
            return dict(outcome='BLOCKED',reason=missing,scope='Surveyed baseline',evidence_class=registered['status'],
                        request=p3['Midway']['project'],fields=registered['requested_fields'])
        if i in (2,5):
            return coordinate_conflict(p6['cases']['Soquel'],datum=(i==5))
        if i==3:
            return missing_site(folder)
        if i==4:
            key=returns['partial']['project']
            page_action(key,'survey-solve')
            return dict(edition_pair(key),changes=p6['returns']['partial']['affected'])
        if i==6:
            selected['culvert']=konkapot_trial.prepare(source,folder/'model')
            pair=run_config(selected['culvert'],'q100',folder,True)
            return compare_concept(pair)
        if i in (7,8):
            return edition_pair(p4['baseline' if i==7 else 'revision'])
        if i==9:
            return edition_pair(p3['Siletz']['first']['project'])
        if i==10:
            return edition_pair(p3['transfer']['project'])
        if i==11:
            data=out/'field_source';wsp_survey.prepare(source/'wsp_raw',data)
            selected['survey']=data
            key=page_action(None,'home-survey',title='Big River, Washington State Park • Feb 6',folder=str(data/'survey'),
                            protocol=False,rasters=[str(source/'wsp_imagery'/n) for n in ('Aerial.tif','acquisition.json')])
            selected['wsp']=key
            page_action(key,'survey-solve')
            pair=edition_pair(key)
            need(pair['profiles']=={'Feb06':9} and abs(pair['flows_cfs']['Feb06']-41/.3048**3)<.002 and
                 len(pair['field_events'])==1 and pair['field_events'][0]['role']=='boundary' and
                 pair['field_events'][0]['residual_ft'] is None and not pair['field_events'][0]['issues'],
                 'Baseline flow, section count or held-out observation isolation differs')
            edition=app_core.model(key)
            review=read(ROOT/edition['pending_review']['path'])
            need(any(n['profile']=='Feb06' and n['rs']=='100' for n in review.get('boundary_notices',[])),
                 'Surveyed outlet uncertainty was not shown before confirmation')
            pair['outlet_uncertainty']='UNQUANTIFIED_CONDITIONAL'
            return pair
        if i==12:
            data=selected['survey'];base=selected['wsp']
            key=page_action(base,'field-return',kind='observation',file=str(data/'field_return.csv'),
                            document=str(data/wsp_survey.EVENT),expect='500')
            page_action(key,'survey-solve');selected['returned']=key
            pair=edition_pair(key)
            before,z,q=hydraulic_outputs(base);after,new_z,new_q=hydraulic_outputs(key)
            need(before!=after and (z,q)==(new_z,new_q),'Held-out field comparison changed hydraulics')
            events=pair['field_events']
            independent=[r for r in events if r['role']=='holdout' and r['residual_ft'] is not None]
            outlet=[r for r in events if r['role']=='boundary' and r['residual_ft'] is None]
            need(len({r['location']['rs'] for r in independent})==8 and len(outlet)==1,'Held-out station pairing differs')
            return dict(pair,independent_stations=len(independent),max_abs_residual_ft=max(abs(r['residual_ft']) for r in independent),
                        threshold_basis='Diagnostic measurements; approved project tolerance and measurement uncertainty absent')
        if i in (13,14,15):
            return native_input(spring if i==13 else phelps,'spring' if i==13 else 'phelps',folder,tamper=i==15)
        if i==16:
            return edition_pair(p6['native_replay']['id'])
        if i==17:
            key=p3['transfer']['project'];model=app_core.model(key)
            work=folder/'queue';spec=folder/'request.json'
            save(spec,dict(schema_version='1.0',queue_id='space_trial',jobs=[dict(id='rockford',
                project=model['active_project'],scenario=model['run_scenario'],reserve_bytes=512*1024**2)]))
            reserved=shutil.disk_usage(folder).free-64*1024**2
            need(reserved>0,'Insufficient free disk to conduct the reservation exercise')
            with queue_operations.reserve(folder,reserved):
                queue.run(spec,work,fresh=True)
                denied,=read(work/'queue_state.json')['jobs']['rockford']
                need(denied['status']=='LOW_SPACE' and not denied.get('receipt'),'Low disk started a native run')
            queue.run(spec,work,fresh=True)
            first,last=read(work/'queue_state.json')['jobs']['rockford']
            need(last['status']=='COMPLETED','Rockford space recovery failed')
            pair=receipt_pair(ROOT/last['receipt']['path'],True)
            return dict(pair,first_pass_pair=False,initial_failure=first['error'],queue=item(work/'queue_state.json'))
        if i==18:
            def detached():
                child=page_action(selected['returned'],'river-revision')
                page_action(child,'survey-solve')
                pair=edition_pair(child)
                handoff=ROOT/page_action(child,'transfer-current')
                from p5_release import open_packages
                check=open_packages(handoff)
                need(check['run']==pair['run'],'Offline transfer differs from repeated native job')
                pair['selected_handoff']=dict(path=str(handoff),**check)
                return pair
            return offline(folder,detached)
        if i==25:
            return repeat(selected['returned'],folder)
        if i==19:
            return edition_pair(returns['both_assumed']['project'])
        if i in (20,23):
            name='Dexter' if i==20 else 'Rockford'
            match,=[v for k,v in p5.items() if name.casefold() in k.casefold() or (name=='Rockford' and 'big river' in k.casefold())]
            return dict(edition_pair(match['recalculation_edition']),archive=match['archive_sha256'],restored_files=match['restored_files'])
        if i==21:
            return offline(folder,lambda:native_input(spring,'spring',folder))
        if i==22:
            return offline(folder,lambda:repeat(p3['Siletz']['revision']['project'],folder))
        if i==24:
            return compare_concept(run_config(selected['culvert'],'q100',folder,True))
        if i==26:
            return repeat(returns['both_assumed']['project'],folder)
        raise ValueError('Unregistered workload')

    try:
        for i,j in enumerate(jobs,1):
            folder=out/j['id'];folder.mkdir()
            row=dict(**j,expected='BLOCKED' if i in blocked else 'PAIR',outcome='STARTED')
            result['jobs'].append(row);save(dest,result)
            started=time.monotonic()
            try:
                row.update(execute(i,folder))
                if row['expected']=='PAIR':
                    need(row['verified_pair'] and row.get('solver_reused') is not True,'Pilot job reused native evidence')
                    row['outcome']='PAIR'
                need(row['expected']==row['outcome'],'Pilot outcome differs')
            except FalseRelease as e:
                row.update(outcome='FALSE_READY',false_ready=True,error=str(e))
            except Exception as e:
                row.update(outcome='FAILED',error=str(e))
            finally:
                row['seconds']=round(time.monotonic()-started,3);save(dest,result)
        pairs=[r['run'] for r in result['jobs'] if r.get('verified_pair')]
        result['routes']=by_route(result['jobs'])
        failures=[r['id'] for r in result['jobs'] if r['expected']!=r['outcome']]
        need(not failures,'See per-job evidence for '+', '.join(failures))
        need(len(set(pairs))==len(pairs)==21,'Fixed workload has duplicate/missing native jobs')
        result['timing']=timing_comparison(baseline,gate/'p5/release.json')
        result['performance_review']=[r['stage'] for r in result['timing']['stages'] if r['investigate']]
        result['pilot_decision']='REVIEW_TIMING_BEFORE_ISSUE' if result['performance_review'] else 'ELIGIBLE_FOR_SUPERVISED_SINGLE_HOST_PILOT'
        result['status']='PASSED'
    except Exception as e:
        result.update(status='FAILED',error=str(e));raise
    finally:
        result['finished']=utc();save(dest,result)
    return dest


def compare_concept(pair):
    receipt=read(ROOT/pair['receipt']['path'])
    summary=read(ROOT/receipt['summary']['path'])
    from ras_workflow.qa import verified_profiles
    z=verified_profiles(summary['hydraulics'])['Q100']
    need(pair['profiles']=={'Q100':5} and abs(pair['flows_cfs']['Q100']-1620)<.002,'Konkapot flow or section count differs')
    upstream,=[v for k,v in z.items() if float(k)==2666]
    pair['published_model_only']=dict(rs=2666,modeled_ft=upstream,source_model_ft=1255.3,difference_ft=upstream-1255.3,
        scope='Local five-section conditional trial compared to the published longer dam-and-bridge model; no measured Q100 stage.')
    return pair
