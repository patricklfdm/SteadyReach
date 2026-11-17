"""Bounded joint DEM section directions and coverage, retaining explicit uncertainty."""
import copy
import math
from collections import Counter

import numpy as np

from .common import finite
from .geometry_qa import intersects,spatial_issues
from .geometry_editor import transform_section

ANGLES = [0.] + [a for n in (1.,2.,3.,5.,7.5,10.,15.,20.,25.,30.) for a in (n,-n)]
MAX_SEARCH_NODES = 100000


def flow_crossing(cut,line):
    """Return the unique along-flowline location, merging duplicate vertex hits."""
    a,b=np.asarray(cut,float)
    u=b-a
    hits=[]
    distance=0.
    cross=lambda x,y:float(x[0]*y[1]-x[1]*y[0])
    for c,d in zip(line,line[1:]):
        c,d=np.asarray(c,float),np.asarray(d,float)
        v=d-c
        length=float(np.linalg.norm(v))
        denominator=cross(u,v)
        if abs(denominator)<1e-9:
            if intersects(a,b,c,d):
                return None
        else:
            t=cross(c-a,v)/denominator
            fraction=cross(c-a,u)/denominator
            if -1e-9<=t<=1+1e-9 and -1e-9<=fraction<=1+1e-9:
                location=distance+fraction*length
                if not any(abs(location-old)<1e-6 for old in hits):
                    hits.append(location)
        distance+=length
    return hits[0] if len(hits)==1 else None


def _crosses(a,b):
    if len(a)!=2 or len(b)!=2:
        return any(_crosses(a[i:i+2],b[j:j+2]) for i in range(len(a)-1) for j in range(len(b)-1))
    for axis in (0,1):
        if max(a[0][axis],a[1][axis])<min(b[0][axis],b[1][axis])-1e-8:
            return False
        if max(b[0][axis],b[1][axis])<min(a[0][axis],a[1][axis])-1e-8:
            return False
    return intersects(*a,*b)


