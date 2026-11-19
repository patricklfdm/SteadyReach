"""Process-local QGIS environment, pinned to the inspected Windows deployment."""
from pathlib import Path
import os, subprocess
from .common import ROOT, read, safe_path


def environment(root=None, tools_config=None):
    configured=tools_config or os.environ.get('HECRAS_WORKFLOW_TOOLS')
    path=safe_path(ROOT,configured or '.tools/workflow_tools.json')
    if configured and not path.is_file():raise ValueError('Explicit tools configuration is missing: '+str(path))
    config=read(path) if path.is_file() else {}
    if config and config.get('schema_version')!='1.0':raise ValueError('Unsupported tools configuration')
    value=root or os.environ.get('HECRAS_QGIS_ROOT') or config.get('qgis_root') or '.tools/qgis_ltr'
    q=(ROOT/Path(value)).resolve()
    required=['bin/python3.exe','apps/qgis-ltr/python/qgis/__init__.py','apps/Python312','apps/Qt5/plugins']
    if any(not (q/p).exists() for p in required):
        raise ValueError('QGIS runtime unavailable: run setup_workflow.cmd and select the QGIS LTR installation root (or configure qgis_root in .tools/workflow_tools.json)')
    env=os.environ.copy()
    env.update(OSGEO4W_ROOT=str(q),QGIS_PREFIX_PATH=(q/'apps/qgis-ltr').as_posix(),PYTHONHOME=str(q/'apps/Python312'),
        PYTHONPATH=str(q/'apps/qgis-ltr/python'),PYTHONUTF8='1',QT_PLUGIN_PATH=str(q/'apps/Qt5/plugins'),
        PROJ_DATA=str(q/'share/proj'),GDAL_DATA=str(q/'apps/gdal/share/gdal'),QT_QPA_PLATFORM='offscreen')
    env['PATH']=';'.join(str(q/p) for p in ['apps/qgis-ltr/bin','apps/Qt5/bin','bin','apps/Python312'])+';'+env.get('PATH','')
    return q,env


def run(request,log_folder,timeout=1200):
    q,env=environment();folder=Path(log_folder)
    progress=folder/'qgis_stdout.log'
    try:
        with progress.open('wb') as out,(folder/'qgis_stderr.log').open('wb') as err:
            r=subprocess.run([str(q/'bin/python3.exe'),str(ROOT/'ras_workflow/qgis_delivery_worker.py'),str(request)],
                env=env,cwd=ROOT,stdout=out,stderr=err,timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired as exc:
        stages=progress.read_text(encoding='utf-8',errors='replace').splitlines()
        stage=stages[-1] if stages else 'QGIS startup'
        raise RuntimeError(f'QGIS export exceeded {timeout:g} s during {stage}. The computed HEC-RAS results are available.') from exc
    if r.returncode:raise RuntimeError('QGIS export failed; inspect qgis_stderr.log')
