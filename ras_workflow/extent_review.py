"""Bind historical flood-edge checks to selected native calculations and source bytes."""
import base64
from datetime import date
from pathlib import Path
from statistics import median
from math import dist
from itertools import chain
from pyproj import CRS, Transformer

from . import app_core as core
from .common import ROOT, finite, intact, item, read, save, unique_id
from .field_feedback import model_for
from .flood_edges import compare, read_lines
from .qa_review import load_summary
from .revision_inputs import bound_inputs, station_key
from .section_context import frame


def project_family(model):
    seen=set()
    while model.get('parent_revision'):
        parent=model['parent_revision'].get('project_id')
        if not parent or parent in seen:break
        seen.add(parent)
        try:model=core.model(parent)
        except (FileNotFoundError,ValueError):return parent
    return model['id']


def variants(model):
    group=project_family(model)
    output={}
    parents={}
    for path in core.BASE.glob('*/app.json'):
        try:m=core.model(path.parent.name)
        except (OSError,ValueError,KeyError):continue
        if m.get('model_type')!='river' or not m.get('summary') or project_family(m)!=group:continue
        if core.deletion_record(m['id']).exists():continue
        def add(ref,label,event=None):
            if ref and intact([ref]):
                output[ref['sha256']]=dict(summary=ref,label=label,event=event,project_id=m['id'])
        add(m['summary'],m['title'])
        parents[m['id']]=m['summary']
        for ref in m.get('observed_event_history',[]):
            if not intact([ref]):continue
            packet=read(ROOT/ref['path'])
            if packet.get('baseline')==m['summary'] and all(packet.get(k) for k in ('study','review','execution','observations')) and intact(
                    [packet[k] for k in ('study','review','execution','observations')]):
                event=packet['event']
                add(packet.get('summary'),m['title']+' / '+event['event']+' '+event['date'],event)
        ref=m.get('latest_geometry_comparison')
        if ref and intact([ref]):
            packet=read(ROOT/ref['path'])
            if packet.get('summaries',{}).get('baseline')==m['summary'] and intact([packet[k] for k in ('study','review','execution')]):
                for key,value in packet['summaries'].items():
                    if key!='baseline':add(value,m['title']+' / '+key)
    # Detached local trial jobs may be linked through their sealed revision
    # origin. Search only the workflow job layout, never client-supplied paths.
    archive=ROOT/'status'
    for path in chain(archive.glob('*/*/jobs/*/summary.json'),archive.glob('*/*/*/jobs/*/summary.json')):
        try:
            record=read(path)
            config=record['configuration']
            origin=config.get('revision_origin') or {}
            parent=origin.get('project_id')
            if parent not in parents or origin.get('summary')!=parents[parent] or record.get('calculation_status')!='COMPUTED':continue
            ref=item(path)
            output.setdefault(ref['sha256'],dict(summary=ref,label=config['title'],event=None,project_id=parent))
        except (KeyError,ValueError,OSError):continue
    studies=chain(core.BASE.glob('*/warning_reviews/*/analysis.json'),archive.glob('*/*/warning_reviews/*/analysis.json'))
    by_ref={r['sha256']:(key,r) for key,r in parents.items()}
    for path in studies:
        try:
            packet=read(path)
            parent,baseline=by_ref[packet['baseline']['sha256']]
            if packet['baseline']!=baseline:continue
            study,review,execution=(packet[k] for k in ('study','review','execution'))
            if not intact([study,review,execution]):continue
            spec,executed=read(ROOT/study['path']),read(ROOT/execution['path'])
            if baseline not in spec['evidence'] or executed['study']!=study or executed['review']!=review:continue
            for case in executed['cases']:
                ref=case.get('summary')
                if case['status']!='COMPUTED' or not ref or not intact([ref]):continue
                tag=' · recommended / 推荐' if case['id']==packet.get('recommended') else ''
                output.setdefault(ref['sha256'],dict(summary=ref,label=spec['id']+' / '+case['id']+tag,event=None,project_id=parent))
        except (KeyError,ValueError,TypeError,OSError):continue
    return output


def choices(key,body):
    m=model_for(key,body)
    options=[]
    for k,row in variants(m).items():
        hyd=read(ROOT/row['summary']['path']).get('hydraulics') or {}
        options.append(dict(id=k,label=row['label'],event=row['event'],profiles=[p['profile_id'] for p in hyd.get('profiles',[])]))
    return dict(options=options,current=m['summary']['sha256'])


