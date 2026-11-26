"""Determine whether a source supports a downstream stage for a particular event."""
import csv
from datetime import date
import re
from pathlib import Path

from .common import finite, read
from .river_observations import datum, FLOWS, locate, number, UNITS
from .revision_inputs import station_key


def iso(value):
    try:return date.fromisoformat(str(value)).isoformat()
    except ValueError:return None


def station(value):
    match=re.search(r'\bUSGS[- .](\d{5,15})\b',str(value),re.I)
    return match.group(1) if match else None


def surveyed_point(original, open_source):
    """Read one original outlet point. A declaration cannot supply the coordinates or elevation."""
    with open_source(original).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ['x', 'y', 'elevation']:
            raise ValueError('Direct survey evidence requires an x,y,elevation CSV point extract')
        row = next(reader, None)
        if not row or next(reader, None) is not None or None in row:
            raise ValueError('Supply exactly one direct survey point per outlet source')
        values = {k: number(row, k) for k in ('x','y','elevation')}
        if any(v is None for v in values.values()):
            raise ValueError('Direct survey point has an invalid coordinate or elevation')
        return values


def direct_event(row, ref, events):
    if row.get('role') != 'boundary' or row.get('kind') != 'boundary_stage' or station(row.get('source')):
        return None
    matches = [e for e in events if e.get('profile') == row.get('profile')]
    if len(matches) != 1:
        return None
    event = matches[0]
    if (event.get('method') != 'direct_outlet_survey' or not event.get('native_point')
            or event.get('station') or event['source']['sha256'] == ref['sha256']
            or not row.get('source') or event.get('point_source') != row['source']
            or any(not row.get(k) or event.get(k) != row[k] for k in
                   ('date','event','unit','horizontal_crs','vertical_datum'))
            or number(row,'vertical_uncertainty') != number(event,'vertical_uncertainty')
            or any(number(row,k) != v for k,v in event['native_point'].items())):
        return None
    return event


def documents(ctx,open_source):
    stations={};measurements=[];observations=[];events=[];transfers=[];zeros=[];ties=[];metadata=[]
    by_hash={r['sha256']:r for r in ctx['sources']};seen=set()
    for ref in [*ctx['attachments'],*(r for a in ctx['attempts'] for r in a.get('sources',[]) if r.get('role')=='USGS_streamgages' or 'early_gages' in r.get('path',''))]:
        name=Path(ref.get('original_name') or ref['path']).name.lower()
        if (name,ref['sha256']) in seen:continue
        seen.add((name,ref['sha256']))
        if name=='observed_profiles.csv' or ref.get('role')=='returned_observations':
            with open_source(ref).open(encoding='utf-8-sig',newline='') as f:
                observations.extend((dict(r),ref) for r in csv.DictReader(f))
            continue
        if not name.endswith('.json'):continue
        try:raw=read(open_source(ref))
        except (UnicodeError,ValueError):
            if name=='intake_evidence.json':raise ValueError('Invalid intake_evidence.json')
            continue
        if not isinstance(raw,dict):continue
        if name=='intake_evidence.json':
            if raw.get('schema')!='intake_evidence_1':raise ValueError('Unsupported intake_evidence.json schema')
            for key,target in [('records',metadata),('events',events),('transfers',transfers),('gage_zeros',zeros),('datum_ties',ties)]:
                values=raw.get(key,[])
                if not isinstance(values,list) or not all(isinstance(r,dict) for r in values):raise ValueError('Expected an evidence record list: '+key)
                for r in values:
                    original=by_hash.get(r.get('source_sha256'))
                    if not original or original['sha256']==ref['sha256']:raise ValueError('Evidence declaration needs a registered original: '+key)
                    if key=='records' and r.get('category') not in ('terrain','channel','flow','stage','structure'):
                        raise ValueError('Unknown evidence category')
                    if (r.get('date') and not iso(r['date'])) or (key!='records' and not iso(r.get('date'))):raise ValueError('Supply an ISO evidence date')
                    bound = dict(r,source=original,declaration=ref['sha256'])
                    if key=='events' and r.get('method')=='direct_outlet_survey':
                        bound['native_point']=surveyed_point(original,open_source)
                    target.append(bound)
            continue
        features=raw.get('features',[]) if raw.get('type')=='FeatureCollection' else [raw]
        for feature in features or []:
            if not isinstance(feature,dict):continue
            props=feature.get('properties') or (feature if feature.get('field_visit_id') else {})
            if not isinstance(props,dict):continue
            identifier=station(props.get('id') or feature.get('id'))
            xy=(feature.get('geometry') or {}).get('coordinates')
            if (identifier and props.get('site_type_code')=='ST' and isinstance(xy,(tuple,list)) and len(xy)>=2
                    and all(finite(v) for v in xy[:2]) and abs(xy[0])<=180 and abs(xy[1])<=90):
                previous=stations.get(identifier)
                conflict=bool(previous and (previous.get('conflict') or previous['lonlat']!=xy[:2] or previous['datum']!=props.get('vertical_datum')))
                stations[identifier]=dict(station=identifier,name=props.get('monitoring_location_name'),lonlat=xy[:2],datum=props.get('vertical_datum'),source=ref,conflict=conflict)
            if props.get('field_visit_id') and props.get('reading_type') in ('Discharge','MeanGageHeight'):
                measurements.append(dict(visit=props['field_visit_id'],station=station(props.get('monitoring_location_id')),date=iso(str(props.get('time'))[:10]),
                    kind=props['reading_type'],value=number(props,'value'),unit=props.get('unit_of_measure'),source=ref))
    for ref in ctx.get('notes',[]):
        note=read(open_source(ref));original=by_hash.get(note['source_sha256'])
        if not original:raise ValueError('The original behind a metadata note is missing')
        metadata.append(dict(note,source=original,declaration=ref['sha256']))
    for profile in ctx['profiles']:
        for m in measurements:
            if m['kind']=='Discharge' and m['visit'] in str(profile.get('source','')) and m['value'] is not None and m['unit'] in ('ft^3/s','ft3/s','cfs') and m['value']==profile.get('flow_cfs'):
                events.append(dict(profile=profile['id'],event=profile['id'],date=m['date'],station=m['station'],source=m['source']))
    return dict(stations=stations,observations=observations,events=events,transfers=transfers,gage_zeros=zeros,datum_ties=ties,metadata=metadata,measurements=measurements)


