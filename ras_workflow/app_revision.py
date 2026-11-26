"""New editable project revisions; solved projects and confirmations are immutable."""
import copy
import os
from .common import ROOT, read, save, item, rel, safe_path, intact, unique_id, utc, finite
from . import app_core as core, intake


def create(key, body):
    parent=core.model(key);core.require_idle(parent)
    if body.get('revision')!=parent['revision']:raise ValueError('Project changed; reload before revising')
    if body.get('confirmed') is not True:raise ValueError('Confirm creating an independent editable revision')
    return create_draft(parent,body)


def create_draft(parent,body,preparation_task=None,field_return=None):
    """Internal snapshot; a worker-owned task keeps its new draft read-only while preparing."""
    if preparation_task:
        task=read(ROOT/preparation_task)
        if (parent.get('task')!=preparation_task or task.get('project_id')!=parent['id']
                or task.get('status')!='RUNNING' or task.get('worker_pid',task.get('pid'))!=os.getpid()):
            raise ValueError('Automatic revision must belong to the current project worker')
    if parent.get('native_review'):raise ValueError('For native-model edits, edit a copy in HEC-RAS and import its input files as a new project')
    if not parent.get('summary') or not intact([parent['summary']]):raise ValueError('An intact completed calculation is required')
    from .app_parameters import objects
    sp,p,d,c,g=objects(parent)
    d=copy.deepcopy(d)
    source_base=(ROOT/p['project']).parent
    delivery_base=source_base
    delivery_settings=copy.deepcopy(c.get('delivery',{}))
    source=None
    if body.get('study_kind') or body.get('comparison_token'):
        from .study_revision import resolve, answers
        if body.get('comparison_token'):
            from .extent_review import revision_source
            source=revision_source(parent,body)
        else:source=resolve(parent,body)
        d['answers']=answers(d['answers'],c,g,source['config'],source['geometry'],parent['scenario'],source)
        d.pop('section_workflow',None)
        d['geometry_edit_sources']=d.get('geometry_edit_sources',[])+source['sources']
        c,g=source['config'],source['geometry']
        source_base=source['config_path'].parent
    key2=field_return['id'] if field_return else 'site_'+unique_id().lower()
    folder=core.folder(key2);folder.mkdir(parents=True)
    c=copy.deepcopy(c);g=copy.deepcopy(g)
    if field_return:
        from .field_return import apply_to_draft
        apply_to_draft(c,d,field_return)
    c['delivery']=delivery_settings
    for field in ('raster','provenance'):
        if c.get('terrain',{}).get(field):
            c['terrain'][field]=os.path.relpath(safe_path(source_base,c['terrain'][field]),folder)
            answer=d.get('answers',{}).get('c.terrain.'+field)
            if answer is not None:answer['value']=c['terrain'][field]
    for field in ('native_project','reference_results','benchmark_preparation'):
        if c.get(field):c[field]=os.path.relpath(safe_path(source_base,c[field]),folder)
    delivery=c.setdefault('delivery',{})
    delivery['additional_sources']=[os.path.relpath(safe_path(delivery_base,v),folder) for v in delivery.get('additional_sources',[])]
    imagery=delivery.get('imagery',{})
    if imagery.get('raster'):imagery['raster']=os.path.relpath(safe_path(delivery_base,imagery['raster']),folder)
    for field in ('authorization','configuration_approval','intake_candidates','section_workflow'):
        c.pop(field,None)
    title=parent['title']+' / '+source['case_id'] if source else parent['title']
    origin=source['summary'] if source else parent['summary']
    c['revision_origin']=dict(project_id=parent['id'],summary=origin)
    c.update(project_id=key2,title=title+' · revision',geometry='geometry.json',model_proposal_pending=True)
    from .bank_reach import refresh as refresh_retained_banks
    refresh_retained_banks(g)
    g.update(approved_for_model=False,status='EDITABLE_REVISION')
    save(folder/'geometry.json',g);save(folder/'initial.json',c)
    session=intake.prepare(folder/'initial.json',parent['scenario'])
    new_sp=ROOT/session['session'];draft=read(new_sp.parent/'draft.json')
    # Preserve explicit values and their origins, never reuse prior consent.
    for field in ('answers','uploads','section_workflow','geometry_edit_sources'):
        if field in d:draft[field]=copy.deepcopy(d[field])
    for answer in draft['answers'].values():answer['confirmed']=False
    draft.update(consent=False,reviewer=None,basis='Editable revision of an existing conditional calculation; confirm all current parameters before a new solve.')
    save(new_sp.parent/'draft.json',draft)
    m=copy.deepcopy(parent)
    m.pop('intake_return',None)
    if field_return:
        confirmed=parent.get('run_confirmation')
        prior_review=read(ROOT/confirmed['path']).get('review') if confirmed and intact([confirmed]) else None
        m['intake_return']=dict(mode=field_return['mode'],fields=[r['key'] for r in field_return['rows'] if field_return['mode']=='geometry'],
            sources=field_return['sources'],confirmation=confirmed,review=prior_review,
            summary=parent['summary'],parent_project=parent['project'])
    m.pop('compiled_checkpoint',None)
    m.pop('latest_question',None)
    m.pop('recovered_task',None)
    for field in ('summary','engine_state','active_project','latest_reports','latest_delivery','previous_delivery','run_confirmation','pending_review','task','run_scenario','exports_need_refresh','pending_study','active_study','latest_study','latest_spacing','latest_coverage','latest_coverage_exports','automatic_preparation','automatic_options','exit_code','sensitivity_suggestions','latest_reports_binding','pending_check_batch','active_check_batch','latest_check_batch','automatic_next_review',
                  'latest_geometry_comparison','latest_warning_study','river_observations','latest_observed_event','observed_event_history','native_export_attempt','assessment_area','extent_review','extent_decision'):
        m.pop(field,None)
    origin=source['summary'] if source else parent['summary']
    m.update(id=key2,title=c['title'],project=rel(folder/'initial.json'),session=session['session'],revision=0,
             status='INPUTS_READY',phase='EDIT_REVISION',errors=[],created_utc=utc(),
             parent_revision=dict(project_id=parent['id'],summary=origin,app=item(core.folder(parent['id'])/'app.json'),
                                  inherited_sources=[r['sha256'] for r in parent.get('attachments', [])],created_utc=utc()))
    if source:
        m['parent_revision'].update(geometry=source['geometry_source'],study=source['analysis'],case_id=source['case_id'])
        m['terrain']=source['terrain']
        m['automatic_options']=dict(maximum_width_ft=source['maximum_width_ft'])
    if preparation_task:
        m.update(task=preparation_task,status='PROCESSING',phase='PREPARING_JOINT_GEOMETRY')
    core.persist(m,'CREATE_EDITABLE_REVISION',dict(parent=parent['id'],summary=origin))
    if source and body.get('prepare') is True:
        try:
            core.launch(key2,'automatic-prepare')
        except ValueError as error:
            m.update(errors=[str(error)],phase='EDIT_REVISION')
            core.persist(m,'AUTOMATIC_PREPARATION_DEFERRED',dict(error=str(error)))
    return core.view(key2)