def current(model):
    ref=model.get('extent_review')
    if ref and intact([ref]):
        data=read(ROOT/ref['path'])
        if data['baseline']==model.get('summary') and intact(data['sources']):
            return data
    return None


def compare_case(variant, profile, lines, event, search_m):
    _,summary,hyd=load_summary(ROOT/variant['summary']['path'])
    _,geometry,refs=bound_inputs(summary)
    rows,crs,native=frame(summary)
    selected=[r for r in rows if r['profile']==profile]
    native_profile=next((p for p in hyd['profiles'] if p['profile_id']==profile),None)
    if not selected or not native_profile:raise ValueError('Select an available native profile')
    centers={station_key(s['rs']):s['center_xy'] for s in geometry['cross_sections']}
    if lines is None:
        result=dict(matched=0,total=len(selected),median_abs_m=None,rows=[])
        for s in selected:
            mapping=s.get('map') or {}
            seg=mapping.get('wet_segments_xy') or []
            result['rows'].append(dict(rs=s['rs'],wse_ft=s['wse_ft'],status='GEOMETRY_COMPARISON',
                    cutline_xy=mapping.get('cutline_xy'),model_xy=[seg[0][0],seg[-1][-1]] if seg else []))
    else:result=compare(lines,crs,selected,centers,search_m)
    warning_count=None
    by_station={}
    if summary.get('native_supplement'):
        from .warning_study import assessment
        audit=assessment(summary,variant['summary'])
        refs.append(audit['native_file'])
        records=[r for r in audit['records'] if r.get('profile')==profile and r['severity']=='WARNING']
        warning_count=len(records)
        for r in records:
            if r.get('station') is not None:by_station.setdefault(station_key(r['station']),[]).append(r['category'])
    for row,section in zip(result['rows'],selected,strict=True):
        row['native_warnings']=by_station.get(row['rs'],[]) if warning_count is not None else None
        ends=(section['left_excess_ft'],section['right_excess_ft'])
        row['wet_ends']=sum(v>0 for v in ends) if all(finite(v) for v in ends) else None
        row['center_xy']=centers.get(row['rs'])
        row['left_right_flow_pct']=section['ob_percent']
    context,extra=station_context(variant,summary,profile,crs)
    refs.extend(extra)
    for row in result['rows']:
        row.update(observations=context['observations'].get(row['rs'],[]),
                   boundary_tests=context['boundary_tests'].get(row['rs'],[]))
    result['context_issues']=context['issues']
    record=variant.get('event') or {}
    same=bool(event) and record.get('event')==event['name'] and record.get('date')==event['date'] and record.get('profile')==profile
    flow=native_profile['flow_cfs']
    same=same and abs(flow-event['flow_cfs'])<=max(1.e-5,1.e-7*flow)
    result.update(summary=variant['summary'],run_id=hyd['run_id'],profile=profile,flow_cfs=flow,crs=crs,datum=hyd.get('datum'),
                  registered_event_match=same,label=variant['label'],native_warning_count=warning_count)
    return result,refs+native+[variant['summary']]


def station_context(variant,summary,profile,crs):
    """Show only registered field locations and sensitivity from this exact run."""
    from . import river_observations as observations
    from .report_studies import collect
    context=dict(observations={},boundary_tests={},issues=[])
    sources=[]
    owner=core.model(variant['project_id'])
    packet=observations.current(owner)
    if packet:
        raw=observations.parse((ROOT/packet['source']['path']).read_text(encoding='utf-8-sig'))
        event=variant.get('event') or {}
        observations_rows=observations.screen(raw,summary,event if event.get('profile')==profile else None)
        for src,row in zip(raw,observations_rows,strict=True):
            loc=row['location']
            if not loc or any(issue in row['issues'] for issue in ('MULTIPLE_NEARBY_SECTIONS','OUTSIDE_SECTION_TOLERANCE','POSITION_UNCERTAINTY_TOO_LARGE','INVALID_POSITION_UNCERTAINTY')):continue
            xy=Transformer.from_crs(src['horizontal_crs'],crs,always_xy=True).transform(float(src['x']),float(src['y']),errcheck=True)
            if not all(finite(v) for v in xy):continue
            entry={k:row.get(k) for k in ('event','date','role','kind','observed_ft','observed_datum','residual_ft','issues')}
            entry.update(xy=list(xy),source=src.get('source'))
            context['observations'].setdefault(loc['rs'],[]).append(entry)
        sources.extend([owner['river_observations'],packet['source']])
    elif owner.get('river_observations'):context['issues'].append('Stored observation evidence could not be verified')
    try:
        studies,refs=collect(ROOT/variant['summary']['path'],summary)
        for study in studies:
            cases={c['id']:c for c in study['cases']}
            for comp in study.get('comparisons',[]):
                paths=[d['path'] for d in cases[comp['case']].get('changes',[])]
                if len(paths)!=1 or not paths[0].startswith(('boundary_slopes.','boundaries.')):continue
                for r in comp['cross_section_differences']:
                    if r['profile']==profile and finite(r['delta_wse_ft']):
                        context['boundary_tests'].setdefault(station_key(r['station']),[]).append(
                            dict(case=comp['case'],parameter=paths[0],delta_ft=r['delta_wse_ft']))
        if context['boundary_tests']:sources.extend(refs)
    except (OSError,ValueError,KeyError) as error:
        context['issues'].append('Boundary study unavailable: '+str(error))
    return context,sources


