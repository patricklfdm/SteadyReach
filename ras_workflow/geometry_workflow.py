"""Connect real terrain candidates to the existing recoverable input wizard.

Automatic proposals never grant geometry approval. All missing engineering
inputs and per-section review decisions remain in the same intake checkpoint.
"""
import copy
import os
import numpy as np
import rasterio
from pyproj import CRS
from .common import ROOT,read,save,item,intact,safe_path,rel,digest,utc,lock,finite
from . import intake
from .banks import annotate
from .geometry_qa import spatial_issues,section_fingerprint
from .sensitivity import VERTICAL_FACTORS


def seed(session_path, project_path, config, terrain_result, folder):
    """Populate only an untouched draft; resume never overwrites operator edits."""
    sp=safe_path(ROOT,session_path);folder=safe_path(ROOT,folder)
    spec_path=safe_path(project_path.parent,config['section_workflow']['spec'])
    spec=read(spec_path);spec_entry=item(spec_path)
    current=read(sp.parent/'draft.json')
    if current.get('section_workflow'):
        prior=current['section_workflow']
        if not intact(prior['sources']):raise ValueError('Terrain workflow sources changed; refresh intake for new geometry')
        return prior
    if current['revision'] or current['answers'] or current['uploads']:
        return dict(status='WAITING_FOR_INPUT',reason='Draft already edited; refresh explicitly before generating sections')
    raster_entry=terrain_result.get('raster')
    if not raster_entry or not intact([raster_entry]):
        return dict(status='WAITING_FOR_INPUT',reason='Valid terrain is required before generating sections')
    t=copy.deepcopy(config['terrain']);meta=spec.get('vertical_review')
    if t.get('mode')=='usgs':
        if not meta or meta.get('unit') not in VERTICAL_FACTORS or not meta.get('datum') or not meta.get('basis') or not intact(meta.get('sources',[])):
            return dict(status='WAITING_FOR_INPUT',reason='USGS vertical_review needs unit, datum, basis and hash-bound metadata sources')
        t.update(mode='local',vertical_unit=meta['unit'],vertical_datum=meta['datum'])
    if t.get('vertical_unit') not in VERTICAL_FACTORS or not t.get('vertical_datum'):
        return dict(status='WAITING_FOR_INPUT',reason='Reviewed DEM units and datum are required')
    folder.mkdir(parents=True,exist_ok=False)
    local=copy.deepcopy(config);local.pop('section_workflow',None)
    t.update(raster=os.path.relpath(ROOT/raster_entry['path'],folder))
    provenance=folder/'terrain_provenance.json';save(provenance,dict(terrain=terrain_result,vertical_review=meta))
    t['provenance']=provenance.name;local['terrain']=t
    for key in ['geometry','authorization']:
        if local.get(key):local[key]=os.path.relpath(safe_path(project_path.parent,local[key]),folder)
    local_path=folder/'sampling_project.json';save(local_path,local)
    sources=[item(project_path),spec_entry,raster_entry,item(provenance)]
    if meta:sources+=meta['sources']
    if spec.get('mode')=='alignment':
        from .alignment import draft
        alignment_path=safe_path(project_path.parent,spec['alignment_spec'])
        working_spec=read(alignment_path);working_spec['allow_incomplete_sections']=True
        save(folder/'alignment_spec.json',working_spec);sources.append(item(alignment_path))
        candidate=draft(local_path,folder/'alignment_spec.json',folder/'alignment')
        sources+=candidate['sources']+[item(folder/'alignment/candidates.json')]
        g=intake.blank_geometry()
        g.update(horizontal_crs=candidate['horizontal_crs'],vertical_datum=candidate['vertical_datum'],
            cross_sections=candidate['cross_sections'],flowlines=candidate['flowlines'])
        # RS is an identifier, not a surveyed distance. A reviewable descending
        # identifier avoids claiming a measured chainage across the structure gap.
        for i,row in enumerate(g['cross_sections']):
            row['rs']=float((len(g['cross_sections'])-i)*100)
            row['rs_basis']='Sequential candidate identifier, not measured chainage; review structure faces separately'
    elif spec.get('mode')=='resample':
        if not config.get('geometry'):raise ValueError('Resampling requires explicit existing geometry')
        gp=safe_path(project_path.parent,config['geometry']);g=read(gp);sources.append(item(gp))
        if not spec.get('basis'):raise ValueError('Resampling basis required')
        with rasterio.open(ROOT/raster_entry['path']) as dem:
            crs=CRS.from_user_input(dem.crs);crs=crs.sub_crs_list[0] if crs.is_compound else crs
            if not crs.equals(CRS.from_user_input(g['horizontal_crs'])) or g['vertical_datum']!=t['vertical_datum']:
                raise ValueError('Explicit matching horizontal CRS and vertical datum required')
            for row in g['cross_sections']:
                cut=np.asarray(row['cutline_xy']);lengths=np.r_[0,np.cumsum(np.linalg.norm(np.diff(cut,axis=0),axis=1))]
                stations=np.asarray(row['station_ft']);pos=(stations-stations[0])/(stations[-1]-stations[0])*lengths[-1]
                points=np.column_stack([np.interp(pos,lengths,cut[:,i]) for i in (0,1)])
                raw=np.ma.vstack(list(dem.sample(points,masked=True)))[:,0].astype(float).filled(np.nan)*VERTICAL_FACTORS[t['vertical_unit']]
                row['elevation_ft']=[float(v) if np.isfinite(v) else None for v in raw]
                row['previous_bank_stations_ft']=row.get('bank_stations_ft')
                row['bank_stations_ft']=None;row.pop('terrain_review',None)
    else:raise ValueError('section_workflow mode must be alignment or resample')
    g.update(schema_version='1.0',approved_for_model=False,status='DRAFT_REQUIRES_REVIEW',provenance=sources)
    for row in g['cross_sections']:
        row['terrain_sampling']=dict(raster=raster_entry,vertical_unit=t['vertical_unit'],vertical_datum=t['vertical_datum'],
            spatial_fingerprint=digest({k:row.get(k) for k in ['cutline_xy','station_ft','elevation_ft','center_xy']}))
    annotate(g,spec.get('bank_screening'))
    save(folder/'geometry.draft.json',g)
    receipt=dict(status='WAITING_FOR_SECTION_REVIEW',sources=sources+[item(folder/'geometry.draft.json')],
        geometry=item(folder/'geometry.draft.json'),terrain=t,terrain_base=rel(folder),
        section_count=len(g['cross_sections']),created_utc=utc())
    with lock(sp.parent/'session.lock'):
        d=read(sp.parent/'draft.json')
        if d['revision']!=current['revision']:raise ValueError('Draft changed during generation; generated candidates retained separately')
        d.update(geometry=g,section_workflow=receipt);d['revision']+=1
        save(sp.parent/'draft.json',d)
    return receipt


