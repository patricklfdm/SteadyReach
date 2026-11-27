"""Register the source roles, run the full blind cohort, then score sealed forecasts."""
import argparse
from collections import Counter
from pathlib import Path
import sys
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from examples.enterprise_pilot.big_river_blind import DATA, REPORT, freeze, published_stage
from ras_workflow import app_outputs
from ras_workflow.cli import execute
from ras_workflow.common import intact, item, read, rel, save, sha, utc
from ras_workflow.factor_study import native_frame
from ras_workflow.inputs import gate
from ras_workflow.revision_inputs import station_key


def registered(raw,out):
    ref=read(out/'registration.json')['protocol']
    if not intact([ref]) or ref!=item(out/'protocol.json'):
        raise ValueError('Protocol changed; keep this registration for audit')
    protocol=read(out/'protocol.json')
    for s in protocol['sources']:
        if sha(raw/s['file'])!=s['sha256']:raise ValueError('USGS study source changed')
    return ref,protocol


def forecasts(raw,out):
    ref,protocol=registered(raw,out)
    entry=out/'forecasts.json'
    if entry.exists():raise ValueError('Forecasts already sealed; score the registered cohort')
    results={}
    for site,site_data in protocol['sites'].items():
        if not intact([site_data['raster'],*site_data['levels'].values()]):raise ValueError('Frozen surveyed geometry changed')
        profiles=[]
        stages=[]
        for event,v in site_data['events'].items():
            if not v['records']:continue
            outlet=v['records'][0]
            if outlet['role']!='outlet':raise ValueError('Expected surveyed outlet')
            stages.append(published_stage(raw/v['file'],outlet))
            profiles.append(dict(id='E'+event,flow_cfs=v['flow_cfs'],source=REPORT+' · Table 4 · '+site+' · '+event))
        results[site]={}
        for label,geometry_ref in site_data['levels'].items():
            case=out/site/label
            case.mkdir(exist_ok=True)
            config_path=case/'project.json'
            g=read(ROOT/geometry_ref['path'])
            g['boundaries']=dict(downstream=dict(type='known_stage',stages_ft=stages))
            lon,lat=site_data['location']
            project='p20_'+site.lower()+'_'+label
            config=dict(schema_version='1.0',case_kind='site_conditional',model_type='river',project_id=project,
                        title='Big River '+site+' blind stage validation · '+label,
                        geometry='geometry.json',geometry_review=g['provenance'],authorization='authorization.json',
                        location=dict(latitude=lat,longitude=lon,crossing_confirmed=True,source=DATA),
                        delivery=dict(enabled=False,mapping_enabled=False),solver_logging='diagnostic',
                        terrain=dict(mode='local',raster='../'+Path(site_data['raster']['path']).name,provenance='survey_sources.json',
                                     vertical_unit='m',vertical_datum='NAVD88'),
                        scenarios=[dict(id='events',profiles=profiles,channel_n=protocol['roughness']['channel'],
                                        overbank_n=protocol['roughness']['overbanks'],parameter_source='Fixed, uncalibrated screening roughness in the registered protocol.')])
            source=dict(protocol=ref,survey=site_data['raster'],publisher=DATA,discharge=REPORT,field_dates=list(site_data['events']))
            if config_path.exists():
                if read(config_path)!=config or read(case/'geometry.json')!=g or read(case/'survey_sources.json')!=source:
                    raise ValueError('Frozen case inputs changed')
            else:
                save(case/'survey_sources.json',source)
                save(case/'geometry.json',g)
                save(case/'authorization.json',dict(project_id=project,allowed_geometry_sha256=sha(case/'geometry.json'),
                     scope='site_conditional',basis='Independent screening under the registered P20 study protocol.'))
                save(config_path,config)
            validation,_=gate(config_path,config,config['scenarios'][0])
            if validation['blocking_items']:raise ValueError(validation['blocking_items'])
            case_receipt=case/'forecast.json'
            if case_receipt.exists():
                receipt=read(case_receipt)
                if receipt['protocol']!=ref or not intact(receipt['files']):raise ValueError('Stored forecast changed')
            else:
                code=execute(str(config_path),'events',fresh=True)
                state=read(case/'state.json')
                if code:raise ValueError(state.get('errors') or state)
                summary_ref=state['latest_summary']
                summary=read(ROOT/summary_ref['path'])
                hyd=summary['hydraulics']
                if summary['configuration']!=config:raise ValueError('Run used different inputs')
                bundle=app_outputs.validate(summary['native_supplement'])
                if bundle['warning_scope'] not in app_outputs.FULL_SCOPES:raise ValueError('Native warning coverage is incomplete')
                rows=bundle['warnings']['records'] if bundle.get('warnings') else []
                by_event={}
                for profile,stage in zip(profiles,stages,strict=True):
                    frame=native_frame(ROOT/hyd['raw_hdf']['path'],profile['id'],profile['flow_cfs'])
                    last=station_key(g['cross_sections'][-1]['rs'])
                    if abs(stage-frame[last]['wse_ft'])>protocol['criteria']['outlet_ft']:raise ValueError('Outlet readback failed')
                    logs=[dict(code=r.get('code'),text=r.get('message') or r.get('text'),station=r.get('station')) for r in rows
                          if r.get('profile')==profile['id'] and r.get('severity')=='WARNING']
                    by_event[profile['id'][1:]]=dict(sections=frame,outlet_error_ft=frame[last]['wse_ft']-stage,
                                                     known_outlet_ft=stage,flow_cfs=profile['flow_cfs'],warnings=logs)
                receipt=dict(protocol=ref,run=hyd['run_id'],events=by_event,
                             files=[summary_ref,hyd['raw_hdf'],summary['native_supplement'],item(case/'geometry.json'),
                                    item(config_path),item(case/'authorization.json'),item(case/'survey_sources.json')])
                save(case_receipt,receipt)
            results[site][label]=item(case_receipt)
            print('Forecast retained:',site,label,receipt['run'],flush=True)
    # No interior stage column has been used in assembling any prediction.
    save(entry,dict(protocol=ref,sites=results,frozen_utc=utc()))
    save(out/'prediction_seal.json',dict(forecasts=item(entry),sealed_utc=utc()))


