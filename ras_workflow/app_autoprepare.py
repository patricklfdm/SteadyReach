"""Prepare an editable conditional draft; the existing final confirmation gates solving."""
import copy
from .common import digest, item, save, unique_id, utc
from . import app_core as core, app_parameters as params, intake


def queue(key, body):
    m = core.model(key)
    core.require_idle(m)
    if body.get('revision') != m['revision']:
        raise ValueError('Project changed; refresh before automatic preparation')
    if m.get('active_project') or m.get('native_review'):
        raise ValueError('Create an editable revision before automatic preparation')
    return core.launch(key, 'automatic-prepare')


def select_candidate(field, g, estimates):
    choices = field.get('parameter_candidates', [])
    sources = [c for c in choices if c.get('source')]
    if sources:
        if any(c.get('requires_applicability_review') for c in sources):
            return None
        values = {digest(c['value']) for c in sources}
        if len(values) != 1:
            return None
        # Conditional source wording must survive duplicate, less-qualified mentions.
        return next((c for c in sources if c['evidence_class'] == 'assumed'), sources[0])
    sourced = [c for c in choices if c.get('source_derived')]
    if sourced:
        return sourced[0] if len({digest(c['value']) for c in sourced}) == 1 else None
    if not estimates:
        choices = [c for c in choices if c['evidence_class'] in ('derived', 'model_setting', 'terrain_derived')]
    if not choices:
        return None
    if len({digest(c['value']) for c in choices}) == 1:
        return choices[0]
    key = field['key']
    target = None
    if estimates and key.endswith(('.chart_scale','.entrance_loss','.culvert_n')):
        baseline=[c for c in choices if c['basis'].startswith('Conditional') and ('baseline' in c['basis'] or 'concrete-box' in c['basis'])]
        if baseline:
            return baseline[-1]
    if estimates and key == 'g.flow_regime':
        target = 'mixed'
    if estimates and key.endswith('.expansion_contraction'):
        i = int(key.split('.')[2])
        rows = g['cross_sections']
        face = next((j for j, r in enumerate(rows) if r['rs'] == g['structure'].get('us_xs_rs')), -100)
        target = [.5, .3] if i in (face-1, face, face+1) else [.3, .1]
    return next((c for c in choices if c['value'] == target), None)


def fill(m, estimates=True, owned_only=False):
    """Resolve dependent values in memory, then save one draft transaction."""
    sp, packet, original, c, g = params.objects(m)
    draft = copy.deepcopy(original)
    changes = {}
    invalidated = set()
    settled = False
    for _ in range(12):
        c, g = intake._objects(packet, draft)
        rows = params.rows(m, context=(sp, packet, draft, c, g))
        if g.get('bank_reach_summary'):
            draft['geometry']['bank_reach_summary']=copy.deepcopy(g['bank_reach_summary'])
            for target,row in zip(draft['geometry']['cross_sections'],g['cross_sections']):
                target['bank_candidates']=copy.deepcopy(row.get('bank_candidates'))
        batch = {}
        for field in rows:
            previous = draft['answers'].get(field['key'], {})
            owned = previous.get('automatic_preparation') is True
            if owned_only and not owned:
                continue
            if not field['missing'] and not owned:
                continue
            choice = select_candidate(field, g, estimates)
            if choice is None:
                if owned and not field['missing']:
                    batch[field['key']] = dict(value=None, evidence_class='missing', confirmed=False,
                        automatic_preparation=True, basis='Automatic candidate is unavailable or conflicting after input changes. Review current sources or edit this field.')
                    invalidated.add(field['key'])
                continue
            old_record = previous.get('candidate_record', {})
            context_changed = owned and any(choice.get(k) != old_record.get(k) for k in
                ('automation_context', 'source', 'sources', 'basis', 'evidence_class'))
            if choice['value'] == field['value'] and not field['missing'] and not context_changed:
                continue
            batch[field['key']] = dict(value=choice['value'], evidence_class=choice['evidence_class'],
                                      basis=choice['basis'], candidate_record=choice, confirmed=False,
                                      automatic_preparation=True)
        if not batch:
            settled = True
            break
        draft['answers'].update(batch)
        changes.update(batch)
    bank_summary=g.get('bank_reach_summary')
    c, g = intake._objects(packet, draft)
    # Derived source labels remove bookkeeping text entry while keeping the
    # individual numbers and source hashes in the input register.
    for field in ([] if owned_only else intake.fields(c, g, m['scenario'])):
        if field['key'].endswith(('.source', '.parameter_source')) and field['value'] in (None, ''):
            value = 'See the parameter input register for source files, derivations and conditional assumptions.'
            draft['answers'][field['key']] = dict(value=value, evidence_class='model_setting', basis=value, confirmed=False)
            changes[field['key']] = draft['answers'][field['key']]
    if changes:
        draft.update(consent=False, reviewer=None, basis='Automatically prepared editable draft; final user confirmation is pending.')
        intake.save_draft(sp, draft, refresh_banks=True)
        m['revision'] += 1
        m.pop('pending_review', None)
        m.pop('run_confirmation', None)
        core.persist(m, 'AUTOMATIC_PARAMETER_DRAFT', dict(fields=list(changes)))
    rows = params.rows(m)
    return dict(changed_fields=list(changes), invalidated_fields=sorted(invalidated), dependencies_settled=settled,
                bank_reach=bank_summary,
                missing_required=[f['key'] for f in rows if f['required'] and f['missing']],
                conflicts=[f['key'] for f in rows if f.get('source_conflict')],
                assumptions=[f['key'] for f in rows if f['evidence_class'] in ('assumed', 'inferred')])


