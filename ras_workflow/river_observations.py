"""Match field measurements to a solved river without changing the design profile."""
import csv
import io
import math
from datetime import date

import numpy as np
from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError, ProjError

from .common import ROOT, intact, item, read, save, unique_id
from .revision_inputs import bound_inputs, station_key
from .result_atlas import native_rows
from .qa_review import load_summary

COLUMNS = ('event','date','role','kind','x','y','horizontal_crs','elevation','unit','vertical_datum',
           'gage_zero','flow','flow_unit','vertical_uncertainty','horizontal_uncertainty_m','source')
UNITS={'ft':1.,'m':1/.3048,'us_survey_ft':(1200/3937)/.3048}
FLOWS={'cfs':1.,'m3/s':1/.3048**3}
ROLES={'calibration','holdout','context','boundary'}
KINDS={'stage','gage_height','bed','boundary_stage'}
MAX_MATCH_M=5.


def number(row,key):
    try:
        value=float(row.get(key,''))
        return value if math.isfinite(value) else None
    except (TypeError,ValueError):
        return None


def datum(s):
    name=''.join(c for c in (s or '').upper() if c.isalnum())
    return {'NAVD1988':'NAVD88','NGVD1929':'NGVD29'}.get(name,name)


def locate(row,geometry):
    x,y=number(row,'x'),number(row,'y')
    if x is None or y is None or not row.get('horizontal_crs'):
        return None,['NEED_COORDINATES_AND_CRS']
    try:
        crs=CRS.from_user_input(geometry['horizontal_crs'])
        source=CRS.from_user_input(row['horizontal_crs'])
        if source.is_geographic and not (-180<=x<=180 and -90<=y<=90):return None,['INVALID_COORDINATES']
        xy=np.asarray(Transformer.from_crs(source,crs,always_xy=True).transform(x,y,errcheck=True))
    except (CRSError,ProjError,ValueError):
        return None,['INVALID_COORDINATES_OR_CRS']
    hits=[]
    for xs in geometry['cross_sections']:
        pts=np.asarray(xs['cutline_xy'],float)
        lengths=np.linalg.norm(np.diff(pts,axis=0),axis=1)
        total=sum(lengths)
        if total<=0:continue
        start=0.
        for p,q,length in zip(pts,pts[1:],lengths):
            if length<=0:continue
            fraction=float(np.dot(xy-p,q-p)/length**2)
            clipped=float(np.clip(fraction,0.,1.))
            distance=float(np.linalg.norm(xy-p-clipped*(q-p)))*crs.axis_info[0].unit_conversion_factor
            xs_station=xs['station_ft'][0]+(start+clipped*length)/total*(xs['station_ft'][-1]-xs['station_ft'][0])
            hits.append((distance,station_key(xs['rs']),xs_station,0.<=fraction<=1.))
            start+=length
    if not hits:return None,['NO_GEOMETRY']
    hits.sort()
    dist,rs,station,on_segment=hits[0]
    details=dict(rs=rs,distance_m=dist,station_ft=station)
    uncertainty=number(row,'horizontal_uncertainty_m')
    if uncertainty is not None and uncertainty<0:return details,['INVALID_POSITION_UNCERTAINTY']
    reasons=[]
    if (row.get('horizontal_uncertainty_m') and uncertainty is None) or (uncertainty or 0)>MAX_MATCH_M:
        reasons.append('POSITION_UNCERTAINTY_TOO_LARGE')
    if dist+(uncertainty or 0)>MAX_MATCH_M or not on_segment:reasons.append('OUTSIDE_SECTION_TOLERANCE')
    if not reasons and any(other!=rs and d<=MAX_MATCH_M+(uncertainty or 0) for d,other,_,_ in hits):
        reasons.append('MULTIPLE_NEARBY_SECTIONS')
    return details,reasons


