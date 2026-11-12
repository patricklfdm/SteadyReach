"""Portable local archives with explicit selection and verified, non-overwriting restore.

Standard library only: usable before the scientific dependencies are installed.
Hashes establish byte integrity, not authorship, safety, or engineering acceptance.
"""
import hashlib
import json
import re
import shutil
import stat
import zipfile
import ast
from pathlib import Path, PurePosixPath
from .common import ROOT, item, read, rel, safe_path, save, sha, utc

MAX_FILE=600_000_000
MAX_TOTAL=4_000_000_000
MANIFEST='DELIVERY_MANIFEST.json'
FORBIDDEN={'.git','.aws','.codex','.agents','.tools','.venv','venv','__pycache__'}


def portable_name(name):
    if not isinstance(name,str) or not name or '\\' in name or PurePosixPath(name).is_absolute():
        raise ValueError('Unsafe archive path')
    parts=name.split('/')
    for part in parts:
        if (not part or part in ['.','..'] or part.endswith((' ','.')) or
            any(ord(c)<32 or c in '<>:"|?*' for c in part) or
            re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',part)):
            raise ValueError('Nonportable Windows archive path: '+name)
        if part.lower() in FORBIDDEN or part.lower().startswith('.env'):
            raise ValueError('Credentials, environments and installed tools are excluded: '+name)
    if name.casefold()==MANIFEST.casefold():raise ValueError('Reserved manifest path')
    return name


def create(spec_path, output):
    spec_path=safe_path(ROOT,spec_path);s=read(spec_path)
    if s.get('schema_version')!='delivery_selection_1.0' or not s.get('purpose'):
        raise ValueError('Explicit delivery selection and purpose required')
    paths=s.get('files',[])
    if not paths or len(paths)>50000:raise ValueError('Explicit bounded file list required')
    out=safe_path(ROOT,output)
    if out.exists():raise ValueError('Choose a new archive output')
    entries=[];seen=set();total=0
    for name in paths:
        portable_name(name)
        if name.casefold() in seen:raise ValueError('Duplicate or case-colliding path')
        seen.add(name.casefold());p=safe_path(ROOT,name)
        if p==out or p.is_symlink() or not p.is_file() or rel(p)!=name:
            raise ValueError('Selection must be an ordinary workspace file: '+name)
        e=item(p);total+=e['size_bytes']
        if e['size_bytes']>MAX_FILE or total>MAX_TOTAL:raise ValueError('Archive selection exceeds size budget')
        entries.append(e)
    manifest=dict(schema_version='delivery_1.0',created_utc=utc(),purpose=s['purpose'],
        workflow_version=__import__('ras_workflow').__version__,project_schema_versions=['1.0'],
        scope=s.get('scope','LOCAL_DELIVERY'),files=entries,total_bytes=total,
        exclusions=['Installed tools, environments, credentials and Git history'],
        engineering_acceptance='NOT_ASSESSED')
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        z.writestr(MANIFEST,json.dumps(manifest,ensure_ascii=False,indent=2))
        for e in entries:z.write(ROOT/e['path'],e['path'])
    verify(out)
    receipt=dict(status='ARCHIVE_BYTES_VERIFIED',archive=item(out),selection=item(spec_path),
        files=len(entries),total_bytes=total,scope=manifest['scope'])
    save(out.with_suffix('.receipt.json'),receipt)
    return receipt


def verified_archive(archive):
    """Inspect all names, sizes and bytes before any restore writes occur."""
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist()
        if len(infos)>50001 or sum(i.filename==MANIFEST for i in infos)!=1:raise ValueError('Missing/ambiguous manifest')
        mi=z.getinfo(MANIFEST)
        if mi.file_size>20_000_000:raise ValueError('Manifest size budget exceeded')
        m=json.loads(z.read(mi))
        if m.get('schema_version')!='delivery_1.0' or not isinstance(m.get('files'),list) or not m['files']:
            raise ValueError('Invalid delivery manifest')
        expected={};total=0
        for e in m['files']:
            name=portable_name(e['path']);key=name.casefold()
            if key in expected:raise ValueError('Duplicate or case-colliding manifest path')
            if type(e.get('size_bytes'))!=int or not 0<=e['size_bytes']<=MAX_FILE or not re.fullmatch('[0-9a-f]{64}',e.get('sha256','')):
                raise ValueError('Invalid file size/hash')
            expected[key]=e;total+=e['size_bytes']
        if total>MAX_TOTAL or total!=m.get('total_bytes'):raise ValueError('Archive size budget or manifest total mismatch')
        actual={}
        for i in infos:
            if i.filename==MANIFEST:continue
            name=portable_name(i.filename);key=name.casefold()
            if key in actual or key not in expected or name!=expected[key]['path']:
                raise ValueError('Unexpected, duplicate or case-colliding archive path')
            mode=i.external_attr>>16
            if i.is_dir() or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in [0,stat.S_IFREG]):
                raise ValueError('Only ordinary files are accepted')
            e=expected[key]
            if i.file_size!=e['size_bytes']:raise ValueError('Archive file size mismatch')
            h=hashlib.sha256();count=0
            with z.open(i) as stream:
                while chunk:=stream.read(1024*1024):h.update(chunk);count+=len(chunk)
            if count!=e['size_bytes'] or h.hexdigest()!=e['sha256']:raise ValueError('Archive hash mismatch: '+name)
            actual[key]=e
        if set(actual)!=set(expected):raise ValueError('Archive is incomplete')
    return m