def score(raw,out):
    ref,protocol=registered(raw,out)
    sealed=read(out/'prediction_seal.json')['forecasts']
    if sealed!=item(out/'forecasts.json') or not intact([sealed]):raise ValueError('Forecast seal changed')
    predictions=read(out/'forecasts.json')
    if predictions['protocol']!=ref:raise ValueError('Forecast refers to a different protocol')
    if predictions['sites'].keys()!=protocol['sites'].keys():raise ValueError('Forecasts must cover every registered reach')
    frames={}
    for site,levels in predictions['sites'].items():
        enrolled=protocol['sites'][site]
        if levels.keys()!=enrolled['levels'].keys() or not intact([enrolled['raster'],*enrolled['levels'].values()]):
            raise ValueError('Both registered geometries are required')
        if not intact(levels.values()):raise ValueError('Forecast file changed')
        frames[site]={label:read(ROOT/r['path']) for label,r in levels.items()}
        for r in frames[site].values():
            if not intact(r['files']) or r['protocol']!=ref:raise ValueError('Restore the original native forecast')
            summary=read(ROOT/r['files'][0]['path'])
            if r['run']!=summary['hydraulics']['run_id'] or r['files'][1]!=summary['hydraulics']['raw_hdf']:
                raise ValueError('Forecast refers to a different native run')
            expected={e for e,obs in enrolled['events'].items() if obs['records']}
            if r['events'].keys()!=expected:raise ValueError('Missing event in the sealed native predictions')
            for event,record in r['events'].items():
                source=ROOT/r['files'][1]['path']
                if native_frame(source,'E'+event,enrolled['events'][event]['flow_cfs'])!=record['sections']:
                    raise ValueError('Sealed forecast differs from native stage, flow or wet endpoints')
    results=[]
    for site,info in protocol['sites'].items():
        for event,obs in info['events'].items():
            result=dict(site=site,event=event,flow_cfs=obs['flow_cfs'],source=obs['file'],observation_accuracy_ft=None,observations=[])
            result['discharge_source']='nearby gage estimate (P)' if site=='PHB' and event=='20191106' else 'concurrent discharge and profile (DP)'
            results.append(result)
            if not obs['records']:
                result.update(status='INSUFFICIENT_OUTLET',within_numerical_limits=False)
                continue
            coarse,fine=[frames[site][l]['events'][event] for l in ('coarse','fine')]
            checks=[]
            for point in obs['records'][1:]:
                level=published_stage(raw/obs['file'],point)
                rs=station_key(point['rs'])
                checks.append(dict(**point,observed_ft=level,forecast_ft=coarse['sections'][rs]['wse_ft'],
                                   residual_ft=coarse['sections'][rs]['wse_ft']-level,
                                   fine_residual_ft=fine['sections'][rs]['wse_ft']-level))
            diffs={rs:fine['sections'][rs]['wse_ft']-v['wse_ft'] for rs,v in coarse['sections'].items()}
            worst=max(diffs,key=lambda rs:abs(diffs[rs]))
            wet=[[rs for rs,v in version['sections'].items() if v['wet_left'] or v['wet_right']] for version in (coarse,fine)]
            bias=sum(v['residual_ft'] for v in checks)/len(checks) if checks else None
            largest=max(checks,key=lambda v:abs(v['residual_ft']),default=None)
            maximum=abs(largest['residual_ft']) if largest else None
            limits=protocol['criteria']
            tests=dict(locations=len(checks)>=limits['independent_locations'],all_points=maximum is not None and maximum<=limits['point_ft'],
                       mean=bias is not None and abs(bias)<=limits['mean_ft'],spacing=abs(diffs[worst])<=limits['refinement_ft'],
                       dry_ends=not any(wet),outlet=max(abs(v['outlet_error_ft']) for v in (coarse,fine))<=limits['outlet_ft'])
            codes=[dict(Counter(r['code'] for r in frame['warnings'])) for frame in (coarse,fine)]
            controls=sorted({code for counts in codes for code in counts
                             if any(part in str(code) for part in ('CRITICAL','BALANCE','MINIMUM_ERROR','HYDRAULIC_JUMP'))})
            result.update(observations=checks,count=len(checks),mean_signed_ft=bias,max_abs_ft=maximum,worst_rs=largest['rs'] if largest else None,
                          wet=wet,spacing_max_signed_ft=diffs[worst],spacing_rs=worst,outlet_error_ft=[v['outlet_error_ft'] for v in (coarse,fine)],
                          native_warnings=[len(v['warnings']) for v in (coarse,fine)],warning_categories=codes,unresolved_native_controls=controls,
                          checks=tests,within_numerical_limits=all(tests.values()),engineering_acceptance='NOT_ASSESSED',
                          status='NUMERICAL_SCREEN_PASSED' if all(tests.values()) else 'INVESTIGATE',
                          scope='Registered subreach and event; formal field uncertainty unreported. Review native warning mechanisms separately.')
    dest=out/'scores.json'
    passed=[v for v in results if v['within_numerical_limits'] and not v['unresolved_native_controls']]
    cohort_ok=len(passed)>=3 and len({v['site'] for v in passed})>=2
    panel=dict(status='CONDITIONAL_NUMERICAL_BENCHMARK_PASSED' if cohort_ok else 'BENCHMARK_OPEN',
               registered_events=len(results),passing_events=len(passed),passing_reaches=sorted({v['site'] for v in passed}),
               incomplete_events=[v['site']+' '+v['event'] for v in results if v not in passed],
               accepted_use='Screening at the registered reaches, event discharges and interior locations only.',
               engineering_acceptance='NOT_ASSESSED',observation_vertical_accuracy='NOT_QUANTIFIED_BY_PUBLISHER')
    result=dict(protocol=ref,predictions=sealed,cohort=panel,events=results)
    if dest.exists():
        original=read(dest)
        if {k:v for k,v in original.items() if k!='scored_utc'}!=result:
            raise ValueError('A previous score differs. Retain it and issue a separate investigation.')
    else:
        save(dest,dict(result,scored_utc=utc()))
    print(dest,flush=True)