def review(session_path, revision, index, bank_indices, reviewer, basis, action='ACCEPT', fingerprint=None, *, direct_start=False):
    sp=safe_path(ROOT,session_path)
    if not direct_start and (not isinstance(reviewer,str) or not reviewer.strip() or not isinstance(basis,str) or not basis.strip()):
        raise ValueError('A named reviewer and section-specific basis are required')
    if action not in ['ACCEPT','EXCLUDE']:raise ValueError('Unsupported section review action')
    with lock(sp.parent/'session.lock'):
        sp,s,p,d=intake._load(sp)
        if d['revision']!=revision:raise ValueError('Stale draft revision')
        c,g=intake._objects(p,d);rows=g['cross_sections']
        if type(index)!=int or not 0<=index<len(rows):raise ValueError('Unknown section')
        row=rows[index]
        if fingerprint!=section_fingerprint(row):raise ValueError('Section changed; reload and review its current profile')
        if action=='EXCLUDE':
            if any(row.get('rs')==g.get('structure',{}).get(k) for k in ['us_xs_rs','ds_xs_rs'] if g.get('structure',{}).get(k) is not None):
                raise ValueError('Cannot exclude a configured structure face; revise the geometry explicitly')
            d.setdefault('excluded_sections',[]).append(dict(section=row,reviewer=reviewer,basis=basis,created_utc=utc()))
            rows.pop(index)
            # Removing a section changes neighbouring reach lengths; never bridge
            # the gap with an unreviewed inferred length.
            if index>0:rows[index-1]['reach_lengths_ft']=None;rows[index-1].pop('terrain_review',None)
            for r in rows:r.pop('terrain_review',None)
        else:
            a=row.get('station_ft') or [];z=row.get('elevation_ft') or []
            if not isinstance(bank_indices,list) or len(bank_indices)!=2 or not all(type(i)==int for i in bank_indices) or not 0<bank_indices[0]<bank_indices[1]<len(a)-1:
                raise ValueError('Choose ordered interior left/right sampled bank points')
            if len(a)!=len(z) or not all(finite(v) for v in a+z):
                raise ValueError('NoData sections cannot be accepted; change extent or exclude')
            issues=[q for q in spatial_issues(rows) if index in q['sections']]
            if issues:raise ValueError('Resolve section spatial blockers before accepting: '+str(issues))
            row['bank_stations_ft']=[a[i] for i in bank_indices]
            row['terrain_review']=dict(decision='ACCEPT',reviewer=reviewer,basis=basis,
                fingerprint=section_fingerprint(row),created_utc=utc(),identity='LOCAL_SELECTION_NO_ENGINEERING_REVIEW' if direct_start else 'OPERATOR_ATTESTED',
                policy='local_computation_v1' if direct_start else 'named_review')
        d['geometry']=g
        # Preserve input evidence/confirmation and remap its index on exclusion.
        answers={}
        for key,value in d['answers'].items():
            if key.startswith('g.cross_sections.'):
                parts=key.split('.');old=int(parts[2])
                if old==index and (action=='EXCLUDE' or parts[3]=='bank_stations_ft'):continue
                if action=='EXCLUDE' and old>index:parts[2]=str(old-1);key='.'.join(parts)
            answers[key]=value
        d['answers']=answers
        d['consent']=False;d['revision']+=1
        save(sp.parent/'events'/('geometry_'+str(d['revision'])+'.json'),dict(action=action,section=index,reviewer=reviewer,basis=basis,geometry=g))
        save(sp.parent/'draft.json',d)
    return intake.view(sp)
