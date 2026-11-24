"""An engineer's working choice for one computed edition, separate from hydraulic QA."""
from . import app_core as core
from .app_revision import compare
from .common import ROOT, intact, read, save, unique_id


def latest(model):
    path = core.folder(model['id']) / 'review' / 'iteration_choice.json'
    try:
        record = read(path)
    except FileNotFoundError:
        return None
    except ValueError:
        return {'choice': 'unavailable'}
    if not isinstance(record, dict) or not isinstance(record.get('summary'), dict):
        return {'choice': 'unavailable'}
    if record['summary'] != model.get('summary'):
        return None
    if record.get('choice') not in ('current', 'parent', 'wait', 'review') or not record.get('token'):
        return {'choice': 'unavailable'}
    if record['choice'] == 'parent' and record.get('selected') != {
            k: (model.get('parent_revision') or {}).get(k) for k in ('summary', 'project_id')}:
        return {'choice': 'unavailable'}
    return record


def choose(key, body):
    model = core.model(key)
    core.require_idle(model)
    summary = model.get('summary')
    if (not summary or body.get('summary_hash') != summary['sha256']
            or body.get('revision') != model['revision'] or not intact([summary])):
        raise ValueError('Reopen the current result before choosing an edition. / 请重新打开当前结果后选择版本。')
    prior = latest(model) or {}
    choice = body.get('choice')
    if body.get('previous') != prior.get('token') and choice != prior.get('choice'):
        raise ValueError('The review choice changed in another tab. Reopen the result. / 复核选择已更新，请重开结果。')
    if choice not in ('current', 'parent', 'wait', 'review'):
        raise ValueError('Unknown review choice')
    selected = {'project_id': key, 'summary': summary} if choice == 'current' else None
    parent = model.get('parent_revision')
    if choice == 'parent' or (choice == 'current' and parent):
        comparison = compare(model, read(ROOT / summary['path'])) if parent else None
        if not comparison or comparison['status'] != 'COMPARISON_NOT_ACCEPTANCE' or not comparison.get('profiles'):
            raise ValueError('Both editions need comparable results. / 两版均须有可比的原生结果。')
        if choice == 'parent':
            original = core.model(parent['project_id'])
            if original.get('summary') != parent['summary'] or core.deletion_record(original['id']).exists():
                raise ValueError('Restore the matching baseline edition first. / 请先恢复匹配的基准版本。')
            selected = {'project_id': original['id'], 'summary': parent['summary']}
    if prior.get('choice') == choice and prior.get('selected') == selected:
        return prior
    record = dict(choice=choice, summary=summary, selected=selected, token=unique_id())
    save(core.folder(key) / 'review' / 'iteration_choice.json', record)
    return record
