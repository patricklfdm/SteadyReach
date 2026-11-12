"""Terrain-based external flowline/section candidates between explicit anchors.

Least-cost paths are screening geometry, not observed flow or a hydraulic model.
Disconnected external reaches preserve the structure gap without burning the DEM.
"""
import heapq
import math
import numpy as np
import rasterio
from pyproj import CRS, Transformer

from .common import ROOT, finite, intact, item, read, rel, safe_path, save, utc
from .sections import intersect
from .sensitivity import VERTICAL_FACTORS


def least_cost(z, valid, heights, start, end, grid_ft, elevation_weight, uphill_weight, height_scale_ft):
    """Eight-neighbour Dijkstra; NoData and diagonal corner cutting are forbidden."""
    rows,cols=z.shape
    if not valid[start] or not valid[end]:raise ValueError('Anchor is outside valid terrain/corridor')
    distance=np.full(z.shape,np.inf);previous={};distance[start]=0.;queue=[(0.,start)]
    while queue:
        cost,current=heapq.heappop(queue)
        if cost!=distance[current]:continue
        if current==end:break
        r,c=current
        for dr,dc in [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]:
            nr,nc=r+dr,c+dc
            if not (0<=nr<rows and 0<=nc<cols and valid[nr,nc]):continue
            if dr and dc and (not valid[r,nc] or not valid[nr,c]):continue
            length=grid_ft*math.hypot(dr,dc)
            weight=length*(1+elevation_weight*(heights[current]+heights[nr,nc])/(2*height_scale_ft))
            weight+=uphill_weight*max(0.,z[nr,nc]-z[current])
            next_cost=cost+weight
            if next_cost<distance[nr,nc]:
                distance[nr,nc]=next_cost;previous[(nr,nc)]=current;heapq.heappush(queue,(next_cost,(nr,nc)))
    if not math.isfinite(distance[end]):raise ValueError('No valid terrain route between anchors; no gap filling performed')
    route=[end]
    while route[-1]!=start:route.append(previous[route[-1]])
    return route[::-1],float(distance[end])


def corridor_grid(anchors,half_width,step,sample,xy_to_ft,weights):
    a=np.asarray(anchors,dtype=float)
    if a.ndim!=2 or a.shape[1]!=2 or len(a)<2 or not np.isfinite(a).all():raise ValueError('At least two finite ordered anchor coordinates required')
    lengths=np.linalg.norm(np.diff(a,axis=0),axis=1)
    if (lengths<=0).any():raise ValueError('Duplicate corridor anchors')
    lo=a.min(axis=0)-half_width/xy_to_ft;hi=a.max(axis=0)+half_width/xy_to_ft;spacing=step/xy_to_ft
    count=np.ceil((hi-lo)/spacing).astype(int)+1
    if int(count[0])*int(count[1])>250_000:raise ValueError('Candidate grid exceeds 250000 nodes; narrow corridor or explicitly coarsen screening grid')
    x=lo[0]+np.arange(count[0])*spacing;y=lo[1]+np.arange(count[1])*spacing
    xx,yy=np.meshgrid(x,y);points=np.column_stack([xx.ravel(),yy.ravel()]);dist=np.full(len(points),np.inf);chain=np.zeros(len(points));chain0=0.
    for start,end,length in zip(a,a[1:],lengths):
        delta=end-start;fraction=np.clip((points-start)@delta/(length*length),0,1)
        d=np.linalg.norm(points-(start+fraction[:,None]*delta),axis=1);best=d<dist
        dist[best]=d[best];chain[best]=chain0+fraction[best]*length;chain0+=length
    z=np.asarray(sample(points),dtype=float).reshape(xx.shape)
    valid=np.isfinite(z)&(dist.reshape(z.shape)*xy_to_ft<=half_width)
    bins=np.floor(chain*xy_to_ft/step).astype(int);minimum=np.full(bins.max()+1,np.inf)
    np.minimum.at(minimum,bins[valid.ravel()],z[valid]);heights=(z.ravel()-minimum[bins]).reshape(z.shape)
    heights[~valid]=0.
    indices=[]
    for anchor in a:
        col,row=np.rint((anchor-lo)/spacing).astype(int);indices.append((int(row),int(col)))
    # Every explicit anchor is honoured, not only the endpoints of a curved corridor.
    route=[];cost=0.
    for start,end in zip(indices,indices[1:]):
        part,value=least_cost(z,valid,heights,start,end,step,**weights);route+=part if not route else part[1:];cost+=value
    xy=np.array([[x[c],y[r]] for r,c in route]);elev=np.array([z[r,c] for r,c in route])
    return xy,elev,dict(cost=cost,node_count=int(z.size),valid_nodes=int(valid.sum()),anchor_grid_positions=[list(v) for v in indices],
                       anchor_snap_max_ft=float(max(np.linalg.norm(xy0-anchor)*xy_to_ft for xy0,anchor in zip([[x[c],y[r]] for r,c in indices],a))))


