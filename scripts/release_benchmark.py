"""Replay the frozen measured survey through the local application and both exporters."""
import base64
from contextlib import closing
import http.client
import json
from pathlib import Path
import threading
import time
from zipfile import ZipFile

import h5py
import numpy as np
from ras_workflow import app_core, app_server
from ras_workflow.common import ROOT, intact, read, save, sha
from ras_workflow.delivery_pair import check
from ras_workflow.site_delivery import verify


def hydraulic_matrix(path):
    base='Results/Steady/Output/Output Blocks/Base Output/Steady Profiles/'
    with h5py.File(path) as native:
        stations=[v.decode().strip() for v in native['Geometry/Cross Sections/Attributes']['RS']]
        profiles=[v.decode().strip() for v in native[base+'Profile Names'][:]]
        data={key:native[base+'Cross Sections/'+key][:].astype(float) for key in ('Water Surface','Flow')}
    if not stations or len(stations)!=len(set(stations)) or not profiles or len(profiles)!=len(set(profiles)):
        raise ValueError('Empty or ambiguous native output index')
    if any(v.shape!=(len(profiles),len(stations)) or not np.isfinite(v).all() for v in data.values()):
        raise ValueError('Missing or nonfinite native result')
    return profiles,stations,data


def field_screen(packet, reference, hashes, fresh=None):
    """Reselect the frozen Siletz event and check an interior sensor against native WSE."""
    from examples.siletz_or.prepare import INTERIOR, OUTLET, archived_input, published_flows, select_events
    edition=reference['id']
    if Path(edition).name!=edition or edition in ('.','..'):
        raise ValueError('Invalid field packet edition')
    source=packet/edition/'Sources'
    archive=archived_input(source)
    native=packet/edition/'HEC_RAS/Model.p01.hdf'
    if not archive:
        raise ValueError('Frozen discharge series missing')
    files=[archive,native,*[source/name for name in ('protocol.json','flow_inputs.f01','events.json','Calculated Data.csv','Site Information.csv')]]
    for path in files:
        if hashes.get(path.relative_to(packet).as_posix())!=sha(path):
            raise ValueError('Missing or changed field evidence: '+path.name)
    if sha(source/'protocol.json')!=sha(ROOT/'examples/siletz_or/protocol.json') or sha(native)!=reference['native_hash']:
        raise ValueError('The field protocol or native edition differs from the benchmark')
    changes=published_flows((source/'flow_inputs.f01').read_text().splitlines())
    events=select_events(source,changes[44506]/changes[19532],archive)
    if events!=read(source/'events.json')['events']:
        raise ValueError('Selected event differs from the frozen source series')
    event=next(e for e in events if e['id']=='Holdout')
    run=reference['run']
    if fresh:
        run,native=fresh
    profiles,stations,values=hydraulic_matrix(native)
    stations=[float(rs) for rs in stations]
    if 'Holdout' not in profiles or stations.count(44056)!=1 or stations.count(34913)!=1:
        raise ValueError('Holdout profile or surveyed station is ambiguous or missing')
    i=profiles.index('Holdout')
    if np.max(np.abs(values['Flow'][i]-event['reach_cfs']))>.002:
        raise ValueError('Native flow differs from the selected observed event')
    surface=values['Water Surface'][i]
    boundary_error_ft=float(surface[stations.index(34913)])-event['stage_m'][OUTLET]/.3048
    observed=event['stage_m'][INTERIOR]
    computed=float(surface[stations.index(44056)])*.3048
    residual=computed-observed
    exported=[r for r in reference['rows'] if r['profile']=='Holdout']
    if len(exported)!=1 or exported[0]['date']!=event['date'] or (not fresh and
            not np.isclose(exported[0]['interior_error_m'],residual,atol=1e-8,rtol=0)):
        raise ValueError('Reported holdout differs from native and field records')
    return dict(status='BOUNDARY_MISMATCH' if abs(boundary_error_ft)>.002 else
                'INVESTIGATE' if abs(residual)>.15 else 'WITHIN_SCREEN',
                run=run,profile='Holdout',date=event['date'],interior_rs=44056,observed_m=observed,
                computed_m=computed,signed_residual_m=residual,investigation_threshold_m=.15,
                scored_locations=1,excluded_boundary_rs=34913,boundary_error_ft=boundary_error_ft,
                protocol_sha256=sha(source/'protocol.json'),native_sha256=sha(native),engineering_approval='PENDING')


