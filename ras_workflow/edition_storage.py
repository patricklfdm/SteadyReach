"""Archive and restore one workflow edition on a local Windows workstation."""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

from .common import ROOT, identifier, lock, read, save, sha, unique_id, utc
from .local_backup import member_key
from .storage_inventory import inspect, regular_tree

COLD={'RETIRING','ARCHIVED','RESTORING'}


def record_path(root,key):
    return root/'status/edition_storage'/identifier(key)/'state.json'


def state(root,key):
    path=record_path(root,key)
    return read(path) if path.is_file() else dict(id=key,phase='ONLINE',pinned=False)


def archived(root):
    return [dict(id=r['id'],title=r['title'],phase=r['phase'],archive=r['archive'],sha256=r['sha256'],
                 parent_revision=r.get('parent_revision'),created_utc=r.get('created_utc'))
            for p in sorted((root/'status/edition_storage').glob('*/state.json'))
            if (r:=read(p))['phase'] in COLD]


def local_path(root,name):
    path=root.joinpath(*member_key(name).parts)
    if path.resolve()!=path or path.is_symlink() or path.is_junction():
        raise ValueError('Linked storage path / 存储路径包含链接: '+name)
    return path


def available(path,required):
    free=shutil.disk_usage(path).free
    if free<required:raise ValueError(f'Insufficient space / 可用空间不足: {free:,} / {required:,} bytes')


def preview(root,key):
    p=inspect(root,key);r=state(root,key)
    p['archive_upper_bytes']=archive_bound(p)
    p['restore_reserve_bytes']=sum(p['files'][n][0]+4096 for n in p['reclaim'])
    p['workspace_free_bytes']=shutil.disk_usage(root).free
    p.pop('files')
    candidates=p.pop('reclaim')
    p.update(candidate_files=len(candidates),candidates=candidates,pinned=r['pinned'],archive=r.get('archive'),
             archive_bytes=r.get('archive_bytes'),matches_archive=r.get('token')==p['token'] and Path(r['archive']).is_file(),
             archive_hash=r.get('sha256'),default_directory=str(root.parent),phase=r['phase'])
    p['same_volume']=bool(r.get('archive') and Path(r['archive']).drive.lower()==root.drive.lower())
    if r['pinned']:p['reclaimable_bytes']=0
    return p


def archive_base(root,directory):
    if not isinstance(directory,str) or not directory.strip():raise ValueError('Choose an existing local archive folder')
    base=Path(directory)
    if (not base.is_absolute() or str(base).startswith('\\\\') or not base.is_dir() or base.resolve()!=base
            or base.is_relative_to(root)):
        raise ValueError('Choose a local folder outside this checkout / 选择工作目录以外的本机目录')
    return base


def destination(root,directory):
    folder=archive_base(root,directory)/'SteadyReach_Archives'
    if folder.is_relative_to(root) or folder.resolve()!=folder:raise ValueError('Choose a separate archive folder')
    folder.mkdir(exist_ok=True)
    return folder


def archive_manifest(archive,key):
    record=json.loads(archive.read('EDITION.json'))
    if record['schema']!='steadyreach_edition_1' or record['id']!=key:raise ValueError('Archive edition differs')
    blobs={}
    for name,row in record['members'].items():
        member_key(name)
        h=row['sha256']
        if len(h)!=64 or any(c not in '0123456789abcdef' for c in h):raise ValueError('Invalid member fingerprint')
        if row['size']<0 or blobs.get(h,row['size'])!=row['size']:raise ValueError('Inconsistent member sizes')
        blobs[h]=row['size']
    names=archive.namelist()
    if len(set(names))!=len(names) or set(names)!={'EDITION.json',*('files/'+h for h in blobs)}:
        raise ValueError('Archive inventory differs')
    for h,size in blobs.items():
        if archive.getinfo('files/'+h).file_size!=size:raise ValueError('Archive member size differs')
        with archive.open('files/'+h) as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=h:raise ValueError('Archive content differs')
    return record


def archive_bound(p):
    # Include ZIP records, incompressible data and the filename table.
    overhead=sum(2048+8*len(k.encode()) for k in p['files'])
    return p['logical_bytes']+p['logical_bytes']//100+overhead


