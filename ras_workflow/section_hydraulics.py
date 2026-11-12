"""Inspected horizontal roughness and normal edge ineffective-area layouts.

Native cards and HDF names observed in the public Phelps model. Permanent or
multiple interior ineffective blocks require a separately validated adapter.
"""
from .common import finite

def manning(section,scenario):
    return section.get('manning_segments') or [[section['station_ft'][0],scenario['overbank_n']],
        [section['bank_stations_ft'][0],scenario['channel_n']],[section['bank_stations_ft'][1],scenario['overbank_n']]]

def ineffective(section):
    rows=[]
    for side in ['left','right']:
        v=section.get('ineffective_'+side)
        if v:
            rows.append([section['station_ft'][0] if side=='left' else v[0],v[0] if side=='left' else section['station_ft'][-1],v[1],0])
    return rows

def errors(section):
    result=[];a=section.get('station_ft') or []
    if not a or not all(finite(v) for v in a):return result
    rough=section.get('manning_segments')
    if rough is not None and rough!=[]:
        if not isinstance(rough,list) or not all(isinstance(v,list) and len(v)==2 and all(finite(x) for x in v) and 0<round(v[1],3)<1 for v in rough):result.append('Manning subdivisions need station,n pairs with 0<n<1 at native precision')
        elif rough[0][0]!=a[0] or any(not a[0]<=v[0]<a[-1] for v in rough) or any(round(v[0],3)>=round(w[0],3) for v,w in zip(rough,rough[1:])):result.append('Manning subdivisions must start at the left endpoint and increase inside the section at native precision')
    edges={}
    for side in ['left','right']:
        v=section.get('ineffective_'+side)
        if v is not None and v!=[]:
            if not isinstance(v,list) or len(v)!=2 or not all(finite(x) for x in v) or not a[0]<v[0]<a[-1]:result.append(side+' ineffective area requires an interior limit station and activation elevation')
            else:edges[side]=v[0]
    if len(edges)==2 and edges['left']>=edges['right']:result.append('Left/right ineffective areas overlap or eliminate the active channel')
    return result

def cards(section,fixed):
    if not any(section.get('ineffective_'+side) for side in ['left','right']):return ''
    values=[]
    for side in ['left','right']:
        v=section.get('ineffective_'+side)
        values.extend(([0.,v[0],v[1]] if side=='left' else [v[0],0.,v[1]]) if v else [0.,None,None])
    row=''.join(' '*8 if v is None else fixed([v]).rstrip('\n') for v in values)
    return '#XS Ineff= 2 , 0\n'+row+'\nPermanent Ineff=\n       F       F\n'

def road_profiles(road):
    up=list(map(list,zip(road['station_ft'],road['elevation_ft'])))
    down=list(map(list,zip(road['downstream_station_ft'],road['downstream_elevation_ft']))) if road.get('profile_mode','shared')=='distinct' else up
    return dict(upstream=up,downstream=down)