def execute(key):
    m = core.model(key)
    if m.get('active_project') or m.get('native_review'):
        raise ValueError('Create an editable revision before automatic preparation')
    from .app_acquisition import analyze, progress
    progress(m, 'Extracting materials / 提取资料')
    analyze(key, network=False, reuse_failed=True)
    m = core.model(key)
    before = params.binding(m)
    from . import bank_autoprepare
    protected_banks = bank_autoprepare.protected(before['geometry'], before['answers'])
    results = [fill(m)]
    m = core.model(key)
    from .terrain_extent_auto import ensure as ensure_extent
    progress(m, 'Checking DEM coverage / 检查 DEM 范围')
    extent = ensure_extent(m, m.get('automatic_options'))
    m = core.model(key)
    g = params.objects(m)[4]
    proposal = None
    geometry_applied = False
    from . import app_geometry_auto
    # With only endpoints the physical channel has not been identified through bends.
    # Build that preview after parameter refresh so it reopens with a current signature.
    river_picks=m.get('map_picks', {}).get('river', [])
    preview_route = not g['cross_sections'] and g.get('model_type') == 'river' and (
        len(river_picks)==2 or (not river_picks and m.get('public_reach')))
    progress(m, 'Preparing DEM geometry / 准备 DEM 几何')
    try:
        proposal = None if preview_route else app_geometry_auto.prepare(m, dict(
            mode='qa' if g['cross_sections'] else 'initial', **m.get('automatic_options', {})))
        usable = [v for v in proposal['layouts'] if v['can_apply'] and not v.get('requires_lateral_review')] if proposal else []
        if usable:
            layout = usable[0]
            app_geometry_auto.apply(m, dict(proposal_id=proposal['id'], token=proposal['token'],
                                            layout_id=layout['id'], confirmed=True))
            geometry_applied = True
    except ValueError as error:
        # Inputs remain recoverable, and missing terrain metadata becomes a
        # focused action instead of losing successful source extraction.
        proposal = dict(error=str(error), layouts=[])
    m = core.model(key)
    progress(m, 'Preparing inherited bank candidates / 准备继承岸站候选')
    bank_preparation = bank_autoprepare.stage(m, protected_banks)
    m = core.model(key)
    progress(m, 'Filling dependent draft values / 填入关联草稿参数')
    results.append(fill(m))
    m = core.model(key)
    refreshed = params.refresh_equivalent_candidates(m)
    if preview_route:
        try:
            proposal = app_geometry_auto.prepare(m, dict(mode='initial', **m.get('automatic_options', {})))
        except ValueError as error:
            proposal = dict(error=str(error), layouts=[])
    record = dict(created_utc=utc(), input_signature=digest(before), stages=results,
                  bank_preparation=bank_preparation,
                  refreshed_equivalent_fields=[r['field'] for r in refreshed],
                  terrain_extent=extent, geometry_applied=geometry_applied, geometry_proposal=proposal,
                  solver_run=False, final_confirmation_required=True,
                  attention=params.attention(m, params.rows(m), automatic=True))
    target = core.folder(key)/'automatic_preparation'/unique_id()/'summary.json'
    save(target, record)
    m.update(automatic_preparation=item(target), status='INPUTS_READY', phase='REVIEW_AUTOMATIC_DRAFT', errors=[])
    core.persist(m, 'AUTOMATIC_PREPARATION_FINISHED', dict(summary=m['automatic_preparation']))
