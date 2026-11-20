"""One confirmed, bounded sequence of native checks and refreshed deliverables."""
import copy
from . import app_core as core, app_study, study
from .common import ROOT, intact, item, read, save, unique_id, utc


def eligible(model):
    if model.get('native_review') or not model.get('active_project') or not model.get('summary'):
        raise ValueError('Compute a workflow-built baseline before preparing checks')
    if not intact([model['summary']]):
        raise ValueError('Baseline summary changed')


def adopted_choices(packet):
    choices = []
    deferred = []
    for row in packet['parameters']:
        option = next((o for o in row['options'] if o['id'] == row.get('recommended_id')
                       and o.get('applicability_confirmed')), None)
        if row['inactive'] or option is None or len(choices) >= 4:
            deferred.append(dict(path=row['path'], reason=row['status']))
            continue
        choices.append(dict(path=row['path'], option_id=option['id'], low=option['low'], high=option['high']))
    return choices, deferred


def plan_sources(plan):
    return ([plan['specification']] + plan['source_inputs'] + plan['evidence']
            + [case[key] for case in plan['cases'] for key in ('draft', 'geometry')])


def validate(model, entry):
    eligible(model)
    if not entry or not intact([entry]):
        raise ValueError('Check batch preview changed; prepare it again')
    plan = read(ROOT / entry['path'])
    if (plan['project_id'] != model['id'] or plan['baseline'] != model['summary']
            or plan['active_project'] != model['active_project'] or not intact(plan['sources'])):
        raise ValueError('Check batch belongs to different or changed inputs')
    for step in plan['steps']:
        if step['status'] != 'READY':
            continue
        if not intact([step['study']]):
            raise ValueError('A prepared study changed')
        case_plan = read(ROOT / step['study']['path'])
        if plan['baseline'] not in case_plan['evidence'] or not intact(plan_sources(case_plan)):
            raise ValueError('Prepared case evidence differs from this baseline')
    return plan


def spacing_geometry(case):
    geometry=read(ROOT/case['geometry']['path'])
    if geometry.get('spacing_trial'):
        geometry['spacing_trial'].pop('created_utc',None)
    return geometry


def existing_checks(model):
    from .report_studies import collect
    from .river_review_report import collect as field_review
    path=ROOT/model['summary']['path'];summary=read(path)
    studies,sources=collect(path,summary)
    changes={};spacing=[]
    for s in studies:
        if s.get('coverage'):continue
        if s.get('convergence'):
            old=read(ROOT/s['analysis']['path'])
            spacing.append((read(ROOT/old['study']['path']),s['analysis']))
        else:
            for case in s['cases']:
                if case.get('changes'):
                    signature=tuple((v['path'],v['after']) for v in case['changes'])
                    changes[signature]=s['analysis']
    river,refs=field_review(path,summary)
    geom=None
    if river.get('comparison'):
        analysis=model['latest_geometry_comparison']
        geom=(read(ROOT/read(ROOT/analysis['path'])['study']['path']),analysis)
    return changes,spacing,geom,sources+refs


def prepare(key, body):
    model = core.model(key); core.require_idle(model)
    return prepare_model(model, body)


