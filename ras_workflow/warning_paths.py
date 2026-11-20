"""Terrain-only screen for secondary wetted intervals at native divided-flow locations."""
import numpy as np
from rasterio.transform import rowcol
from scipy.ndimage import label
from scipy.spatial import cKDTree

from .qa_locator import intervals
from .revision_inputs import station_key
from .warning_geometry import along, coordinates, crossing


def review(geometry, audit, sampler):
    flags={(r['profile'],station_key(r['station'])) for r in audit['records'] if r['category']=='NATIVE_DIVIDED_FLOW'}
    result=dict(status='TERRAIN_SCREEN_ONLY',dem=sampler.source,hdf=audit['hdf'],locations=len(flags),intervals=[],unavailable=[])
    if not flags:
        return result
    line=np.array(geometry['flowlines'][0]['xy'])
    chain=along(line)
    cell=sampler.cell_ft/sampler.factor
    rows=geometry['cross_sections']
    locations=[crossing(r['cutline_xy'],line) for r in rows]
    if (chain[-1]/cell>200000 or any(v is None for v in locations)
            or any(a>=b for a,b in zip(locations,locations[1:])) or sampler.transform.b or sampler.transform.d):
        result['status']='UNAVAILABLE_GEOMETRY_OR_GRID'
        return result
    fine=np.unique(np.r_[np.arange(0.,chain[-1],cell),chain])
    tree=cKDTree(coordinates(line,chain,fine))
    for profile,stage_map in audit['stages'].items():
        stages=[stage_map[station_key(r['rs'])] for r in rows]
        for r,w in zip(rows,stages):
            rs=station_key(r['rs'])
            if (profile,rs) not in flags:
                continue
            x=np.array(r['station_ft']);z=np.array(r['elevation_ft'])
            banks=r['bank_stations_ft']
            inside=np.flatnonzero((x>=banks[0])&(x<=banks[1]))
            if not len(inside):
                result['unavailable'].append(dict(rs=rs,profile=profile,reason='NO_CHANNEL_SAMPLE'))
                continue
            bottom=inside[np.argmin(z[inside])]
            wet=intervals(x,z,w)
            primary=next((i for i,(a,b) in enumerate(wet) if a<=x[bottom]<=b),None)
            if primary is None or len(wet)<2:
                result['unavailable'].append(dict(rs=rs,profile=profile,reason='NO_DISTINCT_MODEL_INTERVAL'))
                continue
            cut=np.array(r['cutline_xy'])
            station=x[0]+along(cut)/along(cut)[-1]*(x[-1]-x[0])
            for i,(a,b) in enumerate(wet):
                if i==primary:
                    continue
                indices=np.flatnonzero((x>=a)&(x<=b))
                if not len(indices):
                    continue
                deepest=indices[np.argmin(z[indices])]
                anchors=coordinates(cut,station,[x[bottom],x[deepest]])
                tests={}
                for metres in (25,100):
                    pad=metres/(sampler.factor*.3048)
                    lo=anchors.min(axis=0)-pad;hi=anchors.max(axis=0)+pad
                    ar,ac=rowcol(sampler.transform,anchors[:,0],anchors[:,1])
                    top,left=rowcol(sampler.transform,lo[0],hi[1]);bt,rt=rowcol(sampler.transform,hi[0],lo[1])
                    clipped = top<0 or left<0 or bt>=sampler.z.shape[0] or rt>=sampler.z.shape[1]
                    top,left=max(0,top),max(0,left)
                    bt,rt=min(bt+1,sampler.z.shape[0]),min(rt+1,sampler.z.shape[1])
                    if (bt-top)*(rt-left)>250000 or any(ar<top) or any(ar>=bt) or any(ac<left) or any(ac>=rt):
                        tests[str(metres)]=dict(status='UNAVAILABLE_WINDOW')
                        continue
                    yy,xx=np.mgrid[top:bt,left:rt]
                    px,py=sampler.transform*(xx+.5,yy+.5)
                    _,ix=tree.query(np.column_stack([px.ravel(),py.ravel()]))
                    level=np.interp(fine[ix],locations,stages).reshape(px.shape)
                    dem=sampler.z[top:bt,left:rt]
                    known=np.isfinite(dem)
                    def connected(offset):
                        zones,_=label(known&(dem<level+offset))
                        p,q=zones[ar-top,ac-left]
                        return bool(p>0 and p==q)
                    tests[str(metres)]=dict(status='COMPLETE' if known.all() and not clipped else 'PARTIAL_DEM',
                        at_stage=connected(0),low=connected(-.1),high=connected(.1))
                result['intervals'].append(dict(profile=profile,rs=rs,side='left' if i<primary else 'right',
                    width_ft=float(b-a),max_depth_ft=float(w-z[deepest]),xy=anchors[1].tolist(),tests=tests))
    return result
