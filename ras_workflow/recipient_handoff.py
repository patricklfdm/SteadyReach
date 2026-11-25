"""Portable, bilingual reading notes for a specific verified delivery pair."""
from html import escape
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from urllib.parse import quote

from . import app_core, handoff, result_guidance, site_delivery
from .common import ROOT, digest, item, lock, read, rel, safe_path
from .delivery_pair import check, verified_member


def page(language, model, assessment, folders, receipt, pair, review, selection=None, field_sources=()):
    zh = language == 'zh'
    def t(en, cn):
        return cn if zh else en
    def link(path, label):
        return '<a href="'+escape(quote(path, safe='/.-_'))+'">'+escape(label)+'</a>'
    def package_link(kind, name, label):
        return link(folders[kind].name+'/'+name,label)
    heading=escape(model['title'])
    result=['<!doctype html><html lang="'+t('en','zh-CN')+'"><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1"><title>'+heading+'</title>',
            '<style>body{font:1rem/1.55 system-ui,sans-serif;max-width:52rem;margin:auto;padding:2rem;color:#182e36}h1,h2{line-height:1.2}code{overflow-wrap:anywhere}li{margin:.45rem 0}@media print{nav{display:none}}</style>',
            '<nav>'+link(t('Start_zh-CN.html','Start_EN.html'),t('中文版','English'))+'</nav><main><h1>'+heading+'</h1>',
            '<p>L'+str(assessment['level'])+' · '+escape(assessment['title'][language])+'</p>',
            '<p>'+escape(assessment['use_guide']['allowed'][language])+'</p>',
            '<p>'+escape(assessment['use_guide']['deferred'][language])+'</p>']
    selection=selection or {}
    result.append('<h2>'+t('Edition selected for transfer','本次交接选用版本')+'</h2><p>'+
                  escape(t('Revision','修订版') if model.get('parent_revision') else t('Original calculation','首次计算版'))+' · '+escape(pair['run_id'])+'</p>')
    if selection.get('reason'):
        result.append('<p>'+escape(selection['reason'])+'</p>')
    if not selection.get('reason') and model.get('parent_revision') and review.get('endpoints'):
        result.append('<p>'+t('Compare the endpoint and hydraulic changes below when applying this edition.',
                              '采用此版本时，请核对下方端点状态及水力指标的变化。')+'</p>')
    if selection.get('choice')=='parent':
        result.append('<p>'+t('The review selected this earlier calculation.','本次对比选用了此基准计算。')+'</p>')
    decision=assessment.get('purpose_decision') or {}
    result.append('<p><strong>'+escape(decision.get(language,''))+'</strong></p>')
    outstanding=[r for r in decision.get('rows',[]) if r['state']!='met']
    if outstanding:
        result.append('<h2>'+t('Before the next calculation','触发下一次重算的条件')+'</h2>')
        result.extend('<p>'+escape(r[language])+'</p>' for r in outstanding)
    for r in review.get('investigation',[]):
        result.append('<p>'+escape(r[language])+'</p>')
    for ref in field_sources:
        result.append('<p>'+package_link('complete',ref,t('Field source','实测原件')+' · '+Path(ref).name)+'</p>')
    if review.get('endpoints'):
        ends=review['endpoints']
        result.append('<h2>'+t('Changes since the baseline','相对基准版的变化')+'</h2><p>'+escape(ends[language])+'</p>')
        if review.get('metrics'):
            result.append('<table><thead><tr>'+''.join('<th>'+v+'</th>' for v in
                          [t('Profile','工况'),t('Result','指标'),t('Baseline','基准'),t('Revision','本版'),t('Change','差值')])+'</tr></thead><tbody>')
            for row in review['metrics']:
                values=[row['profile'],row[language]]
                for k in ('previous','current','change'):
                    v=row[k]
                    values.append(format(v,'.8g') if v is not None else
                                  (t('Unavailable','不可比') if k=='change' else t('Unknown','未知')))
                result.append('<tr>'+''.join('<td>'+escape(v)+'</td>' for v in values)+'</tr>')
            result.append('</tbody></table>')
    decision=assessment.get('purpose_decision')
    if decision:
        if decision.get('state')!='CONDITIONS_MET':
            result.append('<p><strong>'+t('Diagnostic handoff. Project delivery conditions remain open.',
                                          '本版供诊断复核，项目约定的交付条件仍有未满足项。')+'</strong></p>')
        completed=[row for row in decision['rows'] if row['state']=='met']
        result.append('<details><summary>'+t('Verified conditions','已核实的条件')+'</summary>')
        result.extend('<p>'+escape(row[language])+'</p>' for row in completed)
        result.append('</details>')
        result.append('<p>'+escape(decision['note_'+language])+'</p>')
    scope=assessment.get('area',{}).get('selected') or []
    if scope:
        result.append('<p>'+t('Area reviewed','复核范围')+' · RS '+escape(str(scope[0]))+' – '+escape(str(scope[-1]))+'</p>')
    result.append('<h2>'+t('Open the deliverables','打开交付文件')+'</h2><ul>')
    report='Reports/'+t('Report_EN.pdf','Report_CN.pdf')
    links=[('complete',report,t('Full technical report (PDF)','完整技术报告（PDF）'))]
    if pair['mapped']:
        links.append(('complete','Graph/Exhibit_'+t('EN','CN')+'.pdf',t('Map exhibit (PDF)','地图展示图（PDF）')))
    for kind in ('minimal','complete'):
        rows=read(ROOT/receipt[kind]['manifest']['path'])['files']
        members={r['path'] for r in rows}
        plans={Path(name).with_suffix('').as_posix().lower() for name in members
               if name.startswith('HEC_RAS/') and len(Path(name).suffix)==4
               and Path(name).suffix.lower().startswith('.p') and Path(name).suffix[2:].isdigit()}
        projects=[name for name in members if name.lower().endswith('.prj') and name[:-4].lower() in plans]
        if len(projects)!=1:
            raise ValueError('Expected one HEC-RAS project with a matching plan / 请核查交付包内的工程与方案文件')
        links.append((kind,projects[0],folders[kind].name+' · HEC-RAS'))
    if pair['mapped']:
        links.append(('complete','GIS_Project.qgz',t('QGIS map and layouts','QGIS 地图与布局')))
    for kind,name,label in links:
        if not (folders[kind]/name).is_file():
            raise ValueError(kind+' / '+name+' is missing')
        result.append('<li>'+package_link(kind,name,label)+'</li>')
    result.extend(['</ul>','<h2>'+t('Review priorities','优先复核事项')+'</h2><ol>'])
    for action in assessment.get('next_actions',[]):
        label=action['reason'][language]
        if action.get('scope')=='CANDIDATE':
            label=t('Unadopted alternative · ','未采用备选方案 · ')+label
        facts=action['facts']
        if facts.get('station') is not None:
            label+=' · RS '+str(facts['station'])
        result.append('<li>'+escape(label)+'</li>')
    if not assessment.get('next_actions'):
        result.append('<li>'+t('Submit the stated scope to the responsible engineer for review.','请将所列适用范围交负责工程师复核。')+'</li>')
    result.extend(['</ol><h2>'+t('Edition and integrity','交付版本与校验')+'</h2>',
                   '<p>'+t('Solver run','求解运行')+' · <code>'+escape(pair['run_id'])+'</code></p>',
                   '<p>HDF SHA-256 · <code>'+escape(pair['native_hdf_sha256'])+'</code></p>'])
    for kind,folder in folders.items():
        result.append('<p>'+package_link(kind,'PACKAGE_MANIFEST.json',folder.name+' · '+t('file manifest','文件清单'))+
                      ' · SHA-256 <code>'+escape(receipt[kind]['manifest']['sha256'])+'</code></p>')
    verify_js=(Path(__file__).parent/'templates/recipient_verify.js').read_text('utf-8')
    result.extend(['<section><h2>'+t('Verify a copied folder','校验复制后的交接目录')+'</h2>',
                   '<p>'+t('Select the folder containing both start pages. Files are checked locally against the selected edition. On Windows, copy the whole folder near the drive root if your browser cannot read a long path.',
                             '选择同时包含两个入口页的目录，浏览器将按所选版本逐文件校验。如果 Windows 浏览器无法读取长路径，请将整个交接目录复制到盘符根目录附近，再重新选择。')+'</p>',
                   '<label>'+t('Handoff folder','交接目录')+' <input type="file" id="verify-directory" webkitdirectory multiple '+
                   'data-run="'+escape(pair['run_id'])+'" data-complete="'+escape(receipt['complete']['manifest']['sha256'])+
                   '" data-minimal="'+escape(receipt['minimal']['manifest']['sha256'])+'"></label>',
                   '<p id="verify-status" role="status">'+t('Awaiting folder selection','请选择待校验目录')+'</p></section>',
                   '<script>'+verify_js+'</script>'])
    result.append('<p>'+t('Transfer this entire folder. Its Complete and Minimal subfolders contain the selected edition. Open the model and GIS files in their desktop applications.',
                          '请整体转交本目录。Complete 和 Minimal 子目录均属于所选版本，模型及 GIS 文件可用相应的桌面软件打开。')+'</p></main></html>')
    return '\n'.join(result)


