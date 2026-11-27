"""Exercise the diagnostic results-page controls on two archived field events in an isolated checkout."""
import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pyproj import Transformer
from midway_release import page_action
from ras_workflow import app_core as core
from ras_workflow.cli import execute
from ras_workflow.common import ROOT, intact, item, read, rel, save, sha, unique_id


def baseline(archive, river, tag):
    folder=archive/'projects/p12_verified'/tag
    request=read(folder/'request.json')
    original=read(folder/'input.json')
    assert sha(folder/'model/Model.g01')==original['geometry_native_sha256']
    exp=request['expected']
    g=read(archive/f'status/p12_final/prepared/{river}_geometry.json')
    g.update(cross_sections=exp['cross_sections'],boundaries=exp['boundaries'],boundary_slopes=exp['boundary_slopes'])
    xy=g['cross_sections'][0]['center_xy']
    lon,lat=Transformer.from_crs(g['horizontal_crs'],4326,always_xy=True).transform(*xy)
    model=core.create(dict(route='coordinates',model_type='river',title=f'{river} P17 {tag}',latitude=lat,longitude=lon,gis=False))
    base=core.folder(model['id'])/'approved'/unique_id()
    base.mkdir(parents=True)
    config=read(ROOT/model['project'])
    stage_source=original['boundary_source']['source']
    save(base/'geometry.json',g)
    for tail in ('.tif','.tif.source'):
        shutil.copyfile(archive/f'status/p12/sources/{river}_2010{tail}',base/('terrain'+tail))
    config.update(geometry='geometry.json',geometry_review=g['provenance'],
                  terrain=dict(mode='local',raster='terrain.tif',provenance='terrain.tif.source',vertical_datum=g['vertical_datum'],vertical_unit='m'),
                  delivery=dict(enabled=False,mapping_enabled=False),authorization='authorization.json',solver_logging='diagnostic')
    config['scenarios']=[dict(id=tag,channel_n=exp['channel_n'],overbank_n=exp['overbank_n'],
                              parameter_source='Frozen P12 diagnostic baseline '+original['protocol'],
                              profiles=[dict(p,source=stage_source) for p in request['profiles']])]
    config['location']['crossing_confirmed']=True
    save(base/'authorization.json',dict(project_id=model['id'],allowed_geometry_sha256=sha(base/'geometry.json'),
         scope='site_conditional',basis='Authorized isolated reproduction of the frozen P12 inputs'))
    save(base/'project.json',config)
    code=execute(str(base/'project.json'),tag,fresh=True)
    state=read(base/'state.json')
    if code!=0:raise ValueError(str(state.get('errors') or state))
    model.update(status='RESULTS_READY',phase='DONE',scenario=tag,active_project=rel(base/'project.json'),
                 summary=state['latest_summary'],engine_state=rel(base/'state.json'))
    core.persist(model)
    return model


def comparison_file(archive,model,river,year,folder):
    source=archive/'status/p12_final/observation_roles.csv'
    with source.open(encoding='utf-8-sig') as stream:
        line,row=next((i,r) for i,r in enumerate(csv.DictReader(stream),2)
                      if r['event']==river+'_'+year and r['role'].startswith('primary') and r['side']=='downstream')
    shift=read(archive/f'status/p12_final/prepared/{river}_audit.json')['datum_shift_ft_us_ds'][0]
    cfg=read(ROOT/model['active_project'])
    geom=read((ROOT/model['active_project']).parent/'geometry.json')
    out=folder/(river+'_comparison.csv')
    with out.open('w',newline='',encoding='utf-8') as s:
        writer=csv.writer(s)
        writer.writerow(['profile','rs','stage_ft','flow_cfs','vertical_datum','source_record'])
        writer.writerow(['Base',geom['cross_sections'][0]['rs'],float(row['published_ft'])+shift,cfg['scenarios'][0]['profiles'][0]['flow_cfs'],
                         geom['vertical_datum'],f'{source.name} row {line} · {row["event"]} · {row["location"]} · {row["side"]} · SHA-256 {sha(source)} · datum shift {shift} ft'])
    return out


