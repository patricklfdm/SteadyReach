"""Explicit wizard generation and preview/apply resampling; never solver calls."""
import copy
import math
import os
import re
import numpy as np
import rasterio
from pyproj import CRS
from .common import ROOT,digest,finite,intact,item,lock,read,rel,safe_path,save,unique_id,utc
from .geometry_qa import spatial_issues,section_fingerprint
from .banks import annotate,propose
from .sensitivity import VERTICAL_FACTORS


def context(session_path):
    from . import intake
    sp,s,p,d=intake._load(session_path);c,g=intake._objects(p,d);project=ROOT/p['project'];t=copy.deepcopy(c.get('terrain',{}))
    terrain=None
    if t.get('mode')=='local' and t.get('raster'):
        raster=safe_path(project.parent,t['raster'])
        if raster.is_file():terrain=dict(status='READY_WITH_LIMITATIONS',raster=item(raster),vertical_unit=t.get('vertical_unit'),vertical_datum=t.get('vertical_datum'))
    if terrain is None:
        cp=sp.parent/'terrain_checkpoint.json'
        if cp.exists():terrain=read(cp)['terrain']
        else:
            state=project.parent/'state.json'
            state=read(state) if state.exists() else {}
            entry=state.get('latest_summary')
            if entry and intact([entry]):terrain=read(ROOT/entry['path']).get('terrain')
    if not terrain or not terrain.get('raster') or not intact([terrain['raster']]):raise ValueError('Acquire a valid DEM first with workflow.py run; terrain is missing or changed')
    with rasterio.open(ROOT/terrain['raster']['path']) as dem:
        crs=CRS.from_user_input(dem.crs);crs=crs.sub_crs_list[0] if crs.is_compound else crs
        if not crs.is_projected:raise ValueError('A projected DEM is required')
        info=dict(crs=crs.to_string(),bounds=list(dem.bounds),resolution=list(dem.res),horizontal_unit=crs.axis_info[0].unit_name)
    return sp,s,p,d,c,g,t,terrain,info


def setup_view(session_path):
    try:
        sp,s,p,d,c,g,t,terrain,info=context(session_path)
        checkpoint=sp.parent/'terrain_checkpoint.json';metadata=read(checkpoint).get('metadata',{}) if checkpoint.exists() else {}
        from .terrain_metadata import review_candidate
        candidate=review_candidate(metadata['products']) if metadata.get('products') else dict(status='MANUAL_METADATA_REVIEW_REQUIRED',review_items=[metadata.get('error','No automatic product metadata candidate available')])
        return dict(status='READY',**info,vertical_unit=t.get('vertical_unit') or terrain.get('vertical_unit'),
            vertical_datum=t.get('vertical_datum') or terrain.get('vertical_datum'),raster=terrain['raster'],
            metadata_candidate=candidate,
            can_resample=bool(g['cross_sections']),coordinate_note='Ordered upstream to downstream; horizontal CRS units',
            defaults=dict(grid_ft=5.,corridor_half_width_ft=40.,height_scale_ft=10.,elevation_weight=1.,uphill_weight=4.,
                section_width_ft=200.,section_spacing_ft=40.,sampling_ft=1.,section_direction='local_tangent'))
    except (ValueError,OSError,KeyError,TypeError) as e:return dict(status='WAITING_FOR_TERRAIN',reason=str(e))


def require_reviewer(payload):
    if any(not isinstance(payload.get(k),str) or not payload[k].strip() for k in ['reviewer','basis']):
        raise ValueError('Reviewer and a specific geometry/metadata basis are required')