def write_archive(root,p,folder):
    available(folder,archive_bound(p))
    target=folder/(p['id']+'_'+unique_id()+'.zip')
    temp=target.with_suffix('.partial')
    members={};seen=set()
    try:
        with ZipFile(temp,'x',ZIP_DEFLATED,compresslevel=1,allowZip64=True) as archive:
            for name,(size,mtime_ns) in p['files'].items():
                source=local_path(root,name);h=sha(source)
                if h not in seen:
                    archive.write(source,'files/'+h);seen.add(h)
                members[name]=dict(size=size,sha256=h,mtime_ns=mtime_ns)
            archive.writestr('EDITION.json',json.dumps(dict(schema='steadyreach_edition_1',id=p['id'],
                    token=p['token'],members=members,reclaim=p['reclaim']),ensure_ascii=False))
        with ZipFile(temp) as archive:archive_manifest(archive,p['id'])
        if inspect(root,p['id'])['token']!=p['token'] or any(sha(local_path(root,k))!=v['sha256'] for k,v in members.items()):
            raise ValueError('Files changed while archiving / 归档期间文件发生变化')
        temp.rename(target)
    finally:temp.unlink(missing_ok=True)
    return target


def reusable(root,r,p,folder):
    if r.get('token')!=p['token'] or not r.get('archive'):return False
    target=Path(r['archive'])
    if target.parent!=folder or not target.is_file() or sha(target)!=r['sha256']:return False
    with ZipFile(target) as archive:
        members=archive_manifest(archive,p['id'])['members']
    return all(sha(local_path(root,k))==v['sha256'] for k,v in members.items())


def protected_jobs(root):
    from .app_core import task_alive
    record=root/'status/app/active.json'
    if record.is_file():
        job_path=read(record).get('record')
        if job_path and local_path(root,job_path).is_file():
            job=read(local_path(root,job_path))
            if job.get('status')=='RUNNING' and task_alive(job):raise ValueError('Wait for the active workflow job / 请等待正在运行的任务')


def restore_file(path,archive,row):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.edition-',suffix='.partial',dir=path.parent)
    temp=Path(name)
    try:
        with os.fdopen(fd,'wb') as out,archive.open('files/'+row['sha256']) as stream:
            shutil.copyfileobj(stream,out)
        if sha(temp)!=row['sha256']:raise ValueError('Restored bytes differ')
        os.utime(temp,ns=(row['mtime_ns'],row['mtime_ns']))
        temp.rename(path)  # Windows refuses to replace an existing member.
    finally:temp.unlink(missing_ok=True)


def materialize(root,r,manifest,archive):
    pending=[]
    for name,row in manifest['members'].items():
        path=local_path(root,name)
        if path.exists():
            if not path.is_file() or sha(path)!=row['sha256']:
                raise ValueError('Existing file differs; resolve the conflict and retry / 已有文件不同: '+name)
        else:
            parts=Path(name).parts
            if parts[0]=='examples':raise ValueError('Restore the matching software version first / 请先恢复原软件版本: '+name)
            if parts[0]=='projects' and parts[1]!=r['id']:
                raise ValueError('Restore the required source edition first / 先恢复来源版本: '+name)
            pending.append((name,row))
    available(root,sum(row['size'] for _,row in pending)+4096*len(pending))
    for name,row in pending:restore_file(local_path(root,name),archive,row)
    return len(pending)