def prepare_model(model, body):
    key = model['id']; eligible(model)
    if body.get('revision') != model['revision']:
        raise ValueError('Project changed; reload before preparing checks')
    sensitivity = body.get('sensitivity', True)
    spacing = body.get('spacing', True)
    integrated=body.get('integrated',False)
    geometry=body.get('geometry',False)
    if type(integrated) is not bool or type(geometry) is not bool or (geometry and model.get('model_type')!='river'):
        raise ValueError('Choose supported river checks')
    if type(sensitivity) is not bool or type(spacing) is not bool or not (sensitivity or spacing or geometry):
        raise ValueError('Select at least one check')
    rounds = body.get('maximum_rounds', 2)
    if type(rounds) is not int or not 0 <= rounds <= 3:
        raise ValueError('Choose zero to three added-section coverage rounds')
    steps = []; sources = [model['summary'], item(ROOT/model['active_project'])]; deferred = []
    changes={};prior_spacing=[];comparison=None
    if integrated:
        changes,prior_spacing,comparison,refs=existing_checks(model);sources.extend(refs)
    if geometry:
        width=body.get('maximum_width_ft',2000)
        if comparison and comparison[0].get('maximum_width_ft')==width:
            steps.append(dict(id='geometry',status='REUSED',result=comparison[1],maximum_calculations=0))
        else:
            prepared=app_study.prepare_model(core.model(key),dict(kind='river_geometry',revision=model['revision'],maximum_width_ft=width))
            steps.append(dict(id='geometry',status='READY',study=prepared['entry'],maximum_calculations=len(prepared['plan']['cases'])))
    if sensitivity:
        from .sensitivity_ranges import current, suggest_model
        packet = current(model,strict=True) if body.get('parameters') is not None else suggest_model(model, dict(revision=model['revision']))
        if not packet:raise ValueError('Prepare and review the sensitivity ranges first')
        choices, deferred = adopted_choices(packet)
        if body.get('parameters') is not None:
            if body.get('range_token')!=packet['token']:raise ValueError('Sensitivity options changed; refresh the ranges')
            choices=body['parameters'];deferred=[]
        sources += packet['sources']
        if choices:
            options=dict(revision=model['revision'], range_token=packet['token'], parameters=choices)
            prepared = app_study.prepare_model(core.model(key),options,verified_changes=changes) if integrated else app_study.prepare_model(core.model(key),options)
            steps.append(dict(id='sensitivity', status='READY' if prepared['entry'] else 'REUSED', study=prepared['entry'],
                reused=prepared.get('reused',[]),parameters=choices,maximum_calculations=len((prepared['plan'] or {}).get('cases',[]))))
        else:
            steps.append(dict(id='sensitivity', status='UNAVAILABLE', reason='NO_ADOPTED_RANGES', maximum_calculations=0))
    if spacing:
        if model.get('model_type') != 'river':
            steps.append(dict(id='spacing', status='UNAVAILABLE', reason='RIVER_SPACING_ONLY', maximum_calculations=0))
        else:
            options = dict(revision=model['revision'], kind='spacing', scope=body.get('spacing_scope','automatic'),
                           maximum_intervals=body.get('maximum_intervals', 12))
            if rounds:
                options['coverage_policy'] = dict(maximum_rounds=rounds, maximum_width_ft=body.get('maximum_width_ft', 2000))
            prepared = app_study.prepare_model(core.model(key), options)
            available = prepared['plan']['status'] != 'NO_ELIGIBLE_INTERVALS'
            new=prepared['plan']
            fields=('scope','coverage_policy','intervals','excluded_intervals','deferred_intervals')
            proof=next((ref for prior,ref in prior_spacing if all(new.get(k)==prior.get(k) for k in fields)
                        and len(prior['cases'])==len(new['cases']) and all(spacing_geometry(x)==spacing_geometry(y) for x,y in zip(prior['cases'],new['cases']))),None)
            steps.append(dict(id='spacing',status='REUSED' if proof else 'READY' if available else 'UNAVAILABLE',
                study=prepared['entry'],result=proof,reason=None if available else 'NO_ELIGIBLE_INTERVALS',
                maximum_calculations=0 if proof or not available else len(new['cases'])*(1+rounds)))
    for step in steps:
        if step.get('study'):
            sources += [step['study'], *plan_sources(read(ROOT/step['study']['path']))]
    plan = dict(schema_version='checks_batch_1', project_id=key, baseline=model['summary'],
                active_project=model['active_project'], created_utc=utc(), steps=steps,
                options=dict(sensitivity=sensitivity, spacing=spacing,geometry=geometry,integrated=integrated,
                    spacing_scope=body.get('spacing_scope','automatic'),maximum_rounds=rounds,
                    maximum_intervals=body.get('maximum_intervals', 12),
                    maximum_width_ft=body.get('maximum_width_ft', 2000)),
                deferred_parameters=deferred, maximum_calculations=sum(s['maximum_calculations'] for s in steps),
                sources=list({e['path']: e for e in sources}.values()), refresh='delivery',
                status='REVIEW_REQUIRED' if any(s['status'] in ('READY','REUSED') for s in steps) else 'NO_AVAILABLE_CHECKS',
                engineering_acceptance='NOT_ASSESSED')
    path = core.folder(key)/'check_batches'/unique_id()/'plan.json'; save(path, plan)
    model = core.model(key); model['pending_check_batch'] = item(path); model.pop('pending_study', None)
    core.persist(model, 'PREPARE_CHECK_BATCH', dict(plan=model['pending_check_batch']))
    return preview(model['pending_check_batch'])


