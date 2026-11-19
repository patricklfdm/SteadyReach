"""Screen dry section endpoints for low terrain beyond an abrupt overbank-flow change."""
import copy

import h5py
import numpy as np

from .common import ROOT, intact, read
from .geometry_qa import spatial_issues
from .qa import BASE
from .section_joint import flow_crossing


def hydraulic_context(summary):
    h=summary['hydraulics']
    if not intact([h['raw_hdf']]):
        raise ValueError('The parent result HDF changed')
    with h5py.File(ROOT/h['raw_hdf']['path']) as file:
        block=file[BASE+'/Cross Sections'];extra=block.get('Additional Variables')
        if extra is None or any(key not in extra for key in ('Flow Left OB','Flow Right OB')):
            return {}
        ids=[float(x['RS'].decode()) for x in file['Geometry/Cross Sections/Attributes']]
        # Keep the comparison within the same actual profile.
        profile=next((i for i,row in enumerate(h['profiles']) if row['profile_id'].lower()=='q100'),None)
        if profile is None:return {}
        flow=block['Flow'][profile];levels=block['Water Surface'][profile]
        left=extra['Flow Left OB'][profile];right=extra['Flow Right OB'][profile]
        return {rs:(float(z),float(l/q),float(r/q)) for rs,z,q,l,r in zip(ids,levels,flow,left,right)
                if q>0 and all(np.isfinite(v) and abs(v)<1e20 for v in (z,q,l,r))}


def screen(geometry, old, readings, sampler, maximum):
    from .geometry_auto_qa import terrain_owned
    rows=geometry['cross_sections']
    output=copy.deepcopy(geometry);changes=[];flags=[]
    if len(geometry.get('flowlines',[]))!=1:return output,changes,flags
    line=geometry['flowlines'][0]['xy']
    keys=('cutline_xy','center_xy','station_ft','elevation_ft','bank_stations_ft')
    unchanged={r['rs'] for r in rows if r['rs'] in old and all(r.get(k)==old[r['rs']].get(k) for k in keys)}
    for i,row in enumerate(rows):
        rs=row['rs']
        if rs not in readings or rs not in unchanged or not terrain_owned(row,sampler):continue
        if any(row.get(k) for k in ('ineffective_left','ineffective_right','manning_segments')):continue
        x=np.asarray(row['station_ft']);z=np.asarray(row['elevation_ft']);cut=np.asarray(row['cutline_xy'],dtype=float)
        if len(cut)!=2:continue
        width=x[-1]-x[0];stage=readings[rs][0]
        direction=(cut[1]-cut[0])/np.linalg.norm(cut[1]-cut[0])
        for side in (0,1):
            end=0 if side==0 else -1;label='left' if side==0 else 'right'
            if z[end]<=stage:continue
            span=np.linalg.norm(cut[end]-row['center_xy'])*sampler.factor
            neighbors=[]
            for other in rows[max(0,i-1):i]+rows[i+1:i+2]:
                other_rs=other['rs']
                if other_rs not in readings or other_rs not in unchanged or other.get('reach_id')!=row.get('reach_id'):continue
                length=np.linalg.norm(np.asarray(other['cutline_xy'][end])-other['center_xy'])*sampler.factor
                share=readings[other_rs][side+1]
                if length>=1.6*span and share>=.20 and share-readings[rs][side+1]>=.15:
                    neighbors.append((float(length),other_rs,share))
            if not neighbors:continue
            length,near,share=max(neighbors)
            limit=min(maximum-width,length-span)
            flag=dict(rs=rs,side=label,neighbor_rs=near,neighbor_share=share,share=readings[rs][side+1],
                      neighbor_half_width_ft=length,current_half_width_ft=float(span),stage_ft=stage)
            if limit<30:
                flags.append(dict(flag,code='LATERAL_SEARCH_WIDTH_LIMIT'));continue
            offsets=np.linspace(0,limit,1+min(600,int(np.ceil(limit/max(sampler.cell_ft,3.)))))
            outward=direction*(-1 if side==0 else 1)
            heights=sampler.sample(cut[end]+offsets[:,None]/sampler.factor*outward)
            low_start=None;last_low=None;dry=None
            for j,height in enumerate(heights):
                if not np.isfinite(height):break
                if height<stage:
                    if low_start is None:low_start=j
                    if offsets[j]-offsets[low_start]>=15:last_low=j
                else:
                    low_start=None
                    if last_low is not None and j>last_low+1 and heights[j-1]>=stage:
                        dry=j;break
            if last_low is None:continue
            if dry is None:
                flags.append(dict(flag,code='LOW_OUTER_GROUND_NO_DRY_LIMIT'));continue
            distances=offsets[1:dry+1];elevations=heights[1:dry+1]
            if len(x)+len(distances)>500:
                flags.append(dict(flag,code='LATERAL_SAMPLE_LIMIT'));continue
            after=copy.deepcopy(row);added=float(distances[-1]);shift=added if side==0 else 0.
            if side==0:
                after.update(station_ft=np.r_[x[0]+added-distances[::-1],x+added].tolist(),
                             elevation_ft=np.r_[elevations[::-1],z].tolist())
            else:
                after.update(station_ft=np.r_[x,x[-1]+distances].tolist(),elevation_ft=np.r_[z,elevations].tolist())
            new_cut=cut.copy();new_cut[end]=cut[end]+outward*added/sampler.factor
            after['cutline_xy']=new_cut.tolist()
            if after.get('bank_stations_ft'):after['bank_stations_ft']=[b+shift for b in after['bank_stations_ft']]
            trial=list(output['cross_sections']);trial[i]=after
            if flow_crossing(new_cut,line) is None or spatial_issues(trial):
                flags.append(dict(flag,code='LATERAL_EXTENSION_CONFLICT'));continue
            sampler.stamp(after);after.pop('terrain_review',None);output['cross_sections'][i]=after
            changes.append(dict(flag,action='REVIEW_OUTER_FLOODPLAIN',left_added_ft=shift,right_added_ft=added-shift,
                station_label_shift_ft=shift,old_points_preserved=True,threshold_prior_wse_ft=stage))
            break
    return output,changes,flags
