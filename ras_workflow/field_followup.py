"""Create a child edition on explicit confirmation and run the normal native solver."""
from . import app_core as core
from .common import ROOT,intact,item,lock,read,rel,save,sha,utc,unique_id
from .field_feedback import model_for,latest
from .revision_inputs import bound_inputs


def confirm(key,body):
    parent=model_for(key,body);core.require_idle(parent)
    mode=body.get('mode')
    if mode not in ('event','geometry') or body.get('confirmed') is not True:raise ValueError('Confirm the displayed field scenario first')
    pointer=core.folder(key)/'field_followups'/('latest_'+mode+'.json')
    with lock(pointer.parent/'confirm.lock'):
        packet=latest(parent,mode,body.get('event'),body.get('date'))
        if not packet or packet['token']!=body.get('token') or parent['revision']!=body.get('revision'):raise ValueError('Field preview changed. Reopen the current preview.')
        spec=packet['review'];ref=packet['source']
        if spec['blockers'] or not intact(spec['sources']+[spec['geometry_summary']]):raise ValueError('Resolve the displayed field gaps or restore their sources')
        child=spec['child'];dest=core.folder(child)
        if not (dest/'app.json').exists():
            create_child(parent,spec,ref,dest)
        m=core.model(child)
        if m.get('feedback_spec')!=ref:raise ValueError('Child belongs to another field review')
        if m.get('task') or m.get('summary'):return dict(id=child,status=m['status'])
        return core.launch(child,'field-run')


def create_child(parent,spec,ref,dest):
    from .coverage_study import case_configuration
    from .site_delivery import config_origin
    native=read(ROOT/spec['geometry_summary']['path']);cfg,g,_=bound_inputs(native);cp,_,_=config_origin(native)
    if read(cp.parent/cfg['geometry'])!=g:raise ValueError('Geometry differs from the sealed calculation')
    scenario=native['hydraulics']['scenario_id'];child=spec['child']
    c=case_configuration(dict(source_project=item(cp),scenario_id=scenario),dest,'field')
    c.pop('revision_origin',None)
    c.update(project_id=child,field_feedback=ref,geometry_review='Independent field-review edition, geometry bound to its source run.',
             authorization='authorization.json',model_proposal_pending=False)
    title=parent['title']+' / '+('Assumed feedback' if spec['assumed'] else 'Field review')
    if spec['mode']=='event':
        if g.get('flow_regime')=='supercritical' or (g.get('flow_regime')=='mixed' and g.get('boundaries',{}).get('upstream',{}).get('type')=='known_stage'):
            raise ValueError('This event batch requires an active downstream boundary and an independently defined upstream control')
        profiles=[dict(id=p['profile'],flow_cfs=spec['flow_cfs'],source=spec['rows'][0]['original_source'],
                       approved_for_model=True,review_status='CONDITIONALLY_REVIEWED') for p in spec['stages']]
        c['scenarios'][0]['profiles']=profiles
        sources=c['scenarios'][0].get('parameter_source')
        if isinstance(sources,dict):
            for field in list(sources):
                if 'flow' in field.lower() or 'profile' in field.lower():
                    sources[field]=dict(source=ref,basis='Event discharge for '+spec['date'],value=spec['flow_cfs'])
        g['boundaries']['downstream']=dict(type='known_stage',stages_ft=[p['stage_ft'] for p in spec['stages']])
        title+=' / '+spec['date']
    else:title+=' / RS '+spec['comparison']['station']+' / '+spec['selected']
    c['title']=title
    save(dest/'geometry.json',g)
    auth=dict(project_id=child,scope=c['case_kind'],allowed_geometry_sha256=sha(dest/'geometry.json'),
              confirmed=True,field_feedback=ref,engineering_acceptance='NOT_ASSESSED',created_utc=utc())
    save(dest/'authorization.json',auth);save(dest/'project.json',c)
    survey_sources=[e for e in spec['sources'] if e.get('role') in ('survey_manifest','survey_source')]
    m=dict(id=child,project=rel(dest/'project.json'),active_project=rel(dest/'project.json'),title=title,
           model_type='river',route=parent['route'],revision=1,status='INPUTS_READY',phase='FIELD_CONFIRMED',
           gis=parent.get('gis',True),metadata=parent.get('metadata',{}),attachments=survey_sources,errors=[],created_utc=utc(),
           scenario=scenario,feedback_spec=ref,feedback_inputs=[item(dest/name) for name in ('project.json','geometry.json','authorization.json')],
           parent_revision=dict(project_id=parent['id'],summary=parent['summary']))
    parent_delivery=parent.get('latest_delivery') or {}
    if parent_delivery.get('mapped'):m['previous_delivery']=parent_delivery
    core.persist(m,'CONFIRM_FIELD_SCENARIO',dict(source=ref,assumed=spec['assumed']))


def execute(key):
    from . import cli,study,site_delivery
    m=core.model(key);spec=m['feedback_spec']
    if not intact([spec]) or not intact(read(ROOT/spec['path'])['sources']):raise ValueError('Field feedback or source evidence changed')
    if m.get('feedback_inputs') and not intact(m['feedback_inputs']):raise ValueError('Confirmed child inputs changed. Prepare a new review.')
    if not m.get('feedback_inputs') and not m.get('summary'):raise ValueError('Confirmed input receipt missing. Prepare a new review.')
    cp=ROOT/m['project'];cfg=read(cp);dest=cp.parent
    if not m.get('summary'):
        code=cli.execute(cp,m['scenario'],timeout=240)
        state=read(dest/'state.json')
        if code or state.get('calculation_status')!='COMPUTED':raise ValueError('Field scenario: '+str(state.get('errors') or state.get('status')))
        m.update(summary=state['latest_summary'],engine_state=rel(dest/'state.json'),phase='FIELD_DELIVERY')
        core.persist(m,'FIELD_COMPUTED')
    study.verified_case(dict(summary=m['summary']),cp,cfg)
    if not m.get('latest_delivery') or m['latest_delivery'].get('status') not in ('READY_FOR_REVIEW','READY_NATIVE_ONLY'):
        previous=m.get('previous_delivery') or {}
        reuse=previous.get('complete',{}).get('path') if previous.get('mapped') else None
        receipt=site_delivery.generate(ROOT/m['summary']['path'],dest/'exports'/unique_id()/'delivery',
                                       reuse_package=reuse,refresh_imagery_extent=True)
        m['latest_delivery']=receipt
        if receipt['status'] not in ('READY_FOR_REVIEW','READY_NATIVE_ONLY'):
            core.persist(m,'FIELD_DELIVERY_INCOMPLETE');raise ValueError('Delivery: '+str(receipt.get('error') or receipt.get('issues')))
    m.update(status='RESULTS_READY',phase='DONE',errors=[])
    core.persist(m,'FIELD_DELIVERY_FINISHED')