def compare(m,summary):
    parent=m.get('parent_revision')
    if not parent:return None
    if not intact([parent['summary']]):return dict(status='SOURCE_CHANGED',rows=[])
    old=read(ROOT/parent['summary']['path'])
    previous,current=old.get('hydraulics') or {},summary.get('hydraulics') or {}
    if not previous or not current:
        return dict(status='COMPARISON_UNAVAILABLE',rows=[],error='Both editions need computed hydraulics')
    if any(previous.get(key)!=current.get(key) for key in ('datum','unit','model_type','case_kind')):
        return dict(status='COMPARISON_INCOMPATIBLE',rows=[],error='Model type, datum, units or case kind differ')
    from .qa import verified_profiles,THRESHOLDS
    try:
        old_water,new_water=verified_profiles(previous),verified_profiles(current)
    except (ValueError,KeyError,OSError) as error:
        return dict(status='COMPARISON_UNAVAILABLE',rows=[],error=str(error))
    from .revision_inputs import collect, station_key
    def station_id(value):
        try:return station_key(value)
        except (TypeError,ValueError):return str(value).strip()
    def station_index(values):
        return {station_id(raw):raw for raw in values}
    input_context=collect(old,summary)
    locations={r['station']:r for r in input_context.get('geometry',{}).get('sections',[])}
    a={p['profile_id']:p for p in previous['profiles']};rows=[];sections=[];profiles=[]
    metrics=('upstream_wse_ft','downstream_wse_ft','max_channel_velocity_fts','max_channel_froude') if current.get('model_type')=='river' else (
        'headwater_wse_ft','tailwater_wse_ft','inlet_velocity_fts','roadway_flow_software_cfs')
    for p in current['profiles']:
        prior=a.get(p['profile_id'])
        if not prior:continue
        if p['flow_cfs']!=prior['flow_cfs']:
            return dict(status='COMPARISON_INCOMPATIBLE',rows=[],error='Matched profiles have different discharges')
        for field in metrics:
            x=prior.get('metrics',{}).get(field);y=p.get('metrics',{}).get(field)
            location_key={'upstream_wse_ft':'headwater_rs','headwater_wse_ft':'headwater_rs',
                          'downstream_wse_ft':'tailwater_rs','tailwater_wse_ft':'tailwater_rs'}.get(field)
            old_rs,new_rs=prior.get(location_key),p.get(location_key)
            location_status='NOT_LOCATION_SPECIFIC'
            if location_key:
                location_status='UNVERIFIED'
                if old_rs is not None and new_rs is not None:
                    location_status='MOVED' if station_id(old_rs)!=station_id(new_rs) else locations.get(station_id(new_rs),{}).get('location_status','UNVERIFIED')
            moved=location_status=='MOVED'
            rows.append(dict(profile=p['profile_id'],metric=field,previous=x,current=y,
                previous_station=old_rs,current_station=new_rs,location_status=location_status,
                location_changed=moved,change=y-x if finite(x) and finite(y) and location_status in ('SAME_CENTER','NOT_LOCATION_SPECIFIC') else None))
        left,right=old_water[p['profile_id']],new_water[p['profile_id']]
        old_ids,new_ids=station_index(left),station_index(right)
        if len(old_ids)!=len(left) or len(new_ids)!=len(right):
            return dict(status='COMPARISON_INCOMPATIBLE',rows=[],error='Ambiguous native station identifiers after matching numeric precision')
        matched=[]
        for key,prior_rs in old_ids.items():
            if key not in new_ids:continue
            rs=new_ids[key]
            if not finite(left[prior_rs]) or not finite(right[rs]):
                return dict(status='COMPARISON_UNAVAILABLE',rows=[],error='Nonfinite native water-surface value')
            location=locations.get(key,{})
            matched.append(dict(profile=p['profile_id'],station=rs,previous=left[prior_rs],current=right[rs],change=right[rs]-left[prior_rs],
                location_status=location.get('location_status','UNVERIFIED'),center_shift_ft=location.get('center_shift_ft'),
                changed_geometry_fields=location.get('changed_fields',[])))
        sections+=matched
        maximum=max(matched,key=lambda row:abs(row['change'])) if matched else None
        coincident=[r for r in matched if r['location_status']=='SAME_CENTER']
        profiles.append(dict(profile=p['profile_id'],matched_sections=len(matched),maximum=maximum,
            verified_center_count=len(coincident),maximum_at_verified_centers=max(coincident,key=lambda r:abs(r['change'])) if coincident else None,
            added_stations=[rs for k,rs in new_ids.items() if k not in old_ids],removed_stations=[rs for k,rs in old_ids.items() if k not in new_ids],
            exceeds_review_threshold=bool(maximum and abs(maximum['change'])>THRESHOLDS['sensitivity_hw_ft'])))
    if not profiles:
        return dict(status='COMPARISON_INCOMPATIBLE',rows=[],error='No matching profiles')
    from .river_review import overbank_changes
    overbanks = overbank_changes(old,summary,locations) if current.get('model_type')=='river' else None
    diagnostics=dict(previous=_diagnostic_summary(old),current=_diagnostic_summary(summary))
    from .revision_review import interpret,metric_rows
    review=interpret(diagnostics,profiles,old_water.keys()==new_water.keys(),THRESHOLDS['sensitivity_hw_ft'])
    from .revision_endpoints import summary as endpoint_summary
    review['endpoints']=endpoint_summary(previous,current,locations,old_water,new_water)
    from .revision_review import investigation
    review['investigation']=investigation(review,overbanks)
    review['metrics']=metric_rows(rows)
    field_sources=[]
    if current.get('model_type')=='river' and review['warning_delta'] is not None and review['warning_delta']<0:
        from .survey_events import records
        from .validation_plan import usable
        from .review_decisions import residual_regression
        from .field_results import collect as feedback, verified_observations
        paired=[]
        try:
            for edition in (old,summary):
                obs,refs=records(edition)
                extra,extra_refs=feedback(edition)
                if extra and extra['mode']=='event':
                    obs.extend(verified_observations(extra))
                field_sources.extend(refs+extra_refs)
                # The parent's holdouts define this historical diagnostic. A child's
                # recalibrated event never acquires a new independent validation role.
                paired.append(usable(obs,edition['configuration'].get('production_scope') or {}) if edition is old else obs)
            review['field_regression']=residual_regression(*paired,sections,review['warning_delta'])
        except (KeyError,OSError,ValueError) as error:
            review['field_regression_error']=str(error)
    diagnostic_sources=[ref for s,d in ((old,diagnostics['previous']),(summary,diagnostics['current']))
                        if d['status']=='VERIFIED' for ref in (s['hydraulics'].get('diagnostics'),s.get('native_supplement')) if ref]
    return dict(status='COMPARISON_NOT_ACCEPTANCE',parent=parent,rows=rows,cross_sections=sections,profiles=profiles,input_context=input_context,overbank_changes=overbanks,
        threshold_ft=THRESHOLDS['sensitivity_hw_ft'],
        unmatched_previous_profiles=sorted(a.keys()-new_water.keys()),
        unmatched_current_profiles=sorted(new_water.keys()-a.keys()),
        diagnostics=diagnostics,review=review,
        sources=[parent['summary'],previous['raw_hdf'],previous['raw_controller'],current['raw_hdf'],current['raw_controller']]+input_context['sources']+diagnostic_sources+field_sources)


