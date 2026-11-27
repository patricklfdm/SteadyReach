"""Replay original STN event downloads and independently compare their located mark IDs."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ras_workflow.common import read, save, sha, unique_id
from ras_workflow.flood_marks import geometry_input
from ras_workflow.flood_register import freeze, replay


def browser_check(archive):
    from midway_release import page_action
    from pyproj import Transformer
    from ras_workflow import app_core as core, intake
    geometry = read(archive/'status/p12_final/prepared/Floyd_geometry.json')
    if isinstance(geometry.get('provenance'),str):
        geometry['provenance']=[geometry['provenance']]
    x,y=geometry['flowlines'][0]['xy'][0]
    lon,lat=Transformer.from_crs(geometry['horizontal_crs'],4326,always_xy=True).transform(x,y)
    model=core.create(dict(route='coordinates',model_type='river',title='Floyd flood mark source review',latitude=lat,longitude=lon))
    path=ROOT/model['project']
    config=read(path)
    config['geometry']='frozen_floyd_geometry.json'
    save(path.parent/config['geometry'],geometry)
    save(path,config)
    session=intake.prepare(path,model['scenario'])
    model.update(session=session['session'],status='INPUTS_READY',phase='SUPPLY_MISSING_INPUTS')
    core.persist(model)
    record=json.loads(page_action(model['id'],'p16-flood',year='2024',river='Floyd River',ids=[348],mark=48210))
    assert record['groups']==4 and record['contextSaved']
    return dict(project=model['id'],**record)


def soquel_check(p11, catalog_file, original):
    from p11_release import copy_baseline
    from ras_workflow import app_core as core
    from ras_workflow.app_parameters import objects
    from ras_workflow.flood_register import registered_stations
    previous=next(r for p in sorted((p11/'status/p11').glob('*/release.json'),reverse=True)
                  if (r:=read(p)).get('status')=='PASSED')
    key=copy_baseline(p11,previous['soquel']['project'])
    model=core.model(key)
    stations=registered_stations(model)
    # Repeat the real location test even though this different regional USGS event has no local marks.
    out=core.folder(key)/'flood_evidence'
    geometry=geometry_input(objects(model)[4])
    v=freeze(out,geometry,'Soquel Creek',catalog_file.read_bytes(),'2024',[348],lambda _:original.read_bytes(),stations)
    result=replay(out,v)
    gage=next(s for s in result['stations'] if s['station']==previous['soquel']['station'])
    assert gage['transfer_required'] and gage['distance_to_boundary_center_m']==previous['soquel']['distance_m']
    assert not result['rows'] and gage['datum']=='NGVD29'
    return dict(station=gage['station'],distance_m=gage['distance_to_boundary_center_m'],independent_marks=0,source=gage['source'])


def main(archive, live, browser, soquel):
    from ras_workflow import flood_marks as marks
    directory = archive/'status/p12_followup'
    sources = {r['event']:r for r in read(directory/'event_sources.json')}
    for r in sources.values():
        assert sha(directory/r['file']) == r['sha256']
    reference = read(directory/'individual_marks.json')
    out = ROOT/'status/p16'/unique_id()
    results = {}
    for name, year, ids in [('Floyd','2018',[307]),('Floyd','2024',[348]),('Turkey','2016',[216,217])]:
        key = name+' '+year
        geometry = geometry_input(read(archive/f'status/p12_final/prepared/{name}_geometry.json'))
        folder = out/key
        catalog = marks.fetch(marks.CATALOG) if live else (directory/'modern_events.json').read_bytes()
        download = marks.fetch if live else lambda url:(directory/sources[int(url.split('event=')[1].split('&')[0])]['file']).read_bytes()
        version = freeze(folder,geometry,name+' River',catalog,year,ids,download)
        p = replay(folder,version)
        expected = {r['id'] for r in reference[key]}
        assert {r['id'] for r in p['rows']} == expected and len(expected)=={'Floyd 2018':4,'Floyd 2024':15,'Turkey 2016':9}[key]
        assert replay(folder,version) == p
        by_id = {r['id']:r for r in p['rows']}
        for r in p['rows']:
            actual = read(directory/sources[r['event']]['file'])[r['line']-1] if not live else read(ROOT/next(s['path'] for s in p['sources'] if s['event']==r['event']))[r['line']-1]
            assert actual['id']==r['id'] and r['lonlat']==[actual['longitude_dd'],actual['latitude_dd']]
            assert 'z_ft' not in r
        if key=='Turkey 2016':
            assert len({by_id[i]['group'] for i in (27060,27063,27065)})==1
            assert all(not by_id[i]['datum_matches'] for i in (27060,27063,27065))
        if key=='Floyd 2024':
            assert by_id[48210]['group']==by_id[48211]['group']
            assert by_id[48359]['group']==by_id[48212]['group']
        results[key]=dict(ids=sorted(expected),groups=p['location_groups'],version=version,files=p['sources'])
    ui=browser_check(archive) if browser else None
    remote=soquel_check(soquel,directory/'modern_events.json',directory/'event_348.json') if soquel else None
    save(out/'release.json',dict(status='PASSED',live=live,events=results,browser=ui,soquel=remote,source='Original STN mark coordinates; no new hydraulic accuracy assessment.'))
    print(out/'release.json')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--browser',action='store_true',help='Also exercise the project page against live USGS in an isolated checkout')
    parser.add_argument('--soquel',type=Path,help='Original P11 checkout for the remote gage check')
    a=parser.parse_args()
    main(a.archive,a.live,a.browser,a.soquel)