def map_view(session_path,bounds=None):
    """An actual DEM thumbnail in its native projected CRS, for draft picks only."""
    import base64,io
    from PIL import Image
    from pyproj import Transformer
    from rasterio.windows import from_bounds
    sp,s,p,d,c,g,t,terrain,info=context(session_path)
    crs=CRS.from_user_input(info['crs']);extent=np.array(info['bounds']);unit=crs.axis_info[0].unit_conversion_factor
    if bounds is None:
        loc=c.get('location') or {}
        center=np.array(Transformer.from_crs(4326,crs,always_xy=True).transform(loc['longitude'],loc['latitude'])) if loc.get('latitude') is not None and loc.get('longitude') is not None else (extent[:2]+extent[2:])/2
        if not ((center>=extent[:2]).all() and (center<=extent[2:]).all()):center=(extent[:2]+extent[2:])/2
        span=min(max(extent[2:]-extent[:2]),1000/unit)
        bounds=[*(center-span/2),*(center+span/2)]
    b=np.asarray(bounds,dtype=float)
    if b.shape!=(4,) or not np.isfinite(b).all() or min(b[2:]-b[:2])<=0:raise ValueError('Invalid map extent')
    if max(b[2:]-b[:2])>4*max(extent[2:]-extent[:2]) or not ((b[:2]<extent[2:]).all() and (b[2:]>extent[:2]).all()):raise ValueError('Map extent outside terrain')
    if min(b[2:]-b[:2])<8*max(info['resolution']):raise ValueError('Map extent smaller than eight DEM cells')
    # Square map with a single coordinate scale.
    center=(b[:2]+b[2:])/2;span=max(b[2:]-b[:2]);b=np.r_[center-span/2,center+span/2]
    with rasterio.open(ROOT/terrain['raster']['path']) as dem:
        a=dem.read(1,window=from_bounds(*b,dem.transform),out_shape=(650,650),masked=True,boundless=True).astype(float)
    valid=a.compressed();low,high=np.percentile(valid,[2,98]) if len(valid) else (0,1)
    gray=np.clip((a.filled(low)-low)/max(high-low,1e-9)*200+30,0,255).astype('uint8')
    rgba=np.stack([gray,gray,gray,np.where(np.ma.getmaskarray(a),0,255).astype('uint8')],axis=2)
    buf=io.BytesIO();Image.fromarray(rgba).save(buf,format='PNG')
    sections=[];section_items=[]
    if g.get('horizontal_crs'):
        transform=Transformer.from_crs(g['horizontal_crs'],crs,always_xy=True)
        for index,row in enumerate(g['cross_sections']):
            cut=row.get('cutline_xy')
            if cut:
                xy=np.column_stack(transform.transform(*np.asarray(cut,float).T))
                if np.isfinite(xy).all():
                    sections.append(xy.tolist());section_items.append(dict(index=index,rs=row.get('rs'),cutline_xy=xy.tolist()))
    return dict(bounds=b.tolist(),crs=info['crs'],unit_to_m=unit,background=base64.b64encode(buf.getvalue()).decode(),raster=terrain['raster'],
        sections=sections,section_items=section_items,terrain_bounds=extent.tolist(),resolution=info['resolution'],min_span=8*max(info['resolution']),max_span=4*max(extent[2:]-extent[:2]),spatial_issues=spatial_issues(g['cross_sections']),note='DEM surface only; picks are unreviewed anchors, not surveyed structure positions')