def selected_comparison(model,body):
    ref=model.get('extent_review')
    if not ref or ref['sha256']!=body.get('comparison_token') or model['revision']!=body.get('revision'):
        raise ValueError('Reopen the saved comparison for the current project edition')
    packet=current(model)
    if packet is None:raise ValueError('The comparison evidence has changed')
    return ref,packet


def disposition(key,body):
    m=model_for(key,body);core.require_idle(m)
    ref,packet=selected_comparison(m,body)
    choice=body.get('decision');station=body.get('station')
    if choice not in ('keep_first','request_survey') or station not in {r['rs'] for c in packet['cases'] for r in c['rows']}:
        raise ValueError('Select an available station and review action')
    decision=dict(comparison=ref,choice=choice,station=station,reference_run=packet['cases'][0]['run_id'],
                  summary=m['summary'],engineering_acceptance='NOT_ASSESSED')
    path=core.folder(key)/'extent_decisions'/unique_id()/'decision.json';save(path,decision)
    m.update(extent_decision=item(path),revision=m['revision']+1,exports_need_refresh=True)
    core.persist(m,'EXTENT_REVIEW_DECISION',decision)
    return decision


def revision_source(parent,body):
    from .inputs import dependencies
    from .site_delivery import config_origin
    ref,packet=selected_comparison(parent,body)
    if len(packet['cases'])!=2 or packet['classification']!='NATIVE_GEOMETRY_COMPARISON':
        raise ValueError('Choose a two-run geometry comparison for an editable model')
    left,right=packet['cases']
    if left['flow_cfs']!=right['flow_cfs'] or not packet.get('max_wse_change'):
        raise ValueError('Use calculations at the same discharge, datum and overlapping physical locations')
    _,summary,hyd=load_summary(ROOT/right['summary']['path'])
    cp,run,manifest=config_origin(summary)
    config,geometry,snapshots=bound_inputs(summary)
    gp=(cp.parent/config['geometry']).resolve()
    geometries=[s for s in manifest['source_inputs'] if ROOT/s['path']==gp]
    if (len(geometries)!=1 or not intact(geometries) or read(gp)!=geometry or dependencies(cp,config)!=manifest['source_inputs'] or
            not any(s['id']==parent['scenario'] for s in config['scenarios'])):
        raise ValueError('Restore the selected run’s bound configuration, terrain and geometry before adoption')
    return dict(config_path=cp,config=config,geometry=geometry,summary=right['summary'],terrain=summary['terrain'],
                geometry_source=geometries[0],sources=packet['sources']+[ref]+snapshots,kind='extent_review',
                case_id=hyd['run_id'],analysis=ref,maximum_width_ft=max(s['station_ft'][-1]-s['station_ft'][0] for s in geometry['cross_sections']))


def aligned_stations(cases):
    first=cases[0]
    available={r['rs']:r for r in first['rows'] if r.get('center_xy')}
    if len(cases)==1:return set(available)
    scale=CRS.from_user_input(first['crs']).axis_info[0].unit_conversion_factor
    return {r['rs'] for r in cases[1]['rows'] if r.get('center_xy') and r['rs'] in available
            and dist(r['center_xy'],available[r['rs']]['center_xy'])*scale<=1.0}