def controls_for_run(m,config,geometry,fields,notices=None):
    """Check declared gage-derived tailwater at the same gate as manual inputs."""
    end=(geometry.get('boundaries') or {}).get('downstream') or {}
    if geometry.get('model_type')!='river' or end.get('type')!='known_stage':return []
    from .intake_register import context
    from .intake_freeze import local
    stage=next((f for f in fields if f['key']=='g.boundaries.downstream.stages_ft'),{})
    named=station(stage.get('basis'))
    candidates=[*m.get('attachments',[]),*config.get('returned_observations',[]),*config.get('field_return_sources',[])]
    if not named and not any(Path(r.get('original_name') or r['path']).name.lower() in ('observed_profiles.csv','intake_evidence.json') for r in candidates):return []
    ctx=context(m,prepared=(config,geometry,fields));checked=screen(ctx,documents(ctx,local));errors=[]
    for p,z in zip(ctx['profiles'],end.get('stages_ft') or []):
        applicable=[r for r in checked['rows'] if r['profile']==p['id'] and r['role']=='boundary']
        if not named and not applicable:continue
        allowed={'ELIGIBLE'}
        if not named and (m.get('production_scope') or {}).get('purpose') in ('screening','review'):
            allowed.add('CONDITIONAL_SURVEY')
        if notices is not None and any(r['status']=='CONDITIONAL_SURVEY' for r in applicable):
            notices.append(dict(profile=p['id'],rs=checked['end_rs'],
                en='Outlet stage comes from a direct survey without quantified vertical uncertainty. Use this stage conditionally and obtain the survey accuracy for engineering acceptance.',
                zh='出口水位来自原位测量，垂直精度尚未量化。本次按条件采用，工程验收前需补测量精度依据。'))
        if not applicable or not finite(z) or any(r['status'] not in allowed or (named and r['station']!=named) or abs(r['stage_ft']-z)>.002 for r in applicable):
            issues=sorted({v for r in applicable for v in r['issues']}) or ['STAGE_OR_STATION_NOT_SUPPORTED']
            errors.append(dict(code='UNSUPPORTED_GAGE_BOUNDARY',field='g.boundaries.downstream.stages_ft',
                en=p['id']+' · verify the event, station, datum and imposed stage. '+', '.join(issues),
                zh=p['id']+' · 请核对事件、测站、基准和采用的边界水位。'+', '.join(issues)))
    return errors


