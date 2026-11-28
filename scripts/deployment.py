"""Migrate local project data into a separate installed copy and select or roll it back."""
import argparse
from contextlib import ExitStack, contextmanager
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

CODE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(CODE))
from ras_workflow.common import digest,lock,read,save,sha,utc
from ras_workflow.local_backup import checkout_id,data_files,member_key,snapshot,verify_archive


@contextmanager
def idle(installation):
    with ExitStack() as locks:
        for name in ('server','launch','execution'):
            locks.enter_context(lock(installation/'status/app'/(name+'.lock')))
        yield


def native_inventory(root):
    """Run inside the selected installed version to exercise its actual project readers."""
    from ras_workflow import app_core as core,handoff,site_delivery
    from ras_workflow.delivery_pair import check
    from ras_workflow.qa import verified_profiles
    from ras_workflow.common import intact,ROOT
    if root!=ROOT:
        raise ValueError('Project reader belongs to a different installation')
    from ras_workflow.edition_storage import archived, archive_manifest
    result = {}
    for row in archived(root):
        if row['phase'] != 'ARCHIVED':
            raise ValueError('Finish the interrupted storage operation: '+row['id'])
        archive = Path(row['archive'])
        if not archive.is_file() or sha(archive) != row['sha256']:
            raise ValueError('Reconnect the verified external edition archive: '+row['id'])
        with ZipFile(archive) as z:
            manifest = archive_manifest(z,row['id'])
        result[row['id']] = dict(phase='ARCHIVED',archive_sha256=row['sha256'],members=len(manifest['members']))
    for path in sorted((root/'projects').glob('*/app.json')):
        key = path.parent.name
        if key in result:
            continue
        model = core.model(key)
        refs=model.get('attachments') or []
        if refs and not intact(refs):raise ValueError('Changed original attachment: '+key)
        summary=model.get('summary');entry=dict(summary_sha256=None,native=None,package_run=None)
        if summary:
            if not intact([summary]):raise ValueError('Different stored summary: '+key)
            data=read(root/summary['path']);h=data.get('hydraulics')
            entry['summary_sha256']=summary['sha256']
            if h:
                sections=verified_profiles(h)
                entry['native']=dict(run=h['run_id'],hdf_sha256=h['raw_hdf']['sha256'],stations={k:len(v) for k,v in sections.items()})
                receipt=handoff.bound_package(model)
                if receipt:
                    roots=[root/receipt[k]['path'] for k in ('complete','minimal')]
                    for folder in roots:site_delivery.verify(folder)
                    pair=check(*roots)
                    if pair['run_id']!=h['run_id']:raise ValueError('Project and delivery disagree: '+key)
                    entry['package_run']=pair['run_id']
        result[key]=entry
    return result


def inventory(root):
    # The old version can predate this administrative utility. Load its own workflow library.
    probe=('import sys,json;from pathlib import Path;root=Path(sys.argv[1]).resolve();'
           'sys.path.insert(0,str(root));import ras_workflow;'
           'import importlib.util;spec=importlib.util.spec_from_file_location("migration_probe",sys.argv[2]);'
           'mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);print(json.dumps(mod.native_inventory(root)))')
    command=[str(root/'.venv/Scripts/python.exe'),'-I','-B','-X','utf8','-c',probe,str(root),str(Path(__file__).resolve())]
    return json.loads(subprocess.check_output(command,cwd=root,text=True,encoding='utf-8'))


def version(root):
    receipt=root/'INSTALLED_RELEASE.json'
    return dict(code=digest(checkout_id(root)),release=read(receipt) if receipt.exists() else None)


def require_distinct(*paths):
    for i,path in enumerate(paths):
        if any(path.is_relative_to(other) or other.is_relative_to(path) for other in paths[:i]):
            raise ValueError('Choose separate installation, control and backup locations')


def migration_inputs(previous,archive):
    manifest=verify_archive(archive)
    if manifest['checkout']!=checkout_id(previous):raise ValueError('Backup belongs to another software version')
    members=data_files(previous)
    if set(members)!=set(manifest['files']) or any(sha(members[n])!=v for n,v in manifest['files'].items()):
        raise ValueError('Source data changed since the backup; prepare a new migration')
    return manifest


def candidate_inventory(candidate, manifest):
    files = data_files(candidate)
    shipped = read(candidate/'INSTALLED_RELEASE.json')['shipped_examples']
    expected = {**shipped, **manifest['files']}
    if set(files) != set(expected):
        raise ValueError('Candidate contains unexpected or missing project data')
    for name, expected_hash in expected.items():
        if sha(files[name]) != expected_hash:
            raise ValueError('Migrated file differs: '+name)


def verified_software(candidate,release,key):
    from software_release import verify_installation
    manifest=verify_installation(candidate,release,key)
    return dict(release=str(release),key=str(key),manifest_sha256=sha(release/'RELEASE.json'),
                trusted_key_sha256=sha(key),git_commit=manifest['git_commit'])


