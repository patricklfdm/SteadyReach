"""Bounded, explainable DEM layout proposals. No hydraulic or buried-geometry inference."""
import copy
import math
import numpy as np
import rasterio
from pyproj import CRS, Transformer
from .common import ROOT, digest, finite, intact, item
from .sensitivity import VERTICAL_FACTORS
from .geometry_qa import spatial_issues, intersects
from .banks import annotate


class Sampler:
    def __init__(self, terrain, unit, datum):
        if unit not in VERTICAL_FACTORS or not datum or not intact([terrain['raster']]):
            raise ValueError('Known DEM units/datum and unchanged raster required')
        self.source=terrain['raster'];self.unit=unit;self.datum=datum
        with rasterio.open(ROOT/self.source['path']) as dem:
            if dem.width*dem.height>16_000_000:raise ValueError('Crop a local DEM before automatic layout (maximum 16 million cells)')
            self.z=dem.read(1,masked=True).astype(float).filled(np.nan)*VERTICAL_FACTORS[unit]
            self.transform=dem.transform;self.crs=CRS.from_user_input(dem.crs)
            if self.crs.is_compound:self.crs=self.crs.sub_crs_list[0]
            if not self.crs.is_projected:raise ValueError('Projected DEM required')
            self.factor=self.crs.axis_info[0].unit_conversion_factor/.3048
            self.cell_ft=max(dem.res)*self.factor;self.bounds=list(dem.bounds)
    def sample(self, points):
        p=np.asarray(points,float);inv=~self.transform
        col=np.floor(inv.a*p[:,0]+inv.b*p[:,1]+inv.c).astype(int)
        row=np.floor(inv.d*p[:,0]+inv.e*p[:,1]+inv.f).astype(int)
        valid=(col>=0)&(row>=0)&(col<self.z.shape[1])&(row<self.z.shape[0]);out=np.full(len(p),np.nan)
        out[valid]=self.z[row[valid],col[valid]];return out
    def stamp(self,row):
        row['terrain_sampling']=dict(raster=self.source,vertical_unit=self.unit,vertical_datum=self.datum,
            spatial_fingerprint=digest({k:row[k] for k in ('cutline_xy','station_ft','elevation_ft','center_xy')}))


def unit_vector(v):
    v=np.asarray(v,float);n=np.linalg.norm(v)
    if n<1e-8:raise ValueError('Distinct exterior locations required')
    return v/n


