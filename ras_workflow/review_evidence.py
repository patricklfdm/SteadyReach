"""Find public field evidence for the physical questions raised by this edition."""
import csv
import io
from html import unescape
import json
import math
import re
from urllib.parse import urlencode
from xml.etree import ElementTree

from pyproj import CRS, Transformer
import numpy as np
from .public_reach import project as project_point
from .geometry_qa import intersects

from .common import ROOT, finite, intact, item, read, save, unique_id, utc
from .result_guidance import text
from .revision_inputs import bound_inputs, station_key
from .source_fetch import Download

from .usgs_water import HOST as WATER, pages, query
CATALOG = 'https://www.sciencebase.gov/catalog/'


def rating(raw, station, discharges):
    lines=raw.decode('utf-8-sig').splitlines()
    if not any(re.search(r'//STATION AGENCY="USGS\s*"', s) and re.search(r'\bNUMBER="'+re.escape(station)+r'\s*"', s) for s in lines):
        raise ValueError('USGS rating identifies a different station')
    if not any('Discharge (ft^3/s)' in s and 'RATING_DEP' in s for s in lines):
        raise ValueError('Rating discharge unit not verified')
    if not any('Gage height (ft)' in s and 'RATING_INDEP' in s for s in lines):
        raise ValueError('Rating stage unit not verified')
    reader=csv.DictReader([line for line in lines if line and not line.startswith('#')],delimiter='\t')
    points=[]
    for row in reader:
        try:q,h=float(row['DEP']),float(row['INDEP'])
        except (TypeError,ValueError,KeyError):continue
        if math.isfinite(q) and math.isfinite(h):points.append((q,h))
    if not points:raise ValueError('No stage-discharge rating rows')
    flows=[q for q,_ in points]
    low,high=min(flows),max(flows)
    brackets={}
    # Keep the two tabulated bounds. Rounded discharges can have several gage heights.
    if all(b>=a for a,b in zip(flows,flows[1:])) and all(b[1]>=a[1] for a,b in zip(points,points[1:])):
        for profile,q in discharges.items():
            if low<=q<=high:
                lo=max(x for x in flows if x<=q)
                hi=min(x for x in flows if x>=q)
                heights=[h for value,h in points if lo<=value<=hi]
                brackets[profile]=[min(heights),max(heights)]
    return dict(min_cfs=low,max_cfs=high,stage_brackets_ft=brackets,profile_in_range={k:low<=q<=high for k,q in discharges.items()},
                validity=[s.lstrip('# /') for s in lines if 'RATING_DATETIME' in s or 'RATING REMARKS' in s])


def gage_manuscript(raw, station):
    """Return the USGS station's gage statement for human date and datum review."""
    try:
        manuscript = ElementTree.fromstring(raw).find('Manuscript')
    except ElementTree.ParseError as exc:
        raise ValueError('USGS station manuscript is not valid XML') from exc
    if (manuscript is None or manuscript.findtext('agency_cd') != 'USGS'
            or manuscript.findtext('site_no') != station):
        raise ValueError('USGS manuscript does not identify the requested station')
    records = []
    for element in manuscript.findall('Element'):
        if (element.findtext('name') or '').strip().upper() != 'GAGE':
            continue
        info = element.find('info')
        if info is not None:
            statement = unescape(re.sub(r'</?[a-zA-Z][^>]*>', ' ', ' '.join(info.itertext())))
            statement = ' '.join(statement.split())
            if statement:
                records.append(dict(kind='gage_history', station=station, statement=statement))
    return records


