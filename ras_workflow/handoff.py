"""Inspect a saved handoff and restore a damaged delivery PDF from identical bytes."""
from pathlib import Path
import os
import shutil
from tempfile import NamedTemporaryFile

from . import app_core as core
from .common import ROOT, digest, intact, item, lock, read, rel, safe_path, save, sha, unique_id


def copy_verified(source, target, expected):
    target.parent.mkdir(parents=True,exist_ok=True)
    with NamedTemporaryFile(dir=target.parent,suffix='.partial',delete=False) as stream:
        temporary=Path(stream.name)
    try:
        shutil.copyfile(source,temporary)
        if sha(temporary)!=expected:raise ValueError('Recovery source changed during copying')
        os.replace(temporary,target)
    finally:
        temporary.unlink(missing_ok=True)


def retain_unique_exhibit(full,receipt):
    if not receipt['mapped']:return
    # English also exists in Minimal. Each report also exists in its registered edition.
    file=full/'Graph/Exhibit_CN.pdf'
    expected=sha(file)
    target=ROOT/'status/pdf_recovery'/expected[:2]/(expected+'.pdf')
    if not target.is_file() or sha(target)!=expected:copy_verified(file,target,expected)


def bound_package(m):
    receipt=m.get('latest_delivery') or m.get('previous_delivery')
    if not receipt and m.get('engine_state'):receipt=read(safe_path(ROOT,m['engine_state'])).get('delivery')
    if not receipt or not all(receipt.get(k,{}).get('manifest') for k in ('complete','minimal')):return None
    if not intact([receipt['summary']]):raise ValueError('Restore the archived calculation summary')
    folder=core.folder(m['id']).resolve()
    for k in ('complete','minimal'):
        path=safe_path(ROOT,receipt[k]['path'])
        ref=receipt[k]['manifest']
        if (not path.is_relative_to(folder) or path/'PACKAGE_MANIFEST.json'!=safe_path(ROOT,ref['path']) or
                not intact([ref])):raise ValueError('The saved package manifest requires review')
    return receipt


def package_member(folder,name):
    path=(folder/name).resolve()
    if not path.is_relative_to(folder) or path==folder or path!=(folder/name).absolute():
        raise ValueError('Invalid sealed package member')
    return path


def storage(m):
    pins=read(ROOT/'scripts/setup_downloads.json')
    cache=ROOT/'.tools/downloads'
    downloads=[]
    for row in pins.values():
        p=cache/row['name']
        if p.is_file() and not p.is_symlink() and p.resolve().parent==cache.resolve() and sha(p)==row['sha256']:
            downloads.append(dict(name=p.name,bytes=p.stat().st_size))
    original=[dict(name=Path(a['path']).name,bytes=a.get('size_bytes'),type=Path(a['path']).suffix.lower()) for a in m.get('attachments',[])]
    return dict(reinstallable=downloads,originals=original)


def inspection(key,body):
    m=core.model(key)
    if body.get('revision')!=m['revision']:raise ValueError('Reopen the current project edition')
    receipt=bound_package(m)
    result=dict(storage=storage(m),package=None)
    if not receipt:return result
    full=safe_path(ROOT,receipt['complete']['path'])
    summary=read(ROOT/receipt['summary']['path'])
    entries={}
    for kind in ('complete','minimal'):
        entries[kind]=read(ROOT/receipt[kind]['manifest']['path'])['files']
    hashes={k:{r['sha256'] for r in v} for k,v in entries.items()}
    attachments=[dict(name=Path(a['path']).name,kind=Path(a['path']).suffix.lower(),**{k:a['sha256'] in h for k,h in hashes.items()})
                 for a in m.get('attachments',[])]
    packs=[]
    for k,rows in entries.items():
        folder=safe_path(ROOT,receipt[k]['path'])
        for row in rows:
            if not row['path'].startswith(('Graph/','Reports/')) or not row['path'].lower().endswith('.pdf'):continue
            p=package_member(folder,row['path'])
            packs.append(dict(package=k,path=row['path'],ok=p.is_file() and p.stat().st_size==row['size_bytes'] and sha(p)==row['sha256']))
    loc=summary['configuration'].get('location') or {}
    result['package']=dict(run=receipt['run_id'],edition=digest([receipt[k]['manifest'] for k in ('complete','minimal')]),
        stale=m.get('exports_need_refresh',False) or receipt['summary']!=m.get('summary'),
        latitude=loc.get('latitude'),longitude=loc.get('longitude'),mapped=receipt.get('mapped'),attachments=attachments,
        coordinate_files={k:[r['path'] for r in rows if r['path'].lower().endswith(('.qgz','.shp','.gpkg','.rasmap','.tif','.g01.hdf'))] for k,rows in entries.items()},
        additional_sources=[r['path'] for r in entries['complete'] if r['path'].startswith('Sources/')],pdfs=packs)
    return result


def repair(key,body):
    m=core.model(key);core.require_idle(m)
    folder=core.folder(key)
    with lock(folder/'pdf_recovery.lock'):
        preview=inspection(key,body)['package']
        if not preview or preview['stale'] or body.get('edition')!=preview['edition']:raise ValueError('Reopen the current handoff')
        kind,name=body.get('package'),body.get('path')
        selected=next((r for r in preview['pdfs'] if (r['package'],r['path'])==(kind,name)),None)
        if not selected:raise ValueError('Select a report or exhibit PDF from the sealed inventory')
        if selected['ok']:return dict(status='ALREADY_VERIFIED',run=preview['run'])
        receipt=bound_package(m)
        root=safe_path(ROOT,receipt[kind]['path'])
        rows=read(ROOT/receipt[kind]['manifest']['path'])['files']
        expected=next(r['sha256'] for r in rows if r['path']==name)
        target=package_member(root,name)
        full=safe_path(ROOT,receipt['complete']['path'])
        other='minimal' if kind=='complete' else 'complete'
        candidates=[package_member(safe_path(ROOT,receipt[other]['path']),name),ROOT/'status/pdf_recovery'/expected[:2]/(expected+'.pdf')]
        if name.startswith('Reports/'):
            manifest_name='Evidence/report_manifest.original.json'
            full_rows=read(ROOT/receipt['complete']['manifest']['path'])['files']
            ref=next((r for r in full_rows if r['path']==manifest_name),{})
            manifest=full/manifest_name
            if sha(manifest)!=ref.get('sha256'):raise ValueError('Restore the sealed report manifest')
            for edition in read(manifest)['reports']:
                if edition['pdf']['sha256']==expected:candidates.append(safe_path(ROOT,edition['pdf']['path']))
        source=next((p for p in candidates if p!=target and p.is_file() and sha(p)==expected),None)
        if not source:raise ValueError('No matching PDF copy survives. Restore this file from a verified backup or publish a new edition from the saved run.')
        copy_verified(source,target,expected)
        record=dict(status='RESTORED',run=preview['run'],restored=item(target),source=item(source),new_solver_calls=0)
        save(folder/'pdf_recovery'/unique_id()/'receipt.json',record)
        return record
