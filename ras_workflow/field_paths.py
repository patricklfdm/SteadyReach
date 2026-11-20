"""Compare a solved geometry alternative at an RS and its immediate neighbors."""
from . import section_context as context
from .common import ROOT,intact,read
from .field_feedback import model_for
from .revision_inputs import station_key
from .river_review_report import collect as review_records


def compare(key,body,with_map=True):
    from .app_core import folder
    m=model_for(key,body);base=m['summary'];summary=read(ROOT/base['path'])
    audited,refs=review_records(ROOT/base['path'],summary)
    if not audited.get('comparison'):raise ValueError('Complete and verify a geometry comparison first')
    comparison=m['latest_geometry_comparison']
    variants=read(ROOT/comparison['path'])['summaries']
    name=body.get('geometry')
    if name not in ('fixed','rotated'):raise ValueError('Choose the fixed or rotated candidate')
    rs=station_key(body['station']);profile=body['profile']
    frames={};crs=None
    for k,entry in variants.items():
        rows,projection,sources=context.frame(read(ROOT/entry['path']))
        if crs and crs!=projection:raise ValueError('Geometry projections differ')
        frames[k]=rows;crs=projection;refs.extend(sources)
    bounds=context.extent(frames)
    layers=context.public_lines(folder(key),bounds,crs,False)
    if with_map and any(v['status']=='NOT_LOADED' for v in layers):
        from .common import lock
        with lock(folder(key)/'context_layers'/'fetch.lock'):
            layers=context.public_lines(folder(key),bounds,crs,True)
    result={};neighborhood=None
    for k in ('baseline',name):
        rows=frames[k]
        strip=context.overbank_strips(read(ROOT/variants[k]['path']),rows,layers,profile,rs)
        stations=[rs]+[s['neighbor'] for s in strip['strips'] if s['side']=='L']
        if neighborhood is not None and neighborhood!=stations:raise ValueError('Neighboring station identities differ')
        neighborhood=stations
        selected=[dict(rs=r['rs'],wse_ft=r['wse_ft'],share=r['ob_percent'],cut=r['map']['cutline_xy'])
                  for r in rows if r['profile']==profile and r['rs'] in stations and r['map']]
        if len(selected)!=len(stations):raise ValueError('A mapped comparison section is missing')
        result[k]=dict(sections=selected,strips=strip['strips'])
        refs+=strip['sources']+[variants[k]]
    response=dict(station=rs,profile=profile,alternative=name,variants=result,summary=base,
                  layer_coverage=strip['layer_coverage'],geometry_summaries=variants,
                  sources=list({e['path']:e for e in refs+[comparison]}.values()))
    if with_map:
        response.update(imagery=context.backdrop(m,bounds,crs),layers=layers)
    return response


DECISIONS=('retain_baseline','use_candidate','request_survey','review_2d')


def decision(key,body):
    choice=body.get('decision');basis=body.get('condition','').strip()
    if choice not in DECISIONS or not basis or len(basis)>1600:raise ValueError('Choose a disposition and state the engineering condition')
    d=compare(key,body,False)
    selected=d['alternative'] if choice=='use_candidate' else 'baseline'
    ref=d['geometry_summaries'][selected]
    refs=d.pop('sources')
    if not intact(refs):raise ValueError('Comparison evidence changed')
    return dict(comparison=d,selected=selected,decision=choice,condition=basis,assumed=body.get('assumed') is True,
                blockers=[],stages=[]),ref,refs