def boundary_evidence(records, discharges, model_datum):
    """Screen public ratings at their station and existing screened field observations."""
    from .river_observations import MAX_MATCH_M, datum
    gages={r['station']:r for r in records if r['kind']=='gage'}
    histories={r['station']:r for r in records if r['kind']=='gage_history'}
    output=[]
    for rating_row in (r for r in records if r['kind']=='rating'):
        station=rating_row['station']
        gage=gages.get(station)
        if not gage:continue
        history=histories.get(station,{})
        # Historical moves, multiple zeros and ambiguous prose require review.
        zero=re.fullmatch(r'(?:[^.]*recorder[^.]*\.\s*)?Datum of gage is ([\d,]+(?:\.\d+)?) ft above (NAVD of 1988|NGVD of 1929)\.',history.get('statement',''),re.I)
        zero_ft=float(zero[1].replace(',','')) if zero else None
        zero_datum=('NAVD88' if 'NAVD' in zero[2].upper() else 'NGVD29') if zero else None
        period=next((re.search(r'BEGIN=(\d{8})\d*.*? END=([\d-]+)',v) for v in rating_row['validity'] if 'BEGIN=' in v),None)
        def day(raw):
            return raw[:4]+'-'+raw[4:6]+'-'+raw[6:8] if raw and raw[:8].isdigit() else None
        start,stop=(day(period[1]),day(period[2])) if period else (None,None)
        dates=sorted({r['date'][:10] for r in records if r['kind']=='peak' and r['station']==station and r.get('date')})
        outside=[d for d in dates if (start and d<start) or (stop and d>stop)]
        for profile,q in discharges.items():
            in_range=rating_row['profile_in_range'].get(profile)
            stages=rating_row.get('stage_brackets_ft',{}).get(profile)
            issues=[]
            if not in_range:issues.append('FLOW_OUTSIDE_RATING')
            elif not stages:issues.append('AMBIGUOUS_STAGE')
            if not zero or zero_datum!=datum(model_datum):issues.append('CHECK_GAGE_ZERO')
            if zero and gage.get('vertical_datum') and datum(gage['vertical_datum'])!=zero_datum:issues.append('CONFLICTING_DATUM_METADATA')
            if gage['distance_to_boundary_m']>MAX_MATCH_M:issues.append('BOUNDARY_TRANSFER_REQUIRED')
            issues.extend(['CONFIRM_RATING_AND_ZERO_DATE','NEED_BOUNDARY_UNCERTAINTY'])
            output.append(dict(station=station,profile=profile,flow_cfs=q,range_cfs=[rating_row['min_cfs'],rating_row['max_cfs']],
                status='OUTSIDE_RANGE' if not in_range else 'STATION_CONTEXT',issues=issues,
                station_wse_bracket_ft=[round(zero_ft+h,4) for h in stages] if stages and zero else None,
                station_datum=zero_datum,distance_m=gage['distance_to_boundary_m'],rating_start=start,rating_end=stop,
                historical_dates_outside=outside,sources=[r['source'] for r in (gage,rating_row,history) if r.get('source')]))
    return output


def observation_candidates(evidence,directory):
    """Export stage records with provenance. Leave unmatched flows and gage zero open."""
    from .river_observations import COLUMNS
    gages={r['station']:r for r in evidence if r['kind']=='gage'}
    peaks=[r for r in evidence if r['kind']=='peak']
    rows=[]
    for stage in peaks:
        if stage['parameter']!='00065' or stage['unit']!='ft' or stage['station'] not in gages:continue
        loc=gages[stage['station']]
        matches=[r for r in peaks if r['station']==stage['station'] and r['date']==stage['date']
                 and r['parameter']=='00060' and r['unit'] in ('ft^3/s','ft3/s') and not r['qualifier']]
        rows.append(dict(event='USGS-'+stage['station']+'-'+stage['date'],date=stage['date'],role='context',kind='gage_height',
            x=loc['longitude'],y=loc['latitude'],horizontal_crs='EPSG:4326',elevation=stage['value'],unit='ft',
            vertical_datum=loc.get('vertical_datum'),flow=matches[0]['value'] if len(matches)==1 and not stage['qualifier'] else '',
            flow_unit='cfs',source=stage['url']))
    if not rows:return None
    path=directory/'Observation_candidates.csv'
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=COLUMNS);writer.writeheader();writer.writerows(rows)
    return item(path)


