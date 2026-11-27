"""Small, explicit sensitivity batches from a completed baseline."""
from .common import ROOT,read,save,item,intact,unique_id,rel,finite,sha,utc
from . import app_core as core,study
from .river import is_river


def prepare(key,body):
    m=core.model(key);core.require_idle(m)
    return prepare_model(m,body)


def prepare_model(m,body,verified_changes=None):
    key=m['id']
    if body.get('revision')!=m['revision']:raise ValueError('Project changed; reload')
    if not m.get('active_project') or not m.get('summary') or not intact([m['summary']]):raise ValueError('Compute a baseline before preparing a sensitivity batch')
    if m.get('native_review'):raise ValueError('This batch editor currently supports workflow-built geometry only')
    if body.get('kind')=='warning_review':
        from .warning_study import prepare as prepare_warnings
        return prepare_warnings(m,body)
    if body.get('kind')=='observed_event':
        from .observed_event import prepare as prepare_event
        return prepare_event(m,body)
    if body.get('kind')=='river_geometry':
        from .river_comparison import prepare as compare_geometries
        return compare_geometries(m,body)
    if body.get('kind')=='river_factor_diagnostic':
        from .factor_study import prepare as prepare_factor
        return prepare_factor(m,body)
    if body.get('kind')=='spacing':
        from .section_spacing import prepare as prepare_spacing
        return prepare_spacing(m,body)
    if body.get('kind')=='coverage':
        from .coverage_study import prepare as prepare_coverage
        return prepare_coverage(m,body)
    choices=body.get('parameters',[])
    range_sources=[]
    if body.get('range_token'):
        from .sensitivity_ranges import resolve
        choices,range_sources=resolve(m,body)
    if not isinstance(choices,list) or not 1<=len(choices)<=4:raise ValueError('Choose 1–4 parameters (up to eight variants plus baseline)')
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
        topic='parameter_'+str(i+1);basis=v['basis'] if range_sources else 'Explicit user-selected sensitivity range; assumed, not a measured confidence interval.'
        if path.endswith('depth_blocked_ft'):
            rise=g['structure']['groups'][int(path.split('.')[1])]['rise_ft']
            if not 0<=low<high<rise:raise ValueError('Blockage depths must be nonnegative and below opening height')
            basis+=' DepthBlocked represents uniform bottom fill along the barrel, not a local inlet obstruction.'
        topics.append(dict(id=topic,measurement_action='Review site evidence and model response for '+path,evidence_status='ASSUMED_TEST_RANGE',range_basis=basis))
        if range_sources:topics[-1].update(parameter_path=path,range_record=v['range_record'])
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
    reused=[]
    if verified_changes:
        fresh=[]
        for case in cases:
            signature=tuple((v['path'],v['value']) for v in case['changes'])
            proof=verified_changes.get(signature)
            if proof:reused.append(dict(case=case['id'],changes=case['changes'],source=proof))
            else:fresh.append(case)
        cases=fresh
        if not cases:return dict(reused=reused,entry=None,plan=None)
    out=core.folder(key)/'studies'/unique_id();spec=dict(id='sensitivity',case_kind=c['case_kind'],purpose='User-selected local sensitivity comparison; not automatic design acceptance',sources=[m['summary']]+range_sources,measurement_topics=topics,cases=cases,delivery_enabled=False)
    save(out/'specification.json',spec);path=study.prepare(ROOT/m['active_project'],m['scenario'],out/'specification.json',out/'prepared')
    m['pending_study']=item(path);core.persist(m,'PREPARE_SENSITIVITY',dict(study=m['pending_study']))
    return dict(token=m['pending_study']['sha256'],entry=m['pending_study'],plan=read(path),reused=reused,warning='Each case is a real HEC-RAS run. Only the displayed ranges are tested; no interaction or convergence claim.')


def start(key,body):
    m=core.model(key);core.require_idle(m)
    entry=m.get('active_study',{}).get('study') if body.get('retry') is True else m.get('pending_study')
    if body.get('retry') is True:
        active=m.get('active_study',{})
        if not entry or not active.get('review') or not intact(list(active.values())):
            raise ValueError('Previous batch confirmation is missing or changed')
        if m.get('pending_study') and m['pending_study']!=entry:
            raise ValueError('A different preview is pending; review that preview before retrying a previous batch')
    if body.get('revision')!=m['revision'] or body.get('confirmed') is not True or not entry or body.get('token')!=entry['sha256'] or not intact([entry]):raise ValueError('Review the current study and explicitly confirm its cases')
    review_entry=confirmation(m,entry)
    m['active_study']=dict(study=entry,review=review_entry);core.persist(m,'CONFIRM_SENSITIVITY')
    return core.launch(key,'study')


