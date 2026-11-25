"""Replay the Midway baseline, supplemental geometry, wet-end revision and portable handoff."""
import csv
import shutil
from html.parser import HTMLParser
from tempfile import TemporaryDirectory
from urllib.parse import unquote, urlsplit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ras_workflow import app_core as core, app_parameters as parameters, iteration_choice, recipient_handoff
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


# Run browser steps on the same checkout and server used by local engineers.


def browser_action(payload):
    import json
    import subprocess
    browser=subprocess.run(['node',str(ROOT/'scripts/midway_page.cjs')],cwd=ROOT,
        input=json.dumps(payload),text=True,encoding='utf-8',capture_output=True,timeout=700)
    need(browser.returncode==0,'Browser acceptance failed: '+browser.stderr)
    return browser.stdout.strip()


def page_action(key,mode,**info):
    from ras_workflow.app_server import create
    from threading import Thread
    server=create()
    worker=Thread(target=server.serve_forever,daemon=True)
    worker.start()
    try:
        return browser_action(dict(url=server.url,project=key,mode=mode,**info))
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
    delivery_dir=(ROOT/model['summary']['path']).parent/'delivery'
    delivery=read(delivery_dir/'delivery.json')
    need(delivery.get('mapped') and delivery['status']=='READY_FOR_REVIEW',
         f"Mapped delivery incomplete for {key}: {delivery.get('error',delivery['status'])}")
    packages=check(delivery_dir/'Complete',delivery_dir/'Minimal')
    need(packages['native_hdf_sha256']==hyd['raw_hdf']['sha256'],'Delivery used another native result')
    return dict(project=key, summary=model['summary'], run_id=hyd['run_id'], hdf=hyd['raw_hdf'],
                delivery=item(delivery_dir/'delivery.json'), package_check=packages,
                confirmation=model['run_confirmation'], road_width_ft=road_width, sections=len(water),
                wet_stations=profile['qa']['wet_edges'],
                widths_ft={str(float(xs['rs'])):xs['station_ft'][-1]-xs['station_ft'][0]
                           for xs in geometry['cross_sections']},
                headwater_ft=profile['metrics']['headwater_wse_ft'],
                tailwater_ft=profile['metrics']['tailwater_wse_ft'])


def verify_detached(folder, expected, baseline):
    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag=='a':
                link=dict(attrs)['href']
                url=urlsplit(link)
                member=(self.base/unquote(url.path)).resolve()
                need(not url.scheme and not url.netloc and member.is_relative_to(self.base) and member.is_file(),
                     'Recipient link is missing or points outside the transfer: '+link)
    with TemporaryDirectory() as tmp:
        copy=Path(tmp)/'Recipient'
        shutil.copytree(folder,copy)
        for name in ('Start_EN.html','Start_zh-CN.html'):
            links=Links()
            links.base=copy
            links.feed((copy/name).read_text('utf-8'))
        for name in ('Complete','Minimal'):
            root=copy/name
            manifest=root/'PACKAGE_MANIFEST.json'
            need(sha(manifest)==sha(folder/name/manifest.name),'Detached manifest changed: '+name)
            from ras_workflow.delivery_pair import verified_member
            for entry in read(manifest)['files']:
                verified_member(root,entry['path'],entry['sha256'])
        pair=check(copy/'Complete',copy/'Minimal')
        browser=dict(mode='recipient-copy',url=(copy/'Start_EN.html').as_uri(),folder=str(copy),run_id=expected['run_id'])
        pair['offline_browser']=browser_action(browser)
        pair['detected_files']={}
        need(pair['native_hdf_sha256']==expected['hdf']['sha256'],'Detached transfer belongs to a different calculation')
        # Verify that missing, mixed or edited files are detected in the disposable recipient copy.
        pdf=copy/'Complete/Reports/Report_EN.pdf'
        fingerprint=sha(pdf)
        length=pdf.stat().st_size
        pdf.rename(pdf.with_suffix('.saved'))
        try:
            baseline_pdf=(ROOT/baseline['delivery']['path']).parent/'Complete/Reports/Report_EN.pdf'
            need(sha(baseline_pdf)!=fingerprint,'Expected two distinct PDF editions')
            for case in ('missing','mixed','changed'):
                if case=='mixed':shutil.copyfile(baseline_pdf,pdf)
                if case=='changed':pdf.write_bytes(b'altered recipient test')
                pair['detected_files'][case]=browser_action(dict(browser,problem='Complete/Reports/Report_EN.pdf'))
                try:check(copy/'Complete',copy/'Minimal')
                except (OSError,ValueError) as error:
                    need('Report_EN.pdf' in str(error),'Expected a file-specific recovery message')
                    continue
                raise ValueError(f'{case} transfer member was accepted')
        finally:
            pdf.with_suffix('.saved').replace(pdf)
        need(pdf.stat().st_size==length and sha(pdf)==fingerprint,'Detached verification did not restore its copy')
    return pair


