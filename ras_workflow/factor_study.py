"""One confirmed factor per native diagnostic run, with the parent and check locations fixed."""
import base64
import csv
import io
from pathlib import Path

import h5py
import numpy as np

from . import app_core as core, factor_geometry
from .common import ROOT, finite, intact, item, read, save, unique_id
from .coverage_study import case_configuration
from .inputs import dependencies
from .qa import BASE, verified_profiles
from .revision_inputs import bound_inputs, station_key
from .section_spacing import confirm_geometry, intervals, refine
from .terrain_auto import Sampler

KIND = 'river_factor_diagnostic'
FACTORS = ('terrain','bed','boundary','spacing')


def upload(doc, dest, suffixes):
    name = doc.get('name') if isinstance(doc,dict) else None
    if not isinstance(name,str) or Path(name).name!=name or Path(name).suffix.lower() not in suffixes:
        raise ValueError('Select a file of the displayed type / 请按提示选择原件')
    data = base64.b64decode(doc.get('content',''),validate=True)
    if not 0<len(data)<=50_000_000:
        raise ValueError('Select a local original of at most 50 MB / 原件须在 50 MB 以内')
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(data)
    return dict(**item(dest,'factor_source'),original_name=name)


def observation_table(model, summary, geometry, selected, doc, folder):
    from .river_observations import current
    profile = selected['id']
    existing = current(model)
    rows = []
    refs = []
    if doc:
        source = upload(doc,folder/'comparison.csv',{'.csv'})
        refs.append(source)
        for row in csv.DictReader(io.StringIO((ROOT/source['path']).read_text('utf-8-sig'))):
            if row.get('profile')!=profile:
                continue
            if (row.get('vertical_datum')!=geometry['vertical_datum'] or not row.get('source_record','').strip()
                    or abs(float(row['flow_cfs'])-selected['flow_cfs'])>1 or not finite(float(row['flow_cfs']))):
                raise ValueError('Check the event discharge, source record and datum / 请核对事件流量、原始记录和高程基准')
            rows.append(dict(rs=station_key(row['rs']),observation_ft=float(row['stage_ft']),source=row['source_record']))
        if not rows:
            raise ValueError('No checks for this profile in the selected file / 文件缺少本工况核验点')
    elif existing and len(summary['hydraulics']['profiles'])==1:
        refs.extend([model['river_observations'],existing['source']])
        for row in existing['rows']:
            if row.get('role') in ('calibration','holdout') and row.get('kind') in ('stage','gage_height') and row.get('residual_ft') is not None and not row['issues']:
                rows.append(dict(rs=station_key(row['location']['rs']),observation_ft=row['observed_ft'],source=row['source']))
    rs = {station_key(r['rs']) for r in geometry['cross_sections']}
    if any(r['rs'] not in rs or r['rs']==station_key(min(map(float,rs))) or not finite(r['observation_ft']) for r in rows):
        raise ValueError('Use finite stages at retained non-outlet locations / 请选用保留断面上的非出口实测水位')
    return rows,refs