def section_candidates(line,sample,xy_to_ft,spec):
    lengths=np.r_[0,np.cumsum(np.linalg.norm(np.diff(line,axis=0),axis=1))*xy_to_ft]
    if len(line)<2 or not np.isfinite(lengths).all() or (np.diff(lengths)<=0).any():
        raise ValueError('Candidate flowline needs distinct finite vertices')
    if lengths[-1]<=spec['section_spacing_ft']/2:
        raise ValueError('External reach too short for the requested section spacing')
    def point(distance):return np.array([np.interp(distance,lengths,line[:,i]) for i in [0,1]])
    result=[];width=spec['section_width_ft'];spacing=spec['section_spacing_ft'];step=spec['sampling_ft']
    orientation=spec.get('section_direction','local_tangent')
    if orientation not in ['local_tangent','external_reach_chord']:raise ValueError('Unsupported section direction method')
    for chainage in np.arange(spacing/2,lengths[-1],spacing):
        center=point(chainage);delta=point(min(lengths[-1],chainage+spacing/4))-point(max(0,chainage-spacing/4))
        if orientation=='external_reach_chord':delta=np.asarray(line[-1],float)-np.asarray(line[0],float)
        if np.linalg.norm(delta)==0:raise ValueError('Local flowline tangent is undefined')
        delta/=np.linalg.norm(delta);left=np.array([-delta[1],delta[0]])
        stations=np.linspace(0,width,math.ceil(width/step)+1)
        points=center+(width/2-stations)[:,None]*left/xy_to_ft;z=sample(points)
        if not np.isfinite(z).all() and not spec.get('allow_incomplete_sections'):
            raise ValueError('Candidate section intersects NoData; adjust its extent, no invented elevations')
        result.append(dict(local_chainage_ft=float(chainage),rs=None,center_xy=center.tolist(),cutline_xy=[points[0].tolist(),points[-1].tolist()],
            station_ft=stations.tolist(),elevation_ft=[float(v) if np.isfinite(v) else None for v in z],bank_stations_ft=None,reach_lengths_ft=None,
            expansion_contraction=None,section_direction=orientation,review_status='DRAFT_REQUIRES_REVIEW'))
    return result


