"""Interpret one original survey table against the editable or solved reach."""
import csv
import io
import json
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np
from pyproj import CRS, Transformer
from .intake_boundary import iso
from .river_observations import datum, number, locate, MAX_MATCH_M, UNITS, FLOWS
from .revision_inputs import station_key

ALIASES = {
    'x': ('x','easting','east','longitude','lon'),
    'y': ('y','northing','north','latitude','lat'),
    'level': ('measwse','wse','watersurfaceelevation','stageelevation','elevation','z','gageheight','gageheightft','gageheightm','stageft','stagem'),
    'group': ('group','barrelgroup','culvertgroup'), 'end': ('end','side','endpoint'),
    'level_in': ('inletinvert','usinvert','inletinvertft','usinvertft'),
    'level_out': ('outletinvert','dsinvert','outletinvertft','dsinvertft'),
    'profile': ('profile','profileid'), 'event': ('event','eventid'), 'date': ('date','eventdate','measurementdate'),
    'flow': ('flow','discharge','q','flowcfs','flowm3s'), 'flow_unit': ('flowunit','dischargeunit'),
    'unit': ('unit','verticalunit','elevationunit'), 'crs': ('crs','horizontalcrs'),
    'datum': ('datum','verticaldatum'), 'uncertainty': ('verticaluncertainty','elevationuncertainty'),
    'station': ('stationid','siteid','siteno','monitoringlocationid')
}

def normal(s):
    return re.sub(r'[^a-z0-9]', '', s.casefold())

def gage_table(data):
    payload=json.loads(data.decode('utf-8-sig'))
    if not isinstance(payload,dict) or payload.get('type')!='FeatureCollection':
        raise ValueError('Select a USGS field-measurement GeoJSON / 请选择 USGS 现场测验 GeoJSON')
    features=payload.get('features')
    if not isinstance(features,list) or len(features)>10000:raise ValueError('Select up to 10,000 USGS features')
    flows={};stages=[]
    for index,feature in enumerate(features,1):
        p=feature.get('properties') or {}
        key=(p.get('monitoring_location_id'),p.get('field_visit_id'))
        if not all(key):continue
        if p.get('reading_type')=='Discharge':
            flows.setdefault(key,[]).append(p)
        elif p.get('reading_type')=='MeanGageHeight':
            xy=(feature.get('geometry') or {}).get('coordinates') or []
            if len(xy)==2:stages.append((index,key,p,xy))
    normalized=[]
    for index,(station,visit),p,xy in stages:
        q=flows.get((station,visit),[])
        units={'ft^3/s':'cfs','ft3/s':'cfs','cfs':'cfs','m^3/s':'m3/s','m3/s':'m3/s'}
        normalized.append((index,dict(x=xy[0],y=xy[1],level=p.get('value'),station=station,
            date=str(p.get('time') or '')[:10],event=visit,crs='EPSG:4326',unit=p.get('unit_of_measure'),
            flow=q[0].get('value') if len(q)==1 else '',flow_unit=units.get(q[0].get('unit_of_measure'),'') if len(q)==1 else '')))
    if not normalized:raise ValueError('No mean gage-height visits with coordinates / 没有带坐标的实测平均水尺读数')
    return normalized


def parse(data, filename, overrides):
    if not isinstance(overrides,dict) or set(overrides)-ALIASES.keys():
        raise ValueError('Unknown column mapping / 不支持的列名映射')
    if Path(filename).suffix.lower() not in ('.csv','.tsv','.txt','.json','.geojson') or not 0<len(data)<=2_000_000:
        raise ValueError('Select a UTF-8 CSV or tab-separated file under 2 MB / 请选择 2 MB 以内的 UTF-8 测量表')
    if Path(filename).suffix.lower() in ('.json','.geojson'):
        rows=gage_table(data)
        headers=list(rows[0][1]);columns={k:k if k in headers else '' for k in ALIASES}
        return headers,columns,rows
    text=data.decode('utf-8-sig')
    sep='\t' if '\t' in text.partition('\n')[0] else ','
    reader=csv.DictReader(io.StringIO(text,newline=''),delimiter=sep,strict=True)
    headers=reader.fieldnames or []
    if not 1<=len(headers)<=80 or len(set(headers))!=len(headers) or any(not k.strip() for k in headers):
        raise ValueError('Use unique nonempty column headings / 请使用非空且唯一的表头')
    mapping={}
    for key,aliases in ALIASES.items():
        hits=[h for h in headers if normal(h) in aliases]
        value=overrides.get(key,hits[0] if len(hits)==1 else '')
        if value and value not in headers:raise ValueError('Column no longer present: '+str(value))
        mapping[key]=value
    used=[v for v in mapping.values() if v]
    if len(used)!=len(set(used)):raise ValueError('Map each column once / 一列只能指定一种含义')
    rows=[]
    for row in reader:
        if None in row or None in row.values():raise ValueError(f'Incorrect number of columns / 列数异常 · {reader.line_num}')
        rows.append((reader.line_num,{k:row[h].strip() for k,h in mapping.items() if h}))
        if len(rows)>10000:raise ValueError('Limit: 10,000 measurement rows / 最多一万行')
    if not rows:raise ValueError('No measurement rows / 表中没有数据行')
    return headers,mapping,rows