def prepare(model,body):
    if model.get('model_type')!='river':
        raise ValueError('Select a solved river reach / 请选择已计算的纯河道')
    factor = body.get('factor')
    basis = str(body.get('basis') or '').strip()
    if factor not in FACTORS or not basis:
        raise ValueError('Select one factor and identify its source or assumption / 请选择一个因素并填写来源或假设')
    summary = read(ROOT/model['summary']['path'])
    cfg,g,sealed = bound_inputs(summary)
    source = ROOT/model['active_project']
    if read(source)!=cfg or read(source.parent/cfg['geometry'])!=g:
        raise ValueError('Parent inputs differ from the native computation / 父版输入与原生计算不一致')
    scenario = next(s for s in cfg['scenarios'] if s['id']==model['scenario'])
    profiles = scenario['profiles']
    profile = next((p for p in profiles if p['id']==body.get('profile')),None)
    if profile is None:
        raise ValueError('Choose a computed profile / 请选择已计算工况')
    folder = core.folder(model['id'])/'factor_diagnostics'/unique_id()
    checks,refs = observation_table(model,summary,g,profile,body.get('checks'),folder)
    queued=None
    if body.get('append_token'):
        pending=model.get('pending_study')
        if not pending or pending['sha256']!=body['append_token'] or not intact([pending]):
            raise ValueError('Reload the queued trials / 请重新读取队列')
        queued=read(ROOT/pending['path'])
        if (queued.get('analysis_kind')!=KIND or queued['evidence'][0]!=model['summary']
                or queued['options']['profile']!=profile['id'] or factor in {c['id'] for c in queued['cases']}):
            raise ValueError('Queue distinct factors for the same parent and event / 同一父版和事件每个因素仅可列入一次')
        if checks and checks!=queued['options']['checks']:
            raise ValueError('Keep the same observed locations in all cases / 同批请沿用相同实测对照点')
        checks=queued['options']['checks']
    doc = body.get('source')
    options = dict(factor=factor,profile=profile['id'],flow_cfs=profile['flow_cfs'],basis=basis,
                   datum=g['vertical_datum'],checks=checks)
    if factor=='terrain':
        alt = upload(doc,folder/'alternative.tif',{'.tif','.tiff'})
        refs.append(alt)
        if body.get('datum')!=g['vertical_datum']:
            raise ValueError('Verify the alternative raster vertical datum / 请核实替代地形的高程基准')
        old = Sampler(summary['terrain'],cfg['terrain']['vertical_unit'],g['vertical_datum'])
        new = Sampler(dict(raster=alt),body.get('unit'),body['datum'])
        refs.append(old.source)
        proposed = factor_geometry.surface(g,old,new)
        options.update(unit=body['unit'],parent_raster=old.source,alternative=alt)
    elif factor=='spacing':
        if doc:
            ref=upload(doc,folder/'refined_sections.json',{'.json'})
            refs.append(ref)
            proposed=factor_geometry.nested(g,read(ROOT/ref['path']))
            options['section_source']=ref
        else:
            sampler=Sampler(summary['terrain'],cfg['terrain']['vertical_unit'],g['vertical_datum'])
            refs.append(sampler.source)
            selected=intervals(g,[],'all')
            refined,_,_=refine(g,selected,sampler)
            proposed=factor_geometry.nested(g,refined)
    else:
        value=body.get('value')
        if not finite(value):
            raise ValueError('Enter the signed value in ft / 请输入有符号英尺数值')
        options['value_ft']=value
        proposed=(factor_geometry.bed(g,value) if factor=='bed' else
                  factor_geometry.outlet(g,value,profiles.index(profile)))
    if proposed==g:
        raise ValueError('Selected change reproduces the parent inputs / 所选工况与父版输入相同')
    # DEM-sample provenance remains bound to the original; the trial records a derived elevation
    # separately so that measured or assumed bed changes are never labeled as direct DEM samples.
    if factor in ('terrain','bed'):
        for base,row in zip(g['cross_sections'],proposed['cross_sections'],strict=True):
            if base['elevation_ft']!=row['elevation_ft']:
                stamp=row.pop('terrain_sampling',None)
                row['derived_elevations']=dict(factor=factor,basis=basis,parent_sampling=stamp,parent_run=summary['hydraulics']['run_id'])
    options.update(original_sections=len(g['cross_sections']),trial_sections=len(proposed['cross_sections']))
    if factor=='spacing':
        # Refinement changes the polygonal overbank paths between retained stations.
        # Report that consequence alongside the invariant main-channel length.
        sums=lambda geom:np.sum([r['reach_lengths_ft'] for r in geom['cross_sections']],axis=0)
        options['length_change_ft']=(sums(proposed)-sums(g)).round(4).tolist()
    dest=folder/'cases'/factor
    plan=dict(id=KIND,analysis_kind=KIND,project_id=model['id'],scenario_id=scenario['id'],case_kind=cfg['case_kind'],
              source_project=item(source),source_geometry=item(source.parent/cfg['geometry']),source_inputs=dependencies(source,cfg),
              evidence=[model['summary'],summary['hydraulics']['raw_hdf'],summary['hydraulics']['raw_controller'],*sealed,*refs],options=options)
    spec=folder/'specification.json'
    save(spec,options)
    plan['specification']=item(spec)
    config=case_configuration(plan,dest,factor)
    config['title']=cfg['title']+' / '+factor
    save(dest/'project.draft.json',config)
    save(dest/'geometry.json',proposed)
    case=dict(id=factor,draft=item(dest/'project.draft.json'),geometry=item(dest/'geometry.json'),section_count=len(proposed['cross_sections']),options=options)
    plan['cases']=[case]
    if queued:
        plan['cases']=[*queued['cases'],case]
        plan['evidence']=list({e['path']:e for e in [*queued['evidence'],queued['specification'],*plan['evidence']]}.values())
    save(folder/'study.json',plan)
    model['pending_study']=item(folder/'study.json')
    core.persist(model,'PREPARE_SINGLE_FACTOR')
    return dict(entry=model['pending_study'],token=model['pending_study']['sha256'],plan=plan)