def _select(options):
    """Minimize unresolved coverage, then rotation, then added width, per component."""
    ids=sorted(options)
    compatible={}
    neighbors={i:set() for i in ids}
    for offset,i in enumerate(ids):
        for j in ids[offset+1:]:
            matrix=[[not _crosses(a['row']['cutline_xy'],b['row']['cutline_xy']) for b in options[j]] for a in options[i]]
            if all(all(row) for row in matrix):
                continue
            compatible[i,j]=matrix
            neighbors[i].add(j)
            neighbors[j].add(i)
    pending=set(ids)
    chosen={}
    trials=[]
    while pending:
        component={min(pending)}
        while True:
            expanded=component|{j for i in component for j in neighbors[i]}
            if expanded==component:
                break
            component=expanded
        pending-=component
        visited=0
        best=None
        best_cost=None
        limited=False
        node_limit=max(1,MAX_SEARCH_NODES//2)
        def search(domains,selection,cost):
            nonlocal visited,best,best_cost,limited
            if visited>=node_limit:
                limited=True
                return
            visited+=1
            lower=tuple(cost[k]+sum(min(options[i][a]['cost'][k] for a in values) for i,values in domains.items()) for k in range(3))
            if best_cost is not None and lower>=best_cost:
                return
            if not domains:
                best=selection.copy()
                best_cost=cost
                return
            i=min(domains,key=lambda index:(len(domains[index]),-len(neighbors[index]),index))
            for a in sorted(domains[i],key=lambda index:options[i][index]['cost']):
                if limited:
                    break
                next_domains={}
                valid=True
                for j,values in domains.items():
                    if i==j:
                        continue
                    pair=(min(i,j),max(i,j))
                    matrix=compatible.get(pair)
                    allowed=values if matrix is None else [b for b in values if (matrix[a][b] if i<j else matrix[b][a])]
                    if not allowed:
                        valid=False
                        break
                    next_domains[j]=allowed
                if valid:
                    next_selection=selection.copy()
                    next_selection[i]=a
                    search(next_domains,next_selection,tuple(cost[k]+options[i][a]['cost'][k] for k in range(3)))
        domains={i:list(range(len(options[i]))) for i in component}
        # First try the best coverage available at every section. This prevents
        # cheap unchanged wet sections from exhausting the search too early.
        covered={i:[a for a in values if options[i][a]['cost'][0]==min(options[i][b]['cost'][0] for b in values)]
                 for i,values in domains.items()}
        search(covered,{},(0,0.,0.))
        coverage_limited=limited
        limited=False
        node_limit=MAX_SEARCH_NODES
        search(domains,{},(0,0.,0.))
        if best is not None:
            chosen.update(best)
        trials.append(dict(sections=sorted(component),visited=visited,search_limit_reached=limited or coverage_limited,
                           status='CANDIDATE_FOUND' if best is not None else 'NO_COMPATIBLE_CANDIDATE',cost=list(best_cost) if best_cost is not None else None))
    return chosen,trials


def repair(geometry,sampler,water,maximum,protected=(),allow_rotation=True):
    from .geometry_auto_qa import extend,terrain_owned
    rows=geometry['cross_sections']
    lines={r['id']:r['xy'] for r in geometry.get('flowlines',[])}
    initial=spatial_issues(rows)
    invalid=[issue for issue in initial if issue['code']!='INTERSECTING_SECTIONS']
    for i,row in enumerate(rows):
        x=row.get('station_ft') or []
        z=row.get('elevation_ft') or []
        if len(x)<2 or len(x)!=len(z) or not all(finite(v) for v in x+z) or any(a>=b for a,b in zip(x,x[1:])):
            invalid.append(dict(code='INVALID_SECTION_PROFILE',sections=[i],rs=row.get('rs')))
    if invalid:
        return dict(geometry=copy.deepcopy(geometry),changes=[],unresolved=invalid,
                    search=dict(method='joint_section_direction_coverage_v1',status='INVALID_GEOMETRY_REQUIRES_REVIEW'))
    if not finite(maximum) or maximum<=0 or not all(finite(v) for v in water.values()):
        raise ValueError('Finite water levels and a positive section-width bound are required')
    original_crossings={i:flow_crossing(row['cutline_xy'],lines[row['reach_id']])
        for i,row in enumerate(rows) if len(row.get('cutline_xy',[]))==2 and row.get('reach_id') in lines}
    active={i for i,row in enumerate(rows) if row['rs'] in water and min(row['elevation_ft'][0],row['elevation_ft'][-1])<=water[row['rs']]}
    active.update(i for issue in initial for i in issue['sections'])
    # Include sections obstructing straight extensions and their immediate neighbors.
    for i in list(active):
        row=rows[i]
        if row['rs'] not in water or i in protected or not terrain_owned(row,sampler) or len(row['cutline_xy'])!=2:
            continue
        extended,_=extend(row,sampler,water[row['rs']],maximum)
        if extended:
            active.update(j for j,other in enumerate(rows) if j!=i and _crosses(extended['cutline_xy'],other['cutline_xy']))
    active.update(j for i in list(active) for j in (i-1,i+1) if 0<=j<len(rows) and rows[j].get('reach_id')==rows[i].get('reach_id'))
    options={}
    attempts=[]
    for i in sorted(active):
        row=rows[i]
        width=row['station_ft'][-1]-row['station_ft'][0]
        level=water.get(row['rs'])
        uncovered=level is not None and min(row['elevation_ft'][0],row['elevation_ft'][-1])<=level
        choices=[dict(row=copy.deepcopy(row),record=None,cost=(int(uncovered),0.,0.))]
        reasons=Counter()
        position=original_crossings.get(i)
        eligible=i not in protected and terrain_owned(row,sampler) and len(row.get('cutline_xy',[]))==2
        if row.get('reach_id') in lines and position is None:
            eligible=False
            reasons['ORIGINAL_FLOWLINE_CROSSING_REQUIRES_REVIEW']+=1
        subdivided=any(row.get(k) for k in ('manning_segments','ineffective_left','ineffective_right'))
        angles=ANGLES if allow_rotation and eligible and not subdivided and position is not None else [0.]
        nearby=[original_crossings[j] for j in (i-1,i+1) if j in original_crossings and original_crossings[j] is not None and rows[j].get('reach_id')==row.get('reach_id')]
        span=min([abs(v-position)/2 for v in nearby]+[math.inf]) if position is not None else 0.
        for angle in angles:
            if not eligible:
                reasons['PROTECTED_OR_NON_TERRAIN_SECTION']+=1
                break
            candidate=copy.deepcopy(row)
            record=None
            if angle:
                cut,center,parameters=transform_section(row,geometry['horizontal_crs'],dict(rotation_deg=angle))
                crossing=flow_crossing(cut,lines[row['reach_id']])
                if crossing is None or abs(crossing-position)>span+1e-6:
                    reasons['FLOWLINE_CROSSING_OR_ORDER']+=1
                    continue
                fractions=(np.asarray(row['station_ft'])-row['station_ft'][0])/width
                z=sampler.sample(cut[0]+fractions[:,None]*(cut[-1]-cut[0]))
                if not np.isfinite(z).all():
                    reasons['NODATA']+=1
                    continue
                candidate.update(cutline_xy=cut.tolist(),center_xy=center.tolist(),elevation_ft=z.tolist(),bank_stations_ft=None)
                candidate.pop('terrain_review',None)
                candidate.pop('bank_candidates',None)
                sampler.stamp(candidate)
                record=dict(action='JOINT_ROTATION_AND_COVERAGE',rotation_deg=angle,parameters=parameters,
                    old_points_preserved=False,banks_need_confirmation=True,flowline_crossing_count=1)
            if level is not None and min(candidate['elevation_ft'][0],candidate['elevation_ft'][-1])<=level:
                after,extension=extend(candidate,sampler,level,maximum)
                if after:
                    candidate=after
                    if record:
                        record.update(extension,old_points_preserved=False)
                    else:
                        record=dict(extension,action='EXTEND_WET_ENDS',rotation_deg=0.)
                else:
                    reasons[extension['status']]+=1
            if record is None:
                continue
            if position is not None:
                crossing=flow_crossing(candidate['cutline_xy'],lines[row['reach_id']])
                if crossing is None or abs(crossing-position)>span+1e-6:
                    reasons['EXTENDED_FLOWLINE_CROSSING_OR_ORDER']+=1
                    continue
            if any(j not in active and _crosses(candidate['cutline_xy'],other['cutline_xy']) for j,other in enumerate(rows)):
                reasons['OUTSIDE_SEARCH_CONFLICT']+=1
                continue
            still_wet=level is not None and min(candidate['elevation_ft'][0],candidate['elevation_ft'][-1])<=level
            record.update(rs=row['rs'],threshold_prior_wse_ft=level,screen_covered=not still_wet)
            added=candidate['station_ft'][-1]-candidate['station_ft'][0]-width
            choices.append(dict(row=candidate,record=record,cost=(int(still_wet),abs(angle),max(0.,added)/maximum)))
        options[i]=choices
        attempts.append(dict(index=i,rs=row['rs'],candidate_count=len(choices),rejected=dict(reasons)))
    chosen,search=_select(options)
    result=copy.deepcopy(geometry)
    changes=[]
    unresolved=[]
    for i,a in sorted(chosen.items()):
        choice=options[i][a]
        result['cross_sections'][i]=choice['row']
        if choice['record']:
            changes.append(choice['record'])
    for i,row in enumerate(result['cross_sections']):
        level=water.get(row['rs'])
        if level is not None and min(row['elevation_ft'][0],row['elevation_ft'][-1])<=level:
            unresolved.append(dict(rs=row['rs'],code='NO_COMPATIBLE_DRY_EXTENT',action='Inspect the bounded candidates, flow paths and available DEM coverage.'))
    return dict(geometry=result,changes=changes,unresolved=unresolved,
                search=dict(method='joint_section_direction_coverage_v1',angles_deg=ANGLES if allow_rotation else [0.],maximum_width_ft=maximum,
                    max_search_nodes=MAX_SEARCH_NODES,attempts=attempts,components=search,
                    limitation='Coverage and intersection screening using prior/reference water levels. Rotated sections are resampled and need new banks and hydraulic calculation.'))
