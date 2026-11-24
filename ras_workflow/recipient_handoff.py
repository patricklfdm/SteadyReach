"""Portable, bilingual reading notes for a specific verified delivery pair."""
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

from . import app_core, handoff, result_guidance, site_delivery
from .common import ROOT, digest, item, lock, read, rel, safe_path
from .delivery_pair import check


def page(language, model, assessment, folders, receipt, pair):
    zh = language == 'zh'
    def t(en, cn):
        return cn if zh else en
    def link(path, label):
        return '<a href="'+escape(quote(path, safe='/.-_'))+'">'+escape(label)+'</a>'
    def package_link(kind, name, label):
        return link('../'+folders[kind].name+'/'+name,label)
    heading=escape(model['title'])
    result=['<!doctype html><html lang="'+t('en','zh-CN')+'"><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1"><title>'+heading+'</title>',
            '<style>body{font:1rem/1.55 system-ui,sans-serif;max-width:52rem;margin:auto;padding:2rem;color:#182e36}h1,h2{line-height:1.2}code{overflow-wrap:anywhere}li{margin:.45rem 0}@media print{nav{display:none}}</style>',
            '<nav>'+link(t('Start_zh-CN.html','Start_EN.html'),t('中文版','English'))+'</nav><main><h1>'+heading+'</h1>',
            '<p>L'+str(assessment['level'])+' · '+escape(assessment['title'][language])+'</p>',
            '<p>'+escape(assessment['use_guide']['allowed'][language])+'</p>',
            '<p>'+escape(assessment['use_guide']['deferred'][language])+'</p>']
    decision=assessment.get('purpose_decision')
    if decision:
        result.append('<h2>'+escape(decision[language])+'</h2>')
        result.extend('<p>'+escape(row[language])+'</p>' for row in decision['rows'])
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
        prj=next((r['path'] for r in rows if r['path'].startswith('HEC_RAS/') and r['path'].lower().endswith('.prj')),None)
        if prj:
            links.append((kind,prj,folders[kind].name+' · HEC-RAS'))
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
    result.append('<p>'+t('When copying this delivery, keep this reading folder beside Complete and Minimal. Open the model and GIS files in their desktop applications.',
                          '转交时，请将本说明文件夹与 Complete、Minimal 并列复制。模型及 GIS 文件可用相应的桌面软件打开。')+'</p></main></html>')
    return '\n'.join(result)


def export(key, body):
    model=app_core.model(key)
    app_core.require_idle(model)
    from .iteration_choice import latest
    decision = latest(model) or {}
    if decision.get('choice') == 'unavailable':
        raise ValueError('Check the saved edition choice before handoff. / 请在结果总览重新核对工作版，再交接。')
    if decision.get('choice') == 'parent':
        raise ValueError('Open the selected baseline to hand it off. / 请打开已选用的基准版，再交接该版成果。')
    if decision.get('choice') == 'wait':
        raise ValueError('Resume this review before handoff. / 本版正在等资料，请先在结果总览继续复核。')
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
        pages={name:page(lang,model,assessment,folders,receipt,pair) for lang,name in [('en','Start_EN.html'),('zh','Start_zh-CN.html')]}
        tag=digest(dict(pages=pages,assessment=assessment['evidence_hash']))
        destination=base/('Handoff_'+tag[:16])
        latest=app_core.model(key)
        if (latest['revision']!=model['revision'] or latest.get('exports_need_refresh') or latest.get('summary')!=model['summary']
                or handoff.bound_package(latest)!=receipt):
            raise ValueError('The project changed during verification. Reopen results.')
        if not destination.exists():
            with TemporaryDirectory(dir=base) as temporary:
                stage=Path(temporary)/'pages'
                stage.mkdir()
                for name,html in pages.items():
                    (stage/name).write_bytes(html.encode('utf-8'))
                stage.rename(destination)
        if (destination.is_symlink() or destination.resolve()!=destination or set(p.name for p in destination.iterdir())!=set(pages)
                or any((destination/n).is_symlink() or (destination/n).read_bytes()!=v.encode('utf-8') for n,v in pages.items())):
            raise ValueError('The exported reading folder was modified. Restore it or move it aside before exporting again.')
        return dict(folder=rel(destination),files=[item(destination/n) for n in pages],level=assessment['level'],run_id=pair['run_id'],
                    edition=tag,summary=receipt['summary'],packages={k:receipt[k]['manifest'] for k in folders})