def prepare(previous,candidate,control,archive,release,trusted_key):
    require_distinct(previous,candidate,control,archive)
    if not (candidate/'INSTALLED_RELEASE.json').is_file():
        raise ValueError('Install the verified target release into a new folder first')
    control.mkdir(parents=True,exist_ok=True)
    with lock(control/'deployment.lock'):
        if not archive.exists():snapshot(previous,archive)
        with idle(previous),idle(candidate):
            manifest=migration_inputs(previous,archive)
            before=inventory(previous)
            if not before:raise ValueError('No project editions to migrate')
            origin=version(previous);target=version(candidate)
            software=verified_software(candidate,release,trusted_key)
            plan=dict(source=str(previous),target=str(candidate),source_version=origin,target_version=target,
                      archive=str(archive),archive_sha256=sha(archive),software=software)
            key=digest(plan);pending=candidate/'MIGRATION_SOURCE.json'
            if pending.exists() and read(pending)!=plan:
                raise ValueError('Candidate is already bound to a different migration')
            if not pending.exists() and (candidate/'projects').exists() and any((candidate/'projects').iterdir()):
                raise ValueError('Use an unused candidate installation')
            save(pending,plan)
            with TemporaryDirectory(dir=candidate.parent) as temp:
                staged=Path(temp);verify_archive(archive,staged)
                for name,expected in manifest['files'].items():
                    dest=candidate.joinpath(*member_key(name).parts)
                    if dest.resolve()!=dest:raise ValueError('Linked destination: '+name)
                    if dest.exists():
                        if sha(dest)!=expected:raise ValueError('Existing candidate file differs: '+name)
                        continue
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    # Stage data and candidate are on the same volume. Each file appears complete.
                    (staged/name).rename(dest)
            candidate_inventory(candidate,manifest)
            after=inventory(candidate)
            if after!=before:raise ValueError('Migrated project or native identity differs')
            # The bound source inventory includes every original; intentionally unchanged formats
            # remain readable by the target edition reader without rewriting sealed hydraulic data.
            result=dict(**plan,token=key,projects=after,verified_utc=utc(),files=len(manifest['files']))
            save(control/'migrations'/(key+'.json'),result)
    return result


def select(control,token,rollback=False):
    if len(token)!=64 or any(ch not in '0123456789abcdef' for ch in token):raise ValueError('Invalid migration token')
    with lock(control/'deployment.lock'):
        record=read(control/'migrations'/(token+'.json'))
        plan={k:record[k] for k in ('source','target','source_version','target_version','archive','archive_sha256','software')}
        if digest(plan)!=token:raise ValueError('Migration receipt changed')
        previous,candidate=Path(record['source']),Path(record['target'])
        archive=Path(record['archive']);pointer=control/'ACTIVE.json'
        active=read(pointer) if pointer.exists() else dict(path=str(previous),history=[])
        destination=previous if rollback else candidate;expected=candidate if rollback else previous
        if active['path']!=str(expected):raise ValueError('The selected installation changed')
        with idle(previous),idle(candidate):
            if version(previous)!=record['source_version'] or sha(archive)!=record['archive_sha256']:
                raise ValueError('Previous software or backup identity changed')
            if not rollback and version(candidate)!=record['target_version']:
                raise ValueError('The selected candidate changed')
            manifest=migration_inputs(previous,archive)
            if not rollback:
                package=record['software']
                if verified_software(candidate,Path(package['release']),Path(package['key']))!=package:
                    raise ValueError('Candidate release or trust anchor changed')
                candidate_inventory(candidate,manifest)
            if inventory(destination)!=record['projects']:raise ValueError('Restore or recheck the selected native results')
            event=dict(action='ROLLBACK' if rollback else 'SWITCH',at=utc(),migration=token,path=str(destination))
            save(pointer,dict(path=str(destination),history=[*active['history'],event]))
    return event


def support(control,token):
    """Produce a shareable check of the active installation and its retained native results."""
    if len(token)!=64 or any(c not in '0123456789abcdef' for c in token):
        raise ValueError('Invalid migration token')
    with lock(control/'deployment.lock'):
        record=read(control/'migrations'/(token+'.json'))
        plan={k:record[k] for k in ('source','target','source_version','target_version','archive','archive_sha256','software')}
        if digest(plan)!=token:raise ValueError('Migration receipt changed')
        pointer=read(control/'ACTIVE.json')
        active=Path(pointer['path'])
        if str(active) not in (record['source'],record['target']):raise ValueError('Unrelated active installation')
        side='source' if str(active)==record['source'] else 'target'
        with idle(active):
            active_version=version(active)
            same_code=active_version==record[side+'_version']
            actual=inventory(active) if same_code else None
        return dict(schema='deployment_support_1',migration=token,active=side,software_build=active_version['code'],
                    matches_registered_version=same_code,
                    matches_registered_projects=actual==record['projects'] if actual is not None else None,
                    backup_matches=Path(record['archive']).is_file() and sha(Path(record['archive']))==record['archive_sha256'],
                    project_count=len(record['projects']),
                    history=[e['action'] for e in pointer.get('history',[]) if e.get('migration')==token
                             and e.get('action') in ('SWITCH','ROLLBACK')])


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='action',required=True)
    new=commands.add_parser('prepare')
    for n in ('previous','candidate','control','archive','release','trusted-key'):new.add_argument('--'+n,type=Path,required=True)
    for a in ('switch','rollback','support','open'):
        cmd=commands.add_parser(a);cmd.add_argument('--control',type=Path,required=True)
        if a!='open':cmd.add_argument('--token',required=True)
    args=parser.parse_args()
    if args.action=='prepare':
        print(json.dumps(prepare(*(getattr(args,n).resolve() for n in ('previous','candidate','control','archive','release','trusted_key'))),indent=2))
    elif args.action=='support':
        print(json.dumps(support(args.control.resolve(),args.token),indent=2))
    elif args.action=='open':
        root=Path(read(args.control/'ACTIVE.json')['path'])
        raise SystemExit(subprocess.call([str(root/'.venv/Scripts/python.exe'),str(root/'app.py'),'serve'],cwd=root))
    else:print(json.dumps(select(args.control.resolve(),args.token,args.action=='rollback'),indent=2))


if __name__=='__main__':
    main()