def endpoints(m,g,s,c):
    """Prefer associated exterior mouths. Do not infer inverts or assign new mouths."""
    from .app_automation import resolve
    surrogate=dict(g,horizontal_crs=g.get('horizontal_crs') or s.crs.to_string())
    mapped,errors=resolve(m,surrogate)
    if mapped and not errors:
        u=np.mean([r['ends'][0]['xy'] for r in mapped],axis=0);d=np.mean([r['ends'][1]['xy'] for r in mapped],axis=0)
        if g.get('horizontal_crs') and not CRS.from_user_input(g['horizontal_crs']).equals(s.crs):
            t=Transformer.from_crs(g['horizontal_crs'],s.crs,always_xy=True);u=np.array(t.transform(*u));d=np.array(t.transform(*d))
        return [dict(us=u.tolist(),ds=d.tolist(),basis='ASSOCIATED_SURVEY_MOUTHS',sources=[r['survey']['source'] for r in mapped],direction_known=True)]
    picks=m.get('map_picks',{});groups=m.get('group_map_picks',{})
    pairs=[v for v in groups.values() if len(v.get('inlet',[]))==len(v.get('outlet',[]))==1]
    if not pairs and len(picks.get('inlet',[]))==len(picks.get('outlet',[]))==1:pairs=[picks]
    if pairs:
        return [dict(us=np.mean([v['inlet'][0] for v in pairs],axis=0).tolist(),ds=np.mean([v['outlet'][0] for v in pairs],axis=0).tolist(),basis='SAVED_MAP_MOUTHS',sources=[],direction_known=True)]
    if len(picks.get('upstream',[]))>=2 and len(picks.get('downstream',[]))>=2:
        return [dict(us=picks['upstream'][-1],ds=picks['downstream'][0],basis='SAVED_EXTERIOR_ANCHORS',sources=[],direction_known=True,already_exterior=True)]
    location=c.get('location',{});lat=location.get('latitude');lon=location.get('longitude')
    if not finite(lat) or not finite(lon):raise ValueError('A site coordinate or associated exterior locations are required')
    center=np.array(Transformer.from_crs(4326,s.crs,always_xy=True).transform(lon,lat));radius=max(60.,s.cell_ft*10)/s.factor
    pairs=[]
    # Opposing low-surface sectors around the pin, not inferred culvert ends.
    for degrees in range(0,180,15):
        axis=np.array([math.cos(math.radians(degrees)),math.sin(math.radians(degrees))]);normal=np.array([-axis[1],axis[0]])
        sides=[]
        for sign in (-1,1):
            choices=center+sign*axis*radius+np.linspace(-radius*.45,radius*.45,9)[:,None]*normal
            z=s.sample(choices)
            if not np.isfinite(z).all():break
            j=int(np.argmin(z));sides.append((choices[j],float(z[j])))
        if len(sides)!=2:continue
        a,b=sides;u,d=(a,b) if a[1]>=b[1] else (b,a)
        pairs.append(dict(us=u[0].tolist(),ds=d[0].tolist(),basis='DEM_LOW_SECTORS_AROUND_SITE_PIN',sources=[],direction_known=False,
            already_exterior=True,score=a[1]+b[1],surface_drop_ft=u[1]-d[1],degrees=degrees))
    selected=[]
    for p in sorted(pairs,key=lambda v:v['score']):
        if any(min(abs(p['degrees']-v['degrees']),180-abs(p['degrees']-v['degrees']))<30 for v in selected):continue
        selected.append(p)
        if len(selected)==3:break
    if not selected:raise ValueError('No valid opposing terrain sectors; identify the crossing/exterior points on the map')
    return selected


def anchors_outward(s,start,direction,length):
    """Find low points in successive, bounded exterior slices without crossing the road gap."""
    a=np.asarray(start,float);axis=unit_vector(direction);normal=np.array([-axis[1],axis[0]]);points=[a];limits=[]
    for distance in np.linspace(length/4,length,4):
        angles=np.linspace(-75.,75.,61);radians=np.radians(angles)
        pp=a+distance/s.factor*(np.cos(radians)[:,None]*axis+np.sin(radians)[:,None]*normal);zz=s.sample(pp);valid=np.isfinite(zz)
        if not valid.any():limits.append('DEM_LIMIT_REACHED');break
        # Weak lateral penalty avoids choosing a distant unrelated low spot solely by one raster cell.
        score=np.where(valid,zz+abs(angles)/75,np.inf);j=int(np.argmin(score));points.append(pp[j])
    if len(points)<3:raise ValueError('Insufficient exterior DEM coverage; choose a shorter reach or acquire more terrain')
    return np.asarray(points),limits


def width_row(s,center,tangent,minimum=120.,maximum=800.):
    tangent=unit_vector(tangent);left=np.array([-tangent[1],tangent[0]]);center=np.asarray(center,float)
    base=np.linspace(-minimum/2,minimum/2,81);z=s.sample(center-base[:,None]/s.factor*left)
    if not np.isfinite(z).all():raise ValueError('Initial section crosses DEM NoData')
    target=float(np.min(z)+max(2.,min(8.,(np.percentile(z,90)-np.min(z))*.5)))
    # Terrain relief is a layout screen, explicitly not a predicted flood elevation.
    best=None
    for width in sorted(set([minimum,min(maximum,minimum*1.5),min(maximum,minimum*2),min(maximum,minimum*3),maximum])):
        station=np.linspace(0,width,min(500,math.ceil(width/max(1.,s.cell_ft))+1));xy=center+(width/2-station)[:,None]/s.factor*left;zz=s.sample(xy)
        if not np.isfinite(zz).all():break
        closed=bool(min(zz[0],zz[-1])>target)
        row=dict(center_xy=center.tolist(),cutline_xy=[xy[0].tolist(),xy[-1].tolist()],station_ft=station.tolist(),elevation_ft=zz.tolist(),bank_stations_ft=None,reach_lengths_ft=None,expansion_contraction=None,
            auto_layout=dict(terrain_relief_screen_ft=target,screen_is_water_level=False,endpoints_above_screen=closed,width_ft=width))
        best=row
        if closed:break
    if best is None:raise ValueError('No complete DEM section at the proposed location')
    s.stamp(best);return best