def preview(entry):
    if not entry or not intact([entry]):
        return None
    plan = read(ROOT/entry['path'])
    studies = [step['study'] for step in plan['steps'] if step.get('study')]
    if studies and not intact(studies):
        return None
    return dict(token=entry['sha256'], entry=entry, plan=plan,
        studies={s['id']: read(ROOT/s['study']['path']) for s in plan['steps'] if s.get('study')})


def start(key, body):
    model = core.model(key); core.require_idle(model)
    retry = body.get('retry') is True
    active = model.get('active_check_batch', {})
    entry = active.get('plan') if retry else model.get('pending_check_batch')
    if body.get('revision') != model['revision'] or body.get('confirmed') is not True or not entry or body.get('token') != entry['sha256']:
        raise ValueError('Confirm the current displayed check batch and limits')
    if retry and model.get('pending_check_batch') not in (None, entry):
        raise ValueError('A different check preview is pending')
    if not retry and active.get('plan') == entry and active.get('review'):
        raise ValueError('This batch is already confirmed; use Resume checks and delivery')
    plan = validate(model, entry)
    if plan['status'] != 'REVIEW_REQUIRED':
        raise ValueError('No available native checks; review the displayed exclusions')
    if retry:
        if not active.get('review') or not intact([active['review']]):
            raise ValueError('Original batch confirmation is missing or changed')
        review = read(ROOT/active['review']['path'])
        if review['plan'] != entry or review.get('confirmed') is not True:
            raise ValueError('Original batch confirmation differs')
    else:
        confirmations = {}
        for step in plan['steps']:
            if step['status'] == 'READY':
                confirmations[step['id']] = app_study.confirmation(model, step['study'])
        path = (ROOT/entry['path']).parent/'confirmation.json'
        save(path, dict(plan=entry, confirmed=True, created_utc=utc(), studies=confirmations,
            action='CONFIRM_CHECKS_AND_REFRESH_DELIVERABLES', engineering_acceptance='NOT_ASSESSED'))
        active = dict(plan=entry, review=item(path))
    model['active_check_batch'] = active
    core.persist(model, 'CONFIRM_CHECK_BATCH', dict(batch=active))
    return core.launch(key, 'check-batch')


