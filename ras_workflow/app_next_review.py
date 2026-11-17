"""Prepare the next result review without granting calculation consent."""
from . import app_core as core
from .common import ROOT, intact, item, read, save, unique_id, utc


def queue(key, body):
    model = core.model(key)
    core.require_idle(model)
    if body.get('revision') != model['revision']:
        raise ValueError('Project changed; reload before preparing the next review')
    if not model.get('summary') or not model.get('active_project'):
        raise ValueError('Compute a baseline first')
    from .qa_review import load_summary
    if not intact([model['summary']]):
        raise ValueError('Baseline summary changed')
    load_summary(ROOT/model['summary']['path'])
    return core.launch(key, 'next-review')


def prepare(model):
    from .qa_review import load_summary
    from .qa_locator import collect
    from . import app_check_batch, coverage_study
    record = dict(schema_version='next_review_1', project_id=model['id'], baseline=model.get('summary'),
                  active_project=model.get('active_project'), created_utc=utc(), solver_started=False,
                  engineering_acceptance='NOT_ASSESSED', status='UNAVAILABLE', action=None)
    if model.get('native_review'):
        return dict(record, reason='IMPORTED_NATIVE_MODEL')
    app_check_batch.eligible(model)
    config_entry = item(ROOT/model['active_project'])
    record['sources'] = [model['summary'], config_entry]
    _, summary, hyd = load_summary(ROOT/model['summary']['path'])
    if read(ROOT/config_entry['path']) != summary['configuration']:
        raise ValueError('Baseline configuration changed; review the current model')
    # Never replace a pending user-selected scope, or repeat a completed repair
    # against its retained, earlier baseline.
    for field in ('pending_study', 'pending_check_batch'):
        if model.get(field):
            if not intact([model[field]]):
                raise ValueError('Existing preview changed; prepare it again in its review panel')
            return dict(record, reason='EXISTING_PREVIEW', existing_preview=model[field])
    if model.get('latest_coverage'):
        return dict(record, reason='EXISTING_COVERAGE_RESULT')
    wet = sorted({float(row['rs']) for row in collect(hyd)['rows']
                  if row['left_excess_ft'] > 0 or row['right_excess_ft'] > 0}, reverse=True)
    record['wet_sections'] = wet
    if wet:
        record.update(action='coverage', reason='WET_SECTION_ENDS')
        if model.get('model_type') != 'river':
            return dict(record, status='GEOMETRY_REVIEW_REQUIRED', reason='STRUCTURE_GEOMETRY_REVIEW')
        options = dict(maximum_rounds=3, maximum_width_ft=2000)
        proposed = coverage_study.prepare(model, options)
        preview = proposed['preview']
        record.update(preview=proposed['entry'], options=options,
                      changes=len(preview['changes']), unresolved=preview['unresolved'],
                      status='PREVIEW_READY' if preview['changes'] else 'GEOMETRY_REVIEW_REQUIRED',
                      reason='WET_SECTION_ENDS' if preview['changes'] else 'NO_COMPATIBLE_EXTENSION')
    else:
        record.update(action='checks', reason='NO_WET_SECTION_ENDS')
        options = dict(revision=model['revision'], sensitivity=True, spacing=model.get('model_type') == 'river',
                       maximum_intervals=12, maximum_rounds=2, maximum_width_ft=2000)
        proposed = app_check_batch.prepare_model(model, options)
        record.update(preview=proposed['entry'], options=options,
                      maximum_calculations=proposed['plan']['maximum_calculations'],
                      status='PREVIEW_READY' if proposed['plan']['status'] == 'REVIEW_REQUIRED' else 'NO_AVAILABLE_CHECKS')
    return record


def execute(key):
    """Runs inside the normal worker; failure cannot erase a computed result."""
    model = core.model(key)
    status, phase = model['status'], model.get('phase', 'DONE')
    if status == 'PROCESSING':
        state = read(ROOT/model['engine_state'])
        if state.get('calculation_status') != 'COMPUTED':
            raise ValueError('A completed baseline is required for next-review preparation')
        status = 'RESULTS_READY_MAP_PENDING' if (state.get('delivery') or {}).get('status') == 'INCOMPLETE' else 'RESULTS_READY'
        phase = 'DONE'
    try:
        record = prepare(model)
    except Exception as exc:
        record = dict(schema_version='next_review_1', project_id=key, baseline=model.get('summary'),
                      active_project=model.get('active_project'), status='PREPARATION_FAILED', error=str(exc),
                      created_utc=utc(), solver_started=False, engineering_acceptance='NOT_ASSESSED')
    path = core.folder(key)/'next_reviews'/unique_id()/'review.json'
    save(path, record)
    latest = core.model(key)
    latest.update(automatic_next_review=item(path), status=status, phase=phase)
    core.persist(latest, 'PREPARE_NEXT_REVIEW', dict(review=latest['automatic_next_review']))
    return record


def current(model):
    entry = model.get('automatic_next_review')
    if not entry or not intact([entry]):
        return None
    record = read(ROOT/entry['path'])
    if (record.get('baseline') != model.get('summary') or record.get('active_project') != model.get('active_project')
            or record.get('sources') and not intact(record['sources'])):
        return None
    if record.get('preview'):
        field = 'pending_study' if record['action'] == 'coverage' else 'pending_check_batch'
        active = model.get('active_study' if record['action'] == 'coverage' else 'active_check_batch', {})
        if record['preview'] == active.get('study' if record['action'] == 'coverage' else 'plan'):
            return dict(record, status='CONFIRMED_SEPARATELY')
        if record['preview'] != model.get(field) or not intact([record['preview']]):
            return None
        plan = read(ROOT/record['preview']['path'])
        sources = plan.get('sources') if record['action'] == 'checks' else plan['source_inputs']+plan['evidence']
        if not intact(sources):
            return None
    return record