def configure(session_path,revision,payload):
    """Generate a separate snapshot without rewriting project JSON or evidence."""
    from . import intake
    from .geometry_workflow import seed
    if payload.get('policy')!='local_computation_v1':require_reviewer(payload)
    sp,s,p,d,c,g,t,terrain,info=context(session_path)
    if revision!=d['revision']:raise ValueError('Stale draft; reload before generating')
    if g['cross_sections'] and payload.get('replace_existing') is not True:raise ValueError('Explicitly confirm replacing draft sections; the old draft remains in history')
    mode=payload.get('mode')
    if mode not in ['alignment','resample']:raise ValueError('Choose alignment or resample')
    meta=payload.get('vertical_review',{})
    if meta.get('unit') not in VERTICAL_FACTORS or not meta.get('datum') or not meta.get('basis'):
        raise ValueError('Confirm DEM vertical unit, datum and metadata basis')
    paths=meta.get('source_paths',[])
    if not isinstance(paths,list) or not paths:raise ValueError('At least one workspace metadata/source path is required')
    evidence=[item(safe_path(ROOT,v),'reviewed_terrain_metadata') for v in paths]
    folder=sp.parent/'geometry_generations'/unique_id();folder.mkdir(parents=True)
    save(folder/'request.json',dict(revision=revision,payload=payload,created_utc=utc(),previous_geometry=g))
    local=copy.deepcopy(c);local['terrain']=dict(mode='usgs',create_native=t.get('create_native',False))
    local.pop('authorization',None);local.pop('configuration_approval',None)
    local.pop('geometry',None)
    for key in ['native_project','reference_results','benchmark_preparation']:
        if local.get(key):raise ValueError('Imported native projects do not support wizard terrain replacement')
    spec=dict(mode=mode,basis=payload['basis'],vertical_review=dict(unit=meta['unit'],datum=meta['datum'],basis=meta['basis'],sources=evidence))
    if mode=='alignment':
        alignment=dict(payload.get('parameters',{}),crs=info['crs'],purpose=payload['basis'],anchor_basis=payload['basis'],
            upstream_to_downstream_basis=payload.get('direction_basis'),anchor_sources=evidence,
            external_reaches=payload.get('external_reaches',[]))
        save(folder/'alignment.json',alignment);spec['alignment_spec']='alignment.json'
    else:
        if not g['cross_sections']:raise ValueError('Resample requires existing draft sections')
        save(folder/'geometry.json',g);local['geometry']='geometry.json'
    save(folder/'spec.json',spec);local['section_workflow']=dict(spec='spec.json');save(folder/'project.json',local)
    work=folder/'work';work.mkdir();save(work/'draft.json',dict(revision=0,answers={},uploads=[]))
    receipt=seed(work/'session.json',folder/'project.json',local,terrain,folder/'generated')
    if not receipt.get('geometry'):raise ValueError(receipt.get('reason','Generation did not produce geometry'))
    generated=read(ROOT/receipt['geometry']['path']);receipt['sources']+=[item(folder/'request.json')]
    if mode=='alignment':
        # Keep separately reviewed structure context, but its face identifiers
        # cannot be carried to new sequential RS numbers without a new decision.
        generated['structure']=copy.deepcopy(g['structure'])
        if g.get('model_type')!='river':
            for key in ['rs','us_xs_rs','ds_xs_rs']:generated['structure'][key]=None
            generated['structure']['road']['station_ft']=None
            if generated['structure']['road'].get('profile_mode')=='distinct':generated['structure']['road']['downstream_station_ft']=None
            for group in generated['structure']['groups']:group['centers_ft']=None
        for key in ['river','reach','boundary_slopes','boundaries','flow_regime','channel_geometry_basis']:
            if g.get(key):generated[key]=copy.deepcopy(g[key])
    with lock(sp.parent/'session.lock'):
        _,_,_,current=intake._load(sp)
        if current['revision']!=revision:raise ValueError('Draft changed during generation; candidate files retained separately')
        save(sp.parent/'events'/('before_generation_'+unique_id()+'.json'),current)
        current.update(geometry=generated,section_workflow=receipt,consent=False,revision=revision+1,section_review_drafts={})
        current['answers']={k:v for k,v in current['answers'].items() if not k.startswith(('g.cross_sections.','c.terrain.')) and k not in ['g.horizontal_crs','g.vertical_datum'] and not (mode=='alignment' and (k in ['g.structure.rs','g.structure.us_xs_rs','g.structure.ds_xs_rs','g.structure.road.station_ft','g.structure.road.downstream_station_ft'] or k.startswith('g.structure.groups.') and k.endswith('.centers_ft')))}
        save(sp.parent/'draft.json',current);save(sp.parent/'geometry_checkpoint.json',receipt)
    return intake.view(sp)


def transform_section(row,crs,parameters):
    crs=CRS.from_user_input(crs)
    if not crs.is_projected:raise ValueError('Projected geometry CRS required')
    factor=crs.axis_info[0].unit_conversion_factor/.3048
    cut=np.asarray(row['cutline_xy'],dtype=float);center=np.asarray(row['center_xy'],dtype=float)
    old_length=float(np.linalg.norm(np.diff(cut,axis=0),axis=1).sum()*factor)
    if not np.isfinite(cut).all() or not np.isfinite(center).all() or old_length<=0:raise ValueError('Valid nonzero cutline and center required')
    p=dict(rotation_deg=0.,shift_east_ft=0.,shift_north_ft=0.,width_ft=old_length,sampling_ft=max(1.,old_length/498.))
    if not isinstance(parameters,dict) or set(parameters)-set(p):raise ValueError('Unknown geometry adjustment')
    p.update(parameters)
    if not all(finite(v) for v in p.values()) or not -60<=p['rotation_deg']<=60 or p['width_ft']<=0 or p['sampling_ft']<=0 or math.ceil(p['width_ft']/p['sampling_ft'])>499:
        raise ValueError('Use rotation within ±60 degrees and positive width/sampling with at most 500 points')
    if max(abs(p['shift_east_ft']),abs(p['shift_north_ft']))>2000 or p['width_ft']>5000:raise ValueError('Adjustment exceeds local preview extent')
    angle=math.radians(p['rotation_deg']);rotation=np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
    shift=np.array([p['shift_east_ft'],p['shift_north_ft']])/factor
    after=(cut-center)@rotation.T*(p['width_ft']/old_length)+center+shift
    return after,center+shift,p


