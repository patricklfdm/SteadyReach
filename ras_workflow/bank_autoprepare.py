"""Stage bounded morphology candidates in editable drafts, before solver consent."""
from . import bank_reassessment as banks
from .bank_review import inventory
from .common import ROOT, item, lock, read, save, unique_id, utc


def identity(row):
    return row.get('reach_id'), row.get('rs')


def protected(geometry, answers):
    """Remember saved controls even if a later DEM extension drops review metadata."""
    fixed = set()
    for row in inventory(geometry, answers)['sections']:
        answer = answers.get(row['field'], {})
        manual = bool(answer) and not any(answer.get(k) for k in
            ('automatic_preparation', 'inherited_spacing_bank'))
        if manual or not set(row['categories']) & {'inferred', 'missing'}:
            fixed.add(identity(row))
    return fixed


def prepare(geometry, draft, preserved=()):
    fixed = set(preserved) | protected(geometry, draft['answers'])
    indices = {i for i, row in enumerate(geometry['cross_sections']) if identity(row) in fixed}
    proposal = banks.propose(geometry, draft['answers'], 'inferred', locked=indices)
    proposal.update(input_hash=banks.context(geometry, draft), created_utc=utc(),
                    selection_mode='AUTOMATIC_EDITABLE_DRAFT')
    proposal['id'] = banks.proposal_id(proposal)
    selected = [r['index'] for r in proposal['rows'] if r['recommended']]
    updated = banks.adopt(geometry, draft, proposal, selected, automatic=True)[1] if selected else None
    return proposal, selected, updated


def stage(m, preserved=()):
    from . import app_core as core, intake
    if m.get('active_project') or m.get('native_review'):
        raise ValueError('Create an editable revision before preparing banks')
    sp = ROOT / m['session']
    with lock(sp.parent / 'session.lock'):
        _, _, packet, draft = intake._load(sp, active=False)
        _, geometry = intake._objects(packet, draft)
        proposal, selected, updated = prepare(geometry, draft, preserved)
        if updated is not None:
            path = sp.parent / 'events' / ('automatic_banks_' + unique_id() + '.json')
            save(path, dict(proposal=proposal, selected_indices=selected,
                            final_confirmation_required=True, engineering_acceptance='NOT_ASSESSED'))
            updated.setdefault('geometry_edit_sources', []).append(item(path, 'bank_reassessment'))
            save(sp.parent / 'draft.json', updated)
    if updated is not None:
        m['revision'] += 1
        m.pop('pending_review', None)
        m.pop('run_confirmation', None)
        core.persist(m, 'AUTOMATIC_BANK_DRAFT', dict(indices=selected, evidence=item(path)))
    return dict(staged_count=len(selected),
        rows=[{k: r[k] for k in ('index','rs','reach_id','before_ft','proposed_ft','confidence')}
              for r in proposal['rows'] if r['index'] in selected],
        deferred_count=sum(r['index'] not in selected for r in proposal['rows']),
        excluded=proposal['excluded'],
        attention_count=inventory((updated or {}).get('geometry', geometry),
                                  (updated or draft)['answers'])['attention_count'],
        final_confirmation_required=True, engineering_acceptance='NOT_ASSESSED')
