"""Measured same-workstation workload timing, storage, and package outcomes."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import shutil
import threading
import time

from ras_workflow.common import read, save, sha, utc


def nearest_p95(samples):
    ordered = sorted(samples)
    if not ordered:
        return None
    return ordered[math.ceil(.95 * len(ordered))-1]


def site_timing(case):
    folder = Path(case['rerun_handoff'])
    model = read(folder.parent/'app.json')
    root = folder.parent.parent.parent
    summary = root/model['summary']['path']
    if sha(summary) != model['summary']['sha256']:
        raise ValueError('Timing record belongs to a changed summary')
    run = read(summary)['hydraulics']
    if case['new_run'] != run['run_id']:
        raise ValueError('Timing source and native run differ')
    job = summary.parent
    native = read((root/run['raw_hdf']['path']).parents[1]/'execution.json')
    def interval(start,end):
        value = (datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds()
        if value < 0:
            raise ValueError('Clock order differs in '+str(job))
        return round(value,3)
    rows = dict(archive_and_retire=case['archive_and_retire_seconds'],restore=case['restore_seconds'],
                recalculate_and_deliver=case['recalculate_and_deliver_seconds'],
                native_worker=interval(native['started_at_utc'],native['finished_at_utc']))
    for name in ('Report_EN','Report_CN','Summary_EN'):
        base = job/'reports/qa'/name
        rows['render_'+name] = interval(read(base/'request.json')['created_utc'],read(base/'supervisor.json')['finished_utc'])
    # The legacy QGIS request records no start timestamp. Preserve this as unknown.
    rows['qgis_only'] = None
    return rows


def timing_comparison(baseline, candidate):
    old, new = read(baseline),read(candidate)
    if old['status'] != 'PASSED' or new['status'] != 'PASSED' or old['workstation'] != new['workstation']:
        raise ValueError('Timing requires identical hardware, OS, environment and passed restore workloads')
    def series(result):
        if len(result['cases']) != 2 or any(v['compared_station_profiles'] != 9 for v in result['cases']):
            raise ValueError('Different workload or station count')
        return {v['site']:site_timing(v) for v in result['cases']}
    left,right=series(old),series(new)
    if left.keys()!=right.keys():
        raise ValueError('Site pair differs')
    rows=[]
    for name in next(iter(left.values())):
        first=[v[name] for v in left.values() if v[name] is not None]
        second=[v[name] for v in right.values() if v[name] is not None]
        a,b=nearest_p95(first),nearest_p95(second)
        percent=round(100*(b/a-1),2) if a and b is not None else None
        rows.append(dict(stage=name,baseline_n=len(first),candidate_n=len(second),baseline_p95=a,candidate_p95=b,
                         change_percent=percent,investigate=percent is not None and percent>20))
    return dict(baseline_sha256=sha(baseline),candidate_sha256=sha(candidate),method='nearest-rank P95 by stage across the same two nine-section restore jobs; n=2 yields the slower of the two',
                sites=list(left),workstation=new['workstation'],baseline=left,candidate=right,stages=rows)


def working_bytes(folders):
    total=0
    def ignore_disappeared(error):
        if not isinstance(error,FileNotFoundError):
            raise error
    for directory in folders:
        if not directory.is_dir():
            continue
        for parent,dirs,files in os.walk(directory,onerror=ignore_disappeared):
            for name in files:
                try:total+=(Path(parent)/name).stat().st_size
                except FileNotFoundError:continue
    return total


@contextmanager
def sample_storage(root,gate,interval=15):
    """Sample only this cohort's gate, new projects and converter work directories."""
    start=gate.name[:15]
    record=gate/'storage_samples.jsonl'
    stopped=threading.Event()
    def sample():
        projects=[p for p in (root/'projects').glob('site_*') if p.name[5:20].upper()>=start]
        conversion=[p for p in (root/'.tools/lo').glob('*') if p.name[:15]>=start]
        sample=dict(utc=utc(),free_bytes=shutil.disk_usage(root).free,logical_bytes=working_bytes([gate,*projects,*conversion]))
        with record.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(sample)+'\n')
    failures=[]
    def monitor():
        while not stopped.wait(interval):
            try:sample()
            except OSError as err:
                failures.append(str(err))
                break
    sample();thread=threading.Thread(target=monitor,daemon=True);thread.start()
    try:yield
    finally:
        stopped.set();thread.join()
        sample()
        if failures:
            raise RuntimeError('Storage sampling failed: '+failures[0])


def storage_summary(path):
    rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    return dict(samples=len(rows),sampled_peak_logical_bytes=max(v['logical_bytes'] for v in rows),
                minimum_free_volume_bytes=min(v['free_bytes'] for v in rows),
                scope='Logical file lengths for this release gate, its new project editions and converter scratch. Free space is volume-wide. External edition archives are accounted separately.',
                first=rows[0],last=rows[-1],evidence_sha256=sha(path))


