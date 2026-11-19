"""Compare two independent geometric revisions of one solved single-reach Q100."""
import csv
from collections import Counter

import h5py
import numpy as np

from .common import ROOT, finite, intact, item, read, save, unique_id
from .coverage_study import case_configuration, controls, validate_extension
from .geometry_qa import spatial_issues
from .qa import BASE, verified_profiles
from .revision_inputs import bound_inputs, station_key
from .section_direction import crossing_issues, rotation_controls
from .section_joint import repair
from .terrain_auto import Sampler

KIND = 'river_geometry_comparison'
CASES = ('fixed', 'rotated')


def prepare(model, body):
    from . import app_core as core, app_parameters
    from .banks import annotate
    from .inputs import dependencies
    if model.get('model_type') != 'river':
        raise ValueError('Choose a computed river reach')
    _, maximum = controls(dict(maximum_rounds=1, maximum_width_ft=body.get('maximum_width_ft',1200)))
    summary = read(ROOT/model['summary']['path'])
    config, geometry, sources = bound_inputs(summary)
    source = ROOT/model['active_project']
    if config != read(source) or geometry != read(source.parent/config['geometry']):
        raise ValueError('The editable inputs differ from the native run')
    hyd = summary['hydraulics']
    profiles = verified_profiles(hyd)
    if len(profiles)!=1 or next(iter(profiles)).lower()!='q100':
        raise ValueError('Select a single Q100 calculation for this comparison')
    water = {float(k):v for k,v in next(iter(profiles.values())).items()}
    rows = geometry['cross_sections']
    wet = {r['rs']:water[r['rs']] for r in rows if min(r['elevation_ft'][0],r['elevation_ft'][-1])<=water[r['rs']]}
    sampler = Sampler(summary['terrain'],config['terrain']['vertical_unit'],geometry['vertical_datum'])
    locks = rotation_controls(rows,app_parameters.objects(model)[2]['answers'])
    folder = core.folder(model['id'])/'geometry_comparisons'/unique_id()
    plan = dict(id=KIND, analysis_kind=KIND, case_kind=config['case_kind'], scenario_id=model['scenario'],
        project_id=model['id'], source_project=item(source), source_geometry=item(source.parent/config['geometry']),
        source_inputs=dependencies(source,config), evidence=[model['summary'],hyd['raw_hdf'],hyd['raw_controller'],sampler.source]+sources,
        cases=[], maximum_width_ft=maximum, engineering_acceptance='NOT_ASSESSED')
    save(folder/'specification.json',dict(maximum_width_ft=maximum, alternatives=list(CASES),
        basis='One geometry, Q100, roughness, regime and boundary configuration. Compare left and right endpoint stages and native flow redistribution.'))
    plan['specification']=item(folder/'specification.json')
    for name in CASES:
        result = repair(geometry,sampler,wet,maximum,allow_rotation=name=='rotated',rotation_locks=locks,prior_stages=water)
        g = result['geometry']
        if name=='fixed':
            validate_extension(geometry,g,sampler,maximum)
        else:
            annotate(g)
        bank_edits=[]
        for row in g['cross_sections']:
            if row.get('bank_stations_ft'):continue
            bank = row.get('bank_candidates') or {}
            indices = bank.get('selected_indices')
            if not indices or len(indices)!=2:
                raise ValueError(f"RS {row['rs']}: select bank controls in a revision before batching")
            row['bank_stations_ft'] = [row['station_ft'][j] for j in indices]
            bank_edits.append(dict(rs=row['rs'],banks_ft=row['bank_stations_ft'],confidence=bank.get('confidence'),reasons=bank.get('reasons',[])))
        if spatial_issues(g['cross_sections']) or crossing_issues(g):
            raise ValueError('A candidate has a section crossing conflict')
        dest=folder/'cases'/name
        cfg=case_configuration(plan,dest,name)
        cfg['title']=config['title']+' / '+name
        save(dest/'project.draft.json',cfg)
        save(dest/'geometry.json',g)
        plan['cases'].append(dict(id=name,draft=item(dest/'project.draft.json'),geometry=item(dest/'geometry.json'),
            section_count=len(rows),changes=result['changes'],banks=bank_edits,unresolved=result['unresolved']))
    save(folder/'study.json',plan)
    model['pending_study']=item(folder/'study.json')
    core.persist(model,'PREPARE_RIVER_COMPARISON')
    return dict(entry=model['pending_study'],token=model['pending_study']['sha256'],plan=plan)


