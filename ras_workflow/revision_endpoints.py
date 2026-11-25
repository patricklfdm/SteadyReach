"""Compare wet ends from the two verified native results at corresponding section sides."""
import h5py
from .common import ROOT, finite, safe_path
from .qa import number
from .revision_inputs import station_key


def endpoints(hyd,water):
    """Read ground once per section. Water levels were authenticated by verified_profiles."""
    values={}
    with h5py.File(safe_path(ROOT,hyd['raw_hdf']['path'])) as hdf:
        group=hdf['Geometry/Cross Sections']
        geom=group['Attributes'][:]
        output=hdf['Results/Steady/Output/Geometry Info/Cross Section Attributes'][:]
        index=group['Station Elevation Info'][:]
        heights=group['Station Elevation Values'][:,1]
        if len(geom)!=len(output) or len(index)!=len(output):
            raise ValueError('Native section inventories differ')
        for section,native,(start,count) in zip(geom,output,index):
            def identity(row,rs):
                return tuple(row[k].decode().strip() for k in ('River','Reach',rs))
            river,reach,rs=identity(section,'RS')
            if (river,reach,rs)!=identity(native,'Station'):
                raise ValueError('Native geometry and output locations differ')
            if start<0 or count<2 or int(start)+int(count)>len(heights):
                raise ValueError('Native section sample range is invalid')
            for side,offset in [('left',start),('right',int(start)+int(count)-1)]:
                ground=number(heights[offset])
                for profile,stations in water.items():
                    key=(profile,station_key(rs),side)
                    if key in values:
                        raise ValueError('Duplicate profile, station and side')
                    wse=number(stations[rs])
                    depth=wse-ground if wse is not None and ground is not None else None
                    values[key]=(river,reach,depth)
    return values


def compare_ends(previous,current,locations):
    counts=dict(new_wet=0,still_wet=0,became_dry=0,both_dry=0,unmatched=0)
    details=[]
    for key in sorted(previous.keys()|current.keys(),key=lambda k:(k[0],-float(k[1]),k[2])):
        profile,rs,side=key
        a,b=previous.get(key),current.get(key)
        old=a[2] if a else None
        new=b[2] if b else None
        loc=locations.get(rs,{})
        angle=loc.get('rotation_degrees')
        if not a or not b:
            reason='absent'
        elif a[:2]!=b[:2] or loc.get('location_status')!='SAME_CENTER':
            reason='location'
        elif not finite(angle) or abs(angle)>=90:
            reason='direction'
        elif old is None or new is None:
            reason='missing'
        else:
            reason=None
        if reason:
            state='unmatched'
        elif new>0:
            state='still_wet' if old>0 else 'new_wet'
        else:
            state='became_dry' if old>0 else 'both_dry'
        counts[state]+=1
        if state!='both_dry':
            details.append(dict(profile=profile,station=rs,side=side,state=state,reason=reason,
                                previous_depth_ft=old,current_depth_ft=new))
    return dict(counts=counts,rows=details)


def summary(previous,current,locations,old_water,new_water):
    try:
        if previous.get('unit')!='international ft' or current.get('unit')!=previous['unit']:
            raise ValueError('Native endpoint units could not be verified')
        result=compare_ends(endpoints(previous,old_water),endpoints(current,new_water),locations)
    except (OSError,KeyError,TypeError,ValueError,IndexError) as error:
        return dict(status='UNAVAILABLE',error=str(error),rows=[],counts=None,
                    en='The native endpoint comparison is unavailable.',zh='缺少可核验的原生端点对比。')
    n=result['counts']
    return dict(**result,status='COMPARED',
                en=(f"Section ends by profile: {n['new_wet']} newly wet, {n['still_wet']} still wet, "
                    f"{n['became_dry']} now dry, {n['both_dry']} dry in both editions, {n['unmatched']} unmatched."),
                zh=(f"按工况和断面侧别统计：新增过水 {n['new_wet']}，持续过水 {n['still_wet']}，"
                    f"转为干端 {n['became_dry']}，两版均干 {n['both_dry']}，无法配对 {n['unmatched']}。"))