def adaptive_sections(s,line,reach,maximum):
    line=np.asarray(line,float);dist=np.r_[0,np.cumsum(np.linalg.norm(np.diff(line,axis=0),axis=1))*s.factor];length=dist[-1]
    spacing=max(20.,min(80.,length/7));positions=list(np.arange(0,length,spacing))+[length];reasons={round(float(v),6):'REGULAR_AND_EXTERIOR_FACE' for v in positions}
    # Extra samples at strong bends / longitudinal slope changes, bounded and separated.
    probes=np.linspace(0,length,25);xy=np.column_stack([np.interp(probes,dist,line[:,k]) for k in (0,1)]);z=s.sample(xy)
    for i in range(1,len(probes)-1):
        a=unit_vector(xy[i]-xy[i-1]);b=unit_vector(xy[i+1]-xy[i]);turn=math.degrees(math.acos(float(np.clip(a@b,-1,1))))
        slope_change=abs((z[i+1]-2*z[i]+z[i-1])/(probes[i]-probes[i-1]))
        if (turn>25 or slope_change>.03) and min(abs(probes[i]-v) for v in positions)>spacing*.35 and len(positions)<16:
            positions.append(float(probes[i]));reasons[round(float(probes[i]),6)]='BEND_OR_SLOPE_BREAK'
    positions.sort();rows=[]
    for pos in positions:
        point=lambda x:np.array([np.interp(x,dist,line[:,k]) for k in (0,1)])
        center=point(pos);delta=point(min(length,pos+spacing/2))-point(max(0,pos-spacing/2))
        row=width_row(s,center,delta,maximum=maximum);row.update(reach_id=reach,local_chainage_ft=float(pos),rs=None,
            position_basis=reasons[round(float(pos),6)],review_status='DRAFT_REQUIRES_REVIEW');rows.append(row)
    return rows,spacing