def east_fork_screen(packet):
    """Check a second site's withheld event without fitting another roughness or inventing a tolerance."""
    base=packet/'East_Fork'
    spec=read(base/'frozen_training.json')
    event=read(base/'frozen_holdout.json')
    published=ROOT/'examples/east_fork_wy'
    cal=read(base/'frozen_calibration.json')
    trial=read(base/'holdout_result.json')
    inputs=read(base/'holdout/inputs.json')
    chosen=min(cal['trials'],key=lambda t:t['rmse_m'])['n']
    if (spec!=read(published/'training.json') or event!=read(published/'holdout.json') or
            event['date']!=spec['holdout_date'] or event['date']==spec['calibration']['date'] or
            event!=inputs['event'] or trial['observation_source']['sha256']!=sha(base/'frozen_holdout.json') or
            trial['calibration']['sha256']!=sha(base/'frozen_calibration.json') or
            any(v!=chosen for v in (inputs['scenario']['channel_n'],inputs['scenario']['overbank_n'],cal['selected_n'],trial['result']['n']))):
        raise ValueError('East Fork holdout identity or calibrated roughness differs')
    native=base/'holdout/Model.p01.hdf'
    execution=read(base/'holdout/execution.json')
    if not execution['compute_completed'] or sha(native)!=execution['hdf_sha256'] or sha(native)!=trial['result']['native']['sha256']:
        raise ValueError('East Fork execution and native result differ')
    profiles,stations,values=hydraulic_matrix(native)
    stations=[float(s) for s in stations]
    expected=[s['rs'] for s in spec['sections']]
    if (profiles!=['HOLDOUT'] or stations!=expected or np.max(np.abs(values['Flow'][0]-round(event['flow_m3s']/.3048**3,3)))>.002):
        raise ValueError('East Fork section, flow or profile differs')
    boundary=expected[-1]
    observations={r['rs']:spec['offset_m']+r['stage_m'] for r in event['observations']}
    if set(observations)!=set(expected) or len(event['observations'])!=len(expected):
        raise ValueError('East Fork observation index differs')
    residuals=[dict(rs=rs,signed_m=float(w)*.3048-observations[rs]) for rs,w in zip(expected,values['Water Surface'][0],strict=True)]
    boundary_error=residuals.pop()['signed_m']
    errs=np.array([r['signed_m'] for r in residuals])
    rmse=float(np.sqrt(np.mean(errs**2)))
    if abs(boundary_error)>.001 or not np.isclose(rmse,trial['result']['rmse_m'],atol=1e-8,rtol=0):
        raise ValueError('East Fork boundary readback or reproduced holdout RMSE differs')
    return dict(status='DESCRIPTIVE_NO_ACCEPTANCE_LIMIT',date=event['date'],selected_n=chosen,scored_locations=len(errs),
                excluded_boundary_rs=boundary,boundary_error_m=boundary_error,rmse_m=rmse,bias_m=float(np.mean(errs)),
                worst=max(residuals,key=lambda r:abs(r['signed_m'])),residuals=residuals,native_sha256=sha(native),
                engineering_approval='PENDING')