def archive(raw,out):
    from ras_workflow import site_delivery
    from ras_workflow.delivery_pair import check
    from ras_workflow.common import lock
    ref,protocol=registered(raw,out)
    scored=read(out/'scores.json')
    if scored['protocol']!=ref or not intact([scored['predictions']]):
        raise ValueError('Restore the verified comparison before archiving')
    name=out/'P20_blind_validation.zip'
    with lock(out/'pack.lock'):
        if name.exists():
            last=read(out/'release.json')
            if intact([last['archive'],last['scores']]) and last['archive']==item(name):
                print(out/'release.json',flush=True)
                return
            raise ValueError('A previously verified archive has changed; preserve the original receipt.')
        pairs={}
        for site in protocol['sites']:
            native=read(out/site/'coarse/forecast.json')['files'][0]
            target=out/site/'Delivery'
            receipt=read(target/'delivery.json') if (target/'delivery.json').exists() else site_delivery.generate(ROOT/native['path'],target)
            if receipt['summary']!=native or receipt['status']!='READY_NATIVE_ONLY':
                raise ValueError('Expected a verified native delivery of this forecast')
            for scale in ('Complete','Minimal'):site_delivery.verify(target/scale)
            pairs[site]=check(target/'Complete',target/'Minimal')
        sources=[out/n for n in ('registration.json','protocol.json','prediction_seal.json','forecasts.json','scores.json')]
        for site,site_info in protocol['sites'].items():
            sources.extend(ROOT/r['path'] for r in (site_info['raster'],*site_info['levels'].values()))
            sources.extend(p for p in (out/site/'Delivery').rglob('*') if p.is_file())
            for level in ('coarse','fine'):
                case=out/site/level
                results=read(case/'forecast.json')
                sources.extend([case/'forecast.json',*(ROOT/r['path'] for r in results['files'])])
                hdf=ROOT/results['files'][1]['path']
                sources.extend(p for p in hdf.parent.iterdir() if p.is_file() and p.suffix.lower() in ('.prj','.g01','.f01','.p01','.hdf','.o01'))
        temp=name.with_suffix('.zip.partial')
        originals={raw/r['file']:'USGS_originals/'+r['file'] for r in protocol['sources']}
        members={file:file.relative_to(out).as_posix() for file in set(sources)}
        members.update(originals)
        with ZipFile(temp,'w',ZIP_DEFLATED,compresslevel=4) as z:
            for file,member in sorted(members.items()):
                z.write(file,member)
            z.writestr('START_HERE.txt',('Big River, Missouri | Independent event comparisons / 独立事件核验\n'
                'Read scores.json for all five events and their limitations. Open STW or PHB, then Delivery → Complete → Reports for the native-run reports. '
                'Minimal → HEC_RAS contains the portable hydraulic project. Both packages use native-only delivery. '
                'USGS_originals contains the registered sources. Reported survey precision is unavailable. No engineering signoff.\n'
                'scores.json 列出五场的偏差和适用条件。STW 和 PHB 下的 Delivery/Complete/Reports 为原生计算报告，'
                'Delivery/Minimal/HEC_RAS 可打开模型。两组均为原生工程交付，未含 GIS 展示。USGS_originals 保留原件。'
                '观测精度未量化，工程签审待办。\n').encode('utf-8-sig'))
        with ZipFile(temp) as z:
            if z.testzip() is not None:raise ValueError('Delivery archive checksum failure')
            import hashlib
            for file,member in members.items():
                if hashlib.sha256(z.read(member)).hexdigest()!=sha(file):
                    raise ValueError('Archived bytes differ from original '+file.name)
        temp.replace(name)
        save(out/'release.json',dict(cohort=scored['cohort'],archive=item(name),scores=item(out/'scores.json'),pairs=pairs,
                                    human='DEFERRED',cross_machine='DEFERRED'))
    print(out/'release.json',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('freeze','forecast','score','archive'))
    p.add_argument('--raw',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if not args.out.resolve().is_relative_to(ROOT):raise ValueError('Keep study runs within the isolated checkout')
    {'freeze':freeze,'forecast':forecasts,'score':score,'archive':archive}[args.action](args.raw.resolve(),args.out.resolve())
