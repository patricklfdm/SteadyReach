"""Verify the fixed offline artifact, two historic project migrations and the ten-job native queue."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from zipfile import ZipFile
import sys

from ras_workflow import app_core as core
from ras_workflow.common import ROOT,read,save,sha,unique_id
from midway_release import need,page_action
import deployment
import software_release
import p9_queue_check


def candidate_sources(release,manifest):
    status=subprocess.run(['git','diff','--quiet',manifest['git_commit'],'--','.'],cwd=ROOT)
    if status.returncode:raise ValueError('The working tree differs from the signed release')
    extra=subprocess.check_output(['git','ls-files','--others','--exclude-standard','--','ras_workflow','scripts'],cwd=ROOT,text=True)
    if extra.strip():raise ValueError('Uncommitted application files are present')
    with ZipFile(release/'SteadyReach.zip') as archive:
        if not all((ROOT/p.filename).is_file() for p in archive.infolist() if not p.is_dir()):
            raise ValueError('Release software member missing from this checkout')


def run(gate,specification):
    spec=read(specification)
    release=Path(spec['release']).resolve(strict=True);key=Path(spec['trusted_key']).resolve(strict=True)
    python=Path(spec['python']).resolve(strict=True)
    out=gate/'p9';out.mkdir(exist_ok=False)
    result=dict(status='RUNNING',human='DEFERRED',cross_machine='DEFERRED',migrations=[])
    receipt=out/'release.json';save(receipt,result)
    try:
        verified=software_release.verify(release,key)
        candidate_sources(release,verified)
        result['distribution']=dict(version=verified['version'],commit=verified['git_commit'],manifest_sha256=sha(release/'RELEASE.json'),
                                    sbom=sha(release/'SBOM.json'),components=len(read(release/'SBOM.json')['components']))
        with tempfile.TemporaryDirectory(dir=out) as temp:
            altered=Path(temp)/'release';shutil.copytree(release,altered)
            with (altered/'LICENSE.txt').open('ab') as file:file.write(b'x')
            try:software_release.verify(altered,key)
            except ValueError as err:
                need('changed' in str(err),'Unrelated integrity error')
                result['tamper']='REJECTED'
            else:raise ValueError('Altered release accepted')
        earlier=[Path(p).resolve(strict=True) for p in spec['previous_installations']]
        need(len(earlier)==2 and len({deployment.version(p)['code'] for p in earlier})==2,'Two independently versioned earlier projects required')
        for ix,previous in enumerate(earlier,1):
            dest=out/('installed_'+str(ix));control=out/('control_'+str(ix));backup=out/('backup_'+str(ix)+'.zip')
            started=time.monotonic()
            software_release.install(release,key,dest,python)
            bind=[str(dest/'.venv/Scripts/python.exe'),'-B',str(dest/'scripts/bind_release_tools.py'),'--installation',str(dest)]
            for n in ('qgis','converter','runtime'):bind.extend(['--'+n,str(Path(spec[n]).resolve(strict=True))])
            subprocess.run(bind,cwd=dest,check=True,capture_output=True)
            change=deployment.prepare(previous,dest,control,backup,release,key)
            need(any(v.get('package_run') for v in change['projects'].values()),'No historic native result and package')
            switch=deployment.select(control,change['token'])
            undo=deployment.select(control,change['token'],True)
            need(read(control/'ACTIVE.json')['path']==str(previous),'Old installation did not become active')
            result['migrations'].append(dict(source=change['source_version']['code'],files=change['files'],projects=change['projects'],
                switched=switch,rolled_back=undo,backup_hash=change['archive_sha256'],elapsed_seconds=round(time.monotonic()-started,3)))
            save(receipt,result)
        base=read(gate/'p4/release.json')['baseline']
        project=page_action(base,'river-revision')
        page_action(project,'survey-solve')
        operations=p9_queue_check.run(out,project)
        result.update(status='PASSED',operations=dict(path=str(operations.relative_to(out)),sha256=sha(operations)))
    except Exception as exc:
        result.update(status='FAILED',error=str(exc));raise
    finally:save(receipt,result)
    return receipt
