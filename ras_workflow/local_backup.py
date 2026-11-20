"""Offline, byte-verified backup of local project data and shared evidence."""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import os
import shutil
import tempfile
from zipfile import ZIP_STORED, ZipFile

from .common import ROOT, lock, sha, utc

TRANSIENT={'status/app/server.json','status/app/server.lock','status/app/active.json',
           'status/app/launch.lock','status/app/execution.lock'}


def data_files(root):
    result={}
    for directory in ('projects','status','data','examples'):
        base=root/directory
        if not base.exists():continue
        for parent,dirs,files in os.walk(base):
            for name in dirs+files:
                path=Path(parent)/name
                if path.is_symlink() or path.is_junction():raise ValueError(f'Linked dataset needs separate review: {path}')
            for name in files:
                path=Path(parent)/name
                key=path.relative_to(root).as_posix()
                if key not in TRANSIENT:result[key]=path
    if not result:raise ValueError('No local data to back up')
    return result


def checkout_id(root):
    files=[root/'requirements.lock.txt',root/'app.py',root/'workflow.py',*sorted((root/'ras_workflow').rglob('*.py')),
           *sorted((root/'ras_workflow/templates').glob('*'))]
    return {p.relative_to(root).as_posix():sha(p) for p in files if p.is_file()}


def snapshot(root,dest):
    root=Path(root).resolve(strict=True);dest=Path(dest).resolve()
    if dest.exists() or dest.is_relative_to(root):raise ValueError('Select a new archive outside the checkout')
    dest.parent.mkdir(parents=True,exist_ok=True)
    with ExitStack() as owned:
        # The normal desktop server and background execution hold these same
        # kernel locks. Closing a browser tab alone does not stop the server.
        for name in ('server','launch','execution'):owned.enter_context(lock(root/'status/app'/(name+'.lock')))
        files=data_files(root);total=sum(p.stat().st_size for p in files.values())
        overhead=sum(2048+8*len(k.encode('utf8')) for k in files)
        if shutil.disk_usage(dest.parent).free < total+overhead:
            raise OSError('Insufficient free space for the uncompressed project snapshot')
        fd,tmp=tempfile.mkstemp(dir=dest.parent,suffix='.partial');os.close(fd)
        tmp=Path(tmp)
        try:
            with ZipFile(tmp,'w',compression=ZIP_STORED,allowZip64=True) as archive:
                hashes={}
                for k,p in sorted(files.items()):
                    archive.write(p,k);hashes[k]=sha(p)
                record=dict(schema='steadyreach_local_backup_1',created=utc(),checkout=checkout_id(root),files=hashes)
                archive.writestr('BACKUP.json',json.dumps(record,ensure_ascii=False).encode('utf8'))
            verify_archive(tmp)
            if set(data_files(root))!=set(files) or any(sha(p)!=hashes[k] for k,p in files.items()):
                raise ValueError('Workspace changed during backup; close native editors and retry')
            # Windows rename refuses an existing destination.
            tmp.rename(dest)
        finally:tmp.unlink(missing_ok=True)
    return dict(archive=str(dest),files=len(files),source_bytes=total,sha256=sha(dest))


def member_key(name):
    posix=PurePosixPath(name);win=PureWindowsPath(name)
    if (not posix.parts or posix.parts[0] not in ('projects','status','data','examples') or name in TRANSIENT or
        posix.as_posix()!=name or win.drive or win.root or '\\' in name or ':' in name or '..' in posix.parts or
        any(part.endswith((' ','.')) or PureWindowsPath(part).is_reserved() for part in posix.parts)):
        raise ValueError('Invalid backup member')
    return posix


def verify_archive(path,dest=None):
    with ZipFile(path) as archive:
        names=archive.namelist()
        if len(set(n.casefold() for n in names))!=len(names) or 'BACKUP.json' not in names:raise ValueError('Missing or duplicate backup members')
        record=json.loads(archive.read('BACKUP.json'))
        hashes=record['files']
        if record['schema']!='steadyreach_local_backup_1' or set(hashes)!=set(names)-{'BACKUP.json'}:
            raise ValueError('Archive and manifest disagree')
        for k,expected in hashes.items():
            member=member_key(k)
            with archive.open(k) as stream:
                if dest is None:value=hashlib.file_digest(stream,'sha256').hexdigest()
                else:
                    target=dest.joinpath(*member.parts)
                    target.parent.mkdir(parents=True,exist_ok=True)
                    with target.open('xb') as output:shutil.copyfileobj(stream,output)
                    value=sha(target)
            if value!=expected:raise ValueError('Backup fingerprint mismatch: '+k)
    return record


def restore(path,destination):
    destination=Path(destination).resolve()
    if destination.exists():raise ValueError('Restore into a new folder; existing projects stay intact')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as staging:
        payload=Path(staging)/'restore';payload.mkdir()
        record=verify_archive(path,payload)
        payload.rename(destination)
    return dict(folder=str(destination),files=len(record['files']),same_checkout=record['checkout']==checkout_id(ROOT))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    commands=p.add_subparsers(dest='action',required=True)
    commands.add_parser('size')
    commands.add_parser('write').add_argument('archive',type=Path)
    commands.add_parser('verify').add_argument('archive',type=Path)
    z=commands.add_parser('restore');z.add_argument('archive',type=Path);z.add_argument('destination',type=Path)
    args=p.parse_args()
    if args.action=='size':
        files=data_files(ROOT);out=dict(files=len(files),bytes=sum(p.stat().st_size for p in files.values()))
    elif args.action=='write':out=snapshot(ROOT,args.archive)
    elif args.action=='verify':
        record=verify_archive(args.archive);out=dict(files=len(record['files']),created=record['created'],sha256=sha(args.archive))
    else:out=restore(args.archive,args.destination)
    print(json.dumps(out,indent=2))
