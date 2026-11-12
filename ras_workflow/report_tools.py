"""Explicit local LibreOffice plus pip-installed PDFium; no agent runtime paths."""
import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys

from .common import ROOT, item, read, rel, safe_path, save, sha, unique_id, utc


def discover(config_path=None):
    configured = config_path or os.environ.get('HECRAS_WORKFLOW_TOOLS')
    path = safe_path(ROOT, configured or '.tools/workflow_tools.json')
    config = read(path) if path.exists() else {}
    if config and config.get('schema_version') != '1.0': raise ValueError('Unsupported tools configuration')
    value = config.get('libreoffice_executable')
    # An explicit installed path may be outside the workspace. It is read-only.
    executable = (ROOT/str(value)).resolve() if value else ROOT/'.tools/LibreOfficePortable/App/libreoffice/program/soffice.com'
    blockers = []
    if configured and not path.exists(): blockers.append('Explicit tools configuration is missing')
    if not executable.is_file(): blockers.append('LibreOffice executable missing: configure libreoffice_executable in .tools/workflow_tools.json')
    packages = {}
    for name in ['python-docx', 'pypdf', 'pypdfium2', 'Pillow', 'pywin32']:
        try: packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: blockers.append('Python dependency missing: '+name)
    version = None
    if executable.is_file():
        try:
            import win32api
            info = win32api.GetFileVersionInfo(str(executable), '\\')
            version = '.'.join(str(v) for v in [info['FileVersionMS']>>16, info['FileVersionMS']&65535, info['FileVersionLS']>>16, info['FileVersionLS']&65535])
        except Exception as e: blockers.append('Cannot read LibreOffice file version: '+str(e))
    return dict(status='BLOCKED' if blockers else 'READY', checked_at_utc=utc(), blocking_items=blockers,
                configuration=item(path) if path.exists() else None,
                libreoffice=dict(path=str(executable), version=version, sha256=sha(executable) if executable.is_file() else None),
                python_executable=sys.executable, packages=packages, renderer='repository_worker_with_libreoffice_and_pdfium')


def render(docpath, config_path=None):
    import win32api, win32job
    docpath = safe_path(ROOT, docpath); tools = discover(config_path)
    if tools['status'] != 'READY': raise RuntimeError('; '.join(tools['blocking_items']))
    out = docpath.parent/'qa'/docpath.stem; out.mkdir(parents=True, exist_ok=False)
    request = dict(docx=item(docpath), tools=tools, output=rel(out), created_utc=utc())
    save(out/'request.json', request)
    job = win32job.CreateJobObject(None, 'Local\\HecReport_'+unique_id())
    limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
    limits['BasicLimitInformation']['LimitFlags'] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
    proc = None; status = 'FAILED'; code = None
    try:
        with (out/'render.log').open('wb') as log:
            proc = subprocess.Popen([sys.executable, '-m', 'ras_workflow.render_worker', str(out/'request.json')],
                cwd=ROOT, stdin=subprocess.PIPE, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                win32job.AssignProcessToJobObject(job, proc._handle)
                proc.stdin.write(b'GO\n'); proc.stdin.close()
                code = proc.wait(timeout=240); status = 'EXITED'
            except subprocess.TimeoutExpired: status = 'TIMEOUT'
            except Exception:
                proc.terminate(); proc.wait(timeout=10); raise
    finally:
        win32api.CloseHandle(job)
        if proc and proc.poll() is None: proc.wait(timeout=15)
        save(out/'supervisor.json', dict(status=status, returncode=code, finished_utc=utc(),
             worker_pid=proc.pid if proc else None, cleanup='Only this render worker and its owned descendants'))
    if status != 'EXITED' or code != 0: raise RuntimeError('Report render '+status+' (exit '+str(code)+'); '+rel(out/'render.log'))
    result = read(out/'render_manifest.json')
    from .common import intact
    if result['docx'] != item(docpath) or not intact([result['pdf']]+result['pages']):
        raise ValueError('Rendered document identity mismatch')
    return ROOT/result['pdf']['path'], len(result['pages']), [ROOT/p['path'] for p in result['pages']]
