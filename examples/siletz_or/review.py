"""Assemble a portable review packet from sealed local attempts and original observations."""
import argparse
import csv
import json
from pathlib import Path
import shutil

import h5py
import numpy as np

from prepare import INTERIOR, OUTLET, select_events, archived_input
from ras_workflow.common import ROOT, intact, read, safe_path, sha
from ras_workflow.site_delivery import verify

BASE='Results/Steady/Output/Output Blocks/Base Output/Steady Profiles'


def dump(path,data):
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8')


def copy_file(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(src,dst)
    if sha(src)!=sha(dst):raise ValueError(f'Copy changed: {dst}')


def collect(receipt,destination):
    run=read(receipt)
    folder=safe_path(ROOT,'projects/'+run['project_id'])
    ref=run['summary']
    if not intact([ref]):raise ValueError('Summary fingerprint changed')
    summary_path=safe_path(folder,Path(ROOT/ref['path']).relative_to(folder))
    summary=read(summary_path)
    solver=summary_path.parent/'solver__siletz'
    request=read(solver/'request.json')
    project=ROOT/request['project']
    if project.parent.resolve()!=(solver/'project').resolve():raise ValueError('Different solver attempt')
    hdf=project.with_suffix('.p01.hdf')
    hydraulics=summary.get('hydraulics')
    if hydraulics and (hydraulics['raw_hdf']['sha256']!=sha(hdf) or hydraulics['run_id']!=request['run_id']):
        raise ValueError('Native evidence differs from calculated summary')
    survey=folder/'survey'
    manifest=read(survey/'survey.json')
    for entry in manifest['files']:
        path=safe_path(survey,entry['name'])
        if sha(path)!=entry['sha256']:raise ValueError('Source changed: '+entry['name'])
    f01=(survey/'flow_inputs.f01').read_text()
    changes={}
    for line,following in zip(f01.splitlines(),f01.splitlines()[1:]):
        if line.startswith('River Rch & RM='):changes[int(line.rsplit(',',1)[1])]=float(following[16:24])
    events={e['id']:e for e in select_events(survey,changes[44506]/changes[19532])}
    if events!={e['id']:e for e in read(survey/'events.json')['events']}:raise ValueError('Observed-event selection changed')
    rows=[];sections=[]
    with h5py.File(hdf) as h:
        xs=[int(float(s.decode())) for s in h['Geometry/Cross Sections/Attributes']['RS']]
        profiles=[v.decode().strip() for v in h[BASE+'/Profile Names'][:]]
        if profiles!=[p['id'] for p in request['profiles']] or len(xs)!=18 or len(set(xs))!=18 or xs[-1]!=34913:
            raise ValueError('Unexpected native reach or profiles')
        for i,name in enumerate(profiles):
            e=events[name];w=h[BASE+'/Cross Sections/Water Surface'][i].astype(float)
            q=h[BASE+'/Cross Sections/Flow'][i].astype(float)
            critical=float(h[BASE+'/Cross Sections/Additional Variables/Critical Water Surface'][i,-1])
            if not np.isfinite(w).all() or np.max(np.abs(q-e['reach_cfs']))>.002:raise ValueError('Native stage or flow check failed')
            target=e['stage_m'][OUTLET]/.3048
            computed=float(w[xs.index(44056)])*.3048
            err=computed-e['stage_m'][INTERIOR]
            rows.append(dict(profile=name,date=e['date'],gage_cfs=e['gage_cfs'],reach_cfs=e['reach_cfs'],
                             boundary_target_ft=target,boundary_actual_ft=w[-1],boundary_critical_ft=critical,
                             boundary_matches=bool(abs(w[-1]-target)<=.002),interior_observed_m=e['stage_m'][INTERIOR],
                             interior_computed_m=computed,interior_error_m=err,within_015m=abs(err)<=.15))
            sections.extend(dict(profile=name,rs=rs,flow_cfs=float(flow),stage_ft=float(level)) for rs,flow,level in zip(xs,q,w,strict=True))
    target=destination/run['project_id'];target.mkdir()
    for suffix in ('.prj','.g01','.f01','.p01','.p01.hdf','.g01.hdf','.p01.computeMsgs.txt'):
        copy_file(project.with_suffix(suffix),target/'HEC_RAS'/('Model'+suffix))
    for src in [summary_path,solver/'request.json',solver/'execution.json',solver/'worker_stderr.log',receipt]:
        copy_file(src,target/'Run'/src.name)
    for name in ['survey.json','protocol.json','events.json','Calculated Data.csv','Site Information.csv',archived_input(survey).name,
                 'Siletz River Surface Water Elevation.xml','flow_inputs.f01','geometry_inputs.hdf']:
        copy_file(survey/name,target/'Sources'/name)
    supplement=summary.get('native_supplement')
    if supplement:
        if not intact([supplement]):raise ValueError('Invalid native warning export')
        from ras_workflow.warning_study import assessment
        audit=assessment(summary,ref)
        if not intact([audit['native_file']]):raise ValueError('Native warning text changed')
        copy_file(ROOT/audit['native_file']['path'],target/'Run'/'warnings.txt')
        warnings=audit['metrics']['warnings']
    else:warnings=None
    with (target/'sections.csv').open('w',encoding='utf8',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=list(sections[0]));writer.writeheader();writer.writerows(sections)
    delivery=run.get('delivery') or {}
    packages={}
    if delivery.get('mapped') and delivery.get('status')=='READY_FOR_REVIEW':
        if delivery['summary']!=ref or delivery['run_id']!=request['run_id']:
            raise ValueError('Delivery belongs to a different run')
        for key in ('minimal','complete'):
            pack=delivery[key]
            check=verify(pack['path'])
            if not intact([pack['manifest']]):raise ValueError('Delivery manifest changed')
            local=destination/'Packages'/key.capitalize()
            shutil.copytree(ROOT/pack['path'],local)
            for entry in read(local/'PACKAGE_MANIFEST.json')['files']:
                if sha(safe_path(local,entry['path']))!=entry['sha256']:raise ValueError('Copied package changed')
            packages[key]=dict(path=local.relative_to(destination).as_posix(),original=pack['path'],manifest=pack['manifest']['sha256'],files=check['files'])
    return dict(id=run['project_id'],run=request['run_id'],summary_hash=ref['sha256'],native_hash=sha(hdf),
                outcome=run['status'],rows=rows,sections=sections,warnings=warnings,packages=packages,
                mapping_error=delivery.get('error'),engineering_review='PENDING')


def east_fork(holdout,destination):
    j=read(holdout)
    if not intact([j['calibration'],j['observation_source']]):raise ValueError('East Fork evidence changed')
    training=read(ROOT/j['calibration']['path'])
    best=next(t for t in training['trials'] if t['n']==training['selected_n'])
    if best['n']!=j['result']['n']:raise ValueError('Roughness changed between events')
    folder=destination/'East_Fork'
    for name,row in [('calibration',best),('holdout',j['result'])]:
        if not intact([row[k] for k in ('native','execution','inputs','log')]):raise ValueError('East Fork run changed')
        for k in ('native','execution','inputs','log'):
            path=ROOT/row[k]['path'];copy_file(path,folder/name/path.name)
    for ref in [training['training'],j['calibration'],j['observation_source']]:
        src=ROOT/ref['path'];copy_file(src,folder/('frozen_'+src.name))
    copy_file(holdout,folder/'holdout_result.json')
    return dict(selected_n=best['n'],calibration_rmse_m=best['rmse_m'],holdout_rmse_m=j['result']['rmse_m'],
                holdout_bias_m=j['result']['bias_m'],holdout_worst_m=j['result']['worst_m'])


def packet(receipts,holdout,destination,projects=()):
    destination.mkdir(parents=True,exist_ok=False)
    if projects:
        from ras_workflow import app_core
        folder=destination/'Selected_runs';folder.mkdir()
        receipts=list(receipts)
        for key in projects:
            m=app_core.model(key);app_core.require_idle(m)
            view=app_core.view(key)
            path=folder/(key+'.json')
            dump(path,dict(project_id=key,status=view['status'],phase=view.get('phase'),
                           summary=view['summary'],delivery=view.get('delivery'),task=m.get('task')))
            receipts.append(path)
    runs=[collect(r,destination) for r in receipts]
    east=east_fork(holdout,destination)
    by_event={}
    for run in runs:
        for v in run['sections']:
            k=v['profile'],v['rs']
            if k in by_event and abs(by_event[k]-v['stage_ft'])>.002:
                raise ValueError('Water levels changed between isolated runs')
            by_event[k]=v['stage_ft']
    dump(destination/'review.json',dict(east_fork=east,siletz=runs,engineering_signoff='PENDING'))
    (destination/'Engineering_response.md').write_text(
        '# Independent engineering response / 独立工程复核意见\n\n'
        'Pending / 待填写\n\n'
        '| Item / 项目 | Response / 意见 |\n|---|---|\n'
        '| Project, run ID and HDF fingerprint / 项目、运行与 HDF 指纹 | |\n'
        '| Intended use and reaches / 拟用场景与河段 | |\n'
        '| Acceptable error and basis / 适用误差及依据 | |\n'
        '| Downstream control, roughness and discharge transfer / 出口控制、糙率及流量传递 | |\n'
        '| Warnings and affected stations / 警告及位置 | |\n'
        '| Decision, conditions or measurements needed / 意见、条件及需补测项 | |\n'
        '| Reviewer and date / 复核人与日期 | |\n\n'
        'Save the completed response as a new file beside the sealed packet. / 请将填写后的意见另存于冻结复核包旁。\n',encoding='utf8')
    for lang in ('en','zh'):
        template=Path(__file__).with_name('review_'+lang+'.md').read_text(encoding='utf8')
        labels=['yes','no'] if lang=='en' else ['一致','不一致']
        inventory=[]
        for run in runs:
            for row in run['rows']:
                inventory.append('| '+ ' | '.join([run['id'],row['profile'],row['date'],f"{row['reach_cfs']:.2f}",f"{row['boundary_target_ft']:.3f} / {row['boundary_actual_ft']:.3f}",labels[0 if row['boundary_matches'] else 1],f"{row['interior_observed_m']:.4f} / {row['interior_computed_m']:.4f}",f"{row['interior_error_m']:+.4f}"])+' |')
        packages=[f"- {run['id']} · {k} · {v['files']} files · `{v['path']}`" for run in runs for k,v in run['packages'].items()]
        report=template.replace('{{results}}','\n'.join(inventory)).replace('{{packages}}','\n'.join(packages) or '—').replace('{{training}}',f"{east['calibration_rmse_m']:.5f}").replace('{{holdout}}',f"{east['holdout_rmse_m']:.5f}")
        (destination/('START_HERE.md' if lang=='en' else 'START_HERE.zh-CN.md')).write_text(report,encoding='utf8')
    hashes={p.relative_to(destination).as_posix():sha(p) for p in sorted(destination.rglob('*')) if p.is_file()}
    dump(destination/'SHA256.json',hashes)
    if any(sha(destination/name)!=expected for name,expected in hashes.items()):raise ValueError('Packet integrity failure')
    print(destination)


if __name__=='__main__':
    cli=argparse.ArgumentParser()
    cli.add_argument('--receipt',type=Path,action='append',default=[])
    cli.add_argument('--project',action='append',default=[],help='Use the current verified edition of a saved Siletz benchmark project')
    cli.add_argument('--east-holdout',type=Path,required=True)
    cli.add_argument('--out',type=Path,required=True)
    opts=cli.parse_args()
    if not opts.receipt and not opts.project:cli.error('Select at least one receipt or saved project')
    packet(opts.receipt,opts.east_holdout,opts.out,opts.project)
