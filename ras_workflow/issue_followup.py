"""Carry a reviewed engineering question from the source run into later editions."""
from .common import ROOT, digest, intact, item, read, save
from . import app_core as core

ROUTES = {
    'VERIFY_BARREL_INVERTS': ('invert-request',
        'Request each group’s inlet and outlet elevations on the model datum and the original survey. Compare headwater, road flow and wet ends after revision.',
        '逐组索取同基准的进出口涵底及原始测量。修订后对比涵前水位、路面越流及湿端。'),
    'VERIFY_OUTLET_INFLUENCE': ('field-feedback',
        'Obtain event-matched outlet control with a datum tie. Check the affected stations and repeat the applicable boundary tests on the revised geometry.',
        '取得同期出口控制及高程联测资料。核对受影响断面，在修订几何上重新检验适用边界。'),
    'VERIFY_FLOW_PATH': ('field-feedback',
        'Request surveyed overbank openings and connected sections at the flagged reach. Compare native flow shares and stages before choosing the geometry.',
        '索取异常河段的漫滩开口及连通断面测量。选用几何前核对原生分流比例和水位。'),
}


def route(issue):
    tool, en, zh = ROUTES.get(issue['code'], (
        (issue.get('action') or {}).get('tool', 'qa'),
        'Check the cited evidence. If it changes an input, confirm and compute a separate revision. Compare the affected controls before selecting an edition.',
        '核查所列依据。若输入改变，在独立修订版中确认并重算，比较受影响的控制项后选版。'))
    return dict(tool=tool, heading=dict(en='Evidence and revision check', zh='所需资料与修订核查'), en=en, zh=zh)


def start(key, body):
    from .result_guidance import collect
    m = core.model(key)
    core.require_idle(m)
    summary = m.get('summary')
    if not summary or body.get('summary_hash') != summary['sha256'] or body.get('revision') != m['revision']:
        raise ValueError('Reopen the current result / 请重新打开当前结果')
    assessment = collect(key, dict(summary_hash=summary['sha256'], include_assessment=True))['assessment']
    issue = (assessment.get('edition_brief') or {}).get('next_decision')
    if not issue or assessment.get('level') == 0 or body.get('issue_token') != digest(issue):
        raise ValueError('The primary issue changed. Refresh the result. / 首要问题已变化，请刷新本次结果。')
    record = dict(project=key, summary=summary, run=assessment['run_id'], issue=issue)
    path = core.folder(key)/'review'/'issues'/(digest(record)+'.json')
    if not path.exists():
        save(path, record)
    if read(path) != record:
        raise ValueError('Restore the recorded investigation / 请恢复问题记录')
    ref = item(path, 'engineering_issue')
    if m.get('active_issue') != ref:
        m['active_issue'] = ref
        core.persist(m, 'FOLLOW_ENGINEERING_ISSUE', ref)
    return ref


def active(m):
    ref = m.get('active_issue')
    if not ref:
        return None
    if not intact([ref]):
        raise ValueError('Restore the linked issue record / 请恢复已关联的问题记录')
    if read(ROOT/ref['path'])['summary'] == m.get('summary'):
        return ref
    return None


def selection_row(summary):
    from .iteration_choice import latest
    key = (summary.get('configuration') or {}).get('project_id')
    if not key or not (core.folder(key)/'app.json').is_file():
        return None
    model = core.model(key)
    if not (model.get('active_issue') or (model.get('parent_revision') or {}).get('issue')):
        return None
    record = latest(model) or {}
    ref = record.get('summary')
    if not ref or not intact([ref]) or read(ROOT/ref['path']).get('hydraulics', {}).get('run_id') != summary['hydraulics'].get('run_id'):
        return None
    labels = {'wait': ('Wait for field records', '等待补资料'), 'review': ('Review resumed', '已恢复复核'),
              'parent': ('Retain previous calculation', '保留上一版'), 'current': ('Use this working edition', '采用本工作版')}
    en, zh = labels[record['choice']]
    selected = (record.get('selected') or {}).get('summary')
    if selected and intact([selected]):
        run = read(ROOT/selected['path'])['hydraulics']['run_id']
        en += ' · '+run
        zh += ' · '+run
    if record.get('reason'):
        en += ' · '+record['reason']
        zh += ' · '+record['reason']
    return dict(heading=dict(en='Working edition decision', zh='工作版本选择'), en=en, zh=zh)


def inherited_row(summary):
    origin = summary.get('configuration', {}).get('revision_origin') or {}
    ref = origin.get('issue')
    if not ref:
        return None
    heading = dict(en='Issue carried from the baseline', zh='从基准版沿用的问题')
    if intact([ref]):
        source = read(ROOT/ref['path'])
        if source['summary'] == origin.get('issue_summary', origin['summary']) and source['project'] == origin['project_id']:
            issue = source['issue']
            return dict(heading=heading,en=source['run']+' · '+issue['en'],zh=source['run']+' · '+issue['zh'])
    return dict(heading=heading,en='Restore the source-run issue record before selecting an edition.',
                zh='选版前请恢复原运行的问题记录。')
