"""Open a disposable preview copy with the configured native QGIS environment."""
import os,shutil,subprocess
from .common import ROOT,read,rel,safe_path,unique_id
from . import app_core as core


def qgis(key,body):
    m=core.model(key);core.require_idle(m);v=core.view(key);delivery=v.get('delivery')
    if m.get('exports_need_refresh') or not delivery or not delivery.get('complete'):raise ValueError('Generate a current Complete package first')
    from .site_delivery import verify
    source=safe_path(ROOT,delivery['complete']['path']);verify(source)
    from .qgis_runtime import environment
    root,env=environment();executable=root/'bin/qgis-ltr-bin.exe'
    if not executable.is_file():raise ValueError('Configured QGIS executable is missing; rerun setup')
    if not (source/'GIS_Project.qgz').is_file():raise ValueError('This package has no editable GIS project')
    destination=core.folder(key)/'desktop_previews'/unique_id()/'Complete';shutil.copytree(source,destination)
    project=destination/'GIS_Project.qgz'
    env.pop('QT_QPA_PLATFORM',None)
    process=subprocess.Popen([str(executable),str(project)],env=env,cwd=root/'bin',stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    core.persist(m,'OPEN_QGIS_PREVIEW',dict(path=rel(project),pid=process.pid,original_package=rel(source)))
    return dict(path=rel(project),status='LAUNCHED_NOT_VISUALLY_VERIFIED')
