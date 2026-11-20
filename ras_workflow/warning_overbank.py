"""Coordinate DEM-only overbank cuts when simply extending a wet end would cross a neighbor."""
from copy import deepcopy
from functools import lru_cache
import math

import numpy as np
from .geometry_auto_qa import terrain_owned
from .geometry_qa import spatial_issues
from .section_joint import _crosses
from .warning_geometry import CONTROLS, along, coordinates


def sweep(geometry, stages, sampler, maximum, clearance):
    if geometry.get('channel_geometry_basis') != 'conditional_surface_dem':
        return geometry, [], [dict(reason='PRESERVE_REVIEWED_BATHYMETRY')]
    output = deepcopy(geometry)
    changed, omitted = [], []
    for side in ('right','left'):
        rows = output['cross_sections']
        left = side == 'left'
        end = 0 if left else -1
        centers = np.array([r['center_xy'] for r in rows])
        line = geometry['flowlines'][0]['xy']
        work = []
        for r in rows:
            x,z,cut = (np.array(r[k],float) for k in ('station_ft','elevation_ft','cutline_xy'))
            bank = r['bank_stations_ft'][0 if left else 1]
            origin = x[0]
            if left:
                cut,z,x = cut[::-1],z[::-1],x[-1]-x[::-1]
                bank = r['station_ft'][-1]-bank
            else:
                x,bank = x-origin,bank-origin
            stations = along(cut)*sampler.factor
            if abs(stations[-1]-x[-1])>.005:
                return geometry, [], [dict(rs=r['rs'],reason='CUT_LENGTH_DIFFERS_FROM_STATIONING')]
            anchor = coordinates(cut,stations,[bank])[0]
            kept = cut[stations < bank-1e-6]
            work.append((x,z,cut,bank,anchor,kept,origin))
        bank_points = np.array([v[4] for v in work])
        ends = np.array([v[2][-1] for v in work])
        original = [r['cutline_xy'] for r in rows]
        selected = {}
        cell = sampler.cell_ft/sampler.factor

        @lru_cache(None)
        def options(i):
            r = rows[i]
            if any(r.get(k) for k in CONTROLS) or not terrain_owned(r,sampler):
                return []
            x,z,cut,bank,anchor,kept,origin = work[i]
            old = cut[-1]-anchor
            norm = np.linalg.norm(old)
            if norm <= 0:
                return []
            old = old/norm
            ds = np.arange(cell,(maximum-bank)/sampler.factor,cell)
            if len(ds)<5:
                return []
            bearings=[old]
            for points in (bank_points,centers,ends):
                for radius in (1,2,4,8,len(rows)):
                    dx,dy=points[min(i+radius,len(rows)-1)]-points[max(0,i-radius)]
                    v=np.array([-dy,dx])
                    mag=np.linalg.norm(v)
                    if mag<1e-8:
                        continue
                    v=v/mag
                    if old@v<0:
                        v=-v
                    bearings.extend((v,old+v))
            candidates,seen=[],set()
            target=stages[float(r['rs'])]+clearance
            inside=x<bank-1e-6
            for v in bearings:
                unit=v/np.linalg.norm(v)
                angle=math.degrees(math.acos(float(np.clip(old@unit,-1.,1.))))
                direction=round(math.degrees(math.atan2(unit[1],unit[0]))/2)
                if angle>50 or direction in seen:
                    continue
                seen.add(direction)
                sample=sampler.sample(anchor+ds[:,None]*unit)
                invalid=np.flatnonzero(~np.isfinite(sample))
                if len(invalid):
                    sample=sample[:invalid[0]]
                if len(sample)<5:
                    continue
                dry=(sample>target)&(ds[:len(sample)]*sampler.factor>=x[-1]-bank)
                ends_at=np.flatnonzero(np.convolve(dry.astype(int),np.ones(5,int),'valid')==5)
                if not len(ends_at):
                    continue
                n=int(ends_at[0])+5
                if np.count_nonzero(inside)+1+n>500:
                    continue
                endpoint=anchor+ds[n-1]*unit
                newcut=np.vstack([kept,anchor,endpoint])
                if _crosses([anchor,endpoint],line) or spatial_issues([dict(cutline_xy=newcut)]):
                    continue
                newx=np.r_[x[inside],bank,bank+ds[:n]*sampler.factor]
                if np.min(np.diff(newx))<.002:
                    continue
                newz=np.r_[z[inside],np.interp(bank,x,z),sample[:n]]
                banks=np.array(r['bank_stations_ft'])
                if left:
                    newcut,newz,banks=newcut[::-1],newz[::-1],banks+newx[-1]-x[-1]
                    newx=newx[-1]-newx[::-1]
                candidate=dict(cutline_xy=newcut.tolist(),station_ft=(newx+origin).tolist(),
                               elevation_ft=newz.tolist(),bank_stations_ft=banks.tolist())
                candidates.append((angle,ds[n-1]*sampler.factor,candidate))
            return sorted(candidates,key=lambda v:(v[0],v[1]))

        def fit(i, edits, budget):
            if budget==0 or i in selected or i in edits:
                return None
            for angle,length,candidate in options(i):
                trial={**edits,i:(angle,length,candidate)}
                conflicts=[]
                for j,oldcut in enumerate(original):
                    if j==i:
                        continue
                    other=trial.get(j) or selected.get(j)
                    if _crosses(candidate['cutline_xy'],other[2]['cutline_xy'] if other else oldcut):
                        conflicts.append(j)
                if not conflicts:
                    return trial
                if len(conflicts)==1 and budget>1:
                    match=fit(conflicts[0],trial,budget-1)
                    if match:
                        return match
            return None

        for i,r in enumerate(rows):
            if i in selected or r['elevation_ft'][end]>stages[float(r['rs'])]+clearance:
                continue
            found=fit(i,{},2)
            if found:
                selected.update(found)
            else:
                omitted.append(dict(rs=r['rs'],side=side,reason='NO_COMPATIBLE_OVERBANK_PAIR'))
        for i,(angle,length,geometry_fields) in selected.items():
            row=rows[i]
            row.update(geometry_fields)
            sampler.stamp(row)
            changed.append(dict(rs=row['rs'],side=side,angle_deg=angle,new_limb_ft=length,
                                basis='DEM and neighboring bank/valley orientation; floodplain direction inferred'))
    return output,changed,omitted