def search(key,body):
    from . import app_core as core
    from .result_guidance import collect
    from .section_context import public_lines
    from .river_observations import datum
    model=core.model(key)
    result=collect(key,dict(summary_hash=body.get('summary_hash'),include_assessment=True))
    a=result['assessment']
    if not a.get('run_id') or model.get('model_type')!='river':raise ValueError('Choose a verified river result')
    folder=core.folder(key)/'field_search'
    pointer=folder/'latest.json'
    archived_queries={}
    if pointer.exists() and not body.get('refresh'):
        ref=read(pointer)
        if intact([ref]):
            previous=read(ROOT/ref['path'])
            if previous.get('summary')==model['summary']:
                archived_queries={(r['kind'],r.get('url')):(r['source'],r.get('retrieved_utc') or
                                  (previous.get('created_utc') if r.get('retrieval')!='ARCHIVED' else None)) for r in previous['searches']
                                  if r.get('url') and r.get('source') and r['status'] in ('CANDIDATES','NO_RECORDS')}
            if previous.get('schema_version')==6 and previous['assessment']==a['evidence_hash'] and intact(previous['sources']):return previous
    out=folder/unique_id();out.mkdir(parents=True)
    summary=read(ROOT/model['summary']['path'])
    _,geom,sources=bound_inputs(summary)
    cases=a['candidate_findings'];flags={r['code'] for r in a['findings']}
    rows={station_key(r['rs']):r for r in geom['cross_sections']}
    crs=CRS(geom['horizontal_crs'])
    to_geo=Transformer.from_crs(crs,4326,always_xy=True)
    project=Transformer.from_crs(4326,crs,always_xy=True)
    sections={rs:np.asarray(r['cutline_xy'],float) for rs,r in rows.items()}
    end=a['area']['stations'][-1]
    boundary=np.asarray(rows[end]['center_xy'],float)
    units=crs.axis_info[0].unit_conversion_factor
    evidence=[];requests=[];jobs=[]
    def field(topic,rs,where,need,decision):
        lon,lat=to_geo.transform(*where)
        jobs.append(dict(topic=topic,rs=rs,longitude=round(lon,7),latitude=round(lat,7),need=need,decision=decision))
    sides={case['parameter'].split('.')[1] for case in a['boundary_cases'] if case['affected']}
    coverage=next((f for f in a['findings'] if f['code']=='BOUNDARY_SCOPE'),None)
    if coverage:
        for missing in coverage['facts']['missing']:
            sides.update(s for s in ('upstream','downstream') if s in str(missing))
    if 'upstream' in sides:
        head=a['area']['stations'][0]
        field('upstream',head,rows[head]['center_xy'],text('Seek independent stage or control at the upstream limit.','查上游边界的独立水位或控制依据。'),
              text('Verify location, event discharge, datum and uncertainty.','核对位置、同期流量、高程基准和不确定度。'))
    if 'downstream' in sides:
        field('tailwater',end,boundary,text('Seek a stage-discharge relation, gage zero and tailwater at the downstream control.','查下游控制断面的水位流量关系、水尺零点与尾水记录。'),
              text('Confirm datum, flood date, flow range and transfer from the gage.','核实基准、洪水日期、适用流量及从测站到边界的水位传递。'))
    for finding in a['findings']:
        if finding['code']!='FIELD_RESIDUAL': continue
        for obs in finding['facts']['observations']:
            rs=(obs.get('location') or {}).get('rs')
            if rs not in rows: continue
            when=obs.get('date') or obs.get('event') or ''
            field('accuracy',rs,rows[rs]['center_xy'],text(f'Obtain the original survey record for {when}.',f'查找 {when} 的原始测量记录。'),
                  text('Identify measured versus interpolated points, vertical control and observation uncertainty.',
                       '核实实测点与插值点身份、垂直控制和测点不确定度。'))
    for row in cases:
        f=row['facts'];rs=f['station'];line=sections[rs];p=line[0 if f['side']=='L' else -1]
        field('opening',rs,p,text('Find embankment crest, road openings and the longitudinal flood route on this side.','查该侧路堤顶高程、通水开口及相邻断面的纵向过流路径。'),
              text('Confirm whether this floodplain carries flow when choosing the alternative.','选用该候选前判断漫滩是否参与输水。'))
    if cases and 'BOUNDARY_INFLUENCE' not in flags:jobs.sort(key=lambda row:row['topic']!='opening')
    if 'BED_BASIS' in flags or 'FIELD_SUPPORT' in flags:
        middle=a['area']['selected'][len(a['area']['selected'])//2]
        field('survey',middle,rows[middle]['center_xy'],text('Seek surveyed bed transects and independent flood marks with measured flow, datum and uncertainty.','查水下河床断面及独立洪痕的同期流量、高程基准与测量误差。'),
              text('Confirm survey coverage and reserve non-boundary marks from a separate flood.','确认测量覆盖范围，保留独立洪水的非边界测点。'))
    searcher=Download(limit=12_000_000,timeout=9)
    def request(kind,url,parse,paginate=False):
        def fetch(address):
            attempt=dict(kind=kind,url=address);requests.append(attempt)
            ref,received=archived_queries.get((kind,address),(None,None))
            if ref and intact([ref]):
                data=(ROOT/ref['path']).read_bytes()
                attempt.update(retrieval='ARCHIVED',retrieved_utc=received)
            else:
                data=searcher.get(address,limit=2_000_000)
                raw=out/(str(len(requests))+'_'+kind+'.dat');raw.write_bytes(data)
                ref=item(raw)
                attempt.update(retrieval='FETCHED',retrieved_utc=utc())
            sources.append(ref);attempt['source']=ref
            return data
        try:
            responses=pages(url,fetch) if paginate else [(url,fetch(url),None)]
            for address,data,_ in responses:
                attempt=requests[-1]
                records=parse(data)
                attempt.update(status='CANDIDATES' if records else 'NO_RECORDS',count=len(records))
                for entry in records:evidence.append(dict(**entry,source=attempt['source'],url=address))
        except (OSError,ValueError,KeyError,TypeError) as exc:
            if requests[-1].get('status'):
                requests.append(dict(kind=kind,url=url,status='PARTIAL',error=str(exc)))
            else:requests[-1].update(status='UNAVAILABLE',error=str(exc))
    def bbox(buffer):
        points=np.concatenate(list(sections.values()))
        x0,y0=points.min(axis=0)-buffer/units
        x1,y1=points.max(axis=0)+buffer/units
        return x0,y0,x1,y1
    x0,y0,x1,y1=bbox(1500)
    west,south,east,north=to_geo.transform_bounds(x0,y0,x1,y1)
    box=','.join(f'{v:.7f}' for v in (west,south,east,north))
    if jobs:
        def stations(data):
            out_rows=[]
            for f in json.loads(data)['features']:
                p=f['properties'];identity=p.get('id','')
                if not re.fullmatch(r'USGS-\d+',identity) or p.get('site_type_code')!='ST':continue
                xy=np.asarray(project.transform(*f['geometry']['coordinates'][:2]))
                distances={r:project_point(xy,line)[0] for r,line in sections.items()}
                rs=min(distances,key=distances.get)
                out_rows.append(dict(kind='gage',name=p.get('monitoring_location_name'),station=identity[5:],rs=rs,
                    distance_to_section_m=round(units*distances[rs],1),distance_to_boundary_m=round(units*np.linalg.norm(xy-boundary),1),
                    vertical_datum=p.get('vertical_datum'),datum_matches=bool(p.get('vertical_datum')) and datum(p['vertical_datum'])==datum(geom['vertical_datum']),
                    position_accuracy=p.get('horizontal_positional_accuracy'),longitude=f['geometry']['coordinates'][0],latitude=f['geometry']['coordinates'][1]))
            return sorted(out_rows,key=lambda r:r['distance_to_boundary_m'])
        request('gages',query('monitoring-locations',bbox=box,limit=200),stations,paginate=True)
        discharges={p['profile_id']:p['flow_cfs'] for p in summary['hydraulics']['profiles']}
        def rating_index(data):
            return [dict(kind='rating_index',station=f['properties']['monitoring_location_number'])
                    for f in json.loads(data)['features'] if f['id'].endswith('.exsa.rdb')]
        request('rating_index',WATER+'/stac/v0/collections/ratings/items?'+urlencode(dict(bbox=box,limit=100)),rating_index)
        rated={r['station'] for r in evidence if r['kind']=='rating_index'}
        gages=[r for r in evidence if r['kind']=='gage']
        ordered=sorted(gages,key=lambda g:(g['station'] not in rated,g['distance_to_boundary_m']))
        for gage in ordered[:4]:
            station=gage['station']
            manuscript_url='https://sims-manuscripts-bucket.s3.us-west-2.amazonaws.com/sims_USGS_'+station+'.xml'
            request('gage_history',manuscript_url,lambda data:gage_manuscript(data,station))
            request('rating',WATER+'/stac-files/ratings/USGS.'+station+'.exsa.rdb',
                    lambda data:[dict(kind='rating',station=station,**rating(data,station,discharges))])
            def peaks(data):
                features=json.loads(data)['features']
                return [dict(kind='peak',station=station,date=p['time'],parameter=p['parameter_code'],value=p['value'],unit=p['unit_of_measure'],qualifier=p.get('qualifier'))
                        for f in features for p in [f['properties']] if p['monitoring_location_id']=='USGS-'+station
                        and p['parameter_code'] in ('00060','00065')]
            request('peaks',query('peaks',monitoring_location_id='USGS-'+station,limit=500),peaks,paginate=True)
        for topic,term in [('survey','bathymetry'),('opening','crossing survey'),('accuracy','water surface profile')]:
            if not any(j['topic']==topic for j in jobs):continue
            shape=dict(type='Polygon',coordinates=[[[west,south],[east,south],[east,north],[west,north],[west,south]]])
            url=CATALOG+'items?'+urlencode({'format':'json','max':15,'q':term,'filter':'spatialQuery='+json.dumps(shape)})
            def records(data):
                return [dict(kind='catalog',topic=topic,name=r['title'],landing=CATALOG+'item/'+r['id'],dates=r.get('dates',[]),
                             extent=(r.get('spatial') or {}).get('boundingBox')) for r in json.loads(data)['items'] if r.get('title') and re.fullmatch('[0-9a-f]{24}',r.get('id',''))]
            request('catalog_'+topic,url,records)
        if cases:
            for layer in public_lines(folder,bbox(0),geom['horizontal_crs'],True):
                ref=layer.get('source')
                if ref:sources.append(ref)
                requests.append(dict(kind=layer['kind'],status=layer['status'],source=ref,error=layer.get('error')))
                for line in layer.get('lines',[]):
                    road=np.asarray(line['xy'],float)
                    for hit in (j for j in jobs if j['topic']=='opening'):
                        cut=sections[hit['rs']]
                        crossing=any(intersects(p,q,x,y) for p,q in zip(road,road[1:]) for x,y in zip(cut,cut[1:]))
                        distance=0. if crossing else units*min(min(project_point(p,road)[0] for p in cut),
                                                              min(project_point(p,cut)[0] for p in road))
                        if distance<=150:evidence.append(dict(kind='linear_context',name=line['name'],rs=hit['rs'],distance_to_section_m=round(distance,1),source=ref))
    for doc in model.get('attachments',[]):
        if intact([doc]):
            sources.append(doc);evidence.append(dict(kind='local_document',name=doc.get('original_name') or doc['path'],source=doc))
    screened=model.get('river_observations')
    if screened and intact([screened]):
        sources.append(screened)
        for row in read(ROOT/screened['path']).get('rows',[]):
            evidence.append(dict(kind='screened_observation',name=row.get('event'),date=row.get('date'),issues=row.get('issues'),source=screened))
    worksheet=observation_candidates(evidence,out)
    if worksheet:sources.append(worksheet)
    discharges={p['profile_id']:p['flow_cfs'] for p in summary['hydraulics']['profiles']}
    packet=dict(schema_version=6,boundary_evidence=boundary_evidence(evidence,discharges,geom['vertical_datum']),worksheet=worksheet,summary=model['summary'],assessment=a['evidence_hash'],created_utc=utc(),model_datum=geom['vertical_datum'],
                field_requests=jobs,searches=requests,candidates=evidence,sources=list({r['path']:r for r in sources}.values()),
                limitations=text('Nearby records, road lines and catalog footprints require an applicability check. Peak stage and peak flow may occur at different times.','附近测站、道路线与目录覆盖范围仍需核实。最高水位与最大流量可能不同步。'))
    path=out/'search.json';save(path,packet);save(pointer,item(path));return packet
