"""Replay the coordinate-based Midway case from private source material in two fresh projects."""
import base64
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ras_workflow import app_core as core, app_parameters as parameters, app_revision
from ras_workflow import app_autoprepare, app_geometry, iteration_choice, recipient_handoff
from ras_workflow.common import intact, item, read, save, sha
from ras_workflow.delivery_pair import check


def need(condition, message):
    if not condition:
        raise ValueError(message)


def checked_file(folder, entry):
    name = entry['file']
    path = (folder / name).resolve()
    need(path.parent == folder and path.is_file() and sha(path) == entry['sha256'],
         f'Missing or changed private source: {name}')
    return path


def wait_for(job, timeout=1200):
    path = ROOT / job['task']
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        record = read(path)
        if record['status'] != 'RUNNING':
            need(record['status'] == 'FINISHED', f"Inspect {path}: {record}")
            return
        time.sleep(1)
    raise TimeoutError(f'Worker still running; inspect {path}')


def attach(key, paths):
    files = [dict(name=p.name, content=base64.b64encode(p.read_bytes()).decode('ascii')) for p in paths]
    wait_for(core.attach(key, files))


def page_action(key,mode,**info):
    from ras_workflow.app_server import create
    from threading import Thread
    import json
    import subprocess
    server=create()
    worker=Thread(target=server.serve_forever,daemon=True)
    worker.start()
    try:
        browser=subprocess.run(['node',str(ROOT/'scripts/midway_page.cjs')],cwd=ROOT,
            input=json.dumps(dict(url=server.url,project=key,mode=mode,**info)),
            text=True,encoding='utf-8',capture_output=True,timeout=700)
        need(browser.returncode==0,'Browser acceptance failed: '+browser.stderr)
        return browser.stdout.strip()
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def solve(key):
    review = parameters.review(core.model(key))
    need(review['ready'], f"Parameter review: {review['errors']}")
    page_action(key,'solve')
    model = core.model(key)
    need(model.get('summary') and intact([model['summary']]), f'Missing current solver output: {key}')
    summary = read(ROOT / model['summary']['path'])
    hyd = summary['hydraulics']
    from ras_workflow.qa import verified_profiles
    water=verified_profiles(hyd)['Q100']
    need(len(water)>=4 and all(v is not None for v in water.values()), 'Missing native section profiles')
    from ras_workflow.revision_inputs import bound_inputs
    _,geometry,_=bound_inputs(summary)
    road_width=geometry['structure']['road']['width_ft']
    profile = next(p for p in hyd['profiles'] if p['profile_id'] == 'Q100')
    need(profile['flow_cfs'] == 457 and len(profile['culvert_groups']) == 1 and
         profile['culvert_groups'][0]['barrel_count'] == 3, 'Midway profile or opening mismatch')
    return dict(project=key, summary=model['summary'], run_id=hyd['run_id'], hdf=hyd['raw_hdf'],
                confirmation=model['run_confirmation'], road_width_ft=road_width, sections=len(water),
                headwater_ft=profile['metrics']['headwater_wse_ft'],
                tailwater_ft=profile['metrics']['tailwater_wse_ft'])