def screen(ctx,docs):
    from pyproj import CRS,Geod,Transformer
    geom=ctx['geom'];sections=geom.get('cross_sections') or []
    if not all(finite(s.get('rs')) and len(s.get('cutline_xy') or [])>=2 and len(s.get('station_ft') or [])>=2 for s in sections):sections=[]
    end=min(sections,key=lambda s:float(s['rs'])) if sections else None
    end_rs=station_key(end['rs']) if end else None
    profiles={p['id']:p for p in ctx['profiles']};rows=[];stations=[]
    for s in docs['stations'].values():
        distance=None
        if end and geom.get('horizontal_crs') and end.get('center_xy'):
            crs=CRS.from_user_input(geom['horizontal_crs']);xy=Transformer.from_crs(crs,4326,always_xy=True).transform(*end['center_xy'])
            distance=round(Geod(ellps='WGS84').inv(*s['lonlat'],*xy)[2],2)
        at,issues=locate(dict(x=s['lonlat'][0],y=s['lonlat'][1],horizontal_crs='EPSG:4326'),geom) if end and geom.get('horizontal_crs') else (None,['NO_GEOMETRY'])
        stations.append(dict(s,distance_to_boundary_center_m=distance,matched_rs=(at or {}).get('rs'),
            transfer_required=bool(issues or (at or {}).get('rs')!=end_rs) if end else None,
            datum_check='UNKNOWN' if not datum(s.get('datum')) or not datum(geom.get('vertical_datum')) else
                       'MATCH' if datum(s['datum'])==datum(geom['vertical_datum']) else 'CONVERSION_REQUIRED'))
    for row,ref in docs['observations']:
        reasons=[];identifier=station(row.get('source'));profile=profiles.get(row.get('profile'));role=row.get('role')
        control=role=='boundary';event=row.get('event');day=iso(row.get('date'))
        matches=[e for e in docs['events'] if e.get('profile')==row.get('profile')]
        identity={(e.get('event'),e.get('date'),str(e.get('station','')).removeprefix('USGS-')) for e in matches}
        if not control:reasons.append('INDEPENDENT_OR_CONTEXT')
        direct=direct_event(row,ref,docs['events'])
        if not day or not event or (not direct and (not identifier or identity!={(event,day,identifier)})):reasons.append('EVENT_OR_STATION_UNVERIFIED')
        if geom.get('flow_regime')=='supercritical':reasons.append('DOWNSTREAM_CONTROL_INACTIVE')
        q=number(row,'flow');qfactor=FLOWS.get(row.get('flow_unit'));flow=(profile or {}).get('flow_cfs')
        if not finite(flow) or q is None or not qfactor or abs(q*qfactor-flow)>max(1e-5,abs(flow)*1e-7):reasons.append('DISCHARGE_MISMATCH')
        model_datum=datum(geom.get('vertical_datum'));source_datum=datum(row.get('vertical_datum'))
        if model_datum in ('','LOCAL','UNKNOWN','UNSPECIFIED','NONE') or source_datum!=model_datum:reasons.append('DATUM_MISMATCH')
        factor=UNITS.get(row.get('unit'));z=number(row,'elevation');u=number(row,'vertical_uncertainty')
        if not factor or z is None or row.get('kind') not in ('stage','boundary_stage','gage_height'):reasons.append('STAGE_OR_UNIT_MISSING')
        if row.get('kind')=='gage_height':
            zero=number(row,'gage_zero')
            if zero is None:reasons.append('GAGE_ZERO_MISSING')
            else:
                if not any(str(g.get('station','')).removeprefix('USGS-')==identifier and g.get('date')==day and
                           datum(g.get('datum'))==source_datum and finite(g.get('zero_ft')) and factor and abs(g['zero_ft']-zero*factor)<.001
                           for g in docs.get('gage_zeros',[])):reasons.append('DATED_GAGE_ZERO_UNVERIFIED')
                if z is not None:z+=zero
        if u is None or u<=0:reasons.append('UNCERTAINTY_MISSING')
        at,issues=locate(row,geom) if sections and geom.get('horizontal_crs') else (None,['NO_GEOMETRY'])
        registered=docs['stations'].get(identifier)
        if registered:
            if registered.get('conflict'):reasons.append('STATION_METADATA_CONFLICT')
            station_datum=datum(registered.get('datum'))
            if control and row.get('kind')!='gage_height' and station_datum!=source_datum:
                ties=[t for t in docs.get('datum_ties',[]) if identifier and
                      str(t.get('station','')).removeprefix('USGS-')==identifier and t.get('date')==day and t.get('event')==event and
                      station_datum and datum(t.get('from_datum'))==station_datum and datum(t.get('to_datum'))==source_datum and
                      t['source']['sha256']!=ref['sha256'] and str(t.get('basis') or '').strip() and
                      all(finite(t.get(k)) for k in ('source_stage_ft','offset_ft','uncertainty_ft')) and t['uncertainty_ft']>0 and
                      factor and z is not None and abs(t['source_stage_ft']+t['offset_ft']-z*factor)<.001]
                if len(ties)!=1:reasons.append('DOCUMENTED_DATUM_TIE_REQUIRED')
            xy=[number(row,k) for k in ('x','y')]
            try:
                if None in xy:raise ValueError('coordinates')
                ll=Transformer.from_crs(row.get('horizontal_crs'),4326,always_xy=True).transform(*xy,errcheck=True)
                if Geod(ellps='WGS84').inv(*ll,*registered['lonlat'])[2]>5:reasons.append('STATION_LOCATION_MISMATCH')
            except (ValueError,TypeError,RuntimeError):reasons.append('STATION_LOCATION_MISMATCH')
        elif not direct:reasons.append('STATION_LOCATION_UNVERIFIED')
        stage=z*factor if z is not None and factor else None;transfer=None
        if not end_rs:reasons.append('BOUNDARY_GEOMETRY_UNVERIFIED')
        if issues or not at or at['rs']!=end_rs:
            valid=[t for t in docs['transfers'] if identifier and str(t.get('station','')).removeprefix('USGS-')==identifier and
                   t.get('profile')==row.get('profile') and t.get('event')==event and t.get('date')==day and number(t,'target_rs') is not None and station_key(t['target_rs'])==end_rs
                   and datum(t.get('datum'))==model_datum and finite(t.get('offset_ft')) and finite(t.get('uncertainty_ft')) and t['uncertainty_ft']>0
                   and t['source']['sha256']!=ref['sha256'] and str(t.get('basis') or '').strip()]
            if len(valid)!=1:reasons.append('DOCUMENTED_TRANSFER_REQUIRED')
            else:
                transfer=valid[0]
                if stage is not None:stage+=transfer['offset_ft']
        conditional = bool(direct and direct.get('accept_unquantified_for_screening') is True
                           and reasons==['UNCERTAINTY_MISSING'] and row.get('vertical_uncertainty') in (None,''))
        rows.append(dict(profile=row.get('profile'),event=event,date=day,station=identifier,role=role,source=ref,datum=source_datum,
            **({'survey_point_source':direct['source'],'method':'direct_outlet_survey'} if direct else {}),
            observational_uncertainty_ft=u*factor if u is not None and factor else None,
            unit=row.get('unit'),matched_rs=(at or {}).get('rs'),target_rs=end_rs,issues=reasons,transfer=transfer,
            stage_ft=stage if not reasons or conditional else None,status='CONDITIONAL_SURVEY' if conditional else 'ELIGIBLE' if not reasons else 'CONTEXT' if not control else 'BLOCKED'))
    for profile in profiles:
        controls=[r for r in rows if r['profile']==profile and r['role']=='boundary']
        if len({(r['event'],r['date'],r['station'],r['stage_ft']) for r in controls})>1:
            for r in controls:r.update(status='CONFLICT',issues=r['issues']+['CONFLICTING_CONTROLS'],stage_ft=None)
    return dict(end_rs=end_rs,stations=stations,rows=rows,status='CONFLICT' if any(r['status']=='CONFLICT' for r in rows) else
                'BLOCKED' if any(r['status']=='BLOCKED' for r in rows) else 'CONDITIONAL_SURVEY' if any(r['status']=='CONDITIONAL_SURVEY' for r in rows) else 'ELIGIBLE' if any(r['status']=='ELIGIBLE' for r in rows) else 'NO_BOUNDARY_OBSERVATION')