def analyze(key,body):
    m=model_for(key,body);core.require_idle(m)
    if body.get('revision')!=m['revision']:raise ValueError('Reopen the current revision')
    geometry_only=body.get('mode')=='geometry'
    event=body.get('event') or {}
    name=str(event.get('name','')).strip()
    source=str(event.get('source','')).strip()
    role=event.get('use')
    if not geometry_only and (not name or len(name)>120 or not 1<=len(source)<=1600 or role not in ('context','used','reserved')):
        raise ValueError('Enter a dated event, source and prior use of the flood extent')
    lines=None
    if not geometry_only:
        when=date.fromisoformat(event['date']).isoformat()
        q=event.get('flow_cfs')
        if not finite(q) or q<=0:raise ValueError('Supply the measured event discharge in cfs')
        event=dict(name=name,date=when,flow_cfs=q,source=source,use=role)
        file=body['file'];raw=base64.b64decode(file['content'],validate=True)
        lines=read_lines(file['name'],raw,body.get('layer','').strip())
    else:event=None
    options=variants(m);selected=body['cases']
    if not isinstance(selected,list) or not 1<=len(selected)<=2 or len({c['id'] for c in selected})!=len(selected):
        raise ValueError('Select one or two distinct verified calculations in this project family')
    if geometry_only and len(selected)!=2:raise ValueError('Select two native runs for a geometry comparison')
    cases=[];sources=[m['summary']]
    for choice in selected:
        if choice['id'] not in options:raise ValueError('The selected calculation changed or is outside this project family')
        result,refs=compare_case(options[choice['id']],choice['profile'],lines,event,body.get('search_m',400))
        cases.append(result);sources.extend(refs)
    if len(cases)==2 and cases[0]['crs']!=cases[1]['crs']:raise ValueError('Select calculations in the same projected CRS')
    from hashlib import sha256
    fingerprint=sha256(raw).hexdigest() if not geometry_only else None
    # Once the same source is declared used for interpretation, a subsequent
    # upload in this family cannot turn it into independent evidence.
    used_before=False
    family=project_family(m)
    for path in core.BASE.glob('*/extent_reviews/*/review.json') if fingerprint else ():
        owner=path.parents[2].name
        if project_family(core.model(owner))!=family:continue
        prior=read(path)
        if (prior.get('extent') or {}).get('sha256')==fingerprint and prior['event']['use']=='used':used_before=True
    matched_event=all(c['registered_event_match'] for c in cases)
    classification=('NATIVE_GEOMETRY_COMPARISON' if geometry_only else 'SPATIAL_CONTEXT' if not matched_event or role=='context' else
                    'USED_FOR_GEOMETRY_OR_CALIBRATION' if used_before or role=='used' else 'RESERVED_EVENT_REVIEW')
    aligned=aligned_stations(cases)
    keys=aligned.intersection(*[{r['rs'] for r in case['rows'] if r['status']=='MATCHED'} for case in cases])
    for case in cases:
        values=[abs(r[k]) for r in case['rows'] if r['rs'] in keys for k in ('left_shortfall_m','right_shortfall_m')]
        case['common_median_abs_m']=round(median(values),3) if values else None
    delta=None
    if len(cases)==2 and cases[0]['flow_cfs']==cases[1]['flow_cfs'] and cases[0].get('datum') and cases[0]['datum']==cases[1].get('datum'):
        old={r['rs']:r['wse_ft'] for r in cases[0]['rows']}
        shifts=[(r['rs'],r['wse_ft']-old[r['rs']]) for r in cases[1]['rows'] if r['rs'] in aligned and finite(r['wse_ft']) and finite(old.get(r['rs']))]
        if shifts:
            rs,signed=max(shifts,key=lambda pair:abs(pair[1]))
            delta=dict(station=rs,signed_ft=signed,common_count=len(shifts))
    result=dict(baseline=m['summary'],event=event,extent=None,extent_sha256=fingerprint,layer=body.get('layer'),search_m=body.get('search_m',400),
        classification=classification,prior_use=used_before,common_sections=len(keys),cases=cases,max_wse_change=delta,
        sources=list({r['path']:r for r in sources}.values()),engineering_acceptance='NOT_ASSESSED')
    if body.get('preview') is True:return dict(result,preview=True)
    dest=core.folder(key)/'extent_reviews'/unique_id();dest.mkdir(parents=True)
    if not geometry_only:
        src=dest/('extent'+Path(file['name']).suffix.lower());src.write_bytes(raw)
        result['extent']=item(src);result['sources'].append(result['extent'])
    path=dest/'review.json';save(path,result);m['extent_review']=item(path)
    m.pop('extent_decision',None)
    m['revision']+=1;m['exports_need_refresh']=True
    core.persist(m,'FLOOD_EXTENT_REVIEW',dict(review=m['extent_review'],classification=classification))
    return result
