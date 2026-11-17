"""Small, explicit sensitivity batches from a completed baseline."""
from .common import ROOT,read,save,item,intact,unique_id,rel,finite,sha,utc
from . import app_core as core,study
from .river import is_river


def prepare(key,body):
    m=core.model(key);core.require_idle(m)
    if body.get('revision')!=m['revision']:raise ValueError('Project changed; reload')
    if not m.get('active_project') or not m.get('summary') or not intact([m['summary']]):raise ValueError('Compute a baseline before preparing a sensitivity batch')
    if m.get('native_review'):raise ValueError('This batch editor currently supports workflow-built geometry only')
    choices=body.get('parameters',[])
    if not isinstance(choices,list) or not 1<=len(choices)<=3:raise ValueError('Choose 1–3 parameters (up to six variants plus baseline)')
    c=read(ROOT/m['active_project']);g=read((ROOT/m['active_project']).parent/c['geometry']);sc=next(s for s in c['scenarios'] if s['id']==m['scenario'])
    allowed={'scenario.channel_n','scenario.overbank_n','boundary_slopes.upstream','boundary_slopes.downstream'}
    allowed|={f'groups.{i}.depth_blocked_ft' for i in range(len(g['structure']['groups']))}
    if is_river(g):
        for side in ('upstream','downstream'):
            if g.get('boundaries',{}).get(side,{}).get('type')!='normal_depth' or side=='upstream' and g.get('flow_regime')=='subcritical':allowed.discard('boundary_slopes.'+side)
        if g.get('boundaries',{}).get('downstream',{}).get('type')=='known_stage':
            allowed|={f'boundaries.downstream.stages_ft.{i}' for i in range(len(sc['profiles']))}
    topics=[];cases=[];seen=set()
    for i,v in enumerate(choices):
        path=v.get('path');low=v.get('low');high=v.get('high')
        if path not in allowed or path in seen or not all(finite(x) and not isinstance(x,bool) for x in (low,high)) or low>=high:raise ValueError('Unique supported parameters and finite low < high values required')
        seen.add(path)
        if path.startswith('scenario.') and any(r.get('manning_segments') for r in g['cross_sections']):raise ValueError('Explicit section roughness subdivisions override scenario roughness; revise those subdivisions before testing this parameter')
        if path=='boundary_slopes.upstream' and g.get('flow_regime')=='subcritical':raise ValueError('This subcritical plan does not use the upstream normal-depth boundary')
        topic='parameter_'+str(i+1);basis='Explicit user-selected sensitivity range; assumed, not a measured confidence interval.'
        if path.endswith('depth_blocked_ft'):
            rise=g['structure']['groups'][int(path.split('.')[1])]['rise_ft']
            if not 0<=low<high<rise:raise ValueError('Blockage depths must be nonnegative and below opening height')
            basis+=' DepthBlocked represents uniform bottom fill along the barrel, not a local inlet obstruction.'
        topics.append(dict(id=topic,measurement_action='Review site evidence and model response for '+path,evidence_status='ASSUMED_TEST_RANGE',range_basis=basis))
        for suffix,value in [('low',low),('high',high)]:
            current=sc[path.split('.')[1]] if path.startswith('scenario.') else g['boundary_slopes'][path.split('.')[1]] if path.startswith('boundary_slopes.') else g['boundaries']['downstream']['stages_ft'][int(path.split('.')[-1])] if path.startswith('boundaries.') else g['structure']['groups'][int(path.split('.')[1])].get('depth_blocked_ft')
            if value==current:continue
            changes=[dict(path=path,value=value,basis=basis)]
            if path.endswith('depth_blocked_ft'):changes.append(dict(path=path.rsplit('.',1)[0]+'.blockage_basis',value=basis,basis=basis))
            try:study.apply_changes(g,sc,changes,c['case_kind'])
            except ValueError as e:
                if str(e)=='Variant does not change any parameter':continue
                raise
            cases.append(dict(id=topic+'_'+suffix,topic=topic,changes=changes))
    if not cases:raise ValueError('The selected range does not change baseline inputs')
    out=core.folder(key)/'studies'/unique_id();spec=dict(id='sensitivity',case_kind=c['case_kind'],purpose='User-selected local sensitivity comparison; not automatic design acceptance',sources=[m['summary']],measurement_topics=topics,cases=cases,delivery_enabled=False)
    save(out/'specification.json',spec);path=study.prepare(ROOT/m['active_project'],m['scenario'],out/'specification.json',out/'prepared')
    m['pending_study']=item(path);core.persist(m,'PREPARE_SENSITIVITY',dict(study=m['pending_study']))
    return dict(token=m['pending_study']['sha256'],plan=read(path),warning='Each case is a real HEC-RAS run. Only the displayed ranges are tested; no interaction or convergence claim.')


def start(key,body):
    m=core.model(key);core.require_idle(m);entry=m.get('pending_study')
    if body.get('revision')!=m['revision'] or body.get('confirmed') is not True or not entry or body.get('token')!=entry['sha256'] or not intact([entry]):raise ValueError('Review the current study and explicitly confirm its cases')
    path=ROOT/entry['path'];plan=read(path)
    if m['summary'] not in plan['evidence']:raise ValueError('Baseline edition changed; prepare the study again')
    review=dict(study_sha256=sha(path),decision='APPROVE_CONDITIONAL_STUDY',policy=core.POLICY,confirmed=True,reviewer=None,
        basis='Displayed sensitivity cases confirmed for local computation; no named engineering approval.',approved_case_kind=plan['case_kind'],engineering_acceptance='NOT_ASSESSED',created_utc=utc())
    save(path.parent/'local_confirmation.json',review);study.reviewed(path,path.parent/'local_confirmation.json')
    m['active_study']=dict(study=entry,review=item(path.parent/'local_confirmation.json'));core.persist(m,'CONFIRM_SENSITIVITY')
    return core.launch(key,'study')


def execute(key):
    m=core.model(key);active=m['active_study']
    if not intact(list(active.values())):raise ValueError('Confirmed sensitivity changed')
    result=study.run(active['study']['path'],active['review']['path'])
    path=(ROOT/active['study']['path']).parent/'analysis.json'
    m.update(latest_study=item(path),status='RESULTS_READY',phase='STUDY_FINISHED',errors=[])
    core.persist(m,'SENSITIVITY_FINISHED',dict(status=result['status'],analysis=m['latest_study']))