def write_field_notes(folder, siletz, east):
    for zh,name in [(False,'Field_review.md'),(True,'Field_review.zh-CN.md')]:
        def tr(en,cn):
            return cn if zh else en
        rows=[
            '# '+tr('Withheld event review','留出事件复核'),
            tr('[中文](Field_review.zh-CN.md)','[English](Field_review.md)'),
            tr('Independent engineering review is pending.','独立工程复核待办。'),
            '## Siletz',
            f"{siletz['date']} · RS {siletz['interior_rs']} · {siletz['status']}",
            tr('Observed / computed elevation','实测／计算高程')+f" · {siletz['observed_m']:.4f} / {siletz['computed_m']:.4f} m",
            tr('Signed difference / investigation threshold','有符号偏差／调查门槛')+
                f" · {siletz['signed_residual_m']:+.4f} / {siletz['investigation_threshold_m']:.2f} m",
            tr('One interior sensor scored. The prescribed downstream station is excluded.','仅内点传感器参与评分，排除用作下游边界的测点。')+
                f" RS {siletz['excluded_boundary_rs']}",
            '## East Fork',
            f"{east['date']} · n = {east['selected_n']:.3f} · {east['scored_locations']} "+tr('scored stations','个评分断面'),
            f"RMSE {east['rmse_m']:.5f} m · "+tr('largest absolute difference at','最大绝对偏差位于')+
                f" RS {east['worst']['rs']} ({east['worst']['signed_m']:+.5f} m)",
            tr('The outlet is excluded. This case has no agreed acceptance tolerance.','出口测点不参与评分。本例尚未约定接受误差。')+
                f" RS {east['excluded_boundary_rs']}",
            tr('[Run evidence and fingerprints](release.json)','[运行证据及文件指纹](release.json)')]
        (folder/name).write_text('\n\n'.join(rows)+'\n',encoding='utf-8')