def execute(key):
    model = core.model(key); active = model['active_check_batch']; plan = validate(model, active['plan'])
    if not intact([active['review']]):
        raise ValueError('Check batch confirmation changed')
    review = read(ROOT/active['review']['path'])
    if review['plan'] != active['plan'] or review.get('confirmed') is not True:
        raise ValueError('Check batch confirmation differs')
    path = (ROOT/active['plan']['path']).parent/'execution.json'
    journal = read(path) if path.exists() else dict(plan=active['plan'], review=active['review'], steps={})
    if journal['plan'] != active['plan'] or journal['review'] != active['review']:
        raise ValueError('Check batch execution identity differs')
    if journal.get('error'):
        journal.setdefault('previous_failures', []).append(dict(error=journal.pop('error'),
            stopped_utc=journal.pop('stopped_utc', None), steps=copy.deepcopy(journal['steps'])))
    journal.update(status='RUNNING', started_utc=journal.get('started_utc', utc()))
    def record(step, status, **extra):
        journal['steps'][step] = dict(status=status, **extra); save(path, journal)
    current_step = None
    try:
        for step in plan['steps']:
            current_step = step['id']
            if step['status']=='REUSED':
                record(step['id'],'REUSED',reused=step.get('reused',[]),source=step.get('result'));continue
            if step['status'] != 'READY':
                record(step['id'], 'UNAVAILABLE', reason=step['reason']); continue
            confirmation = review['studies'][step['id']]
            if not intact([confirmation]):
                raise ValueError('Child study confirmation changed')
            study.reviewed(step['study']['path'], confirmation['path'])
            model = core.model(key)
            model.update(status='PROCESSING', phase='CHECK_BATCH_'+step['id'].upper(),
                         active_study=dict(study=step['study'], review=confirmation))
            core.persist(model, 'CHECK_BATCH_STAGE', dict(stage=step['id']))
            record(step['id'], 'RUNNING')
            # The study runner authenticates completed native cases on retry.
            result = study.run(step['study']['path'], confirmation['path'])
            analysis = item((ROOT/step['study']['path']).parent/'analysis.json')
            if result['status'] == 'INCOMPLETE' or result.get('failed_cases'):
                record(step['id'], 'INCOMPLETE', analysis=analysis)
                raise ValueError('Native check incomplete; saved cases remain available for retry')
            record(step['id'], 'COMPLETED', analysis=analysis, assessment=result['status'])
            model = core.model(key)
            model[{'spacing':'latest_spacing','sensitivity':'latest_study','geometry':'latest_geometry_comparison'}[step['id']]] = analysis
            model['exports_need_refresh'] = True
            core.persist(model, 'CHECK_BATCH_STUDY_FINISHED', dict(stage=step['id'], analysis=analysis))
        model = core.model(key); model.update(status='PROCESSING', phase='CHECK_BATCH_DELIVERY')
        current_step = 'delivery'
        core.persist(model); record('delivery', 'RUNNING')
        core.regenerate(key, 'delivery')
        model = core.model(key); delivery = model.get('latest_delivery') or {}
        if model.get('exports_need_refresh') or delivery.get('status') not in ('READY_FOR_REVIEW','READY_NATIVE_ONLY','READY'):
            raise ValueError('Checks are saved; delivery is incomplete: '+str(delivery.get('error') or delivery.get('status')))
        record('delivery', 'COMPLETED', reports=model['latest_reports'], delivery=delivery)
        journal.update(status='COMPLETED_WITH_LIMITATIONS', finished_utc=utc(), hydraulic_qa='REVIEW_REQUIRED', engineering_acceptance='NOT_ASSESSED')
        save(path, journal)
        final_path=path.parent/'analysis.json';save(final_path,journal)
        model['latest_check_batch']=item(final_path);model.pop('pending_check_batch',None)
        model.update(status='RESULTS_READY',phase='CHECK_BATCH_FINISHED',errors=[])
        core.persist(model,'CHECK_BATCH_FINISHED',dict(analysis=model['latest_check_batch']))
    except Exception as error:
        if current_step:
            failed=journal['steps'].setdefault(current_step,{})
            failed.update(status='INCOMPLETE',error=str(error))
        journal.update(status='INCOMPLETE',error=str(error),stopped_utc=utc());save(path,journal)
        raise


def progress(model):
    active=model.get('active_check_batch')
    if not active:return None
    path=(ROOT/active['plan']['path']).parent/'execution.json'
    if not path.exists():return dict(status='QUEUED',steps={})
    journal=read(path)
    if journal['plan']!=active['plan'] or journal['review']!=active['review']:
        raise ValueError('Check batch progress identity differs')
    return journal