def verify_outcomes(key, folder, model_type):
    from pypdf import PdfReader
    from ras_workflow.app_revision import compare
    model=core.model(key)
    comparison=compare(model,read(ROOT/model['summary']['path']))
    review=comparison['review']
    ends=review['endpoints']
    metric='roadway_flow_software_cfs' if model_type=='culvert' else 'upstream_wse_ft'
    required=({'headwater_wse_ft','tailwater_wse_ft','roadway_flow_software_cfs'} if model_type=='culvert'
              else {'upstream_wse_ft','downstream_wse_ft','max_channel_velocity_fts','max_channel_froude'})
    for profile in comparison['profiles']:
        keys={r['metric'] for r in review['metrics'] if r['profile']==profile['profile']}
        need(keys==required,'Missing or inappropriate metrics for '+profile['profile'])
    label=next(r['en'] for r in review['metrics'] if r['metric']==metric)
    manifest=read(folder/'Complete/Evidence/report_manifest.original.json')
    from ras_workflow.delivery_pair import verified_member
    ref=manifest['data']
    archived=read(verified_member(folder/'Complete/Reports',Path(ref['path']).name,ref['sha256']))
    frozen=archived['revision_comparison']['review']
    need(frozen['endpoints']==ends and frozen['metrics']==review['metrics'],'Frozen report assessment differs from edition page')
    need(ends['status']=='COMPARED' and ends['counts']['unmatched']==0,'Expected matching native section sides')
    section=next((r for r in ends['rows'] if r['current_depth_ft'] is not None),None)
    page_action(key,'edition-outcomes',caption=ends['en'],chinese=ends['zh'],metric=label,map_case=section)
    for language,edition,start in [('en','EN','Start_EN.html'),('zh','CN','Start_zh-CN.html')]:
        text=''.join(p.extract_text() or '' for p in PdfReader(folder/'Complete/Reports'/('Report_'+edition+'.pdf')).pages)
        need(''.join(ends[language].split()) in ''.join(text.split()),'Endpoint summary missing from '+edition+' PDF')
        need(ends[language] in (folder/start).read_text('utf-8'),'Endpoint summary missing from '+start)
    return dict(counts=ends['counts'],rows=ends['rows'],metrics=review['metrics'])


