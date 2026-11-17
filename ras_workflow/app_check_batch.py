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


def prepare(key, body):
    model = core.model(key); core.require_idle(model)
    return prepare_model(model, body)


def prepare_model(model, body):
    key = model['id']; eligible(model)
    if body.get('revision') != model['revision']:
        raise ValueError('Project changed; reload before preparing checks')
    sensitivity = body.get('sensitivity', True)
    spacing = body.get('spacing', True)
    if type(sensitivity) is not bool or type(spacing) is not bool or not (sensitivity or spacing):
        raise ValueError('Select at least one check')
    rounds = body.get('maximum_rounds', 2)
    if type(rounds) is not int or not 0 <= rounds <= 3:
        raise ValueError('Choose zero to three added-section coverage rounds')
    steps = []; sources = [model['summary'], item(ROOT/model['active_project'])]; deferred = []
    if sensitivity:
        from .sensitivity_ranges import suggest_model
        packet = suggest_model(model, dict(revision=model['revision']))
        choices, deferred = adopted_choices(packet)
        sources += packet['sources']
        if choices:
            prepared = app_study.prepare_model(core.model(key), dict(revision=model['revision'], range_token=packet['token'], parameters=choices))
            steps.append(dict(id='sensitivity', status='READY', study=prepared['entry'],
                parameters=choices, maximum_calculations=len(prepared['plan']['cases'])))
        else:
            steps.append(dict(id='sensitivity', status='UNAVAILABLE', reason='NO_ADOPTED_RANGES', maximum_calculations=0))
    if spacing:
        if model.get('model_type') != 'river':
            steps.append(dict(id='spacing', status='UNAVAILABLE', reason='RIVER_SPACING_ONLY', maximum_calculations=0))
        else:
            options = dict(revision=model['revision'], kind='spacing', scope='automatic',
                           maximum_intervals=body.get('maximum_intervals', 12))
            if rounds:
                options['coverage_policy'] = dict(maximum_rounds=rounds, maximum_width_ft=body.get('maximum_width_ft', 2000))
            prepared = app_study.prepare_model(core.model(key), options)
            available = prepared['plan']['status'] != 'NO_ELIGIBLE_INTERVALS'
            steps.append(dict(id='spacing', status='READY' if available else 'UNAVAILABLE', study=prepared['entry'],
                reason=None if available else 'NO_ELIGIBLE_INTERVALS',
                maximum_calculations=len(prepared['plan']['cases'])*(1+rounds)))
    for step in steps:
        if step.get('study'):
            sources += [step['study'], *plan_sources(read(ROOT/step['study']['path']))]
    plan = dict(schema_version='checks_batch_1', project_id=key, baseline=model['summary'],
                active_project=model['active_project'], created_utc=utc(), steps=steps,
                options=dict(sensitivity=sensitivity, spacing=spacing, maximum_rounds=rounds,
                    maximum_intervals=body.get('maximum_intervals', 12),
                    maximum_width_ft=body.get('maximum_width_ft', 2000)),
                deferred_parameters=deferred, maximum_calculations=sum(s['maximum_calculations'] for s in steps),
                sources=list({e['path']: e for e in sources}.values()), refresh='delivery',
                status='REVIEW_REQUIRED' if any(s['status']=='READY' for s in steps) else 'NO_AVAILABLE_CHECKS',
                engineering_acceptance='NOT_ASSESSED')
    path = core.folder(key)/'check_batches'/unique_id()/'plan.json'; save(path, plan)
    model = core.model(key); model['pending_check_batch'] = item(path); model.pop('pending_study', None)
    core.persist(model, 'PREPARE_CHECK_BATCH', dict(plan=model['pending_check_batch']))
    return preview(model['pending_check_batch'])


def preview(entry):
    if not entry or not intact([entry]):
        return None
    plan = read(ROOT/entry['path'])
    if not intact([s['study'] for s in plan['steps'] if s.get('study')]):
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
            model['latest_spacing' if step['id']=='spacing' else 'latest_study'] = analysis
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
