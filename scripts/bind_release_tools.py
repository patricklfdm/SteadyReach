"""Connect one offline release to existing workstation installations of its native tools."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


def bind(root,qgis,converter,runtime):
    if not (root/'INSTALLED_RELEASE.json').is_file():
        raise ValueError('Complete the verified software installation first')
    expected=(root/'.venv/Scripts/python.exe').resolve()
    if Path(sys.executable).resolve()!=expected:
        raise ValueError('Run this command with the installed release Python: '+str(expected))
    sys.path.insert(0,str(root))
    from ras_workflow import native, qgis_runtime, report_tools
    from ras_workflow.common import ROOT, lock, read, save, sha
    if ROOT!=root or sha(runtime)!=native.RUNTIME_SHA:
        raise ValueError('Selected application or Microsoft runtime differs from the pinned build')
    if not converter.is_file() or not (qgis/'bin/python3.exe').is_file():
        raise ValueError('Select the installed QGIS LTR root and LibreOffice executable')
    for key in ('HECRAS_WORKFLOW_TOOLS','HECRAS_QGIS_ROOT'):
        os.environ.pop(key,None)
    with ExitStack() as locks:
        for name in ('server','launch','execution'):
            locks.enter_context(lock(root/'status/app'/(name+'.lock')))
        dest=root/'.tools/solver_runtime/msvcr100.dll'
        dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists() and sha(dest)!=native.RUNTIME_SHA:
            raise ValueError('Existing configured runtime differs')
        if not dest.exists():
            with TemporaryDirectory(dir=dest.parent) as tmp:
                copied=Path(tmp)/dest.name
                shutil.copy2(runtime,copied)
                if sha(copied)!=native.RUNTIME_SHA:raise ValueError('Changed runtime copy')
                copied.rename(dest)
        config=root/'.tools/workflow_tools.json'
        previous=read(config) if config.exists() else None
        save(config,dict(schema_version='1.0',qgis_root=str(qgis),libreoffice_executable=str(converter)))
        try:
            engine=native.discover()
            pdf=report_tools.discover()
            qgis,environment=qgis_runtime.environment()
            qversion=subprocess.check_output([str(qgis/'bin/python3.exe'),'-c',
                'from qgis.core import Qgis;print(Qgis.QGIS_VERSION)'],env=environment,text=True,timeout=90).strip()
            if engine['status']!='READY' or pdf['status']!='READY':
                raise ValueError('Tool preflight: '+str(engine['blocking_items']+pdf['blocking_items']))
            record=dict(solver=engine['selected'],runtime_sha256=native.RUNTIME_SHA,components=engine['executables'],
                        converter=pdf['libreoffice'],qgis=qversion,configuration_sha256=sha(config))
        except (OSError,ValueError,subprocess.SubprocessError):
            if previous is None:config.unlink(missing_ok=True)
            else:save(config,previous)
            raise
        save(root/'INSTALLED_TOOLS.json',record)
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('installation','qgis','converter','runtime'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(bind(*(getattr(args,n).resolve(strict=True) for n in ('installation','qgis','converter','runtime'))),indent=2))