def verify_transfer(destination, pages, receipt, pair):
    expected=set(pages)|{'Complete','Minimal'}
    if (destination.resolve()!=destination or {p.name for p in destination.iterdir()}!=expected
            or any((destination/n).resolve()!=destination/n or (destination/n).read_bytes()!=v.encode('utf-8')
                   for n,v in pages.items())):
        raise ValueError('Transfer folder contents changed / 转交目录内容已改变')
    for name in ('Complete','Minimal'):
        folder=destination/name
        if folder.resolve()!=folder or item(folder/'PACKAGE_MANIFEST.json')['sha256']!=receipt[name.lower()]['manifest']['sha256']:
            raise ValueError('Transfer manifest mismatch / 转交清单不匹配: '+name)
        site_delivery.verify(folder)
    if check(destination/'Complete',destination/'Minimal')!=pair:
        raise ValueError('Transferred results differ from the selected edition / 转交结果与所选版本不同')


def export(key, body):
    model=app_core.model(key)
    app_core.require_idle(model)
    from .iteration_choice import latest as latest_choice
    decision = latest_choice(model) or {}
    if decision.get('choice') == 'unavailable':
        raise ValueError('Check the saved edition choice before handoff. / 请在结果总览重新核对工作版，再交接。')
    if decision.get('choice') == 'parent':
        raise ValueError('Open the selected baseline to hand it off. / 请打开已选用的基准版，再交接该版成果。')
    if decision.get('choice') == 'wait':
        raise ValueError('Resume this review before handoff. / 本版正在等资料，请先在结果总览继续复核。')
    def selection():
        origin=body.get('selected_from')
        if not origin:
            return latest_choice(model) or {}
        selected=latest_choice(app_core.model(origin['id'])) or {}
        if (selected.get('choice')!='parent' or selected.get('token')!=origin.get('token')
                or selected.get('selected')!=dict(project_id=key,summary=model['summary'])):
            raise ValueError('Reopen the selected baseline from the revision. / 请从修订版重新打开选用的基准版。')
        return selected
    chosen=selection()
    receipt=handoff.bound_package(model)
    if (model['revision']!=body.get('revision') or not receipt or model.get('exports_need_refresh')
            or receipt['summary']!=model.get('summary') or body.get('summary_hash')!=receipt['summary']['sha256']):
        raise ValueError('Open the current results and refresh the delivery / 请打开当前结果并更新交付包')
    folders={kind:safe_path(ROOT,receipt[kind]['path']) for kind in ('complete','minimal')}
    base=folders['complete'].parent
    if base!=folders['minimal'].parent:
        raise ValueError('The portable folders must share a parent directory')
    with lock(app_core.folder(key)/'recipient_handoff.lock'):
        for kind,folder in folders.items():
            try:
                site_delivery.verify(folder)
            except (ValueError,OSError) as exc:
                raise ValueError(folder.name+' / '+str(exc)) from exc
        pair=check(folders['complete'],folders['minimal'])
        assessment=result_guidance.collect(key,dict(summary_hash=body['summary_hash'],include_assessment=True))['assessment']
        if (pair['run_id']!=assessment.get('run_id') or pair['summary_sha256']!=body['summary_hash']
                or not assessment.get('evidence_hash') or assessment.get('summary')!=receipt['summary']):
            raise ValueError('The delivery and use assessment refer to different runs')
        reports=read(folders['complete']/'Evidence/report_manifest.original.json')
        data=reports['data']
        report_data=read(verified_member(folders['complete']/'Reports',Path(data['path']).name,data['sha256']))
        review=(report_data.get('revision_comparison') or {}).get('review') or {}
        field_names={r['source_file'] for r in report_data.get('river_checks',{}).get('events',[]) if r.get('source_file')}
        evidence={r['sha256'] for r in report_data.get('sources',[]) if r.get('role') in ('survey_source','returned_observations') and Path(r['path']).name in field_names}
        field_sources=[r['path'] for r in read(ROOT/receipt['complete']['manifest']['path'])['files']
                       if r['path'].startswith('Sources/') and r['sha256'] in evidence]
        originals={r['sha256'] for r in report_data.get('sources',[]) if r.get('role')=='field_original'}
        if originals:
            archived=read(folders['complete']/'Evidence/ReportSources/index.json')['entries']
            linked={r['source']['sha256']:r['package_path'] for r in archived if r['source']['sha256'] in originals}
            if set(linked)!=originals:raise ValueError('Restore the supporting field originals before handoff')
            field_sources=list(dict.fromkeys([*field_sources,*linked.values()]))
        pages={name:page(lang,model,assessment,folders,receipt,pair,review,chosen,field_sources) for lang,name in [('en','Start_EN.html'),('zh','Start_zh-CN.html')]}
        guide_hashes={name:hashlib.sha256(html.encode('utf-8')).hexdigest() for name,html in pages.items()}
        pages['HANDOFF.json']=json.dumps(dict(run_id=pair['run_id'],pages=guide_hashes),sort_keys=True,indent=2)
        tag=digest(dict(pages=pages,assessment=assessment['evidence_hash']))
        # Browser directory pickers can omit long Windows paths even when Python verifies them.
        transfer_root=app_core.folder(key)
        destination=transfer_root/('Handoff_'+tag[:16])
        latest=app_core.model(key)
        if (latest['revision']!=model['revision'] or latest.get('exports_need_refresh') or latest.get('summary')!=model['summary']
                or handoff.bound_package(latest)!=receipt):
            raise ValueError('The project changed during verification. Reopen results.')
        if destination.exists():
            verify_transfer(destination,pages,receipt,pair)
        else:
            size=sum(r['size_bytes'] for kind in folders for r in read(ROOT/receipt[kind]['manifest']['path'])['files'])
            if shutil.disk_usage(base).free<size:
                raise ValueError('Free space needed for the portable copy / 空间不足以生成可转交副本')
            with TemporaryDirectory(dir=transfer_root) as temporary:
                stage=Path(temporary)/'transfer'
                stage.mkdir()
                for name,html in pages.items():
                    (stage/name).write_bytes(html.encode('utf-8'))
                for kind,folder in folders.items():
                    shutil.copytree(folder,stage/kind.capitalize())
                verify_transfer(stage,pages,receipt,pair)
                current=app_core.model(key)
                if (current.get('summary')!=model['summary'] or handoff.bound_package(current)!=receipt
                        or current.get('exports_need_refresh') or (latest_choice(current) or {})!=decision or selection()!=chosen):
                    raise ValueError('Selected edition changed during export / 导出期间所选版本已变化')
                stage.rename(destination)
        return dict(folder=rel(destination),files=[item(destination/n) for n in pages],level=assessment['level'],run_id=pair['run_id'],
                    edition=tag,summary=receipt['summary'],packages={k:receipt[k]['manifest'] for k in folders})
