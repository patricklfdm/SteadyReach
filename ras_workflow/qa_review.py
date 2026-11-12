"""Immutable QA workpapers: raw evidence, issue matching, and operator dispositions.

Absence from a new run is a review observation, never an automatic QA pass.
"""
import csv
import html
import shutil
import tempfile
from collections import Counter
from pathlib import Path

import h5py

from .common import ROOT, digest, intact, item, read, rel, safe_path, save, utc
from .qa import BASE, compare, diagnostics, verified_profiles


def load_summary(path):
    path = safe_path(ROOT, path)
    data = read(path)
    hyd = data.get('hydraulics')
    if data.get('calculation_status') != 'COMPUTED' or not hyd:
        raise ValueError('A computed summary is required')
    verified_profiles(hyd)
    sealed = data.get('hydraulic_results')
    if not sealed or not intact([sealed]) or read(ROOT/sealed['path']) != hyd:
        raise ValueError('Summary differs from sealed hydraulic extraction')
    return path, data, hyd


def issue_key(issue):
    evidence = issue['evidence']
    # Numerical values and output hashes deliberately excluded from matching.
    identity = {k: issue.get(k) for k in ('code', 'profile', 'station')}
    identity.update({k: evidence.get(k) for k in ('side', 'group_id', 'downstream_station',
                                                'river', 'reach', 'culvert', 'native_message')})
    return digest(identity)[:24]


def trends(previous, current, comparison, current_stations, coverage):
    matched = {r['profile'] for r in comparison['rows']}
    before = {issue_key(i): i for i in previous}
    after = {issue_key(i): i for i in current}
    rows = []
    for key in sorted(before.keys() | after.keys()):
        a, b = before.get(key), after.get(key)
        observable = bool(a and a['profile'] in matched and
            (a['station'] is None or a['station'] in current_stations[a['profile']]))
        if a and a['code'].startswith('NATIVE_'):
            observable = observable and coverage == 'EXPORTED_SCOPE_OPERATOR_ATTESTED'
        state = 'PERSISTING' if a and b else 'NEW' if b else 'ABSENT_REQUIRES_REVIEW' if observable else 'NOT_COMPARABLE'
        rows.append(dict(key=key, state=state, previous=a, current=b))
    return rows


def output_inventory(hyd):
    datasets = []
    with h5py.File(ROOT/hyd['raw_hdf']['path']) as h:
        def collect(name, obj):
            if isinstance(obj, h5py.Dataset) and name.startswith('Results/'):
                datasets.append(dict(path=name, shape=list(obj.shape), dtype=str(obj.dtype)))
        h.visititems(collect)
    coverage = []
    for p in hyd['profiles']:
        for g in p['culvert_groups']:
            for field in ('flow_cfs', 'representative_barrel_flow_cfs', 'inlet_velocity_fts',
                          'outlet_velocity_fts', 'inlet_control_egl_ft', 'outlet_control_egl_ft', 'full_flow_length_ft'):
                value = g[field]
                basis = g['flow_basis'] if 'flow_cfs' in field else g['detail_coverage']
                coverage.append(dict(profile=p['profile_id'], group_id=g['group_id'], field=field, value=value,
                    basis=basis, status='UNAVAILABLE' if value is None else 'DERIVED' if 'DERIVED' in basis else 'OBSERVED',
                    reason='No verified extraction for this field; group log flow does not supply velocity/control details' if value is None else None))
    return dict(source=hyd['raw_hdf'], controller=hyd['raw_controller'], result_datasets=datasets, fields=coverage,
        limitation='Dataset inventory is discovery evidence, not permission to infer meanings from unnamed columns.')


