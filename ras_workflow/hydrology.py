"""Import StreamStats peak-flow report text without turning estimates into approval."""
import re

from pyproj import Geod

from .common import ROOT, finite, item, read, safe_path, save, utc
from .evidence import verified_text

NUM=r'(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
OPTIONAL=rf'(?:{NUM}|--|N/A)'
FLOW=re.compile(rf'(?P<aep>{NUM})-percent\s+AEP\s+flood\s+(?P<q>{NUM})\s+'
                rf'(?P<unit>ft\^3/s|ft³/s|m\^3/s|m³/s|cfs|cms)'
                rf'(?:\s+(?P<pil>{OPTIONAL})\s+(?P<piu>{OPTIONAL})\s+(?P<asep>{OPTIONAL}))?\s*$',re.I|re.M)


def parse(blocks,site=None):
    profiles=[];parameters=[];points=[];regions=[];issues=[];source_warnings=[]
    for block in blocks:
        text=block['text']
        for m in re.finditer(r'Delineation Point \(Latitude, Longitude\):\s*([+-]?[\d.]+),\s*([+-]?[\d.]+)',text):
            lat,lon=map(float,m.groups())
            if not(-90<=lat<=90 and -180<=lon<=180):raise ValueError('Invalid reported pour point')
            points.append(dict(latitude=lat,longitude=lon,locator=block['locator'],quote=m.group(0)))
        regions += [dict(name=m.group(1),locator=block['locator'],quote=m.group(0))
                    for m in re.finditer(r'Peak-Flow Statistics (?:Parameters|Flow Report)\s*\[([^\]]+)\]',text)]
        for line in text.splitlines():
            if re.search(r'warning|extrapolat|outside.*range|regulated|urban',line,re.I):
                source_warnings.append(dict(locator=block['locator'],quote=line))
        # Restrict numeric parsing to the explicitly labelled peak-flow table.
        start=text.find('Peak-Flow Statistics Flow Report')
        if start>=0:
            end=text.find('Peak-Flow Statistics Citations',start)
            segment=text[start:end if end>=0 else len(text)]
            for m in FLOW.finditer(segment):
                aep=float(m['aep'])/100;value=float(m['q']);unit=m['unit'].lower()
                if not finite(aep) or not finite(value) or not 0<aep<=1 or value<=0:raise ValueError('Invalid AEP or nonpositive flow')
                factor=1/.3048**3 if unit in ['m^3/s','m³/s','cms'] else 1.
                def optional(name):
                    v=m[name];n=float(v) if v and re.fullmatch(NUM,v) else None
                    if n is not None and (not finite(n) or n<0):raise ValueError('Invalid prediction interval or standard error')
                    return n
                lower,upper=optional('pil'),optional('piu')
                if lower is not None and upper is not None and not lower<=value<=upper:
                    issues.append('Reported interval does not contain the peak estimate for AEP '+str(aep))
                profiles.append(dict(aep=aep,return_period_years=1/aep,flow_cfs=value*factor,
                    raw_flow=value,raw_unit=m['unit'],conversion_factor_to_cfs=factor,
                    lower_prediction_interval_cfs=None if lower is None else lower*factor,
                    upper_prediction_interval_cfs=None if upper is None else upper*factor,
                    prediction_interval_percent=90 if re.search(r'90%\s+Prediction Interval',segment) else None,
                    asep_percent=optional('asep'),locator=block['locator'],quote=m.group(0),
                    evidence_class='reported_statistical_estimate',review_status='UNREVIEWED'))
        start=text.find('Peak-Flow Statistics Parameters')
        if start>=0:
            segment=re.split(r'Peak-Flow Statistics Flow Report|Maximum Probable Flood Statistics|Bankfull Statistics|Region ID:',text[start:])[0]
            for m in re.finditer(rf'^(DRNAREA|PRECIP)\s+(.+?)\s+({NUM})\s+(square miles|inches)\s+({NUM})\s+({NUM})\s*$',segment,re.M):
                code,name,value,unit,lo,hi=m.groups();value,lo,hi=map(float,[value,lo,hi])
                parameters.append(dict(code=code,description=name,value=value,unit=unit,min=lo,max=hi,
                    within_reported_range=lo<=value<=hi,locator=block['locator'],quote=m.group(0)))
    if not profiles:issues.append('No supported explicitly labelled peak-flow table parsed; required flows remain missing')
    if len({p['aep'] for p in profiles})!=len(profiles):raise ValueError('Duplicate peak-flow AEP rows require explicit regional selection')
    profiles.sort(key=lambda p:p['return_period_years'])
    if any(a['flow_cfs']>b['flow_cfs'] for a,b in zip(profiles,profiles[1:])):issues.append('Flow decreases with increasing return period')
    if not parameters:issues.append('Regression parameter range evidence missing')
    if any(not p['within_reported_range'] for p in parameters):issues.append('Reported basin parameter outside regression range')
    unique={(p['latitude'],p['longitude']) for p in points};point=points[0] if len(unique)==1 else None
    if point is None:issues.append('Reported pour point missing or ambiguous')
    distance=None
    if point and site:
        if not all(finite(site.get(k)) for k in ['latitude','longitude']):raise ValueError('Invalid project location')
        distance=Geod(ellps='WGS84').inv(site['longitude'],site['latitude'],point['longitude'],point['latitude'])[2]
        if distance>.1:issues.append('Report pour point differs from project coordinate; review drainage identity before transfer')
    issues += ['Basin identity and delineation require review',
               'Regulation, urbanization, drainage changes and equation-specific applicability are not automatically established',
               'Design-flow selection has not been approved by this import']
    return dict(status='CANDIDATE_HYDROLOGY_REQUIRES_REVIEW',profiles=profiles,reported_parameters=parameters,
        reported_pour_point=point,project_distance_m=distance,regions=regions,source_warning_candidates=source_warnings,
        applicability_review_items=issues,approved_for_model=False,site_applicability_status='UNREVIEWED',
        required_unresolved_checks=dict(basin_match=None,regulation=None,urbanization=None,equation_scope=None,design_approval=None),
        required_flows={key:next((p['flow_cfs'] for p in profiles if abs(p['aep']-aep)<1e-10),None)
                        for key,aep in [('Q100',.01),('Q200',.005),('Q500',.002)]})


def import_report(evidence_path,project_path,output):
    evidence=verified_text(evidence_path);project=safe_path(ROOT,project_path);c=read(project)
    result=parse(evidence['blocks'],c.get('location'))
    result.update(schema_version='1.0',created_utc=utc(),project_id=c['project_id'],
                  sources=[item(safe_path(ROOT,evidence_path)),evidence['source'],item(project)],
                  interpretation='Imported regression estimates, not observed floods or solver results; no project configuration changed')
    out=safe_path(ROOT,output)
    if out.exists():raise ValueError('Preserve prior import; choose a new output')
    save(out,result);return result