def initial(m,g,c,s,length=400.,maximum=800.):
    from .alignment import corridor_grid
    from .app_section_repair import suggest
    seeds=endpoints(m,g,s,c);layouts=[];failures=[]
    for number,seed in enumerate(seeds):
        try:
            u=np.array(seed['us']);d=np.array(seed['ds']);axis=unit_vector(d-u)
            offset=0. if seed.get('already_exterior') else max(10.,s.cell_ft*3)
            up,un=anchors_outward(s,u-offset/s.factor*axis,-axis,length)
            down,dn=anchors_outward(s,d+offset/s.factor*axis,axis,length)
            reaches=[dict(id='upstream',anchors_xy=up[::-1].tolist()),dict(id='downstream',anchors_xy=down.tolist())]
            rows=[];lines=[];parameters=[]
            for reach in reaches:
                line,z,ev=corridor_grid(reach['anchors_xy'],40.,max(5.,s.cell_ft),s.sample,s.factor,dict(elevation_weight=1.,uphill_weight=4.,height_scale_ft=10.))
                # Keep enough vertices for bends but avoid one-grid-step tangent oscillations.
                chain=np.r_[0,np.cumsum(np.linalg.norm(np.diff(line,axis=0),axis=1))*s.factor]
                at=np.r_[np.arange(0,chain[-1],max(15.,s.cell_ft*3)),chain[-1]]
                line=np.column_stack([np.interp(at,chain,line[:,k]) for k in (0,1)])
                rr,spacing=adaptive_sections(s,line,reach['id'],maximum);rows+=rr;parameters.append(dict(reach=reach['id'],proposed_spacing_ft=spacing))
                lines.append(dict(id=reach['id'],xy=line.tolist(),status='TERRAIN_DERIVED_CANDIDATE',screening=ev))
            candidate=copy.deepcopy(g);candidate.update(horizontal_crs=s.crs.to_string(),vertical_datum=s.datum,cross_sections=rows,flowlines=lines,approved_for_model=False)
            for i,row in enumerate(rows):row['rs']=float((len(rows)-i)*100)
            # Rotate only if a bounded joint solution exists. Never shrink to hide a conflict.
            rotations=suggest(candidate)
            if rotations['changes']:
                from .geometry_editor import transform_section
                for change in rotations['changes']:
                    row=rows[change['index']];cut,center,p=transform_section(row,s.crs,change['parameters']);tangent=np.array([-(cut[-1]-cut[0])[1],(cut[-1]-cut[0])[0]])
                    width=p['width_ft'];station=np.array(row['station_ft']);xy=cut[0]+station[:,None]/width*(cut[-1]-cut[0]);zz=s.sample(xy)
                    if np.isfinite(zz).all():row.update(cutline_xy=cut.tolist(),elevation_ft=zz.tolist());s.stamp(row)
            # An end section may pass the relief screen while cropping a bank
            # break. Try wider DEM coverage before asking for manual stations.
            from .banks import propose as bank_proposal
            for reach in ('upstream','downstream'):
                indices=[i for i,r in enumerate(rows) if r['reach_id']==reach]
                exterior=indices[0] if reach=='upstream' else indices[-1]
                row=rows[exterior]
                settings=dict(window_ft=6.,center_search_fraction=.1,distance_penalty=1.)
                if bank_proposal(row,settings).get('selected_indices'):
                    continue
                old_width=row['station_ft'][-1]-row['station_ft'][0]
                transverse=np.asarray(row['cutline_xy'][-1])-row['cutline_xy'][0]
                tangent=np.array([-transverse[1],transverse[0]])
                for width in sorted(set(min(maximum,old_width*v) for v in (1.5,2.,3.))):
                    if width<=old_width:continue
                    try:
                        wider=width_row(s,row['center_xy'],tangent,minimum=width,maximum=width)
                    except ValueError:
                        break
                    if not bank_proposal(wider,settings).get('selected_indices'):
                        continue
                    updated=dict(row,**wider)
                    trial=rows.copy();trial[exterior]=updated
                    if spatial_issues(trial):
                        continue
                    updated['auto_layout']['bank_coverage_extension_from_ft']=old_width
                    rows[exterior]=updated
                    break
            issues=spatial_issues(rows)
            for row in rows:row['auto_layout']['endpoints_above_screen']=min(row['elevation_ft'][0],row['elevation_ft'][-1])>row['auto_layout']['terrain_relief_screen_ft']
            annotate(candidate)
            warnings=list(dict.fromkeys(un+dn+(['DIRECTION_AND_CROSSING_UNCONFIRMED'] if not seed['direction_known'] else [])+['BOUNDARY_REACH_EXTENT_NOT_HYDRAULICALLY_VERIFIED']))
            layouts.append(dict(id='layout_'+str(number+1),seed=seed,anchors=reaches,parameters=parameters,geometry=candidate,issues=issues,warnings=warnings,
                changed_sections=list(range(len(rows))),missing_heights=0,can_apply=not issues,
                basis='Exterior DEM candidates; adaptive spacing at bends/slope breaks; relief-screen width is not flood extent. No buried opening geometry inferred.'))
        except (ValueError,StopIteration) as e:failures.append(dict(seed=seed,error=str(e)))
    if not layouts:raise ValueError('No complete layout candidate: '+str(failures))
    layouts.sort(key=lambda v:(len(v['issues']),sum(not r['auto_layout']['endpoints_above_screen'] for r in v['geometry']['cross_sections'])))
    return dict(layouts=layouts,failures=failures,sources=[s.source]+[v for seed in seeds for v in seed['sources']],solver_run=False)