def plots(hyd, folder, issues):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    files = {};coverage=[];remaining=24
    with h5py.File(ROOT/hyd['raw_hdf']['path']) as h:
        stations = [v['Station'].decode().strip() for v in h['Results/Steady/Output/Geometry Info/Cross Section Attributes'][:]]
        info = h['Geometry/Cross Sections/Station Elevation Info'][:]
        values = h['Geometry/Cross Sections/Station Elevation Values'][:]
        for pi, profile in enumerate(hyd['profiles']):
            w = h[BASE+'/Cross Sections/Water Surface'][pi]
            e = h[BASE+'/Cross Sections/Energy Grade'][pi]
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(range(len(w)), w, 'o-', label='WSE'); ax.plot(range(len(e)), e, '.-', label='EGL')
            ticks=sorted(set(range(0,len(stations),max(1,len(stations)//18)))|{len(stations)-1})
            ax.set_xticks(ticks, [stations[j] for j in ticks], rotation=65, fontsize=7)
            ax.set(xlabel='Section sequence, upstream to downstream (RS labels)', ylabel='Elevation ('+hyd.get('unit','international ft')+')',
                   title=profile['profile_id']+' | '+hyd['run_id'])
            ax.legend(); ax.grid(alpha=.25); fig.tight_layout()
            name=f'profile_{pi}.png'; fig.savefig(folder/name, dpi=130); plt.close(fig)
            files[(profile['profile_id'], None)] = name
            requested = {i['station'] for i in issues if i['profile']==profile['profile_id'] and i['station'] in stations}
            # Bound rendering cost for hundreds of refined sections. Every issue
            # stays in the ledger; omitted figures never imply omitted checks.
            ranked=sorted(requested,key=lambda rs:(-max((2 if i['code']!='WET_SECTION_EDGE' else 1) for i in issues if i['profile']==profile['profile_id'] and i['station']==rs),stations.index(rs)))
            count=min(remaining,max(1,24//len(hyd['profiles'])))
            needed=ranked[:count];remaining-=len(needed)
            coverage.append(dict(profile=profile['profile_id'],rendered=needed,not_rendered=sorted(requested-set(needed)),
                                 reason='At most 24 section figures per packet; all numerical issues and raw sections remain available'))
            for rs in needed:
                j=stations.index(rs); start, count=info[j]; pts=values[start:start+count]
                fig, ax=plt.subplots(figsize=(8, 3))
                ax.plot(pts[:,0], pts[:,1], color='#694f34', label='Actual model section')
                ax.axhline(float(w[j]), color='#007da5', label='WSE'); ax.axhline(float(e[j]), color='#cb7029', ls='--', label='EGL')
                ax.set(xlabel='Station (international ft)', ylabel='Elevation ('+hyd.get('unit','international ft')+')', title=profile['profile_id']+' | RS '+rs)
                ax.legend(fontsize=8); ax.grid(alpha=.2); fig.tight_layout()
                name=f'section_{pi}_{j}.png'; fig.savefig(folder/name,dpi=120); plt.close(fig)
                files[(profile['profile_id'],rs)]=name
    save(folder/'plot_coverage.json',dict(profiles=coverage,all_issues_retained=True))
    return files


def prepare(summary_path, output, baseline=None, warnings=None, baseline_warnings=None):
    path, summary, hyd=load_summary(summary_path)
    folder=safe_path(ROOT,output); folder.mkdir(parents=True,exist_ok=False)
    current=diagnostics(hyd,folder/'current',warnings)
    sources=[item(path),summary['hydraulic_results']]+current['sources']
    comparison=None; history=[]
    if baseline:
        bp, bs, bh=load_summary(baseline)
        if bh['run_id']==hyd['run_id']:
            raise ValueError('Rerun tracking requires two distinct solver runs, not reused results')
        old=diagnostics(bh,folder/'previous',baseline_warnings)
        comparison=compare(bp,path,folder/'comparison.json')
        history=trends(old['issues'],current['issues'],comparison,verified_profiles(hyd),current['warning_coverage'])
        sources += [item(bp),bs['hydraulic_results']]+old['sources']
    issues=current['issues']
    images=plots(hyd,folder,issues)
    from .qa_locator import draw
    locator=draw(hyd,folder,issues)
    inventory=output_inventory(hyd);save(folder/'output_coverage.json',inventory)
    ledger=[]
    for i in issues:
        ledger.append(dict(key=issue_key(i),issue=i,observation='CURRENT',
            figure=images.get((i['profile'],i['station']),images.get((i['profile'],None))),review_status='OPEN'))
    for t in history:
        if t['current'] is None:
            ledger.append(dict(key=t['key'],issue=t['previous'],observation=t['state'],figure=None,review_status='OPEN'))
    result=dict(schema_version='qa_review_1.0',created_utc=utc(),run_id=hyd['run_id'],project_id=hyd['project_id'],
        sources=sources,warning_coverage=current['warning_coverage'],issues=ledger,trends=history,comparison=comparison,
        output_coverage=item(folder/'output_coverage.json'),section_locator=locator,hydraulic_qa_status='REVIEW_REQUIRED',engineering_acceptance='NOT_ASSESSED')
    save(folder/'review_packet.json',result)
    save(folder/'decisions.template.json',dict(schema_version='qa_decisions_1.0',packet=item(folder/'review_packet.json'),reviewer=None,
        decisions=[dict(key=r['key'],disposition='OPEN',reason=None,action=None,evidence=[]) for r in ledger]))
    if current['warning_coverage']!='EXPORTED_SCOPE_OPERATOR_ATTESTED':
        # Review a copy: opening HEC-RAS must not modify the sealed run evidence.
        original=ROOT/hyd['raw_hdf']['path'];original=original.with_name(original.name[:-8]+'.prj')
        review_dir=folder/'native_warning_review';review_dir.mkdir()
        for suffix in ['.prj','.p01','.g01','.f01','.p01.hdf','.g01.hdf','.O01']:
            source=original.with_suffix(suffix)
            if source.exists():shutil.copyfile(source,review_dir/source.name)
        reaches=[list(v.strip() for v in line.split('=',1)[1].split(',')) for line in original.with_suffix('.g01').read_text(encoding='ascii').splitlines() if line.startswith('River Reach=')]
        save(review_dir/'selection.template.json',dict(run_id=hyd['run_id'],project=rel(review_dir/original.name),
            observer=None,method='HEC-RAS Summary Errors Warnings Notes / File',profiles=[p['profile_id'] for p in hyd['profiles']],
            river_reaches=reaches,ui_evidence=[],empty_table_observed=False))
        for lang in ['EN','CN']:
            note=('Open the copied project in this folder without recomputing. In the native Summary Errors, Warnings and Notes window select all listed profiles and reaches, then export using File. Save an actual image of the selection. Copy selection.template.json to selection.json, enter the observer and hashed ui_evidence items; the prefilled scope must match the observed selection. An empty export needs an observed empty table. Do not claim this step complete from compute messages or the solver log.' if lang=='EN' else
                  '打开本目录中的工程副本，不重算。在 HEC-RAS 原生 Summary Errors, Warnings and Notes 窗口选择全部所列工况和河段，用 File 导出。保存真实的选择状态图。将 selection.template.json 另存 selection.json，填写观察者和带哈希的 ui_evidence 文件项；预填范围必须与实际选择一致。空导出须有空表观察证据。计算消息或求解日志不能代替完整警告表。')
            (review_dir/f'README_{lang}.md').write_text(note+'\n\nworkflow.py warnings-import --summary "'+rel(path)+'" --export "'+rel(review_dir/'warnings.txt')+'" --selection "'+rel(review_dir/'selection.json')+'" --output "'+rel(review_dir/'bundle.json')+'"\n',encoding='utf-8')
    for lang in ['EN','CN']:
        title='QA review workpaper' if lang=='EN' else '水力 QA 审核工作表'
        lines=['# '+title,'',f"Run: `{hyd['run_id']}` | QA: REVIEW_REQUIRED | Engineering: NOT_ASSESSED",'',
               '[English](REVIEW_EN.md) | [简体中文](REVIEW_CN.md)','',
               'Warnings: '+current['warning_coverage'],'',
               'Absence in a rerun requires review; removed sections and missing warning exports cannot prove resolution.' if lang=='EN' else '重跑中未再出现仍须审核；删除断面或缺少警告导出不能证明问题解决。','']
        if comparison:
            lines+=['| Profile | Δ HW ft | Max absolute Δ XS WSE ft |','|---|---:|---:|']
            for r in comparison['rows']:lines.append(f"| {r['profile']} | {r['delta_hw_ft']:.6f} | {r['max_matched_xs_delta_wse_ft']:.6f} |")
        for r in ledger:
            i=r['issue'];lines+=['',f"## {i['code']} · {i['profile']} · RS {i['station']}",'',f"`{r['key']}` — {r['observation']}",'',i['recommended_action'],'',
                'Evidence: `'+str(i['evidence'])+'`','']
            if r['figure']:lines.append(f"![{i['code']}]({r['figure']})")
        (folder/f'REVIEW_{lang}.md').write_text('\n'.join(lines),encoding='utf-8')
    body=''.join('<details><summary>'+html.escape(f"{r['issue']['code']} | {r['issue']['profile']} | RS {r['issue']['station']} | {r['observation']}")+ '</summary><p>'+html.escape(r['issue']['recommended_action'])+'</p><pre>'+html.escape(str(r['issue']['evidence']))+'</pre>'+ (f'<img src="{r["figure"]}" alt="Computed section/profile">' if r['figure'] else '')+'</details>' for r in ledger)
    (folder/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>QA review</title><style>body{font:16px system-ui;max-width:1100px;margin:32px auto;padding:12px}details{padding:14px;border-bottom:1px solid #bbb}img{max-width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>QA review / 水力审核</h1><p>REVIEW_REQUIRED · NOT_ASSESSED</p><p>Run '+html.escape(hyd['run_id'])+'</p><p><a href="REVIEW_EN.md">English</a> · <a href="REVIEW_CN.md">简体中文</a> · <a href="decisions.template.json">Decision template</a></p>'+body+'</html>',encoding='utf-8')
    save(folder/'manifest.json',dict(files=[item(p) for p in folder.rglob('*') if p.is_file() and 'native_warning_review' not in p.relative_to(folder).parts],sources=sources))
    return result


def validate_decisions(packet_path, spec):
    """Validate a review without changing the sealed packet or writing output."""
    packet_path=safe_path(ROOT,packet_path)
    packet=read(packet_path);manifest=read(packet_path.parent/'manifest.json')
    if not intact(manifest['files']+manifest['sources']) or spec.get('packet')!=item(packet_path):
        raise ValueError('QA packet or source identity changed')
    if spec.get('schema_version')!='qa_decisions_1.0' or not isinstance(spec.get('reviewer'),str) or not spec['reviewer'].strip():
        raise ValueError('Explicit reviewer required')
    entries={r['key']:r for r in packet['issues']};decisions=spec.get('decisions',[])
    if len(decisions)!=len(entries) or {r['key'] for r in decisions}!=set(entries):raise ValueError('One decision per issue required')
    for d in decisions:
        state=d.get('disposition');r=entries[d['key']]
        if state not in ['OPEN','INVESTIGATE','EXPLAINED_CONDITIONAL','RESOLVED_BY_RERUN']:raise ValueError('Unsupported disposition')
        if state!='OPEN' and any(not isinstance(d.get(k),str) or not d[k].strip() for k in ['reason','action']):raise ValueError('Reason and action required')
        if d.get('evidence') and not intact(d['evidence']):raise ValueError('Review evidence changed')
        if state=='EXPLAINED_CONDITIONAL' and (r['issue']['severity']=='EVIDENCE_GAP' or not d.get('evidence')):
            raise ValueError('Evidence gaps cannot be explained away; technical explanations need evidence')
        if state=='RESOLVED_BY_RERUN' and r['observation']!='ABSENT_REQUIRES_REVIEW':
            raise ValueError('Resolution requires comparable rerun evidence that the issue is absent')
    return packet


def disposition(packet_path, spec_path, output):
    packet_path=safe_path(ROOT,packet_path);spec_path=safe_path(ROOT,spec_path);out=safe_path(ROOT,output)
    if out.exists():raise ValueError('Preserve previous decisions; choose a new output')
    spec=read(spec_path);validate_decisions(packet_path,spec);decisions=spec['decisions']
    result=dict(status='DISPOSITIONS_RECORDED',created_utc=utc(),reviewer=spec['reviewer'],reviewer_identity='OPERATOR_ATTESTED',
        sources=[item(packet_path),item(spec_path),item(packet_path.parent/'manifest.json')],decisions=decisions,
        counts=dict(Counter(d['disposition'] for d in decisions)),hydraulic_qa_status='REVIEW_REQUIRED',engineering_acceptance='NOT_ASSESSED')
    save(out,result);return result


def closure_status(packet, decisions):
    """Separate completion of issue review from input sufficiency and acceptance."""
    by_key={d['key']:d for d in decisions};blockers=[]
    for row in packet['issues']:
        d=by_key.get(row['key']);state=d['disposition'] if d else 'OPEN'
        if state in ['OPEN','INVESTIGATE'] or (row['issue']['severity']=='EVIDENCE_GAP' and state!='RESOLVED_BY_RERUN'):
            blockers.append(dict(key=row['key'],code=row['issue']['code'],profile=row['issue']['profile'],
                station=row['issue']['station'],disposition=state,action=(d.get('action') if d else None) or row['issue']['recommended_action']))
    if packet['warning_coverage']!='EXPORTED_SCOPE_OPERATOR_ATTESTED':
        blockers.append(dict(code='COMPLETE_NATIVE_WARNING_REVIEW_REQUIRED',action='Complete the prepared native_warning_review export, import it, and prepare a new QA packet.'))
    return dict(status='WAITING_FOR_QA_REVIEW' if blockers else 'TECHNICAL_REVIEW_RECORDED_CONDITIONAL',
                blockers=blockers,hydraulic_qa_status='REVIEW_REQUIRED' if blockers else 'CLOSED_WITH_RECORDED_CONDITIONS',
                input_adequacy='SEPARATE_ASSESSMENT_REQUIRED',engineering_acceptance='NOT_ASSESSED')


def closure(packet_path, decisions_path, output):
    packet_path=safe_path(ROOT,packet_path);decisions_path=safe_path(ROOT,decisions_path)
    out=safe_path(ROOT,output)
    if out.exists():raise ValueError('Preserve previous closure evidence; choose a new output directory')
    out.mkdir(parents=True)
    # Revalidate all decisions against the original sealed packet before judging.
    disposition(packet_path,decisions_path,out/'dispositions.json')
    packet=read(packet_path);spec=read(decisions_path)
    result=closure_status(packet,spec['decisions'])
    result.update(run_id=packet['run_id'],created_utc=utc(),reviewer=spec['reviewer'],
                  sources=[item(packet_path),item(decisions_path),item(out/'dispositions.json')])
    save(out/'closure.json',result)
    return result