def screen(records,summary,event=None):
    _,geom,_=bound_inputs(summary)
    hyd=summary['hydraulics']
    profiles={p['profile_id']:p for p in hyd['profiles']}
    native={(r['profile'],station_key(r['rs'])):r for r in native_rows(hyd)}
    results=[]
    for idx,row in enumerate(records,2):
        location,issues=locate(row,geom)
        kind,role=row.get('kind'),row.get('role')
        if kind not in KINDS:issues.append('NEED_MEASUREMENT_KIND')
        if role not in ROLES:issues.append('NEED_OBSERVATION_ROLE')
        if not row.get('source'):issues.append('NEED_SOURCE')
        try:date.fromisoformat(row.get('date',''))
        except ValueError:issues.append('NEED_ISO_DATE')
        if not row.get('event'):issues.append('NEED_EVENT_ID')
        factor=UNITS.get(row.get('unit'))
        elev=number(row,'elevation')
        if factor is None or elev is None:issues.append('NEED_ELEVATION_AND_UNIT')
        if kind=='gage_height':
            zero=number(row,'gage_zero')
            if zero is None:
                issues.append('NEED_GAGE_ZERO');elev=None
            elif elev is not None:elev+=zero
        z=elev*factor if elev is not None and factor else None
        if datum(row.get('vertical_datum')) in ('','UNKNOWN','UNSPECIFIED','LOCAL','NONE') or datum(row.get('vertical_datum'))!=datum(geom['vertical_datum']):
            issues.append('VERTICAL_DATUM_MISMATCH')
        uncertainty=number(row,'vertical_uncertainty')
        if row.get('vertical_uncertainty') and (uncertainty is None or uncertainty<0):issues.append('INVALID_VERTICAL_UNCERTAINTY')
        q=number(row,'flow');qfactor=FLOWS.get(row.get('flow_unit'))
        q=q*qfactor if q is not None and qfactor and q>0 else None
        if kind!='bed' and q is None:issues.append('NEED_EVENT_DISCHARGE')
        end=station_key(geom['cross_sections'][-1]['rs'])
        if (kind=='boundary_stage' or role=='boundary') and (not location or location['rs']!=end or kind not in ('boundary_stage','stage','gage_height') or role!='boundary'):
            issues.append('BOUNDARY_REQUIRES_DOWNSTREAM_OBSERVATION')
        physical=list(issues)
        event_match=event and event['event']==row.get('event') and event['date']==row.get('date') and event['profile'] in profiles
        if kind!='bed':
            if not event_match:issues.append('NO_MATCHED_EVENT_RUN')
            elif q is not None and abs(profiles[event['profile']]['flow_cfs']-q)>max(1e-5,1e-7*q):issues.append('EVENT_DISCHARGE_MISMATCH')
        if kind!='bed' and event_match and event.get('downstream_ft') is not None and location and location['rs']==end and role!='boundary':
            issues.append('DOWNSTREAM_STAGE_USED_AS_BOUNDARY')
        calc=None
        if not issues and location:
            profile=event['profile'] if event_match else next(iter(profiles))
            n=native[profile,location['rs']]
            calc=float(np.interp(location['station_ft'],n['station_ft'],n['elevation_ft'])) if kind=='bed' else n['wse_ft']
        results.append(dict(line=idx,event=row.get('event'),date=row.get('date'),kind=kind,role=role,source=row.get('source'),
            raw_elevation=row.get('elevation'),raw_unit=row.get('unit'),gage_zero=row.get('gage_zero'),
            location=location,observed_ft=z,observed_datum=row.get('vertical_datum'),model_datum=geom['vertical_datum'],
            flow_cfs=q,uncertainty_ft=uncertainty*factor if uncertainty is not None and factor else None,
            issues=issues,event_eligible=not physical and kind!='bed' and role!='context',
            model_ft=calc,residual_ft=calc-z if calc is not None and z is not None and role not in ('boundary','context') else None))
    return results


def holdout_stages(rows):
    measured=[row for row in rows if row.get('role')=='holdout'
              and row.get('kind') in ('stage','gage_height') and not row.get('issues')
              and number(row,'residual_ft') is not None]
    missing=[r for r in measured if (number(r,'uncertainty_ft') or 0)<=0]
    exceeds=[r for r in measured if (number(r,'uncertainty_ft') or 0)>0
             and abs(r['residual_ft'])>r['uncertainty_ft']]
    return measured,missing,exceeds


def parse(text):
    if not isinstance(text,str) or len(text)>2_000_000:raise ValueError('Use a UTF-8 CSV up to 2 MB')
    reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    if set(reader.fieldnames or [])!=set(COLUMNS) or len(reader.fieldnames)!=len(COLUMNS):
        raise ValueError('Use the supplied CSV header / 请使用下载模板的完整表头')
    records=[]
    for row in reader:
        if None in row or any(v is None for v in row.values()):raise ValueError(f'Malformed CSV at line {reader.line_num}')
        records.append({k:v.strip() for k,v in row.items()})
        if len(records)>2000:raise ValueError('Maximum 2,000 observations per CSV')
    if not records:raise ValueError('The CSV has no data rows / 表内没有观测记录')
    return records


def import_table(key,body):
    from . import app_core as core
    m=core.model(key);core.require_idle(m)
    if body.get('revision')!=m['revision'] or not m.get('summary') or m['summary']['sha256']!=body.get('summary_hash') or not intact([m['summary']]):
        raise ValueError('Reopen the current computed river result')
    _,summary,hyd=load_summary(ROOT/m['summary']['path'])
    if hyd.get('model_type')!='river':raise ValueError('River observations require a computed river')
    text=body['csv'];rows=screen(parse(text),summary)
    folder=core.folder(key)/'observations'/unique_id()
    folder.mkdir(parents=True)
    path=folder/'observations.csv';path.write_bytes(text.encode('utf-8'))
    result=dict(schema_version='river_observations_1',summary=m['summary'],source=item(path),rows=rows,match_tolerance_m=MAX_MATCH_M)
    save(folder/'screen.json',result)
    m['river_observations']=item(folder/'screen.json');m['exports_need_refresh']=True
    m['revision']+=1;core.persist(m,'IMPORT_RIVER_OBSERVATIONS',dict(rows=len(rows)))
    return result


def current(model):
    ref=model.get('river_observations')
    if ref and intact([ref]):
        result=read(ROOT/ref['path'])
        if result['summary']==model.get('summary') and intact([result['source'],result['summary']]):return result
    return None
