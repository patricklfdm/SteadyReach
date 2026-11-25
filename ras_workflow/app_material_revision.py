"""Preview and atomically adopt a supplemental road-width interpretation on a child draft."""
from . import app_core as core, app_parameters as params, intake
from .app_automation import dependency
from .common import digest, intact

ROAD = 'g.structure.road.'
WIDTH = ROAD + 'width_ft'
DEPENDENTS = ('distance_us_ft', 'profile_mode', 'station_ft', 'elevation_ft',
              'downstream_station_ft', 'downstream_elevation_ft')


def answer(candidate):
    return dict(value=candidate['value'], evidence_class=candidate['evidence_class'],
                basis=candidate['basis'], candidate_record=candidate, confirmed=False)


def evaluate(m, candidate_id):
    parent = m.get('parent_revision') or {}
    if m.get('active_project') or m.get('native_review') or not parent.get('summary'):
        raise ValueError('Open an editable revision of a completed run / 请在已计算项目的独立修订版中操作')
    inherited_sources = parent.get('inherited_sources')
    if inherited_sources is None:
        inherited_sources = [r['sha256'] for r in core.model(parent['project_id']).get('attachments', [])]
    sources = m.get('attachments', [])
    if not intact(sources + [parent['summary']]):
        raise ValueError('Source or baseline changed / 来源文件或基准结果已变化')
    prior_hashes = set(inherited_sources)
    new_hashes = {r['sha256'] for r in sources} - prior_hashes
    sp, packet, draft, config, old = params.objects(m)
    fields = {r['key']: r for r in params.rows(m, (sp, packet, draft, config, old))}
    width = fields.get(WIDTH, {})
    candidates = [c for c in width.get('parameter_candidates', [])
                  if (c.get('source') or {}).get('sha256') in new_hashes and c['value'] != width['value']]
    if not any(c['candidate'] == candidate_id for c in candidates):
        raise ValueError('Choose a current width from the new source / 请选择补充资料中当前可用的路宽')
    selected = next(c for c in candidates if c['candidate'] == candidate_id)
    original_width = width['value']
    previous_class = width['evidence_class']
    draft['answers'][WIDTH] = answer(selected)
    config, new = intake._objects(packet, draft)
    after = {r['key']: r for r in params.rows(m, (sp, packet, draft, config, new))}
    changes = []
    for name in DEPENDENTS:
        key = ROAD + name
        field = fields.get(key)
        if field is None:
            continue
        saved = field.get('answer', {})
        record = saved.get('candidate_record') or {}
        choices = after[key]['parameter_candidates']
        expected = dependency(m, new, key)
        proposed = [c for c in choices if c.get('automation_context') == expected]
        unique = (len(choices) == len(proposed) == 1 and not after[key].get('source_conflict')
                  and not proposed[0].get('requires_applicability_review'))
        inherited = bool(record.get('automation_context')
                         and all(saved.get(k) == record.get(k) for k in ('value','basis','evidence_class'))
                         and record['automation_context'] == dependency(m, old, key))
        allowed = unique and (field['missing'] or inherited)
        reason = ('unique' if allowed else 'independent' if not field['missing'] and not inherited
                  else 'competing' if len(choices)>1 else 'needs_evidence')
        choice = proposed[0] if allowed else None
        if choice:
            draft['answers'][key] = answer(choice)
        changes.append(dict(key=key, label=field['label'], unit=field.get('unit'), before=field['value'],
                            after=choice['value'] if choice else None, automatic=bool(choice), reason=reason,
                            basis=choice['basis'] if choice else '', candidate=choice['candidate'] if choice else None))
    result = dict(project=m['id'], parent=parent['project_id'], revision=m['revision'],
                  before=original_width, previous_class=previous_class, selected=selected,
                  changes=changes, ready=len(changes)==len(DEPENDENTS) and all(r['automatic'] for r in changes))
    result['token'] = digest(dict(preview=result, inputs=digest(params.binding(m))))
    return result, sp, draft


def perform(key, body, apply=False):
    m = core.model(key)
    core.require_idle(m)
    if m['revision'] != body.get('revision'):
        raise ValueError('Draft changed. Preview again / 草稿已改变，请重新预览')
    result, sp, draft = evaluate(m, body.get('candidate'))
    if not apply:
        return result
    if not result['ready'] or body.get('confirmed') is not True or body.get('token') != result['token']:
        raise ValueError('Review the current source and all affected fields first / 请先核对当前来源及全部关联参数')
    draft.update(consent=False, reviewer=None)
    intake.save_draft(sp, draft)
    m['revision'] += 1
    m.pop('pending_review', None)
    m.pop('run_confirmation', None)
    core.persist(m, 'ADOPT_SUPPLEMENT_AND_ROAD_PROFILE', result)
    return dict(id=key, revision=m['revision'], changed=[WIDTH]+[r['key'] for r in result['changes']])