def preview(session_path,revision,index,fingerprint,parameters):
    sp,s,p,d,c,g,t,terrain,info=context(session_path)
    if d['revision']!=revision:raise ValueError('Stale draft revision')
    if type(index)!=int or not 0<=index<len(g['cross_sections']):raise ValueError('Unknown section')
    row=g['cross_sections'][index]
    if section_fingerprint(row)!=fingerprint:raise ValueError('Section changed; reload')
    if t.get('vertical_unit') not in VERTICAL_FACTORS or not t.get('vertical_datum') or t['vertical_datum']!=g['vertical_datum']:
        raise ValueError('Review matching DEM units and datum before resampling')
    if not CRS.from_user_input(g['horizontal_crs']).equals(CRS.from_user_input(info['crs'])):raise ValueError('Explicit matching geometry and DEM CRS required')
    cut,center,params=transform_section(row,g['horizontal_crs'],parameters)
    lengths=np.r_[0,np.cumsum(np.linalg.norm(np.diff(cut,axis=0),axis=1))]
    station=np.linspace(0,params['width_ft'],math.ceil(params['width_ft']/params['sampling_ft'])+1)
    distance=station/params['width_ft']*lengths[-1];points=np.column_stack([np.interp(distance,lengths,cut[:,i]) for i in (0,1)])
    with rasterio.open(ROOT/terrain['raster']['path']) as dem:
        z=np.ma.vstack(list(dem.sample(points,masked=True)))[:,0].astype(float).filled(np.nan)*VERTICAL_FACTORS[t['vertical_unit']]
    after=copy.deepcopy(row);after.update(cutline_xy=cut.tolist(),center_xy=center.tolist(),station_ft=station.tolist(),
        elevation_ft=[float(v) if np.isfinite(v) else None for v in z],bank_stations_ft=None,review_status='DRAFT_REQUIRES_REVIEW')
    after.pop('terrain_review',None);after['bank_candidates']=propose(after)
    after['terrain_sampling']=dict(raster=terrain['raster'],vertical_unit=t['vertical_unit'],vertical_datum=t['vertical_datum'],
        spatial_fingerprint=digest({k:after[k] for k in ['cutline_xy','station_ft','elevation_ft','center_xy']}))
    candidate=copy.deepcopy(g);candidate['cross_sections'][index]=after
    issues=[q for q in spatial_issues(candidate['cross_sections']) if index in q['sections']]
    result=dict(id=unique_id(),revision=revision,index=index,fingerprint=fingerprint,before=row,after=after,parameters=params,
        sources=[terrain['raster']]+([item(safe_path((ROOT/p['project']).parent,t['provenance']))] if t.get('provenance') else []),created_utc=utc(),spatial_issues=issues,nodata_samples=int((~np.isfinite(z)).sum()),
        geometry_moved=not np.allclose(np.array(row['cutline_xy']),cut,atol=1e-8,rtol=0),
        limitation='Preview only; narrowing can omit floodplain conveyance. Apply invalidates review; no hydraulic result recalculated.')
    path=sp.parent/'section_edits'/result['id']/'preview.json';save(path,result)
    with lock(sp.parent/'session.lock'):
        index_path=sp.parent/'section_edit_index.json';entries=read(index_path) if index_path.exists() else {}
        entries[result['id']]=item(path);save(index_path,entries)
    return dict(preview=result)