def draft(project_path,spec_path,output):
    project_path=safe_path(ROOT,project_path);c=read(project_path);spec_path=safe_path(ROOT,spec_path);spec=read(spec_path);t=c['terrain']
    if not spec.get('purpose') or not spec.get('anchor_basis') or not spec.get('upstream_to_downstream_basis'):
        raise ValueError('Purpose, anchor provenance and flow-direction basis are required')
    if not spec.get('anchor_sources') or not intact(spec['anchor_sources']):raise ValueError('Anchor evidence must be hash-verified')
    for name in ['grid_ft','corridor_half_width_ft','height_scale_ft','section_width_ft','section_spacing_ft','sampling_ft']:
        if not finite(spec.get(name)) or spec[name]<=0:raise ValueError('Explicit positive candidate parameter required: '+name)
    for name in ['elevation_weight','uphill_weight']:
        if not finite(spec.get(name)) or spec[name]<0:raise ValueError('Explicit nonnegative route weight required: '+name)
    if spec['section_width_ft']/spec['sampling_ft']>499:raise ValueError('Candidate section exceeds 500 samples')
    reach_ids=[r['id'] for r in spec.get('external_reaches',[])]
    if not reach_ids or len(set(reach_ids))!=len(reach_ids):raise ValueError('Explicit external reaches with unique IDs required')
    if t.get('mode')!='local' or t.get('vertical_unit') not in VERTICAL_FACTORS or not t.get('vertical_datum'):
        raise ValueError('Explicit local DEM units/datum required before terrain sampling')
    raster=safe_path(project_path.parent,t['raster']);lines=[];sections=[];route_evidence=[]
    with rasterio.open(raster) as d:
        crs=CRS.from_wkt(d.crs.to_wkt());crs=crs.sub_crs_list[0] if crs.is_compound else crs
        if not crs.is_projected or not crs.equals(CRS.from_user_input(spec['crs'])):raise ValueError('Anchor and DEM CRS must match')
        xy_to_ft=crs.axis_info[0].unit_conversion_factor/.3048
        def sample(points):
            raw=np.ma.vstack(list(d.sample(points,masked=True)))[:,0].astype(float)
            return raw.filled(np.nan)*VERTICAL_FACTORS[t['vertical_unit']]
        for segment in spec['external_reaches']:
            xy,z,evidence=corridor_grid(segment['anchors_xy'],spec['corridor_half_width_ft'],spec['grid_ft'],sample,xy_to_ft,
                {k:spec[k] for k in ['elevation_weight','uphill_weight','height_scale_ft']})
            evidence.update(length_ft=float(np.linalg.norm(np.diff(xy,axis=0),axis=1).sum()*xy_to_ft),
                accumulated_uphill_ft=float(np.maximum(np.diff(z),0).sum()),
                repeated_grid_nodes=len(xy)-len({tuple(p) for p in xy}))
            lines.append(dict(id=segment['id'],xy=xy.tolist(),external_elevation_ft=z.tolist(),status='DRAFT_REQUIRES_REVIEW'))
            rows=section_candidates(xy,sample,xy_to_ft,spec)
            sections.extend([dict(row,reach_id=segment['id']) for row in rows]);route_evidence.append(dict(id=segment['id'],**evidence))
    cuts=[np.asarray(r['cutline_xy']) for r in sections]
    crossings=[(i,j) for i in range(len(cuts)) for j in range(i+1,len(cuts)) if intersect(*cuts[i],*cuts[j])]
    folder=safe_path(ROOT,output);folder.mkdir(parents=True,exist_ok=False)
    result=dict(schema_version='candidate_geometry_1.0',created_utc=utc(),status='DRAFT_REQUIRES_REVIEW',project_id=c['project_id'],
        sources=[item(project_path),item(spec_path),item(raster)]+spec['anchor_sources'],horizontal_crs=crs.to_wkt(),
        hydraulic_unit='international_ft',vertical_datum=t['vertical_datum'],flowlines=lines,cross_sections=sections,
        route_diagnostics=route_evidence,intersecting_cutlines=crossings,structure=None,approved_for_model=False,
        limitations=['Least-cost path is a topographic candidate, not a measured or calculated hydraulic flowline',
          'Anchor locations and upstream/downstream order require independent review; grid endpoints are snapped within recorded tolerance',
          'Separate external reaches have no modelled connection through the road; no DEM burning/filling',
          'Banks, structure, functional section positioning, station IDs and reach lengths remain unresolved',
          'Local-normal sections may intersect or miss an effective flow area; review all candidates before modelling'])
    from .banks import annotate
    annotate(result,spec.get('bank_screening'))
    save(folder/'candidates.json',result);tr=Transformer.from_crs(crs,4326,always_xy=True);features=[]
    for line in lines:
        features.append(dict(type='Feature',properties=dict(role='external_flowline_candidate',id=line['id']),geometry=dict(type='LineString',coordinates=[list(tr.transform(*p)) for p in line['xy']])))
    for i,row in enumerate(sections):
        features.append(dict(type='Feature',properties=dict(role='cross_section_candidate',index=i),geometry=dict(type='LineString',coordinates=[list(tr.transform(*p)) for p in row['cutline_xy']])))
    save(folder/'candidates.geojson',dict(type='FeatureCollection',features=features));plot(raster,spec,result,folder/'review.png')
    save(folder/'manifest.json',dict(status='DRAFT_REQUIRES_REVIEW',files=[item(folder/n) for n in ['candidates.json','candidates.geojson','review.png']],engineering_acceptance='NOT_ASSESSED'))
    return result


