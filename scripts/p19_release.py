"""Replay method selection against field time series and archived native editions."""
import argparse
import base64
import os
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from docx import Document
from ras_workflow import app_core as core, feasibility, method_review, report_data, result_guidance
from ras_workflow.cli import execute
from ras_workflow.common import intact, item, read, rel, save, sha, unique_id
from ras_workflow.recipient_handoff import page
from ras_workflow.river_report import build


def isolate(archive,key):
    if archive==ROOT:
        raise ValueError('Use a separate checkout for this acceptance')
    while key:
        source=archive/'projects'/key
        target=core.folder(key)
        def duplicate(src,dst):
            if Path(src).suffix.lower() in ('.json','.csv','.txt','.md','.html'):
                return shutil.copy2(src,dst)
            # Immutable native, imagery and terrain files stay in place; review does not write them.
            try:os.link(src,dst)
            except OSError:shutil.copy2(src,dst)
        if not target.exists():
            shutil.copytree(source,target,copy_function=duplicate)
        assert sha(source/'app.json')==sha(target/'app.json')
        key=read(source/'app.json').get('parent_revision',{}).get('project_id')


def turkey(raw,source):
    p=read(ROOT/source['baseline']['path'])['configuration']
    parent=core.model(source['project'])
    approved=(ROOT/parent['active_project']).parent
    project=core.create(dict(route='coordinates',model_type='river',title='Turkey P19 timing',gis=False,
                             latitude=p['location']['latitude'],longitude=p['location']['longitude']))
    key=project['id']
    m=core.model(key)
    content=raw.read_bytes()
    assert sha(raw)==read(Path(str(raw)+'.source'))['sha256']
    method_review.attach(key,dict(revision=m['revision'],content=base64.b64encode(content).decode(),
                                  day='2016-08-25',profile='Base',flow_cfs=35700))
    m=core.model(key)
    path=core.folder(key)/'approved'/unique_id()
    path.mkdir(parents=True)
    for file in ('terrain.tif','terrain.tif.source','geometry.json'):
        shutil.copyfile(approved/file,path/file)
    auth=read(approved/'authorization.json');auth['project_id']=key
    save(path/'authorization.json',auth)
    p.update(project_id=key,title=m['title'],production_scope=m['production_scope'])
    g=read(path/'geometry.json')
    prior=feasibility.assess(dict(m,scenario=parent['scenario']),p,g,{})
    note=next(r for r in prior['rows'] if r['key']=='event_timing')
    assert '24.75' in note['en'] and '24.75' in note['zh']
    save(path/'project.json',p)
    code=execute(str(path/'project.json'),parent['scenario'],fresh=True)
    state=read(path/'state.json')
    if code:raise ValueError(state.get('errors') or state)
    m.update(status='RESULTS_READY',phase='DONE',scenario=parent['scenario'],active_project=rel(path/'project.json'),
             summary=state['latest_summary'],engine_state=rel(path/'state.json'))
    core.persist(m)
    return key


def verify(key,words,folder):
    m=core.model(key)
    assert intact([m['summary']])
    path=ROOT/m['summary']['path'];s=read(path)
    assessment=result_guidance.collect(key,dict(summary_hash=m['summary']['sha256'],include_assessment=True))['assessment']
    data=report_data.collect(path)
    assert assessment['edition_brief']==data['edition_brief']
    notes=[r for r in data['edition_brief']['rows'] if r['heading']['en']=='Steady-flow applicability']
    assert notes and all(w in str(notes) for w in words),notes
    file=path.parent/'reports/report_manifest.json'
    manifest=read(file)
    figures=read(ROOT/manifest['figures']['path'])
    docs={}
    handoff={}
    paired=path.parent/'delivery/delivery.json'
    for lang in ('en','zh-CN'):
        doc=build(data,figures.get(lang,figures),folder,lang,'full')
        output=folder/(key+'_'+lang+'.docx')
        doc.save(output)
        body=' '.join(p.text for p in Document(output).paragraphs)
        assert all(w in body for w in words)
        docs[lang]=item(output)
        if paired.exists():
            receipt=read(paired)
            assert receipt['summary']==m['summary']
            locations={k:ROOT/receipt[k]['path'] for k in ('complete','minimal')}
            pair=dict(run_id=s['hydraulics']['run_id'],mapped=receipt['mapped'],native_hdf_sha256=s['hydraulics']['raw_hdf']['sha256'])
            rendered=page('zh' if lang=='zh-CN' else 'en',m,assessment,locations,receipt,pair,{})
            assert all(w in rendered for w in words)
            handoff[lang]=True
    return dict(summary=m['summary'],hdf=s['hydraulics']['raw_hdf'],notes=notes,reports=docs,handoff=handoff)


def run(args):
    out=ROOT/'status/p19'/unique_id()
    out.mkdir(parents=True)
    key=args.turkey or turkey(args.hydrograph,read(args.p17)['events']['Turkey'])
    print('Turkey',key,flush=True)
    results={'Turkey':verify(key,['24.75','35700'],out)}
    for site,key,words in [('Merced','site_20261119t124424_cc9e08fc86',['RS 4700','70.14%']),
                           ('Pagosa','site_20261119t082835_2953e3365d',['14/32','RS 1400','5.793'])]:
        isolate(args.archive.resolve(),key)
        results[site]=verify(key,words,out)
    save(out/'release.json',dict(status='PASSED',cases=results))
    print(out/'release.json')


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--hydrograph',type=Path,required=True)
    cli.add_argument('--archive',type=Path,required=True)
    cli.add_argument('--p17',type=Path,required=True)
    cli.add_argument('--turkey',help='Reuse a verified P19 Turkey edition when checking report output again')
    run(cli.parse_args())
