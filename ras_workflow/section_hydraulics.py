"""Inspected horizontal roughness and normal edge ineffective-area layouts.

Native cards and HDF names observed in the public Phelps model. Permanent or
multiple interior ineffective blocks require a separately validated adapter.
"""
from .common import finite

def manning(section,scenario):
    return section.get('manning_segments') or [[section['station_ft'][0],scenario['overbank_n']],
        [section['bank_stations_ft'][0],scenario['channel_n']],[section['bank_stations_ft'][1],scenario['overbank_n']]]

def manning_cards(roughness, fixed):
    """Write station and n at their respective fixed-width precision."""
    rows = []
    for station, coefficient in roughness:
        if not finite(coefficient) or not 0 < coefficient < 1:
            raise ValueError('Manning n must be finite and between zero and one')
        number = f'{coefficient:.7f}'.lstrip('0')
        if len(number) > 8 or not 0 < float(number) < 1:
            raise ValueError('Manning n cannot be represented in the native eight-character field')
        rows.append(fixed([station]).rstrip('\n') + number.rjust(8) + fixed([0]).rstrip('\n'))
    return '\n'.join(''.join(rows[i:i+3]) for i in range(0, len(rows), 3)) + '\n'


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
    # Normal edge cards use three fields per side. An absent limit and
    # elevation must stay blank, including the first field on the right.
    left = section.get('ineffective_left')
    right = section.get('ineffective_right')
    values = [0., left[0], left[1]] if left else [0., None, None]
    values.extend([right[0], 0., right[1]] if right else [None, 0., None])
    row=''.join(' '*8 if v is None else fixed([v]).rstrip('\n') for v in values)
    return '#XS Ineff= 2 , 0\n'+row+'\nPermanent Ineff=\n       F       F\n'

def road_profiles(road):
    up=list(map(list,zip(road['station_ft'],road['elevation_ft'])))
    down=list(map(list,zip(road['downstream_station_ft'],road['downstream_elevation_ft']))) if road.get('profile_mode','shared')=='distinct' else up
    return dict(upstream=up,downstream=down)
