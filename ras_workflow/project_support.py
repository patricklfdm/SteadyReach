"""Preview and recheck a small, locally generated support record for one edition."""
import re
from .local_backup import checkout_id

from . import app_core
from .common import ROOT, digest, intact, read, safe_path

PAGES = {'model', 'confirm', 'overview', 'review', 'delivery'}
ACTIONS = {'prepare', 'acquire', 'analyze', 'run', 'resume-run', 'delivery', 'report', 'native-export',
           'native-outputs', 'check-batch', 'study', 'field-resume'}
CODES = {'INPUT_EVIDENCE', 'EDITION_MISMATCH', 'EXPORT_TIMEOUT', 'EXPORT_FAILED', 'LOW_SPACE',
         'ENVIRONMENT', 'SOLVER', 'UNCLASSIFIED'}


def classify(message, action=''):
    message = str(message).lower()
    if any(word in message for word in ('disk full','no space','磁盘已满','free space')):
        return 'LOW_SPACE'
    if any(word in message for word in ('mismatch','changed','stale','different edition','版本错配','已变化')):
        return 'EDITION_MISMATCH'
    if any(word in message for word in ('timeout','timed out','qgis export exceeded','超时')) and (
            action in ('delivery','report') or any(w in message for w in ('qgis','pdf','render','export'))):
        return 'EXPORT_TIMEOUT'
    if any(word in message for word in ('not installed','runtime missing','environment','未安装')):
        return 'ENVIRONMENT'
    if action in ('delivery','report','native-export','native-outputs'):
        return 'EXPORT_FAILED'
    if any(word in message for word in ('survey','datum','missing input','source file','资料缺失')):
        return 'INPUT_EVIDENCE'
    if action in ('run','resume-run'):
        return 'SOLVER'
    return 'UNCLASSIFIED'


def preview(key, body):
    m = app_core.model(key)
    page = body.get('page')
    if page not in PAGES:
        raise ValueError('Select a current workflow screen / 请返回当前工程页面')
    requested = body.get('incident')
    if requested is not None and requested not in CODES:
        raise ValueError('Unknown incident category')
    task = read(safe_path(ROOT,m['task'])) if m.get('task') else {}
    if task and task.get('project_id') != key:
        raise ValueError('Task belongs to another edition')
    action = task.get('action')
    status = task.get('status')
    summary = m.get('summary')
    verified = bool(summary and intact([summary]))
    h = read(safe_path(ROOT,summary['path'])).get('hydraulics',{}) if verified else {}
    job_error = task.get('error') or ' '.join(map(str,m.get('errors') or []))
    if requested:
        incident = requested
    elif summary and not verified:
        incident = 'EDITION_MISMATCH'
    elif job_error or status=='FAILED':
        incident = classify(job_error,action)
    else:
        incident = 'NO_FAILURE_RECORDED'
    release = ROOT/'INSTALLED_RELEASE.json'
    declared = read(release).get('git_commit') if release.is_file() else None
    raw = h.get('raw_hdf') or {}
    bundle = dict(schema='steadyreach_project_support_1',edition=digest(key)[:20],revision=m['revision'],
                  page=page,incident=incident,
                  issue_source='page_request' if requested else 'local_records',
                  task=action if action in ACTIONS else 'other' if action else None,
                  task_status=status if status in ('FAILED','RUNNING','FINISHED','INTERRUPTED','CANCELLED') else None,
                  declared_release=declared if isinstance(declared,str) and re.fullmatch(r'[0-9a-f]{40}',declared) else None,
                  software_build=digest(checkout_id(ROOT)),
                  summary_verified=verified,
                  run_fingerprint=digest(h['run_id'])[:20] if h.get('run_id') else None,
                  registered_hdf=raw.get('sha256') if re.fullmatch('[a-fA-F0-9]{64}',str(raw.get('sha256'))) else None)
    return dict(record=bundle,token=digest(bundle))


def export(key,body):
    current=preview(key,body)
    if current['token']!=body.get('token'):
        raise ValueError('Support preview changed. Preview the current edition again. / 诊断预览已变化，请重新预览当前版本。')
    return current['record']