def replay(fixture, evidence):
    base = fixture.resolve().parent
    spec = read(fixture)
    originals = [checked_file(base, entry) for entry in spec['originals']]
    supplement = checked_file(base, spec['supplement'])
    brief = checked_file(base, spec['brief'])
    need(brief.suffix.lower()=='.txt','Expected the accompanying site brief')
    need(len(originals) == len(set(originals)) == 6 and
         sorted(p.suffix.lower() for p in originals) == ['.jpg']*4+['.kmz','.pdf'] and
         supplement.suffix.lower() == '.docx', 'Expected four original photos, KMZ, StreamStats and supplemental memo')
    dem, metadata, aerial = [checked_file(base, spec[k]) for k in ('terrain','terrain_source','aerial')]
    need(read(metadata)['raster']['sha256'] == sha(dem), 'DEM differs from the USGS provenance receipt')
    scope = dict(purpose='screening',flow_paths='single',criteria=dict(profile='Q100',dry_ends=True,site_geometry=True))
    m = core.create(dict(title='Midway · release replay',route='coordinates',model_type='culvert',
                         latitude=35.18064,longitude=-119.45835,channel_n=.050,overbank_n=.065,
                         dem_vertical_unit='m',dem_vertical_datum='NAVD88',production_scope=scope,gis=True))
    key = m['id']
    folder = core.folder(key)
    print('Fresh project',key,flush=True)
    # Seed only the two public source rasters and the original catalog receipt.
    # The ordinary local-terrain path verifies site coverage and resamples every cross section.
    for path in (dem,metadata,aerial):
        shutil.copyfile(path, folder/path.name)
    config = read(ROOT/m['project'])
    config['terrain'] = dict(mode='local',raster=dem.name,provenance=metadata.name,vertical_unit='m',vertical_datum='NAVD88')
    config['delivery']['imagery'] = dict(raster=aerial.name,source='USGS NAIP, archived site imagery; pinned source raster')
    save(ROOT/m['project'],config)
    core.prepare(key)
    attach(key, originals)
    picks = spec['picks']
    app_geometry.perform(key,'picks',dict(picks=picks,group_index=0,wall_gap_ft=spec['spacing'],parameters=spec['sampling']))
    app_geometry.perform(key,'generate',dict(parameters=spec['sampling'],
                         external_reaches=[dict(id=k,anchors_xy=picks[k]) for k in ('upstream','downstream')]))
    # These dimensions and roughnesses are the commissioning inputs. The first
    # effective crest width is an explicit trial assumption pending the road memo.
    fields = {'g.structure.groups.0.shape':'box','g.structure.groups.0.count':3,
              'g.structure.groups.0.span_ft':8.,'g.structure.groups.0.rise_ft':6.,
              'g.structure.road.width_ft':25.}
    core.update(key,dict(revision=core.model(key)['revision'],values=fields,
                         classes={k:'assumed' if k.endswith('width_ft') else 'reported' for k in fields}))
    app_autoprepare.execute(key)
    first = solve(key)
    print('First native solve', first['run_id'], flush=True)
    revised = app_revision.create(key,dict(revision=core.model(key)['revision'],confirmed=True))['id']
    attach(revised,[supplement,brief])
    model = core.model(revised)
    road = next(r for r in parameters.rows(model) if r['key']=='g.structure.road.width_ft')
    matches = [c for c in road['parameter_candidates'] if c['value']==26 and
               (c.get('source') or {}).get('sha256')==sha(supplement)]
    need(bool(matches), 'The supplemental road memo must yield a source-linked 26 ft width')
    selection = matches[0]
    parameters.choose(model,[dict(field=road['key'], candidate=selection['candidate'])])
    # Follow the same dependency review as the page. Recompute only the six
    # road-profile inputs whose footprint changed with the adopted width.
    from ras_workflow.app_dependency_review import resolve
    review=parameters.review(core.model(revised))
    affected={e.get('field') for e in review['errors'] if e.get('code')=='DERIVED_INPUT_CHANGED'}
    expected={'g.structure.road.'+name for name in ('distance_us_ft','profile_mode','station_ft','elevation_ft',
                                                   'downstream_station_ft','downstream_elevation_ft')}
    need(affected==expected,'Expected a review of the six revised road-profile dependencies')
    selections=[]
    for field in review['fields']:
        if field['key'] in affected:
            candidates=field['parameter_candidates']
            need(len(candidates)==1,'Revised road-profile candidates need inspection')
            selections.append(dict(field=field['key'],action='candidate',candidate=candidates[0]['candidate']))
    resolve(revised,dict(revision=review['revision'],review_token=review['review_token'],selections=selections))
    second = solve(revised)
    need(first['road_width_ft']==25 and second['road_width_ft']==26,'Road width did not reach the compiled geometry')
    need(first['run_id'] != second['run_id'] and first['hdf']['path'] != second['hdf']['path']
         and intact([first['summary'],first['hdf'],second['hdf']]), 'The two native result sets must remain independently intact')
    m = core.model(revised)
    body = dict(revision=m['revision'],summary_hash=m['summary']['sha256'])
    choice = iteration_choice.choose(revised,dict(body,choice='current'))
    handoff = recipient_handoff.export(revised,body)
    path = (ROOT/handoff['folder']).parent
    pair = check(path/'Complete',path/'Minimal')
    need(pair['mapped'] and pair['native_hdf_sha256']==second['hdf']['sha256'] and
         choice['selected']['summary']==second['summary'] and handoff['run_id']==second['run_id'],
         'Selected edition and mapped handoff must match the fresh native result')
    need(intact(handoff['files']) and m['parent_revision']['summary']==first['summary'], 'Broken recipient or baseline reference')
    need(intact([first['confirmation'],second['confirmation']]),'Missing input confirmation')
    need({ref['sha256'] for ref in core.model(key)['attachments']}=={sha(p) for p in originals} and
         sha(supplement) in {ref['sha256'] for ref in m['attachments']},'Source attachment lineage changed')
    from pypdf import PdfReader
    from ras_workflow.result_guidance import collect
    decision=collect(revised,dict(body,include_assessment=True))['assessment']['purpose_decision']
    need(decision['state']=='REVISE' and any(r['state']=='missing' for r in decision['rows']),
         'The Midway replay must retain wet-end and field-geometry limitations')
    from html import escape
    for lang,code,entry in [('en','EN','Start_EN.html'),('zh','CN','Start_zh-CN.html')]:
        pages=PdfReader(path/'Complete'/'Reports'/('Report_'+code+'.pdf')).pages
        normalize=lambda s: ''.join(s.split())
        title=decision[lang]
        text=normalize(''.join(p.extract_text() or '' for p in pages))
        need(normalize(title) in text, f'{code} report did not match the page verdict')
        note=(ROOT/handoff['folder']/entry).read_text('utf-8')
        need(escape(title) in note and second['hdf']['sha256'] in note, f'{entry} differs from the selected result')
    result=dict(first=first,revised=second,decision=decision,baseline_width_ft=25,revised_width_ft=26,
                originals=[dict(name=p.name,sha256=sha(p)) for p in originals],fixture_sha256=sha(fixture),
                supplement_sha256=sha(supplement),brief_sha256=sha(brief),choice=choice,
                handoff=handoff,pair=pair,engineering_approval='NOT_ASSESSED')
    result['browser']=page_action(revised,'handoff',decision=decision,run_id=second['run_id'])
    save(evidence,result)
    return result