def perform(root,key,action,body):
    root=Path(root).resolve();path=record_path(root,key)
    if action=='preview':return preview(root,key)
    if action=='capacity':
        from .storage_capacity import estimate
        count=body.get('editions')
        if type(count) is not int or not 1<=count<=10000:
            raise ValueError('Enter 1..10000 editions / 请输入 1 至 10000 个版本')
        base=archive_base(root,body.get('directory'))
        p=preview(root,key)
        if p['token']!=body.get('token') or p['phase']!='ONLINE':
            raise ValueError('Storage changed. Preview again / 存储已改变，请重新预览')
        # Retain each completed edition. Allow one additional edition for serial temporary work.
        return dict(editions=count,reference_bytes=p['logical_bytes'],**estimate(root,base,
                    work_bytes=(count+1)*p['logical_bytes'],archive_bytes=count*p['archive_upper_bytes'],
                    restore_bytes=p['restore_reserve_bytes']))
    with ExitStack() as locks:
        for name in ('app/launch.lock','app/execution.lock','workflow_solver.lock'):
            locks.enter_context(lock(root/'status'/name))
        protected_jobs(root)
        project_locks=set()
        regular_tree(root/'projects'/key,locks=project_locks)
        for project_lock in sorted(project_locks):locks.enter_context(lock(project_lock))
        r=state(root,key)
        if body.get('confirmed') is not True:raise ValueError('Confirm the displayed edition / 请确认当前版本')
        if action=='pin':
            if not (root/'projects'/key/'app.json').is_file() or r['phase']!='ONLINE' or type(body.get('pinned')) is not bool:
                raise ValueError('Choose an online edition')
            r['pinned']=body['pinned'];save(path,r);return dict(pinned=r['pinned'])
        if action in ('archive','retire') and r['phase']=='ONLINE':
            from .app_core import require_task_finished
            m=read(root/'projects'/key/'app.json')
            if root==ROOT:require_task_finished(m)
            p=inspect(root,key)
            if p['token']!=body.get('token'):raise ValueError('Storage changed. Preview again / 存储已改变，请重新预览')
            if action=='archive':
                folder=destination(root,body.get('directory'))
                if not reusable(root,r,p,folder):
                    target=write_archive(root,p,folder)
                    r.update(archive=str(target),archive_bytes=target.stat().st_size,sha256=sha(target),token=p['token'],
                             title=p['title'],parents=p['parents'],parent_revision=m.get('parent_revision'),
                             created_utc=m.get('created_utc'),archived_utc=utc())
                    save(path,r)
                return dict(archive=r['archive'],archive_bytes=r['archive_bytes'],sha256=r['sha256'],
                            same_volume=Path(r['archive']).drive.lower()==root.drive.lower())
            if r['pinned'] or p['dependents'] or not p['reclaimable_bytes']:
                raise ValueError('Pinned, referenced or no releasable files / 当前版本受保护或没有可释放文件')
            if r.get('token')!=p['token']:raise ValueError('Create and verify the current edition archive first / 先生成并校验本版归档')
        elif not (action=='restore' and r['phase'] in COLD or action=='retire' and r['phase']=='RETIRING'):
            raise ValueError('Action unavailable for this edition state')
        target=Path(r['archive'])
        if not target.is_file() or sha(target)!=r['sha256']:raise ValueError('Restore the registered archive / 请找回已登记的归档: '+str(target))
        if body.get('archive_hash')!=r['sha256']:raise ValueError('Refresh the archive identity before confirming')
        free=shutil.disk_usage(root).free
        with ZipFile(target) as archive:
            manifest=archive_manifest(archive,key)
            if manifest['token']!=r['token']:raise ValueError('Archive inventory identity differs')
            if action=='restore':
                r['phase']='RESTORING';save(path,r)
                count=materialize(root,r,manifest,archive)
                r.update(phase='ONLINE',restored_utc=utc(),restored_files=count)
            else:
                if r['phase']=='ONLINE':
                    if manifest['reclaim']!=p['reclaim']:raise ValueError('Cleanup policy changed; generate a new archive')
                    for name,row in manifest['members'].items():
                        if sha(local_path(root,name))!=row['sha256']:
                            raise ValueError('File changed since archive / 归档后文件已改变: '+name)
                    r.update(phase='RETIRING',free_before_retirement=free);save(path,r)
                else:
                    current=inspect(root,key)
                    remaining={n for n in manifest['reclaim'] if local_path(root,n).exists()}
                    if current['dependents'] or current['unverified_sources'] or not remaining.issubset(current['reclaim']):
                        raise ValueError('References changed; restore this edition and preview again / 引用有变化，请恢复后重新预览')
                for name in manifest['reclaim']:
                    if not name.startswith('projects/'+key+'/'):raise ValueError('Cleanup outside the selected edition')
                    file=local_path(root,name)
                    if file.exists():
                        if sha(file)!=manifest['members'][name]['sha256']:raise ValueError('File changed before cleanup: '+name)
                        file.unlink()
                r.update(phase='ARCHIVED',retired_utc=utc(),actual_volume_gain=shutil.disk_usage(root).free-r['free_before_retirement'])
        save(path,r)
        return dict(id=key,phase=r['phase'],actual_volume_gain=r.get('actual_volume_gain'),restored_files=r.get('restored_files'))