def file_date(name):
    match=re.search(r'(?<!\d)(20\d\d|19\d\d)[-_]?(\d\d)[-_]?(\d\d)(?!\d)',name)
    return iso('-'.join(match.groups())) if match else None

def suggestions(rows, mapping, filename, profiles):
    out={}
    for key in ('profile','event','date','flow','flow_unit','unit','crs','datum','uncertainty'):
        values={row.get(key) for _,row in rows if row.get(key)}
        if len(values)==1:out[key]=values.pop()
    if len(profiles)==1:
        p=profiles[0]
        out.setdefault('profile',p['id'])
        if 'flow' not in out and 'flow_unit' not in out and p.get('flow_cfs') is not None:
            out.update(flow=p['flow_cfs'],flow_unit='cfs')
    if 'date' not in out and file_date(filename):out['date']=file_date(filename)
    out.setdefault('event',out.get('profile',''))
    # An undocumented measurement datum/CRS stays blank even when the model has one.
    if 'unit' not in out:
        levels=[normal(mapping[k]) for k in ('level','level_in','level_out') if mapping[k]]
        if levels and all(h.endswith('ft') for h in levels):out['unit']='ft'
        elif levels and all(h.endswith('m') for h in levels):out['unit']='m'
    return out

def metadata(row, settings):
    return {k:row.get(k) or settings.get(k,'') for k in
            ('profile','event','date','flow','flow_unit','crs','datum','unit','uncertainty')}

def checks(meta,geometry,profiles,stage):
    issues=[]
    vertical=datum(str(meta['datum']))
    if not vertical or vertical in ('UNKNOWN','LOCAL','UNSPECIFIED','UNREVIEWED','NONE') or vertical!=datum(geometry.get('vertical_datum')):
        issues.append('DATUM_MISMATCH')
    if meta['unit'] not in UNITS:issues.append('UNIT_REQUIRED')
    if stage:
        if not iso(meta['date']) or not meta['event']:issues.append('EVENT_REQUIRED')
        p=next((p for p in profiles if p['id']==meta['profile']),None)
        q=number(meta,'flow');factor=FLOWS.get(meta['flow_unit'])
        if not p or not p.get('flow_cfs') or not factor or q is None or q<=0 or not math.isclose(q*factor,p['flow_cfs'],rel_tol=1e-7,abs_tol=1e-5):
            issues.append('DISCHARGE_MISMATCH')
        if meta['uncertainty'] not in ('',None) and (number(meta,'uncertainty') or 0)<=0:issues.append('UNCERTAINTY_INVALID')
    return issues

def invert_rows(rows,settings,geom,profiles):
    groups=(geom.get('structure') or {}).get('groups',[])
    result=[];keys=Counter()
    for line,row in rows:
        m=metadata(row,settings)
        index=row.get('group') or ('1' if len(groups)==1 else '')
        sides={'level_in':'us','level_out':'ds'}
        mixed_columns=bool(row.get('level') and (row.get('level_in') or row.get('level_out')))
        if row.get('level') and not mixed_columns:
            sides={'level':{'inlet':'us','outlet':'ds','upstream':'us','downstream':'ds','us':'us','ds':'ds'}.get(row.get('end','').lower())}
        for col,side in sides.items():
            if not row.get(col):continue
            issues=checks(m,geom,profiles,False);target=None
            if mixed_columns:issues.append('AMBIGUOUS_COLUMNS')
            if side and index.isdigit() and 1<=int(index)<=len(groups):
                target=f'g.structure.groups.{int(index)-1}.{side}_invert_ft';keys[target]+=1
            else:issues.append('GROUP_OR_END_REQUIRED')
            val=number(row,col)
            if val is None:issues.append('INVALID_VALUE')
            result.append(dict(line=line,role='invert',target=target,value=val,unit=m['unit'],datum=m['datum'],
                               value_ft=val*UNITS[m['unit']] if not issues else None,issues=issues))
    for entry in result:
        if keys[entry['target']]>1:entry['issues'].append('DUPLICATE_TARGET')
    represented={r['target'] for r in result if not r['issues']}
    missing=[f'g.structure.groups.{i}.{side}_invert_ft' for i in range(len(groups)) for side in ('us','ds')
             if f'g.structure.groups.{i}.{side}_invert_ft' not in represented]
    return result,missing

