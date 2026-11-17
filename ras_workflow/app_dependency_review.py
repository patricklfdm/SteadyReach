"""Explicit, atomic choices for changed derivations in the final input review."""
import copy
from . import app_core as core, app_parameters as parameters, intake
from .app_automation import dependency, preflight
from .common import ROOT, digest, intact, read, utc


def resolve(key, body):
    m = core.model(key)
    core.require_idle(m)
    if m.get('active_project') or m.get('native_review'):
        raise ValueError('Create an editable revision first / 请先建立可编辑修订版')
    entry = m.get('pending_review')
    if (body.get('revision') != m['revision'] or not entry or not intact([entry])
            or body.get('review_token') != entry['sha256']):
        raise ValueError('Review changed; refresh the parameter list / 核对已变化，请刷新参数清单')
    review = read(ROOT / entry['path'])
    if review['fingerprint'] != digest(parameters.binding(m)):
        raise ValueError('Inputs changed; refresh the parameter list / 输入已变化，请刷新参数清单')
    selections = body.get('selections')
    if not isinstance(selections, list) or not selections or len(selections) > len(review['fields']):
        raise ValueError('Choose the changed inputs to save / 请选择要保存的关联参数')
    sp, packet, original, config, geometry = parameters.objects(m)
    draft = copy.deepcopy(original)
    affected = {q.get('field') for q in preflight(m, geometry)['issues']
                if q['code'] == 'DERIVED_INPUT_CHANGED'}
    available = {f['key']: f for f in parameters.rows(m)}
    changes = []
    seen = set()
    for selection in selections:
        field = selection.get('field')
        if field not in affected or field in seen:
            raise ValueError('Select each changed input once / 每个待复核参数只能选择一次')
        seen.add(field)
        row = available.get(field)
        if row is None:
            raise ValueError('Input no longer applies; refresh / 参数已不适用，请刷新')
        previous = copy.deepcopy(draft['answers'].get(field, {}))
        action = selection.get('action')
        if action == 'candidate':
            choice = next((c for c in row['parameter_candidates']
                           if c['candidate'] == selection.get('candidate')), None)
            if choice is None:
                raise ValueError('Candidate changed; refresh / 候选已变化，请刷新')
            answer = {k: copy.deepcopy(choice[k]) for k in ('value', 'evidence_class', 'basis')}
            answer.update(candidate_record=copy.deepcopy(choice), confirmed=False)
            if any(digest(s) == choice['candidate'] for s in row.get('suggestions', [])):
                answer['suggestion'] = choice['candidate']
        elif action == 'retain':
            if row['missing']:
                raise ValueError('A missing value cannot be retained / 缺失值不能作为假设保留')
            answer = dict(value=copy.deepcopy(row['value']), evidence_class='assumed', confirmed=False,
                          basis='Explicitly retained after reviewing changed derivation dependencies; conditional assumption, not a newly derived or measured value.')
        else:
            raise ValueError('Choose a current candidate or explicitly retain the saved assumption / 请采用当前候选或明确保留原值为假设')
        answer['dependency_review'] = dict(action=action, context=dependency(m, geometry, field),
                                           previous_answer=previous, review=entry, created_utc=utc())
        draft['answers'][field] = answer
        changes.append(dict(field=field, action=action, before=previous, after=answer))
    # Validate the complete batch before any write; other unresolved inputs stay blocked.
    intake._objects(packet, draft)
    draft['consent'] = False
    intake.save_draft(sp, draft)
    m['revision'] += 1
    m.pop('pending_review', None)
    m.pop('run_confirmation', None)
    core.persist(m, 'RESOLVE_CHANGED_DEPENDENCIES', dict(review=entry, changes=changes))
    return dict(id=key, revision=m['revision'], saved_fields=[r['field'] for r in changes])