def verify(archive):
    archive=safe_path(ROOT,archive);m=verified_archive(archive)
    return dict(status='ARCHIVE_BYTES_VERIFIED',archive=item(archive),files=len(m['files']),total_bytes=m['total_bytes'])


def restore(archive, destination):
    archive=safe_path(ROOT,archive);before=sha(archive);m=verified_archive(archive)
    dest=safe_path(ROOT,destination)
    if dest.exists():raise ValueError('Restore requires a nonexistent destination; existing workspace is never overwritten')
    dest.mkdir(parents=True,exist_ok=False)
    try:
        with zipfile.ZipFile(archive) as z:
            for e in m['files']:
                p=dest/e['path'];p.parent.mkdir(parents=True,exist_ok=True)
                with p.open('xb') as f,z.open(e['path']) as stream:shutil.copyfileobj(stream,f,1024*1024)
                if p.stat().st_size!=e['size_bytes'] or sha(p)!=e['sha256']:raise ValueError('Restored hash mismatch')
        if sha(archive)!=before:raise ValueError('Archive changed during restore')
    except Exception:
        # Partial evidence is retained. Never recursively delete an unknown destination.
        save(dest/'RESTORE_FAILED.json',dict(status='FAILED_DO_NOT_USE',archive=str(archive)))
        raise
    save(dest/MANIFEST,m)
    receipt=dict(status='RESTORED_BYTES_VERIFIED',created_utc=utc(),archive=item(archive),
        destination=rel(dest),files=len(m['files']),total_bytes=m['total_bytes'],
        environment='NOT_PROVISIONED',fresh_solver='NOT_RUN',engineering_acceptance='NOT_ASSESSED')
    save(dest/'RESTORE_RECEIPT.json',receipt)
    return receipt


def verify_tree(directory):
    root=safe_path(ROOT,directory);m=read(root/MANIFEST);failed=[]
    if m.get('schema_version')!='delivery_1.0':raise ValueError('Unsupported delivery manifest')
    for e in m['files']:
        name=portable_name(e['path']);p=safe_path(root,name)
        if not p.is_relative_to(root) or not p.is_file() or p.stat().st_size!=e['size_bytes'] or sha(p)!=e['sha256']:failed.append(name)
    return dict(status='RESTORED_BYTES_VERIFIED' if not failed else 'FAILED',failed=failed,files=len(m['files']),
        note='Checks packaged files only; new local outputs are allowed. Not an authenticity signature.')


def upgrade_check(archive,directory='.'):
    """Read-only impact report. Upgrade by side-by-side restore, never overwrite."""
    archive=safe_path(ROOT,archive);root=safe_path(ROOT,directory);m=verified_archive(archive)
    version_file=root/'ras_workflow/__init__.py';installed=None
    if version_file.exists():
        for statement in ast.parse(version_file.read_text(encoding='utf-8')).body:
            if isinstance(statement,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__version__' for t in statement.targets):
                installed=ast.literal_eval(statement.value)
    incoming=m.get('workflow_version');supported=m.get('project_schema_versions',[])
    projects=[];blockers=[]
    for folder in ['projects','benchmarks']:
        for p in sorted((root/folder).glob('*/project.json')):
            try:
                c=read(p);schema=c.get('schema_version');compatible=schema in supported
                projects.append(dict(path=p.relative_to(root).as_posix(),schema=schema,compatible=compatible))
                if not compatible:blockers.append('Unsupported project schema: '+str(p.relative_to(root)))
            except (ValueError,OSError) as e:blockers.append('Cannot inspect project '+str(p.relative_to(root))+': '+str(e))
    changed=[];added=[];same=[]
    for e in m['files']:
        p=safe_path(root,e['path'])
        if not p.is_relative_to(root):raise ValueError('Upgrade candidate leaves target tree')
        if not p.exists():added.append(e['path'])
        elif p.is_file() and sha(p)==e['sha256']:same.append(e['path'])
        else:changed.append(e['path'])
    if not incoming:blockers.append('Archive predates version metadata; inspect legacy delivery manually')
    return dict(status='REVIEW_REQUIRED' if blockers else 'READY_FOR_SIDE_BY_SIDE_RESTORE',created_utc=utc(),
        installed_version=installed,incoming_version=incoming,archive=item(archive),projects=projects,blockers=blockers,
        changed_files=changed,new_files=added,unchanged_files=same,
        action='Back up selected private inputs/results, restore into a new directory, verify hashes, provision environment, and run fresh acceptance. No files changed by this check.',
        compatibility='Schema check only; no solver or cross-machine acceptance',engineering_acceptance='NOT_ASSESSED')