def native_sections(summary):
    from .result_atlas import native_rows
    h=summary['hydraulics']
    profiles=verified_profiles(h)
    if len(profiles)!=1 or next(iter(profiles)).lower()!='q100':
        raise ValueError('Q100 native outputs required')
    _,geometry,_=bound_inputs(summary)
    by_rs={station_key(r['rs']):r for r in geometry['cross_sections']}
    controller=read(ROOT/h['raw_controller']['path'])
    cases={station_key(r['station']):r['metrics'].get('Std Stp Case') for r in controller['rows']
           if not r['node_type'] and r['profile'].lower()=='q100'}
    result={}
    with h5py.File(ROOT/h['raw_hdf']['path']) as f:
        block=f[BASE+'/Cross Sections']
        extra=block.get('Additional Variables')
        for i,r in enumerate(native_rows(h)):
            rs=station_key(r['rs']);g=by_rs[rs];stage=r['wse_ft']
            flow=float(block['Flow'][0,i])
            if not finite(flow) or flow<=0 or stage is None:raise ValueError('Invalid Q100 native output')
            shares=[]
            for key in ('Flow Left OB','Flow Right OB'):
                value=float(extra[key][0,i]) if extra is not None and key in extra else None
                shares.append(100*value/flow if finite(value) and abs(value)<1e20 else None)
            ends=[r['elevation_ft'][0],r['elevation_ft'][-1]]
            case=cases.get(rs)
            if isinstance(case,(list,tuple)):case=case[0] if case else None
            result[rs]=dict(stage_ft=stage,flow_cfs=flow,ends_ft=ends,wet=[stage>z for z in ends],
                ob_percent=shares,critical_fallback=(int(case)==3) if finite(case) and abs(case)<1e10 else None,
                cut=g['cutline_xy'],center=g['center_xy'])
    return result


def comparison(frames):
    base=frames['baseline']
    records=[]
    totals={}
    for key,frame in frames.items():
        if frame.keys()!=base.keys():raise ValueError('Station inventory differs')
        totals[key]=Counter()
    for rs,row in base.items():
        for key,frame in frames.items():
            v=frame[rs]
            if v['center']!=row['center'] or v['flow_cfs']!=row['flow_cfs']:
                raise ValueError('Section centers or discharges differ')
            v['delta_wse_ft']=v['stage_ft']-row['stage_ft']
            v['new_wet']=[a and not b for a,b in zip(v['wet'],row['wet'])]
            v['cleared_wet']=[b and not a for a,b in zip(v['wet'],row['wet'])]
            totals[key].update(dict(wet_ends=sum(v['wet']),wet_sections=int(any(v['wet'])),new_wet_ends=sum(v['new_wet']),
                cleared_wet_ends=sum(v['cleared_wet']),critical_fallbacks=int(v['critical_fallback'] is True),
                missing_fallbacks=int(v['critical_fallback'] is None)))
        records.append(dict(rs=rs,variants={name:frame[rs] for name,frame in frames.items()}))
    return records,{k:dict(v) for k,v in totals.items()}


def analyze(sp,plan,rp,journal):
    from .study import verified_case
    base=read(ROOT/plan['evidence'][0]['path'])
    frames={'baseline':native_sections(base)}
    summaries={'baseline':plan['evidence'][0]}
    for case in plan['cases']:
        record=next((r for r in journal['cases'] if r['id']==case['id']),{})
        if record.get('status')!='COMPUTED':
            return dict(analysis_kind=KIND,status='INCOMPLETE',cases=journal['cases'],rows=[],study=item(sp),review=item(rp))
        dest=(ROOT/case['draft']['path']).parent
        _,summary,_=verified_case(record,dest/'project.json',read(dest/'project.json'))
        from .section_spacing import confirm_geometry
        expected=confirm_geometry(read(ROOT/case['geometry']['path']),item(rp),basis=read(rp)['basis'])
        cfg=summary['configuration']
        if read(dest/cfg['geometry'])!=expected or cfg['scenarios']!=[s for s in base['configuration']['scenarios'] if s['id']==plan['scenario_id']]:
            raise ValueError('Computed inputs differ from confirmed alternatives')
        frames[case['id']]=native_sections(summary)
        summaries[case['id']]=record['summary']
    rows,totals=comparison(frames)
    target=sp.parent/'section_comparison.csv'
    with target.open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.writer(file)
        writer.writerow(['RS','variant','Q_cfs','WSE_ft','delta_WSE_ft','end_L_ft','end_R_ft','wet_L','wet_R','new_wet_L','new_wet_R','cleared_L','cleared_R','Q_LOB_percent','Q_ROB_percent','critical_fallback'])
        for r in rows:
            for name,v in r['variants'].items():
                writer.writerow([r['rs'],name,v['flow_cfs'],v['stage_ft'],v['delta_wse_ft'],*v['ends_ft'],*v['wet'],*v['new_wet'],*v['cleared_wet'],*v['ob_percent'],v['critical_fallback']])
    return dict(analysis_kind=KIND,status='COMPARISON_REQUIRES_REVIEW',study=item(sp),review=item(rp),execution=item(sp.parent/'execution.json'),
        summaries=summaries,rows=rows,totals=totals,table=item(target),engineering_acceptance='NOT_ASSESSED')
