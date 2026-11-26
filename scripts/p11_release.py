"""Run the three original P11 cases in an isolated checkout using the local project page."""
import argparse
import base64
import csv
import io
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'examples/enterprise_pilot')]
import wsp_survey
from midway_release import need,page_action
from ras_workflow import app_core as core, app_parameters, intake_freeze, raw_intake
from ras_workflow.common import read,save,sha,unique_id
from ras_workflow.common import digest

def copy_baseline(source,key):
    project=source/'projects'/key
    target=ROOT/'projects'/key
    if target.exists():
        need(sha(target/'app.json')==sha(project/'app.json'),'Use a fresh isolated copy of the baseline')
    else:
        shutil.copytree(project,target,ignore=shutil.ignore_patterns('Handoff_*','exports','page-*.png'))
    return key

def contents(path):
    return base64.b64encode(path.read_bytes()).decode('ascii')

def preview(key,path,mode,settings):
    model=core.model(key)
    body=dict(id=key,revision=model['revision'],mode=mode,name=path.name,content=contents(path),settings=settings)
    p=raw_intake.action(key,body,'preview')
    return body,p

def run(p10,soquel_source,visits):
    need(ROOT!=p10 and ROOT!=soquel_source,'Run from a separate acceptance checkout')
    gate=Path(read(p10/'status/p10/closeout.json')['gate'])
    panel=read(gate/'p6/release.json')['cases'];jobs=read(gate/'p10/release.json')['jobs']
    source=p10/'status/p10_inputs/wsp_raw'
    out=ROOT/'status/p11'/unique_id();out.mkdir(parents=True)
    midway=copy_baseline(p10,panel['Midway']['id'])
    soquel=copy_baseline(soquel_source,panel['Soquel']['id'])
    baseline=next(j for j in jobs if j['site']=='Washington State Park' and j['id']=='case_11')
    solved=copy_baseline(p10,Path(baseline['receipt']['path']).parts[1])
    original_hashes={k:sha(core.folder(k)/'app.json') for k in (midway,soquel,solved)}
    # Import the actual survey geometry, terrain, discharge and FGDC metadata. Withhold
    # the prepared observation rows and declaration so the page must rebuild them.
    wsp_survey.prepare(source,out/'geometry')
    survey=out/'geometry/survey';manifest=read(survey/'survey.json')
    field=source/wsp_survey.EVENT
    manifest['files']=[r for r in manifest['files'] if r['name'] not in ('SurveyedOutlet.csv','observed_profiles.csv','intake_evidence.json')]
    save(survey/'survey.json',manifest)
    payload=[dict(name=n,content=contents(survey/n)) for n in ['survey.json',*[r['name'] for r in manifest['files']]]]
    imagery=source.parent/'wsp_imagery'
    aerial=[dict(name=n,content=contents(imagery/n)) for n in ('Aerial.tif','acquisition.json')]
    fresh=core.create(dict(route='survey',title='P11 Washington original field book',gis=True,survey_files=payload,local_rasters=aerial,
                           production_scope=dict(purpose='screening',flow_paths='single')))
    key=fresh['id'];core.prepare(key)
    origin=sha(field);need(origin==read(ROOT/'examples/enterprise_pilot/source_hashes.json')[field.name],'Washington field book fingerprint')
    opts=dict(profile='Feb06',event='Feb06',date='2019-02-06',flow=41,flow_unit='m3/s',crs='EPSG:32615',datum='NAVD88',unit='m')
    body,base=preview(key,field,'stage',opts)
    need(len(base['selectable'])==1 and len([r for r in base['rows'] if r['role']=='interior'])==8,'Unexpected Washington station mapping')
    def rejects(body,problem):
        try:raw_intake.action(key,body,'apply')
        except ValueError as error:need(problem in str(error),str(error))
        else:raise ValueError('Unexpected adoption: '+problem)
    confirmation=dict(body,confirmed=True,lines=base['selectable'],token=base['token'])
    rejects(dict(confirmation,token='old-preview'),'Refresh')
    rejects(confirmation,'uncertainty')
    need(all(r['value'] is None for r in base['rows'] if r['role']=='interior'),'Interior elevations leaked in the baseline preview')
    bad=raw_intake.action(key,dict(body,settings=dict(opts,datum='NGVD29')),'preview')
    need(not bad['selectable'] and all(r['line'] and 'DATUM_MISMATCH' in r['issues'] for r in bad['rows']),'Wrong datum passed')
    line=base['selectable'][0]
    repeated=out/'repeated.csv'
    lines=field.read_text('utf-8-sig').splitlines()
    repeated.write_text('\n'.join([*lines,lines[line-1]])+'\n',encoding='utf-8')
    _,dups=preview(key,repeated,'stage',opts)
    need(not dups['selectable'] and any('DUPLICATE_POINT' in r['issues'] for r in dups['rows']),'Duplicate outlet passed')
    got=page_action(key,'p11-field-book',file=str(field),expectedDefaults=dict(date='2019-02-06',unit='m',datum='NAVD88',crs='EPSG:32615'),count=1,conditional=True)
    need(got==key,'Outlet import did not save')
    m=core.model(key);ctx,reg=intake_freeze.build(m)
    need(reg['boundary']['status']=='CONDITIONAL_SURVEY','Raw outlet failed the normal boundary gate')
    checked=app_parameters.review(m)
    need(not any('UNSUPPORTED_GAGE_BOUNDARY' in str(e) for e in checked['errors']),'Pre-compute boundary was rejected')
    frozen=intake_freeze.perform(key,'freeze',dict(token=digest(ctx)))
    need(intake_freeze.perform(key,'replay',{})['register']==reg,'Frozen raw intake replay differs')
    need(checked['ready'],str(checked['errors']))
    page_action(key,'survey-solve')
    first_summary=read(ROOT/core.model(key)['summary']['path'])
    from ras_workflow.survey_events import records
    from ras_workflow.delivery_pair import check
    from ras_workflow.site_delivery import verify
    def pair(project):
        job=(ROOT/core.model(project)['summary']['path']).parent
        complete=job/'delivery/Complete';minimal=job/'delivery/Minimal'
        result=check(complete,minimal)
        for package in (complete,minimal):verify(package)
        need(result['mapped'],'Missing georeferenced delivery')
        return result
    first_pair=pair(key)
    need(first_pair['native_hdf_sha256']==first_summary['hydraulics']['raw_hdf']['sha256'],'Baseline HDF changed')
    need([r['role'] for r in records(first_summary)[0]]==['boundary'],'Baseline should contain only the outlet')
    returned=page_action(key,'p11-field-book',file=str(field),count=8,child=True)
    child=core.model(returned)
    report=app_parameters.review(child)
    need(child['parent_revision']['project_id']==key and child['intake_return']['mode']=='observation','Observation return lost original association')
    need(report['ready'] and report['return_scope']['affected']==[],str(report['errors'])+' · unexpected reopened hydraulic inputs')
    from ras_workflow.app_parameters import objects
    _,_,_,updated,_=objects(child)
    rows=list(csv.DictReader((ROOT/updated['returned_observations'][-1]['path']).open(encoding='utf-8-sig')))
    need(len(rows)==8 and all(r['role']=='holdout' and 'row ' in r['source'] for r in rows),'Outlet entered the independent return')
    page_action(returned,'survey-solve')
    return_pair=pair(returned)
    measured=records(read(ROOT/core.model(returned)['summary']['path']))[0]
    holdouts=[r for r in measured if r['role']=='holdout']
    worst=max(holdouts,key=lambda r:abs(r['residual_ft']))
    need(len(holdouts)==8 and len(measured)==9 and all(not r['issues'] for r in measured) and worst['location']['rs']=='400','Interior validation changed')
    need(abs(worst['residual_ft']-0.4291452323)<0.003,'Raw survey disagrees with published workstation baseline')
    need(first_pair['run_id']!=return_pair['run_id'],'Expected a newly computed revision')
    from ras_workflow.qa import verified_profiles
    reference=verified_profiles(read(ROOT/core.model(solved)['summary']['path'])['hydraulics'])
    for stage in (key,returned):
        levels=verified_profiles(read(ROOT/core.model(stage)['summary']['path'])['hydraulics'])
        need(levels==reference and len(levels['Feb06'])==9,'Native water surfaces differ from the independent P10 reproduction')
    model=core.model(soquel);info=raw_intake.action(soquel,dict(revision=model['revision']),'inspect')
    gauge=next(r for r in info['stations'] if r['station']=='11160000')
    need(gauge['transfer_required'] and gauge['datum_check']=='CONVERSION_REQUIRED','Soquel water level was promoted')
    _,visit_preview=preview(soquel,visits,'gage',dict(profile='Q100',datum='NGVD29'))
    need(not visit_preview['selectable'] and visit_preview['rows'] and all('GAGE_REQUIRES_REGISTER' in r['issues'] and 'DATUM_MISMATCH' in r['issues'] for r in visit_preview['rows']),'Relative water levels were promoted')
    need(page_action(soquel,'p11-field-book',inspectText='11160000',file=str(visits),measurement='gage',metadata=dict(datum='NGVD29'),count=0)=='BLOCKED','Soquel gage page failed')
    info=raw_intake.action(midway,dict(revision=core.model(midway)['revision']),'inspect')
    need(len(info['invert_fields'])==2 and all(f['missing'] or f['classification'] in ('assumed','inferred','terrain_derived') for f in info['invert_fields']),'Unexpected original Midway evidence')
    incomplete=out/'missing.csv';incomplete.write_text('group,inletinvertft,outletinvertft,datum\n1,,,NAVD88\n',encoding='utf-8')
    need(page_action(midway,'p11-field-book',file=str(incomplete),count=0)=='BLOCKED','Missing invert became numeric')
    # This regression-only return exercises a single changed field; it is not Midway survey evidence.
    g=objects(core.model(midway))[4];row=g['structure']['groups'][0]
    delta=out/'Rehearsal_only.csv';delta.write_text(f'group,inletinvertft,outletinvertft,datum\n1,{row["us_invert_ft"]+.1},,{g["vertical_datum"]}\n',encoding='utf-8')
    partial=page_action(midway,'p11-field-book',file=str(delta),count=1,child=True)
    partial_review=app_parameters.review(core.model(partial))
    need(core.model(partial)['intake_return']['fields']==['g.structure.groups.0.us_invert_ft'],'Untouched field reopened')
    need(partial_review['ready'] and [r['key'] for r in partial_review['return_scope']['affected']]==['g.structure.groups.0.us_invert_ft'],'Only the measured rehearsal inlet should reopen')
    for k,h in original_hashes.items():need(sha(core.folder(k)/'app.json')==h,'Source project changed '+k)
    save(out/'release.json',dict(status='PASSED',human='DEFERRED',cross_machine='DEFERRED',
        washington=dict(draft=key,computed_baseline=solved,native_run=baseline['run'],withheld_return=returned,original_sha256=origin,
            outlet_line=line,held_out_source_rows=[r['source'] for r in rows],frozen_archive=frozen['archive'],boundary=reg['boundary']['status'],
            precompute_ready=checked['ready'],returned_ready=report['ready'],wrong_datum_rejected=True,duplicate_rejected=True,
            new_native_pairs=[first_pair,return_pair],matched_native_sections=9,stale_preview_rejected=True,unknown_accuracy_requires_consent=True,
            worst_rs=worst['location']['rs'],worst_signed_ft=worst['residual_ft']),
        soquel=dict(project=soquel,station=gauge['station'],distance_m=gauge['distance_to_boundary_center_m'],datum=gauge['datum'],mapped_rs=gauge['matched_rs'],
                   blocked_visits=len(visit_preview['rows']),original_visit_sha256=sha(visits)),
        midway=dict(baseline=midway,software_rehearsal_child=partial,actual_surveyed_inverts=0,reopened=core.model(partial)['intake_return']['fields'],
                    partial_ready=partial_review['ready']),original_project_hashes=original_hashes))
    print(out/'release.json',flush=True)
    return out/'release.json'

if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--p10-workspace',required=True,type=Path)
    cli.add_argument('--soquel-workspace',required=True,type=Path)
    cli.add_argument('--soquel-visits',required=True,type=Path,help='Frozen USGS field-measurements GeoJSON for station 11160000')
    args=cli.parse_args()
    run(args.p10_workspace.resolve(),args.soquel_workspace.resolve(),args.soquel_visits.resolve())
