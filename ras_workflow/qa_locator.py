"""Locate actual wet edges and disconnected wetted intervals, without inferring flow paths."""
import h5py
from .common import ROOT, intact
from .qa import BASE, verified_profiles


def intervals(x,z,water):
    result=[];active=None
    for a,b,za,zb in zip(x,x[1:],z,z[1:]):
        wa,wb=za<water,zb<water
        if wa and active is None:active=a
        if wa!=wb:
            cut=a+(water-za)/(zb-za)*(b-a)
            if wa:result.append([active,cut]);active=None
            else:active=cut
        if wb and b==x[-1] and active is not None:result.append([active,b]);active=None
    return result


def collect(h,geometry=None):
    verified_profiles(h);rows=[]
    with h5py.File(ROOT/h['raw_hdf']['path']) as f:
        attrs=f['Geometry/Cross Sections/Attributes'][:];info=f['Geometry/Cross Sections/Station Elevation Info'][:];points=f['Geometry/Cross Sections/Station Elevation Values'][:]
        for pi,p in enumerate(h['profiles']):
            water=f[BASE+'/Cross Sections/Water Surface'][pi]
            for i,(a,(offset,count)) in enumerate(zip(attrs,info)):
                xy=points[offset:offset+count];x=xy[:,0].astype(float).tolist();z=xy[:,1].astype(float).tolist();w=float(water[i]);wet=intervals(x,z,w)
                if w<=min(z[0],z[-1]) and len(wet)<2:continue
                rs=a['RS'].decode().strip();matches=[v for v in (geometry or {}).get('cross_sections',[]) if str(v['rs'])==rs or float(v['rs'])==float(rs)]
                rows.append(dict(index=i,rs=rs,profile=p['profile_id'],station_ft=x,elevation_ft=z,wse_ft=w,
                    left_excess_ft=max(0,w-z[0]),right_excess_ft=max(0,w-z[-1]),wet_intervals_ft=wet,
                    cutline_xy=matches[0]['cutline_xy'] if len(matches)==1 else None,
                    review='Ground/WSE intersections only; separate wetted intervals do not establish connected bypass flow'))
    return dict(rows=rows,raw_hdf=h['raw_hdf'],hydraulic_qa='REVIEW_REQUIRED')