def _diagnostic_summary(summary):
    """Retain full native coverage and numerical issues as distinct evidence."""
    hyd=summary['hydraulics']
    entry=hyd.get('diagnostics')
    if not entry or not intact([entry]):
        return dict(status='UNAVAILABLE',error='Diagnostic evidence missing or changed')
    try:
        data=read(ROOT/entry['path'])
        if data.get('run_id')!=hyd.get('run_id') or not data.get('sources') or not intact(data['sources']):
            raise ValueError('Diagnostic sources differ from this run')
        native_count=None
        severity=None
        if summary.get('native_supplement'):
            from .app_outputs import validate,diagnostics,FULL_SCOPES
            supplement=validate(summary['native_supplement'])
            bound=read(ROOT/supplement['summary']['path'])['hydraulics']
            if (bound['run_id'],bound['raw_hdf'])!=(hyd['run_id'],hyd['raw_hdf']):
                raise ValueError('Native messages belong to a different run')
            data=diagnostics(hyd,supplement)
            warnings=supplement.get('warnings')
            if warnings is not None:
                native_count=len(warnings['records'])
                if supplement['warning_scope'] in FULL_SCOPES:
                    severity={s:warnings['counts'].get(s,0) for s in ('WARNING','NOTE','ERROR')}
        wet_ends=[dict(profile=row['profile'],station=row['station'],side=row['evidence']['side'],
                       excess_ft=row['evidence']['exceedance_ft'])
                  for row in data['issues'] if row.get('code')=='WET_SECTION_EDGE']
        return dict(status='VERIFIED',counts=data['counts'],warning_coverage=data['warning_coverage'],wet_ends=wet_ends,severity=severity,
                    native_messages=native_count,issue_count=len(data['issues']))
    except (ValueError,KeyError,TypeError,OSError) as error:
        return dict(status='UNAVAILABLE',error=str(error))