def replay(packet,reference,hashes,destination,p2=False):
    source=packet/reference['id']/'Sources/survey.json'
    by_hash={v:packet/k for k,v in hashes.items()}
    data=[dict(name='survey.json',content=base64.b64encode(source.read_bytes()).decode())]
    for record in read(source)['files']:
        path=by_hash[record['sha256']]
        if sha(path)!=record['sha256']:raise ValueError('Frozen survey input changed')
        data.append(dict(name=record['name'],content=base64.b64encode(path.read_bytes()).decode()))
    server=app_server.create()
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    token=server.url.rstrip('/').split('/')[-1]
    progress={}
    def api(route,body):
        with closing(http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=180)) as conn:
            conn.request('POST','/'+token+'/'+route,body=json.dumps(body).encode(),
                         headers={'Origin':server.origin,'Content-Type':'application/json','X-Workflow-Token':token})
            response=conn.getresponse()
            value=json.loads(response.read())
            if response.status!=200:raise ValueError(value.get('error',str(response.status)))
            return value
    def wait(key):
        deadline=time.monotonic()+1800
        while time.monotonic()<deadline:
            model=app_core.view(key,detail=False)
            if model['status']=='INTERRUPTED':
                raise ValueError('Release job interrupted: '+key)
            if model['status']!='PROCESSING':
                return model
            time.sleep(1)
        raise TimeoutError('The local job is still active. Inspect its saved task before retrying.')
    try:
        archive=packet/'Packages/Complete/Evidence/Imagery'
        rasters=[]
        for name in ('Aerial.tif','acquisition.json'):
            path=archive/name
            if path.is_file() and hashes.get(path.relative_to(packet).as_posix())==sha(path):
                rasters.append(dict(name=name,content=base64.b64encode(path.read_bytes()).decode()))
        created=api('create',dict(route='survey',title='Siletz River · local release regression',
                    production_scope={'purpose':'review','flow_paths':'single'},survey_files=data,gis=True,
                    local_rasters=rasters if len(rasters)==2 else None))
        key=created['id'];progress.update(project_id=key,preparation=created)
        save(destination/'fresh_job.json',progress)
        wait(key)
        review=api('review',dict(id=key))
        if not review['ready']:raise ValueError('Published survey requires additional inputs')
        progress.update(review=review['path'],task=api('start',dict(id=key,revision=review['revision'],
                      review_token=review['review_token'],start=True,confirmed=True)))
        save(destination/'fresh_job.json',progress)
        model=wait(key)
        if p2:
            if model['status']!='RESULTS_READY' or not model.get('summary'):
                raise ValueError('Could not complete the first mapped river edition: '+str(model.get('errors')))
            revision=api('revision',dict(id=key,revision=model['revision'],confirmed=True))
            child=revision['id']
            review=api('review',dict(id=child))
            if not review['ready']:
                raise ValueError('Independent river review: '+str(review.get('errors')))
            task=api('start',dict(id=child,revision=review['revision'],review_token=review['review_token'],
                                       start=True,confirmed=True))
            progress.update(revision=child,revision_task=task)
            save(destination/'fresh_job.json',progress)
            revised=wait(child)
            if revised['status']!='RESULTS_READY' or not revised.get('summary') or not intact([revised['summary']]):
                raise ValueError('Independent river revision failed: '+str(revised.get('errors')))
    finally:
        server.shutdown();server.server_close();thread.join()
    if not model.get('summary') or not intact([model['summary']]):raise ValueError('Fresh calculated summary unavailable')
    summary=read(ROOT/model['summary']['path'])
    hyd=summary.get('hydraulics') or {}
    if summary.get('solver_reused') or not hyd or hyd['run_id']==reference['run'] or not intact([hyd['raw_hdf']]):
        raise ValueError('Release replay requires a new native solve')
    job=ROOT/model['summary']['path']
    delivery=read(job.parent/'delivery/delivery.json')
    if not delivery.get('mapped') or delivery.get('status')!='READY_FOR_REVIEW':raise ValueError('Fresh mapped delivery incomplete')
    for kind in ('minimal','complete'):verify(ROOT/delivery[kind]['path'])
    pair=check(ROOT/delivery['complete']['path'],ROOT/delivery['minimal']['path'])
    fresh=ROOT/hyd['raw_hdf']['path']
    if pair['native_hdf_sha256']!=sha(fresh) or pair['run_id']!=hyd['run_id']:raise ValueError('Replayed packages and solver differ')
    old=by_hash[reference['native_hash']]
    profiles,stations,values=hydraulic_matrix(old)
    new_profiles,new_stations,new_values=hydraulic_matrix(fresh)
    if (profiles,stations)!=(new_profiles,new_stations):raise ValueError('Reference and fresh hydraulic indices disagree')
    differences={key:float(np.abs(values[key]-new_values[key]).max()) for key in values}
    if differences['Water Surface']>.002 or differences['Flow']>.002:raise ValueError('Same-input hydraulic regression: '+str(differences))
    manifest=read(fresh.parent.parent/'manifest.json')
    archive=manifest['code_archive']
    if not intact([archive]):raise ValueError('Native workflow source archive changed')
    import hashlib
    with ZipFile(ROOT/archive['path']) as frozen:
        if frozen.namelist()!=[e['path'] for e in manifest['code']] or any(
                hashlib.sha256(frozen.read(e['path'])).hexdigest()!=e['sha256'] for e in manifest['code']):
            raise ValueError('Archived source differs from solver manifest')
    checks={}
    if p2:
        from midway_release import verify_outcomes
        from ras_workflow import recipient_handoff
        revised_run=read(ROOT/revised['summary']['path'])['hydraulics']
        if revised_run['run_id']==hyd['run_id'] or revised['parent_revision']['summary']!=model['summary']:
            raise ValueError('River comparison must use an independently computed child')
        transfer=recipient_handoff.export(child,dict(revision=revised['revision'],summary_hash=revised['summary']['sha256']))
        if transfer['run_id']!=revised_run['run_id']:
            raise ValueError('River handoff differs from the chosen revision')
        checks=dict(revised_run=revised_run['run_id'],handoff=transfer['folder'],
                    field=field_screen(packet,reference,hashes,fresh=(hyd['run_id'],fresh)),
                    outcomes=verify_outcomes(child,ROOT/transfer['folder'],'river'))
    return dict(project_id=key,baseline_run=reference['run'],new_run=hyd['run_id'],p2=checks,profiles=profiles,stations=stations,
                maximum_absolute_difference=differences,source_archive=archive,pair=pair,
                replication_tolerance_ft=.002,replication_tolerance_cfs=.002,engineering_approval='PENDING')