def native_frame(path, profile, flow):
    with h5py.File(path) as h:
        labels=[s.decode().strip() for s in h[BASE+'/Profile Names'][:]]
        index=labels.index(profile)
        ids=[station_key(s['Station'].decode().strip()) for s in h['Results/Steady/Output/Geometry Info/Cross Section Attributes'][:]]
        z=h[BASE+'/Cross Sections/Water Surface'][index].astype(float)
        q=h[BASE+'/Cross Sections/Flow'][index].astype(float)
        infos=h['Geometry/Cross Sections/Station Elevation Info'][:]
        values=h['Geometry/Cross Sections/Station Elevation Values']
        if (len(set(ids))!=len(ids) or not len(q) or not np.isfinite(q).all() or not np.isfinite(z).all()
                or np.max(np.abs(q-flow))>1 or np.max(np.abs(z))>1e20):
            raise ValueError('Native discharge, location or stage check failed / 原生流量、断面或水位核验失败')
        out={}
        for rs,level,(i,n) in zip(ids,z,infos,strict=True):
            left,right=float(values[i,1]),float(values[i+n-1,1])
            out[rs]=dict(wse_ft=float(level),wet_left=bool(level>left),wet_right=bool(level>right))
        return out


def warnings(summary,profile):
    from . import app_outputs
    entry=summary.get('native_supplement')
    if not entry:
        return None
    bundle=app_outputs.validate(entry)
    original=read(ROOT/bundle['summary']['path'])['hydraulics']
    if original['raw_hdf']!=summary['hydraulics']['raw_hdf']:
        raise ValueError('Native warning export belongs to a different run')
    if bundle['warning_scope'] not in app_outputs.FULL_SCOPES or not bundle.get('warnings'):
        return None
    return sum(r['profile']==profile and r['severity']=='WARNING' for r in bundle['warnings']['records'])


def compare(base,trial,checks,warning_counts):
    if not base.keys()<=trial.keys():
        raise ValueError('The trial lost parent sections / 本次试算缺少父版断面')
    rows=[dict(rs=k,parent=base[k],trial=trial[k],delta_ft=trial[k]['wse_ft']-base[k]['wse_ft']) for k in base]
    observed=[]
    for check in checks:
        k=check['rs']
        observed.append(dict(**check,parent_error_ft=base[k]['wse_ft']-check['observation_ft'],trial_error_ft=trial[k]['wse_ft']-check['observation_ft']))
    worse=[r['rs'] for r in observed if abs(r['trial_error_ft'])>abs(r['parent_error_ft'])+.00001]
    wet=[[rs for rs,r in frame.items() if r['wet_left'] or r['wet_right']] for frame in (base,trial)]
    stop='RETAIN_PARENT_OBSERVATION_WORSENED' if worse else 'FIELD_CHECK_REQUIRED' if not observed or wet[1] else 'REVIEW_TESTED_FACTOR'
    return dict(rows=rows,checks=observed,worsened_at=worse,wet_sections=wet,warning_counts=warning_counts,
                max_change=max(rows,key=lambda r:abs(r['delta_ft'])),stop=stop)


def compare_case(plan,rp,case,record):
    from .study import verified_case
    options=case.get('options',plan['options'])
    result=dict(id=case['id'],status='INCOMPLETE',options=options,baseline=plan['evidence'][0])
    if record.get('status')!='COMPUTED':
        result['errors']=record.get('errors') or [record.get('error') or 'No completed calculation']
        return result
    base=read(ROOT/result['baseline']['path'])
    dest=(ROOT/case['draft']['path']).parent
    cfg=read(dest/'project.json')
    _,trial,_=verified_case(record,dest/'project.json',cfg)
    _,geom,_=bound_inputs(trial)
    if (geom!=confirm_geometry(read(ROOT/case['geometry']['path']),item(rp),basis=read(rp)['basis'])
            or cfg['scenarios']!=read(ROOT/case['draft']['path'])['scenarios']):
        raise ValueError('Native case differs from the confirmed factor trial / 原生计算与已确认单因素试算不一致')
    profile=options['profile']
    frames=[]
    for summary in (base,trial):
        h=summary['hydraulics']
        verified_profiles(h)
        frames.append(native_frame(ROOT/h['raw_hdf']['path'],profile,options['flow_cfs']))
    result.update(compare(*frames,options['checks'],[warnings(s,profile) for s in (base,trial)]))
    result.update(status='DIAGNOSTIC_REVIEW',trial=record['summary'])
    return result


def analyze(sp,plan,rp,journal):
    records={r['id']:r for r in journal['cases']}
    comparisons=[compare_case(plan,rp,c,records.get(c['id'],{})) for c in plan['cases']]
    status='DIAGNOSTIC_REVIEW' if all(c['status']=='DIAGNOSTIC_REVIEW' for c in comparisons) else 'INCOMPLETE'
    return dict(status=status,analysis_kind=KIND,baseline=plan['evidence'][0],
                comparisons=comparisons,review=item(rp),study=item(sp),execution=item(sp.parent/'execution.json'),
                engineering_acceptance='NOT_ASSESSED')