def run(archive,folder):
    folder.mkdir(parents=True,exist_ok=True)
    saved=folder/'cases.json'
    cases=read(saved) if saved.exists() else {}
    results={}
    for river,tag,kind,year in [('Floyd','f24base','terrain','2024'),('Turkey','t16fine','spacing','2016')]:
        if river not in cases:
            m=baseline(archive,river,tag)
            cases[river]=m['id']
            save(saved,cases)
        m=core.model(cases[river])
        if not intact([m['summary']]):
            raise ValueError('Original parent changed')
        original=m['summary']
        checks=comparison_file(archive,m,river,year,folder)
        if kind=='terrain':
            source=archive/'status/p12/sources/Floyd_2020.tif'
        else:
            source=folder/'Turkey_nested.json'
            g=read(archive/'status/p12_followup/spacing129/prepared/Turkey_geometry.json')
            native=read(archive/'projects/p12_verified/t16x129/request.json')
            g['cross_sections']=native['expected']['cross_sections']
            save(source,g)
        existing=read(ROOT/m['latest_factor_diagnostic']['path']) if m.get('latest_factor_diagnostic') else {}
        if existing.get('status')!='DIAGNOSTIC_REVIEW' or len(existing.get('comparisons',[]))!=2:
            if kind=='terrain':
                bridge=read(archive/'status/p12_followup/bridge_mark_results.json')['Floyd']
                queue=dict(kind='boundary',value=bridge['stages'][1],basis=f"USGS STN {bridge['ids'][0]} at the IA-60 pier. Diagnostic outlet control, NAVD88.")
            else:
                queue=dict(kind='bed',value=-.25,basis='Conditional sensitivity only: lower the channel center 0.25 ft, tapering to zero at both banks. No survey return is asserted.')
            page_action(m['id'],'factor-trial',factor=kind,source=str(source.resolve()),checks=str(checks.resolve()),
                        basis=f'P12 {year} retrospective {kind} test. Retain the frozen event, roughness and surveyed outlet.',queue=queue)
        m=core.model(m['id'])
        if m['summary']!=original:raise ValueError('Parent changed during the trial')
        batch=read(ROOT/m['latest_factor_diagnostic']['path'])
        assert batch['status']=='DIAGNOSTIC_REVIEW'
        r,other=batch['comparisons']
        assert r['options']['flow_cfs']==(41000 if river=='Floyd' else 35700)
        assert other['options']['flow_cfs']==r['options']['flow_cfs'] and other['baseline']==original
        assert other['options']['checks']==r['options']['checks'] and other['options']['original_sections']==r['options']['original_sections']
        if river=='Floyd':
            assert other['warning_counts']==[14,12]
            assert other['stop']=='RETAIN_PARENT_OBSERVATION_WORSENED'
            assert abs(other['checks'][0]['trial_error_ft']+2.202)<.002
        assert len(r['checks'])==1 and abs(r['checks'][0]['trial_error_ft']-(-1.640 if kind=='terrain' else -2.522))<.002
        if kind=='terrain':assert abs(r['checks'][0]['trial_error_ft']-r['checks'][0]['parent_error_ft']-.060)<.001
        else:assert float(r['max_change']['rs'])==16889.98 and abs(r['max_change']['delta_ft']-.788635)<.001 and list(map(len,r['wet_sections']))==[8,17]
        results[river]=dict(project=m['id'],baseline=m['summary'],trial=r['trial'],analysis=m['latest_factor_diagnostic'],
                            checks=r['checks'],worst=r['max_change'],wet=list(map(len,r['wet_sections'])),warning_counts=r['warning_counts'],
                            second_factor=dict(kind=other['id'],stop=other['stop'],warnings=other['warning_counts'],check=other['checks'],trial=other['trial']))
    save(folder/'release.json',dict(status='PASSED',events=results))
    print(folder/'release.json',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('--resume',type=Path)
    args=parser.parse_args()
    run(args.archive.resolve(),args.resume or ROOT/'status/p17'/unique_id())
