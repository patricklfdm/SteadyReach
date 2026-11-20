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


def replay(packet,reference,hashes,destination):
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
    def api(conn,route,body):
        conn.request('POST','/'+token+'/'+route,body=json.dumps(body).encode(),
                     headers={'Origin':server.origin,'Content-Type':'application/json','X-Workflow-Token':token})
        response=conn.getresponse();value=json.loads(response.read())
        if response.status!=200:raise ValueError(value.get('error',str(response.status)))
        return value
    def wait(key):
        deadline=time.monotonic()+1800
        while time.monotonic()<deadline:
            model=app_core.model(key)
            if model['status']!='PROCESSING':return model
            time.sleep(1)
        raise TimeoutError('The local job is still active. Inspect its saved task before retrying.')
    try:
        with closing(http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=180)) as conn:
            created=api(conn,'create',dict(route='survey',title='Siletz River · local release regression',
                        production_scope={'purpose':'review','flow_paths':'single'},survey_files=data,gis=True))
            key=created['id'];progress.update(project_id=key,preparation=created)
            save(destination/'fresh_job.json',progress)
            wait(key)
            review=api(conn,'review',dict(id=key))
            if not review['ready']:raise ValueError('Published survey requires additional inputs')
            progress.update(review=review['path'],task=api(conn,'start',dict(id=key,revision=review['revision'],
                          review_token=review['review_token'],start=True,confirmed=True)))
            save(destination/'fresh_job.json',progress)
            model=wait(key)
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
    return dict(project_id=key,baseline_run=reference['run'],new_run=hyd['run_id'],profiles=profiles,stations=stations,
                maximum_absolute_difference=differences,source_archive=archive,pair=pair,
                replication_tolerance_ft=.002,replication_tolerance_cfs=.002,engineering_approval='PENDING')