def by_route(cases):
    groups={}
    for case in cases:
        row=groups.setdefault(case['route'],dict(requested=0,eligible=0,first_pass_pairs=0,final_pairs=0,
            seeded_blockers=0,detected_blockers=0,false_ready=0))
        row['requested']+=1
        if case['expected']=='BLOCKED':
            row['seeded_blockers']+=1
            row['detected_blockers']+=int(case['outcome']=='BLOCKED')
            row['false_ready']+=int(case.get('false_ready') is True or case['outcome']=='PAIR')
        else:
            row['eligible']+=1
            row['first_pass_pairs']+=int(case.get('first_pass_pair') is True)
            row['final_pairs']+=int(case.get('verified_pair') is True)
            row['false_ready']+=int(case.get('false_ready',False))
    return groups


def write_summary(gate,storage):
    """Write a readable bilingual companion to the immutable job and native evidence."""
    source=gate/'p10/release.json'
    if not source.is_file():
        return {}
    data=read(source)
    jobs=data['jobs']
    detected=sum(r.get('outcome')=='BLOCKED' and r['expected']=='BLOCKED' for r in jobs)
    blocked=sum(r['expected']=='BLOCKED' for r in jobs)
    pairs=sum(r.get('verified_pair') is True for r in jobs)
    ready=sum(r['expected']=='PAIR' for r in jobs)
    first=sum(r.get('first_pass_pair') is True for r in jobs if r['expected']=='PAIR')
    false_ready=sum(r.get('false_ready') is True or (r['expected']=='BLOCKED' and r.get('outcome')=='PAIR') for r in jobs)
    result={}
    for lang in ('EN','CN'):
        def t(en,zh):return zh if lang=='CN' else en
        label={'coordinate':t('Coordinate','坐标'),'partial':t('Partial','部分资料'),'survey':t('Survey','完整测量'),'native':t('Native','原生模型')}
        rows=[t('# Workstation pilot results','# 同机试点验收结果'),'',
              t('Signed candidate','已签名候选版')+' `'+data['candidate']['commit']+'`', '',
              t('Final package pairs','最终双包')+f' **{pairs}/{ready}** · '+t('first job attempt','首次任务')+f' **{first}/{ready}** · '+
              t('expected stops detected','检出预置阻塞')+f' **{detected}/{blocked}** · '+t('false releases','误放行')+f' **{false_ready}**','',
              t('Decision','发行状态')+' `'+data.get('pilot_decision',data['status'])+'`','',
              t('Observed peak logical working bytes','抽样观测的工作文件峰值（字节）')+f" **{storage['sampled_peak_logical_bytes']:,}** · "+
              t('minimum free volume bytes','卷最小可用字节')+f" **{storage['minimum_free_volume_bytes']:,}** · "+
              t('samples','采样数')+f" **{storage['samples']}**",'',
              t('## Individual jobs','## 逐项验收'),'',
              t('| Job | Entry | Site | Result | Native run or stop |','| 任务 | 入口 | 地点 | 结果 | 原生运行或停止原因 |'),
              '|---|---|---|---|---|']
        for r in jobs:
            evidence=r.get('run') or r.get('error') or r.get('reason') or '—'
            rows.append(f"| {r['id']} | {label[r['route']]} | {r['site']} | {r['outcome']} | {str(evidence).replace('|','/')} |")
        if data.get('timing'):
            rows+=['',t('## Matched P5 workloads','## 与 P5 匹配的工作量'),'',
                   t('| Stage | n old/new | Old P95, s | New P95, s | Change, % |','| 阶段 | 旧版／候选样本数 | 旧版 P95 秒 | 候选 P95 秒 | 变化 % |'),
                   '|---|---|---|---|---|']
            for r in data['timing']['stages']:
                rows.append('| {} | {}/{} | {} | {} | {} |'.format(r['stage'],r['baseline_n'],r['candidate_n'],
                    *('—' if r[k] is None else r[k] for k in ('baseline_p95','candidate_p95','change_percent'))))
        for r in jobs:
            if 'independent_stations' in r:
                rows+=['',t('Washington State Park interior comparison','Washington State Park 河段内点对比')+
                       f" · {r['independent_stations']} "+t('stations, maximum absolute residual','条断面，最大绝对水位残差')+
                       f" **{r['max_abs_residual_ft']:.3f} ft**."]
            if r['id']=='case_06' and 'published_model_only' in r:
                c=r['published_model_only']
                rows+=['',t('Konkapot RS 2666, trial / published conceptual model','Konkapot RS 2666，本次局部试算／已发表概念模型')+
                     f" **{c['modeled_ft']:.2f} / {c['source_model_ft']:.2f} ft**."]
        rows+=['',t('The job record contains the package paths, checksums, field observations and errors. Human onboarding, independent engineering sign-off and cross-machine qualification are deferred.',
                     '逐项回执含双包路径、指纹、观测及错误记录。真人首次使用、独立工程签审和跨机器验收均待办。'),'',
               '[release.json](release.json)']
        path=source.parent/('Pilot_'+lang+'.md')
        path.write_text('\n'.join(rows)+'\n',encoding='utf-8')
        result[lang]=dict(path=path.relative_to(gate).as_posix(),sha256=sha(path))
    return result