def apply_preview(session_path,revision,preview_id,reviewer,basis):
    from . import intake
    require_reviewer(dict(reviewer=reviewer,basis=basis));sp=safe_path(ROOT,session_path)
    with lock(sp.parent/'session.lock'):
        _,s,p,d=intake._load(sp);c,g=intake._objects(p,d)
        if d['revision']!=revision:raise ValueError('Stale draft revision')
        entries=read(sp.parent/'section_edit_index.json');entry=entries.get(preview_id)
        if not entry or not intact([entry]):raise ValueError('Preview is missing or changed')
        v=read(ROOT/entry['path']);i=v['index']
        if revision!=v['revision'] or section_fingerprint(g['cross_sections'][i])!=v['fingerprint'] or not intact(v['sources']):
            raise ValueError('Preview is stale; preview current geometry/terrain again')
        if v['nodata_samples']:raise ValueError('Preview contains NoData; adjust its extent before applying')
        if v['spatial_issues']:raise ValueError('Preview still intersects other sections; adjust the layout before applying')
        old=copy.deepcopy(d);g['cross_sections'][i]=v['after'];clear=set()
        for key in ['cutline_xy','center_xy','station_ft','elevation_ft','bank_stations_ft']:clear.add(f'g.cross_sections.{i}.'+key)
        if v['geometry_moved']:
            g['functional_section_basis']=None;clear.add('g.functional_section_basis')
            for j in [i-1,i]:
                if 0<=j<len(g['cross_sections'])-1:
                    for key in ['reach_lengths_ft','reach_length_basis']:
                        g['cross_sections'][j][key]=None;clear.add(f'g.cross_sections.{j}.'+key)
        old_stations=v['before']['station_ft'];new_stations=v['after']['station_ft']
        reference_changed=not np.allclose([old_stations[0],old_stations[-1]],[new_stations[0],new_stations[-1]],atol=1e-6,rtol=0)
        if (v['geometry_moved'] or reference_changed) and v['before'].get('rs') in [g['structure'].get('us_xs_rs'),g['structure'].get('ds_xs_rs')]:
            for j,b in enumerate(g['structure']['groups']):b['centers_ft']=None;clear.add(f'g.structure.groups.{j}.centers_ft')
            g['structure']['road']['station_ft']=None;clear.add('g.structure.road.station_ft')
            if g['structure']['road'].get('profile_mode')=='distinct':
                g['structure']['road']['downstream_station_ft']=None;clear.add('g.structure.road.downstream_station_ft')
        if v['geometry_moved'] or reference_changed:
            for key in ['manning_segments','ineffective_left','ineffective_right']:
                if g['cross_sections'][i].get(key):
                    g['cross_sections'][i][key]=None;clear.add(f'g.cross_sections.{i}.'+key)
        for row in g['cross_sections']:row.pop('terrain_review',None)
        annotate(g);g['provenance']+=v['sources']+[entry]
        d.update(geometry=g,revision=revision+1,consent=False,section_review_drafts={})
        d['answers']={k:val for k,val in d['answers'].items() if k not in clear}
        d.setdefault('geometry_edit_sources',[]).extend(v['sources']+[entry])
        save(sp.parent/'events'/('resample_'+unique_id()+'.json'),dict(before=old,preview=entry,reviewer=reviewer,basis=basis,created_utc=utc()))
        save(sp.parent/'draft.json',d)
    return intake.view(sp)


def alternatives(session_path,index):
    _,_,_,_,_,g,_,_,_=context(session_path)
    if type(index)!=int or not 0<=index<len(g['cross_sections']):raise ValueError('Unknown section')
    row=g['cross_sections'][index];cut,center,p=transform_section(row,g['horizontal_crs'],{})
    base=len([q for q in spatial_issues(g['cross_sections']) if index in q['sections']]);candidates=[]
    for ratio in [1.,.9,.8]:
        for angle in [0.,-10.,10.,-20.,20.]:
            if ratio==1 and angle==0:continue
            params=dict(rotation_deg=angle,width_ft=p['width_ft']*ratio,sampling_ft=p['sampling_ft'])
            cut,center,_=transform_section(row,g['horizontal_crs'],params)
            rows=copy.deepcopy(g['cross_sections']);rows[index].update(cutline_xy=cut.tolist(),center_xy=center.tolist())
            count=len([q for q in spatial_issues(rows) if index in q['sections']])
            if count<base:candidates.append(dict(parameters=params,remaining_spatial_issues=count,narrower=ratio<1))
    candidates.sort(key=lambda r:(r['remaining_spatial_issues'],r['narrower'],abs(r['parameters']['rotation_deg'])))
    return dict(alternatives=candidates[:3],current_spatial_issues=base,requires_dem_preview=True,
        limitation='Geometric alternatives only; floodplain coverage and effective flow paths still require review')