def rehearse_return(key, second, directory):
    directory.mkdir()
    worksheet=Path(page_action(key,'condition-review',download=str(directory),run_id=second['run_id']))
    with worksheet.open(encoding='utf-8-sig',newline='') as handle:
        reader=csv.DictReader(handle)
        fields=reader.fieldnames
        rows=list(reader)
    need(len(rows)==2 and all(not r['value'] and r['datum']=='NAVD88' for r in rows),'Expected two blank invert requests with datum')
    for row in rows:
        row.update(value=row['prior_ft'],source='Isolated software replay of the existing estimate. No field survey.',
                   evidence_class='assumed')
    returned=directory/'assumed_return.csv'
    with returned.open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    child=page_action(key,'survey-return',files=[str(returned)])
    model=core.model(child)
    answers=parameters.objects(model)[2]['answers']
    for row in rows:
        saved=answers[row['field']]
        need(saved['evidence_class']=='assumed' and saved['candidate_record']['source']['sha256']==sha(returned),
             'Return must remain linked to its source and keep its assumption class')
    need(not model.get('summary') and model['parent_revision']['summary']==second['summary'],'Survey return must remain an independent draft')
    return dict(draft=child,worksheet=item(worksheet),returned=item(returned),values_measured=False)


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
    imagery_label='USGS NAIP, archived site imagery; pinned source raster'
    if spec.get('aerial_source'):
        receipt=checked_file(base,spec['aerial_source'])
        record=read(receipt)
        need(record['raster']['sha256']==sha(aerial),'Imagery differs from its acquisition receipt')
        imagery_label=record['source']
        shutil.copyfile(receipt,folder/receipt.name)
        config['delivery'].setdefault('additional_sources',[]).append(receipt.name)
    config['delivery']['imagery'] = dict(raster=aerial.name,source=imagery_label)
    save(ROOT/m['project'],config)
    core.prepare(key)
    fields = {'g.structure.groups.0.shape':'box','g.structure.groups.0.count':3,
              'g.structure.groups.0.span_ft':8.,'g.structure.groups.0.rise_ft':6.,
              'g.structure.road.width_ft':25.}
    first_page = page_action(key,'prepare-crossing',files=[str(p) for p in originals],dimensions=fields,
                             openings={k:spec['picks'][k][0] for k in ('inlet','outlet')},
                             gap=spec['spacing'],length=150,maximum=160)
    session=ROOT/core.model(key)['session']
    proposals=list((session.parent/'automatic_geometry').glob('*/proposal.json'))
    need(len(proposals)==1,'Expected one fresh layout preview')
    layout=read(proposals[0])['layouts'][0]
    need(layout['seed']['basis']=='SAVED_MAP_MOUTHS' and len(layout['anchors'])==2 and
         all(len(r['anchors_xy'])>=2 for r in layout['anchors']), 'Expected exterior anchors generated by the DEM')
    first = solve(key)
    print('First native solve', first['run_id'], flush=True)
    revised = page_action(key,'supplement',files=[str(supplement),str(brief)])
    model=core.model(revised)
    need(model['parent_revision']['project_id']==key,'Supplement must create a separate revision')
    updated=parameters.objects(model)[2]['answers']
    road=updated['g.structure.road.width_ft']
    need(road['evidence_class']=='assumed' and road['candidate_record']['source']['sha256']==sha(supplement),
         'The supplemental nominal width must retain the document hash and conditional interpretation')
    from ras_workflow.app_material_revision import DEPENDENTS, ROAD
    need(all(updated[ROAD+field].get('candidate_record',{}).get('automation_context') for field in DEPENDENTS),
         'Expected six traceable road-profile derivations')
    second = solve(revised)
    need(first['road_width_ft']==25 and second['road_width_ft']==26,'Road width did not reach the compiled geometry')
    need(first['run_id'] != second['run_id'] and first['hdf']['path'] != second['hdf']['path']
         and intact([first['summary'],first['hdf'],first['delivery'],second['hdf']]),
         'The two native result sets and baseline delivery must remain independently intact')
    m = core.model(revised)
    body = dict(revision=m['revision'],summary_hash=m['summary']['sha256'])
    wet_key=page_action(revised,'wet-revision')
    wet=solve(wet_key)
    need(wet['run_id']!=second['run_id'] and intact([second['hdf'],second['summary']]),'Wet-end revision must have its own calculation')
    changed=[rs for rs,width in second['widths_ft'].items()
             if abs(wet['widths_ft'][rs]-width)>.01]
    need(len(changed)==1 and changed[0] in {str(float(rs)) for rs in second['wet_stations']}
         and wet['widths_ft'][changed[0]]>second['widths_ft'][changed[0]],'Widened section must match a computed wet end')
    wet['adjusted_station']=changed[0]
    from ras_workflow.app_revision import compare
    wet_review=compare(core.model(wet_key),read(ROOT/wet['summary']['path']))['review']['endpoints']
    need(wet_review['status']=='COMPARED' and wet_review['counts']['unmatched']==0,'Wet revision lost section correspondence')
    wet['adjusted_ends']=[r for r in wet_review['rows'] if float(r['station'])==float(changed[0])]
    need(wet['adjusted_ends'],'Cannot locate the previously wet section in the new side-by-side assessment')
    survey_return=rehearse_return(revised,second,evidence.parent/'survey')
    transfer=page_action(revised,'edition-transfer',parent=key)
    choice=iteration_choice.latest(core.model(revised))
    need([r['choice'] for r in choice['history']][-4:]==['wait','parent','review','current'],'Edition selection history incomplete')
    handoff=recipient_handoff.export(revised,body)
    need(handoff['folder']==transfer,'Browser transfer and verified selection disagree')
    path=ROOT/transfer
    detached=verify_detached(path,second,first)
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
    expected_state='REVISE' if any(r['state']=='exceeded' for r in decision['rows']) else 'NEED_EVIDENCE'
    need(decision['state']==expected_state and
         any(r['state']=='missing' for r in decision['rows']),
         'Unmeasured site geometry must remain visible in the purpose decision')
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
    result['edition_outcomes']=verify_outcomes(revised,path,'culvert')
    result['browser']=page_action(revised,'handoff',decision=decision,run_id=second['run_id'])
    result.update(wet_revision=wet,survey_return=survey_return,detached=detached,
                  first_page=first_page, geometry_proposal=item(proposals[0]), seed=layout['seed']['basis'],
                  generated_anchors={r['id']:len(r['anchors_xy']) for r in layout['anchors']},
                  road_fields=list(DEPENDENTS), revised_width_class=road['evidence_class'])
    save(evidence,result)
    return result
