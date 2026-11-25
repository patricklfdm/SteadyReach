"""Verify edition-level retirement and native replay using two fresh same-machine cases."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time

import h5py
from pypdf import PdfReader

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ras_workflow import app_core as core, edition_storage as storage
from ras_workflow.common import ROOT, item, read, rel, save, sha
from ras_workflow.delivery_pair import check
from ras_workflow.qa import BASE, verified_profiles
from ras_workflow.site_delivery import verify
from midway_release import need, page_action


def desktop_readers(folder,request):
    from ras_workflow import native
    from ras_workflow.qgis_runtime import environment
    evidence={};engine=native.discover()
    need(engine.get('status')=='READY','HEC-RAS is required to open both packages')
    with tempfile.TemporaryDirectory(prefix='package_open_',dir=ROOT/'status') as destination:
        scratch=Path(destination)
        for name in ('Minimal','Complete'):
            package=scratch/name;shutil.copytree(folder/name,package)
            project=package/'HEC_RAS/Model.prj'
            originals=[item(project.with_suffix(ext),'packaged_model') for ext in ('.prj','.p01','.g01','.f01','.O01','.p01.hdf')]
            probe=dict(request,operation='native_export',project=rel(project),engine=engine,export_sources=originals)
            probe.pop('native_terrain',None)
            control=scratch/(name+'_probe')/'request.json';save(control,probe)
            record=native.run_isolated(control,90)
            need(record.get('status')=='EXPORT_ATTEMPTED' and not record['solver_invoked'],'Packaged HEC-RAS project did not open')
            evidence[name]=dict(project=project.name,version=record['version'],read_existing_run=True)
        qgis,env=environment()
        opened=subprocess.run([str(qgis/'bin/python3.exe'),str(ROOT/'scripts/p5_open_gis.py'),str(scratch/'Complete')],env=env,
                              capture_output=True,encoding='utf-8',errors='replace',timeout=90)
        need(opened.returncode==0,'QGIS could not reopen delivery: '+opened.stderr[-1200:])
        evidence['GIS']=json.loads(opened.stdout.strip().splitlines()[-1])
    return evidence


def open_packages(folder):
    pair=check(folder/'Complete',folder/'Minimal')
    need(pair['mapped'],'Mapped packages required')
    counts={}
    for name in ('Complete','Minimal'):
        package=folder/name;counts[name]=verify(package)['files']
        pdf=package/('Reports/Report_EN.pdf' if name=='Complete' else 'Graph/Exhibit_EN.pdf')
        need(len(PdfReader(pdf).pages)>0,'Unreadable '+str(pdf))
        with h5py.File(next((package/'HEC_RAS').glob('*.p01.hdf'))) as h:
            need(len(h[BASE+'/Profile Names'])>0,'Missing HDF results')
    page_action(None,'recipient-copy',url_override=(folder/'Start_EN.html').as_uri(),run_id=pair['run_id'],folder=str(folder))
    return dict(run=pair['run_id'],hdf_sha256=pair['native_hdf_sha256'],package_files=counts)


def hydraulic_outputs(key):
    summary=read(ROOT/core.model(key)['summary']['path']);hyd=summary['hydraulics']
    stages=verified_profiles(hyd)
    with h5py.File(ROOT/hyd['raw_hdf']['path']) as h:
        rows=h[BASE+'/Cross Sections/Flow'][:].tolist()
        flows={name:dict(zip(stages[name],row,strict=True)) for name,row in zip(stages,rows,strict=True)}
    return hyd['run_id'],stages,flows


def run(release_dir,archive_dir):
    out=release_dir/'p5';out.mkdir(exist_ok=True);receipt=out/'release.json'
    need(release_dir.resolve().is_relative_to(ROOT/'status/release_checks'),'Use an isolated release cohort')
    dexter=read(release_dir/'p4/release.json');river=read(release_dir/'p3/journeys.json')['cases']['transfer']
    locations=[('Dexter',dexter['revision'],Path(dexter['handoff'])),(river['site'],river['project'],Path(river['folder']))]
    result=dict(status='RUNNING',cases=[],archive_directory=str(archive_dir),human_acceptance='DEFERRED',cross_machine='DEFERRED')
    result['workstation']=dict(os=platform.platform(),architecture=platform.machine(),processor=platform.processor(),
                               logical_cpus=os.cpu_count(),python=platform.python_version(),volume_bytes=shutil.disk_usage(ROOT).total)
    snapshots={};outputs={}
    try:
        for title,key,folder in locations:
            need(folder.resolve().is_relative_to(ROOT/'projects'/key),'Handoff must belong to selected isolated edition')
            before=storage.inspect(ROOT,key);need(before['reclaimable_bytes']>0,'No cleanable bytes: '+str(before['dependents']))
            hashes={name:sha(ROOT/name) for name in before['files']};snapshots[key]=hashes
            measured_bytes=sum((ROOT/name).stat().st_size for name in hashes)
            measured_candidates=sum((ROOT/name).stat().st_size for name in before['reclaim'])
            need(measured_bytes==before['logical_bytes']==before['exclusive_bytes']+before['shared_bytes']
                 and measured_candidates==before['reclaimable_bytes']
                 and sum(v['bytes'] for v in before['groups'].values())==measured_bytes,'Storage totals differ from disk inventory')
            outputs[key]=hydraulic_outputs(key)
            hyd=read(ROOT/core.model(key)['summary']['path'])['hydraulics']
            request=read((ROOT/hyd['raw_hdf']['path']).parent.parent/'request.json')
            case=dict(site=title,id=key,original_run=outputs[key][0],handoff=str(folder),inventory_files=len(hashes),
                      logical_bytes=before['logical_bytes'],exclusive_bytes=before['exclusive_bytes'],shared_bytes=before['shared_bytes'],
                      reclaimable_bytes=before['reclaimable_bytes'],candidate_files=len(before['reclaim']),groups=before['groups'],
                      free_before_archive=shutil.disk_usage(ROOT).free)
            if key==dexter['revision']:
                terrain=core.model(key)['terrain']['raster'];other=core.model(dexter['baseline'])['terrain']['raster']
                need(terrain['path']==other['path'] and terrain['sha256']==hashes[terrain['path']]
                     and before['groups']['terrain']['shared_bytes']>=(ROOT/terrain['path']).stat().st_size
                     and terrain['path'] not in before['reclaim'],'Shared Dexter survey terrain was counted as releasable')
                case['shared_terrain']=dict(path=terrain['path'],sha256=terrain['sha256'],other_edition=dexter['baseline'])
            result['cases'].append(case);save(receipt,result)
            start=time.monotonic()
            need(page_action(key,'home-storage-retire',folder=str(archive_dir))=='VERIFIED','Archive page did not finish')
            r=storage.state(ROOT,key);case.update(archive=r['archive'],archive_bytes=r['archive_bytes'],archive_sha256=r['sha256'],
                        before_cleanup=r['free_before_retirement'],measured_retirement_gain=r['actual_volume_gain'],
                        free_after_cleanup=shutil.disk_usage(ROOT).free,archive_and_retire_seconds=round(time.monotonic()-start,2))
            case['archive_on_project_volume']=Path(r['archive']).drive.casefold()==ROOT.drive.casefold()
            case['measured_net_volume_change']=case['free_after_cleanup']-case['free_before_archive']
            need(r['phase']=='ARCHIVED' and all(not (ROOT/n).exists() for n in before['reclaim']),'Incomplete edition retirement')
            protected=set(hashes)-set(before['reclaim'])
            need(all(sha(ROOT/n)==hashes[n] for n in protected),'Protected member changed during retirement')
            case['protected_files']=len(protected)
            try:core.model(key)
            except ValueError as error:need('Restore' in str(error),'Unexpected inactive edition failure')
            else:raise ValueError('Retired model still editable')
            case['cold_packages']=open_packages(folder)
            case['native_package_open']=desktop_readers(folder,request);save(receipt,result)
        for case in result['cases']:
            key=case['id'];start=time.monotonic()
            need(page_action(key,'home-storage-restore')=='VERIFIED','Restore page did not finish')
            r=storage.state(ROOT,key);hashes=snapshots[key]
            need(r['phase']=='ONLINE' and all(sha(ROOT/n)==h for n,h in hashes.items()),'Restored files differ')
            case.update(restored_files=r['restored_files'],verified_files=len(hashes),restore_seconds=round(time.monotonic()-start,2))
            need(hydraulic_outputs(key)==outputs[key],'Restored native results differ')
            case['restored_packages']=open_packages(Path(case['handoff']))
            need(case['cold_packages']==case['restored_packages'],'Restored package identity differs');save(receipt,result)
        for case in result['cases']:
            key=case['id'];start=time.monotonic();old,stages,flows=outputs[key]
            child=page_action(key,'river-revision');case['recalculation_edition']=child;save(receipt,result)
            page_action(child,'survey-solve');new,new_stages,new_flows=hydraulic_outputs(child)
            need(new!=old and stages.keys()==new_stages.keys() and all(stages[k].keys()==new_stages[k].keys() for k in stages),
                 'Fresh HEC-RAS run or station inventory differs')
            delta_stage=max(abs(value-new_stages[k][rs]) for k,profile in stages.items() for rs,value in profile.items())
            delta_flow=max(abs(value-new_flows[k][rs]) for k,profile in flows.items() for rs,value in profile.items())
            need(delta_stage<=0.002 and delta_flow<=0.002,'Restored model exceeds same-input replay tolerance')
            folder=ROOT/page_action(child,'transfer-current',selection='Verify the restored edition on this workstation.')
            case.update(fresh_packages=open_packages(folder),rerun_handoff=str(folder),new_run=new,
                        compared_station_profiles=sum(map(len,stages.values())),max_stage_difference_ft=delta_stage,max_flow_difference_cfs=delta_flow,
                        recalculate_and_deliver_seconds=round(time.monotonic()-start,2))
            need(case['fresh_packages']['run']==new,'Recalculated delivery uses the wrong run');save(receipt,result)
        result['status']='PASSED'
    except Exception as error:
        result.update(status='FAILED',error=str(error));raise
    finally:save(receipt,result)
    return receipt
