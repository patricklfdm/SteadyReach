"""Run event-specific flow through the existing geometry with one explicit consent."""
from .common import ROOT, intact, item, read, save, unique_id
from .coverage_study import case_configuration
from .inputs import dependencies
from .qa_review import load_summary
from .revision_inputs import bound_inputs
from .river_observations import current, parse, screen

KIND='river_observed_event'


def prepare(model,body):
    from . import app_core as core
    packet=current(model)
    if not packet:raise ValueError('Import observations bound to this calculation first')
    identity=(body.get('event'),body.get('date'))
    rows=[r for r in packet['rows'] if (r['event'],r['date'])==identity]
    eligible=[r for r in rows if r['event_eligible']]
    if not eligible:raise ValueError('The event lacks a located, datum-compatible stage and measured discharge')
    if {r['role'] for r in rows}>={'calibration','holdout'}:
        raise ValueError('Reserve the complete event for calibration or holdout, not both')
    flows={r['flow_cfs'] for r in eligible}
    if len(flows)!=1:raise ValueError('Resolve conflicting event discharges before computing')
    q=flows.pop()
    _,summary,_=load_summary(ROOT/model['summary']['path'])
    cfg,g,bound=bound_inputs(summary)
    source=ROOT/model['active_project']
    if read(source)!=cfg or read(source.parent/cfg['geometry'])!=g:
        raise ValueError('Current inputs differ from the verified baseline')
    boundary=[r for r in eligible if r['role']=='boundary']
    if len({r['observed_ft'] for r in boundary})>1:raise ValueError('Resolve conflicting downstream stages for this event')
    if not boundary and g['boundaries']['downstream']['type']=='known_stage':
        raise ValueError('Provide the downstream observed stage for this event')
    folder=core.folder(model['id'])/'observed_events'/unique_id()
    dest=folder/'cases'/'event'
    flow_profile='Observed'
    spec=dict(event=identity[0],date=identity[1],profile=flow_profile,flow_cfs=q,
              downstream_ft=boundary[0]['observed_ft'] if boundary else None,observations=packet['source'])
    save(folder/'specification.json',spec)
    plan=dict(id=KIND,analysis_kind=KIND,project_id=model['id'],scenario_id=model['scenario'],case_kind=cfg['case_kind'],
        source_project=item(source),source_inputs=dependencies(source,cfg),evidence=[model['summary'],model['river_observations'],packet['source']]+bound,
        specification=item(folder/'specification.json'),event=spec,cases=[],engineering_acceptance='NOT_ASSESSED')
    config=case_configuration(plan,dest,'event')
    config['title']=cfg['title']+' / observed event '+identity[1]
    config['scenarios'][0]['profiles']=[dict(id=flow_profile,flow_cfs=q,source='Observed event '+identity[1]+'; '+eligible[0]['source'])]
    config['scenarios'][0]['profiles'][0].update(approved_for_model=True,review_status='CONDITIONALLY_REVIEWED')
    sources=config['scenarios'][0].get('parameter_source')
    if isinstance(sources,dict):
        # Keep the roughness evidence but replace design-flow provenance for this event.
        for field in list(sources):
            if 'flow' in field.lower() or 'profile' in field.lower():
                sources[field]=dict(source=packet['source'],basis='Measured discharge for '+identity[1],value=q)
    if boundary:
        g['boundaries']['downstream']=dict(type='known_stage',stages_ft=[spec['downstream_ft']])
    save(dest/'geometry.json',g);save(dest/'project.draft.json',config)
    plan['cases']=[dict(id='event',draft=item(dest/'project.draft.json'),geometry=item(dest/'geometry.json'),section_count=len(g['cross_sections']))]
    save(folder/'study.json',plan)
    model['pending_study']=item(folder/'study.json')
    core.persist(model,'PREPARE_OBSERVED_EVENT')
    return dict(entry=model['pending_study'],token=model['pending_study']['sha256'],plan=plan)


def analyze(sp,plan,rp,journal):
    from .study import verified_case
    result=dict(analysis_kind=KIND,status='INCOMPLETE',study=item(sp),review=item(rp),execution=item(sp.parent/'execution.json'),
                event=plan['event'],observations=plan['event']['observations'],baseline=plan['evidence'][0],rows=[],engineering_acceptance='NOT_ASSESSED')
    case=plan['cases'][0];record=journal['cases'][0]
    if record['status']!='COMPUTED':return result
    dest=(ROOT/case['draft']['path']).parent
    cfg=read(dest/'project.json')
    _,summary,_=verified_case(record,dest/'project.json',cfg)
    if read(dest/cfg['geometry'])!=read(ROOT/case['geometry']['path']) or cfg['scenarios']!=read(ROOT/case['draft']['path'])['scenarios']:
        raise ValueError('Computed event differs from its confirmed inputs')
    spec=plan['event']
    records=parse((ROOT/spec['observations']['path']).read_text(encoding='utf-8-sig'))
    chosen=[r for r in records if r['event']==spec['event'] and r['date']==spec['date']]
    result.update(status='EVENT_COMPUTED_REVIEW_REQUIRED',summary=record['summary'],rows=screen(chosen,summary,spec))
    return result