def confirmation(m,entry):
    """Bind one displayed study; called only after explicit study/batch consent."""
    path=ROOT/entry['path'];plan=read(path)
    if m['summary'] not in plan['evidence']:raise ValueError('Baseline edition changed; prepare the study again')
    if plan.get('analysis_kind')=='section_spacing' and (plan.get('status')=='NO_ELIGIBLE_INTERVALS' or len(plan.get('cases',[]))!=3):raise ValueError('No complete nested spacing cases to confirm; review the excluded intervals')
    review=dict(study_sha256=sha(path),decision='APPROVE_CONDITIONAL_STUDY',policy=core.POLICY,confirmed=True,reviewer=None,
        basis='Displayed sensitivity cases confirmed for local computation; no named engineering approval.',approved_case_kind=plan['case_kind'],engineering_acceptance='NOT_ASSESSED',created_utc=utc())
    if plan.get('analysis_kind')=='river_observed_event':
        from .river_observations import current
        packet=current(m)
        if not packet or packet['source']!=plan['event']['observations']:raise ValueError('The reviewed observation table changed; prepare the event again')
        review['basis']='Confirmed the displayed event date, observed discharge and downstream boundary for an independent event computation.'
    if plan.get('analysis_kind')=='native_warning_review':
        review['basis']='Confirmed bounded terrain-only warning trials, inferred floodplain directions and bank-aligned DEM midpoints. Flow, boundaries and original banks remain fixed.'
    if plan.get('analysis_kind')=='river_geometry_comparison':
        review['basis']='Displayed fixed-direction extension and rotation-enabled geometry and bank candidates confirmed for two independent Q100 calculations with the original hydraulic inputs.'
    if plan.get('coverage_policy'):
        from .spacing_cycle import policy
        policy(plan)
        review['basis']='Confirmed displayed nested spacing and bounded actual-water exterior DEM extension of added sections only; shared profiles remain identical across levels. Original profiles, flow, boundaries, roughness, banks in plan and interior samples remain fixed. All original rounds are retained; geometric limits and the confirmed round/width limits stop automation.'
    if plan.get('analysis_kind')=='coverage_repair':
        review['basis']='Confirmed bounded actual-water exterior DEM extension batch, preserving original samples, bank plan positions, direction, flow, boundaries and roughness. Exterior overbank material and floodplain connectivity remain conditional.'
    review_path=path.parent/'local_confirmation.json'
    if plan.get('analysis_kind')=='river_factor_diagnostic':
        review['basis']=' | '.join(c.get('options',plan['options'])['basis'] for c in plan['cases'])
    if review_path.exists():
        study.reviewed(path,review_path)
    else:
        save(review_path,review)
    study.reviewed(path,review_path)
    return item(path.parent/'local_confirmation.json')


def execute(key):
    m=core.model(key);active=m['active_study']
    if not intact(list(active.values())):raise ValueError('Confirmed sensitivity changed')
    result=study.run(active['study']['path'],active['review']['path'])
    path=(ROOT/active['study']['path']).parent/'analysis.json'
    entry=item(path)
    result_field={'native_warning_review':'latest_warning_study','section_spacing':'latest_spacing','coverage_repair':'latest_coverage','river_geometry_comparison':'latest_geometry_comparison','river_observed_event':'latest_observed_event','river_factor_diagnostic':'latest_factor_diagnostic'}.get(result.get('analysis_kind'),'latest_study')
    m.update(status='RESULTS_READY',phase='STUDY_FINISHED',errors=[])
    m[result_field]=entry
    if result.get('analysis_kind')=='river_observed_event' and result['status']!='INCOMPLETE':
        history=m.setdefault('observed_event_history',[])
        if entry not in history:history.append(entry)
    if result.get('analysis_kind')=='coverage_repair':
        if result['status']!='INCOMPLETE':
            m.update(status='PROCESSING',phase='COVERAGE_EXPORTS')
            core.persist(m,'COVERAGE_COMPUTED',dict(status=result['status'],analysis=entry))
            from .coverage_study import export
            m['latest_coverage_exports']=export(result,m)
            exports=read(ROOT/m['latest_coverage_exports']['path'])
            if exports['delivery']['status']=='READY_FOR_REVIEW':m.pop('pending_study',None)
        m.update(status='RESULTS_READY',phase='STUDY_FINISHED')
    elif result['status']!='INCOMPLETE' or result.get('analysis_kind') not in ('river_geometry_comparison','river_observed_event','native_warning_review','river_factor_diagnostic'):
        m.pop('pending_study',None)
    m['exports_need_refresh']=True
    core.persist(m,'SENSITIVITY_FINISHED',dict(status=result['status'],analysis=entry))