def plot(raster,spec,result,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from rasterio.windows import from_bounds
    from matplotlib.colors import LightSource
    points=np.concatenate([np.array(r['cutline_xy']) for r in result['cross_sections']]);lo=points.min(axis=0)-50;hi=points.max(axis=0)+50
    with rasterio.open(raster) as d:
        window=from_bounds(lo[0],lo[1],hi[0],hi[1],d.transform).round_offsets().round_lengths()
        z=d.read(1,window=window,masked=True,boundless=True);bounds=rasterio.windows.bounds(window,d.transform);resolution=d.res[0]
    origin=np.floor(lo/1000)*1000;fig,ax=plt.subplots(figsize=(8,8));shade=LightSource(315,45).hillshade(z.filled(float(z.mean())),dx=resolution,dy=resolution)
    ax.imshow(shade,extent=[bounds[0]-origin[0],bounds[2]-origin[0],bounds[1]-origin[1],bounds[3]-origin[1]],cmap='gray',alpha=.8)
    for i,line in enumerate(result['flowlines']):
        p=np.array(line['xy'])-origin;ax.plot(p[:,0],p[:,1],color='#007da5',lw=2,label='Terrain path candidate' if i==0 else None)
        p=np.array(spec['external_reaches'][i]['anchors_xy'])-origin;ax.plot(p[:,0],p[:,1],'o--',color='#c8791c',ms=3,lw=.8,label='Explicit anchor corridor' if i==0 else None)
    for i,row in enumerate(result['cross_sections']):
        p=np.array(row['cutline_xy'])-origin;ax.plot(p[:,0],p[:,1],color='#b32a70',lw=.8,label='Unreviewed section' if i==0 else None)
        ax.text(p[0,0],p[0,1],str(i+1),fontsize=7,color='#812052')
    crs=CRS.from_wkt(result['horizontal_crs']);unit=crs.axis_info[0].unit_name
    ax.set(title='External flowline and section candidates',xlabel=f'Easting {unit}; origin {origin[0]:.0f}',ylabel=f'Northing {unit}; origin {origin[1]:.0f}',aspect='equal')
    ax.legend(fontsize=8);ax.annotate('Grid N',xy=(.94,.92),xytext=(.94,.84),xycoords='axes fraction',ha='center',arrowprops=dict(arrowstyle='->'))
    length=100*.3048/crs.axis_info[0].unit_conversion_factor;x=lo[0]-origin[0]+25;y=lo[1]-origin[1]+25
    ax.plot([x,x+length],[y,y],'k-',lw=3);ax.text(x,y+12,'100 international ft',fontsize=7)
    fig.text(.08,.02,f'DEM: {rel(raster)} | {result["vertical_datum"]} | {utc()[:10]}\n{crs.to_string()} | Separate external reaches; no buried geometry or inundation map',fontsize=7)
    fig.tight_layout(rect=[0,.065,1,1]);fig.savefig(output,dpi=160);plt.close(fig)