def stage_rows(rows,settings,geom,profiles,mapping,mode):
    cuts=geom.get('cross_sections') or []
    if not cuts or any(not c.get('center_xy') or not c.get('cutline_xy') for c in cuts):
        raise ValueError('First locate the cross sections on the map / 请先定位河段断面')
    model_crs=CRS.from_user_input(geom['horizontal_crs'])
    if not model_crs.is_projected:raise ValueError('A projected model CRS is required / 模型需要投影坐标系')
    centers=np.array([c['center_xy'] for c in cuts]);scale=model_crs.axis_info[0].unit_conversion_factor
    targets=[station_key(c['rs']) for c in cuts];end=station_key(min(float(c['rs']) for c in cuts))
    transforms={};located={};result=[];outside=[];locations=Counter()
    for line,row in rows:
        m=metadata(row,settings)
        if mode=='gage' and row.get('station'):
            # A missing paired discharge cannot inherit the project's design flow.
            m.update(flow=row.get('flow',''),flow_unit=row.get('flow_unit',''))
        x,y,z=(number(row,k) for k in ('x','y','level'))
        info=dict(line=line,x=x,y=y,value=z,unit=m['unit'],issues=[],role='context',meta=m)
        if None in (x,y,z):
            info['issues'].append('INVALID_COORDINATES_OR_LEVEL');result.append(info);continue
        try:
            if m['crs'] not in transforms:transforms[m['crs']]=Transformer.from_crs(m['crs'],model_crs,always_xy=True)
            xy=transforms[m['crs']].transform(x,y,errcheck=True)
        except (TypeError,ValueError,RuntimeError):
            info['issues'].append('CRS_REQUIRED');result.append(info);continue
        locations[(xy,m['profile'],m['date'])]+=1
        distances=np.linalg.norm(centers-xy,axis=1)*scale
        i=int(distances.argmin());dist=float(distances[i]);rs=targets[i]
        info.update(xy=list(xy),rs=rs,distance_m=dist)
        # Longitudinal traces can contain many samples per section. Never average upstream/downstream marks.
        if dist>MAX_MATCH_M:
            if mode=='gage' or row.get('station') or 'gageheight' in normal(mapping['level']):
                info['issues']=checks(m,geom,profiles,True)+['GAGE_REQUIRES_REGISTER','OUTSIDE_SECTION_CENTER']
                result.append(info)
            else:outside.append(info)
            continue
        match,problems=locate(dict(x=x,y=y,horizontal_crs=m['crs']),geom)
        info['issues']=checks(m,geom,profiles,True)+problems
        if not match or match['rs']!=rs:info['issues'].append('AMBIGUOUS_SECTION')
        if mode=='gage' or row.get('station') or 'gageheight' in normal(mapping['level']):
            info['issues'].append('GAGE_REQUIRES_REGISTER')
        info['role']='outlet' if rs==end else 'interior'
        key=(m['profile'],m['event'],m['date'],rs)
        located.setdefault(key,[]).append(info)
    for choices in located.values():
        choices.sort(key=lambda entry:entry['distance_m'])
        first=choices[0]
        for e in choices:
            if locations[(tuple(e['xy']),e['meta']['profile'],e['meta']['date'])]>1:e['issues'].append('DUPLICATE_POINT')
        if any('DUPLICATE_POINT' in e['issues'] for e in choices):first['issues'].append('CHECK_REPEATED_ROWS')
        if len(choices)>1 and abs(choices[1]['distance_m']-first['distance_m'])<.001:first['issues'].append('AMBIGUOUS_NEAREST')
        first['nearby_lines']=[e['line'] for e in choices[1:]]
        result.append(first)
    return sorted(result,key=lambda e:e['line']),outside
