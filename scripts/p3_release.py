"""Fresh same-machine browser journeys using field originals and a separate transfer case."""
import argparse
from pathlib import Path
import shutil
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ras_workflow import app_core
from ras_workflow.common import ROOT, read, save, sha, unique_id
from ras_workflow.delivery_pair import check
from midway_release import checked_file, need, page_action, solve


def run(packet,fixture,blind,dest,transfer_imagery=None):
    from release_benchmark import field_screen
    from pypdf import PdfReader
    dest.mkdir(parents=True,exist_ok=True)
    receipt=dict(scope='isolated same-machine browser',status='RUNNING',cases={},steps=[])
    def update():
        save(dest/'journeys.json',receipt)
    def page(key,mode,**info):
        start=time.monotonic()
        step=dict(mode=mode,project=key,status='RUNNING')
        receipt['steps'].append(step);update()
        try:
            result=page_action(key,mode,**info)
            step['status']='PASSED'
            return result
        except Exception as exc:
            step.update(status='FAILED',error=str(exc))
            raise
        finally:
            step['seconds']=round(time.monotonic()-start,2)
            update()
    def handoff(key):
        model=app_core.model(key)
        summary=read(ROOT/model['summary']['path'])
        folder=ROOT/page(key,'transfer-current')
        pair=check(folder/'Complete',folder/'Minimal')
        need(pair['run_id']==summary['hydraulics']['run_id'] and pair['native_hdf_sha256']==summary['hydraulics']['raw_hdf']['sha256'],'Transfer edition differs')
        page(None,'recipient-copy',url_override=(folder/'Start_EN.html').as_uri(),run_id=pair['run_id'],folder=str(folder))
        return folder,pair
    try:
        hashes=read(packet/'SHA256.json')
        review=read(packet/'review.json')
        frozen=check(packet/'Packages/Complete',packet/'Packages/Minimal')
        ref=next(s for s in review['siletz'] if s['run']==frozen['run_id'])
        source=packet/ref['id']/'Sources/survey.json'
        inputs=dest/'siletz_sources';inputs.mkdir()
        by_hash={v:packet/k for k,v in hashes.items()}
        shutil.copyfile(source,inputs/'survey.json')
        for r in read(source)['files']:
            raw=by_hash[r['sha256']]
            need(sha(raw)==r['sha256'],'Frozen source changed.')
            shutil.copyfile(raw,inputs/r['name'])
        aerial=packet/'Packages/Complete/Evidence/Imagery'
        rasters=[aerial/name for name in ('Aerial.tif','acquisition.json')]
        need(all(hashes.get(f.relative_to(packet).as_posix())==sha(f) for f in rasters),'Archived Siletz imagery changed.')
        key=page(None,'home-survey',title='Siletz · field comparison',folder=str(inputs),protocol=True,rasters=list(map(str,rasters)))
        receipt['cases']['Siletz']={'project':key};update()
        for name in ('first','revision'):
            if name=='revision':
                key=page(key,'river-revision')
            page(key,'survey-solve')
            folder,pair=handoff(key)
            model=app_core.model(key)
            s=read(ROOT/model['summary']['path'])
            field=field_screen(packet,ref,hashes,(pair['run_id'],ROOT/s['hydraulics']['raw_hdf']['path']))
            data=read(folder/'Complete/Reports/report_data.json')
            decision=data['purpose_decision']
            need(decision['state']=='REVISE' and abs(field['signed_residual_m']-.524)<.001 and
                 len([r for r in data['river_checks']['events'] if r['role']=='holdout' and not r['issues']])==1,'Wrong event or verdict')
            if name=='first':
                from unittest.mock import patch
                from ras_workflow import survey_events
                from ras_workflow.purpose_acceptance import evaluate
                config,geometry,refs=survey_events.bound_inputs(s)
                with patch.object(survey_events,'bound_inputs',return_value=(config,dict(geometry,vertical_datum='UNKNOWN'),refs)):
                    incomplete=survey_events.records(s)[0]
                need(evaluate(s,incomplete)['state']=='NEED_EVIDENCE' and all(r['residual_ft'] is None for r in incomplete),
                     'Removing datum information must prevent a stage comparison.')
                measured=next(r for r in data['river_checks']['events'] if r['role']=='holdout')
                need(measured['uncertainty_ft'] is None and any(r['state']=='missing' and 'uncertainty' in r['en'] for r in decision['rows']),
                     'Undocumented stage uncertainty must remain open.')
                receipt['cases']['Siletz']['negative_checks']=dict(missing_datum='NEED_EVIDENCE',missing_uncertainty='OPEN')
            for lang,filename in [('EN','Start_EN.html'),('CN','Start_zh-CN.html')]:
                pdf=''.join(p.extract_text() for p in PdfReader(folder/f'Complete/Reports/Report_{lang}.pdf').pages)
                guide=(folder/filename).read_text('utf-8')
                need('Calculated%20Data.csv' in guide,'Missing link to the packaged observation original.')
                for term in (f"{field['signed_residual_m']:+.4f}",'44056','34913','0.150'):
                    need(term in pdf and term in guide,'Missing observed decision in '+lang+' '+term)
            receipt['cases']['Siletz'][name]=dict(project=key,run=pair['run_id'],handoff=str(folder),decision=decision['state'],field=field);update()
        manifest=read(blind/'survey.json')
        frozen_transfer=sha(blind/'survey.json')
        need(manifest['location']!=read(source)['location'],'Select a different site for the transfer test.')
        need(all(sha(blind/r['name'])==r['sha256'] for r in manifest['files']),'Transfer site inventory changed.')
        rasters=[str(transfer_imagery/n) for n in ('Aerial.tif','acquisition.json')] if transfer_imagery else None
        key=page(None,'home-survey',title=manifest['title']+' · transfer case',folder=str(blind),protocol=False,rasters=rasters)
        page(key,'survey-solve');folder,pair=handoff(key)
        transfer=read(folder/'Complete/Reports/report_data.json')
        decision=transfer['purpose_decision']
        need('max_residual_ft' not in (decision['criteria'] or {}),'Another site inherited an unagreed event tolerance.')
        from ras_workflow.qa import verified_profiles
        profiles=verified_profiles(transfer['summary']['hydraulics'])
        expected=manifest['scenario']['profiles']
        need(set(profiles)=={p['id'] for p in expected} and all(len(values)==len(manifest['geometry']['cross_sections']) for values in profiles.values()),
             'Transfer report does not cover all supplied stations and profiles.')
        receipt['cases']['transfer']=dict(project=key,site=manifest['title'],survey_sha256=frozen_transfer,run=pair['run_id'],folder=str(folder),
                                         decision=decision['state'],profiles=expected,sections=len(manifest['geometry']['cross_sections']))
        update()
        base=fixture.parent;spec=read(fixture)
        originals=[str(checked_file(base,r)) for r in spec['originals']]
        rasters=[str(checked_file(base,spec[k])) for k in ('terrain','terrain_source','aerial','aerial_source')]
        fields={'latitude':35.18064,'longitude':-119.45835,'channel_n':.050,'overbank_n':.065,'local-unit':'m','local-datum':'NAVD88','accept-profile':'Q100','accept-ends':'yes'}
        key=page(None,'home-coordinates',title='Midway · original site folder',fields=fields,rasters=rasters)
        page(key,'portal-request',files=originals)
        need(not app_core.model(key).get('summary'),'A site pin must not silently trigger a solve.')
        receipt['cases']['Midway']=dict(project=key,missing='portal identification, buried inverts',originals=[Path(f).name for f in originals])
        update()
        # Manual interpretation of the georeferenced NAIP crop and road edges.
        # These are approximate screening inputs. The solver fixture's saved picks are never read.
        openings=dict(inlet=[276143,3895837],outlet=[276144,3895847])
        dimensions={'g.structure.groups.0.shape':'box','g.structure.groups.0.count':3,
                    'g.structure.groups.0.span_ft':8,'g.structure.groups.0.rise_ft':6,'g.structure.road.width_ft':25}
        exterior=dict(upstream=[[276126,3895796],[276127,3895808],[276134,3895818],[276140,3895828],[276143,3895835]],
                      downstream=[[276145,3895851],[276150,3895860],[276163,3895871],[276170,3895883]])
        page(key,'prepare-crossing',resume=True,files=originals,dimensions=dimensions,openings=openings,gap=1,exterior=exterior)
        saved=app_core.model(key)['map_picks']
        need(all(saved[side]==points for side,points in exterior.items()),'Reviewed map anchors did not persist.')
        session=ROOT/app_core.model(key)['session']
        proposals=sorted((read(f) for f in (session.parent/'automatic_geometry').glob('*/proposal.json')),key=lambda r:r['created_utc'])
        before,after=proposals[0]['layouts'][0],proposals[-1]['layouts'][0]
        pairs=sum(r['code']=='INTERSECTING_SECTIONS' for r in before['issues'])
        need(pairs>0 and not after['issues'] and after['missing_heights']==0 and proposals[0]['bounds']==proposals[-1]['bounds'],
             'The repair must clear intersecting cuts at the original search width.')
        for line in after['geometry']['flowlines']:
            import math
            for anchor in exterior[line['id']]:
                need(any(math.dist(anchor,xy)<.001 for xy in line['xy']),'A reviewed anchor was bypassed by the calculated centerline.')
        receipt['cases']['Midway']['map_review']=dict(crs='EPSG:26911',anchors=exterior,basis='interpreted open channel on NAIP and DEM after intersecting automatic cuts',
            terrain_sha256=sha(Path(rasters[0])),initial_conflicts=pairs,remaining_conflicts=len(after['issues']),
            limits=proposals[-1]['bounds'],missing_heights=after['missing_heights'])
        update()
        first=solve(key)
        child=page(key,'supplement',files=[str(checked_file(base,spec[k])) for k in ('supplement','brief')])
        revised=solve(child)
        folder,pair=handoff(child)
        need(first['run_id']!=revised['run_id']==pair['run_id'] and revised['road_width_ft']==26,'Supplement failed to produce independent selected run')
        archived=read(folder/'Complete/Evidence/input_paths.json')
        need(any(r['original'].endswith('/terrain_provenance.json') for r in archived['files']) and
             all(sha(folder/'Complete'/r['package_path'])==r['sha256'] for r in archived['files']),
             'Portable input names must map back to the exact original terrain and snapshot bytes.')
        receipt['cases']['Midway'].update(first=first,revised=revised,handoff=str(folder),map_interpretation=dict(
            source=sha(Path(rasters[2])),crs='EPSG:26911',basis='approximate road-edge intersections on archived NAIP, southern inlet assumed',
            assumptions='25 ft initial road width and 1 ft wall spacing for screening; search extent taken from the visible page defaults',**openings))
        receipt['status']='PASSED'
    except Exception as exc:
        receipt.update(status='FAILED',error=str(exc))
        raise
    finally:
        update()
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('packet','fixture','blind'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--transfer-imagery',type=Path)
    args=parser.parse_args()
    folder=ROOT/'status/release_checks'/unique_id()
    print(folder,flush=True)
    run(args.packet.resolve(),args.fixture.resolve(),args.blind.resolve(),folder,args.transfer_imagery)
