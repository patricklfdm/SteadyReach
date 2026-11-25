"""Freeze the exact evidence bytes and rebuild an intake inventory without network I/O."""
import json
from pathlib import Path
import shutil
import tempfile
from zipfile import ZipFile,ZIP_DEFLATED

from . import app_core as core
from .common import ROOT,digest,item,read,rel,safe_path,save,sha,unique_id
from .intake_register import context,inventory


def local(ref):
    path=safe_path(ROOT,ref['path'])
    if not path.is_file() or sha(path)!=ref['sha256']:
        raise ValueError('Locate the matching evidence file / 请找回指纹相符的资料: '+ref['path'])
    return path


def build(m):
    ctx=context(m);cache={}
    def checked(r):
        key=(r['path'],r['sha256'])
        if key not in cache:cache[key]=local(r)
        return cache[key]
    return ctx,inventory(ctx,checked)


def replay(path,expected_hash=None):
    if expected_hash and sha(path)!=expected_hash:raise ValueError('Frozen archive changed / 冻结归档已变化')
    with ZipFile(path) as archive,tempfile.TemporaryDirectory(prefix='intake_replay_') as work:
        manifest=json.loads(archive.read('intake.json'));ctx=manifest['context']
        if ctx.get('schema')!='hydraulic_intake_v1':raise ValueError('Unsupported frozen intake')
        files={r['sha256'] for r in ctx['sources']};names=archive.namelist()
        if len(names)!=len(set(names)) or set(names)!={'intake.json',*('objects/'+h for h in files)}:raise ValueError('Frozen inventory differs')
        for h in files:
            if len(h)!=64 or any(c not in '0123456789abcdef' for c in h):raise ValueError('Invalid frozen fingerprint')
            member=Path(work)/h
            with archive.open('objects/'+h) as src,member.open('xb') as dst:shutil.copyfileobj(src,dst)
            if sha(member)!=h:raise ValueError('Frozen member changed')
        register=inventory(ctx,lambda r:Path(work)/r['sha256'])
        if digest(register)!=manifest['register_hash']:raise ValueError('Offline interpretation differs / 离线复核结论有变化')
        return dict(register=register,register_hash=manifest['register_hash'],files=len(ctx['sources']),objects=len(files),edition=ctx['edition'])


def survey_copy(archive_path,folder,imagery_folder=None):
    """Reconstitute the registered original survey package from frozen member bytes."""
    import hashlib
    from .survey_import import parse
    import base64
    with ZipFile(archive_path) as archive:
        ctx=json.loads(archive.read('intake.json'))['context']
        surveys={r['sha256']:r for r in ctx['attachments'] if r.get('role')=='survey_manifest'}
        if len(surveys)!=1:raise ValueError('A single frozen survey manifest is required / 需要一份冻结实测清单')
        h=next(iter(surveys));raw=archive.read('objects/'+h)
        if hashlib.sha256(raw).hexdigest()!=h:raise ValueError('Frozen survey manifest changed')
        manifest=json.loads(raw)
        package={'survey.json':raw};members={r['sha256'] for r in ctx['sources']}
        for entry in manifest['files']:
            name=entry['name'];h=entry['sha256']
            if Path(name).name!=name or name in package or h not in members:raise ValueError('Survey manifest differs from the frozen inventory')
            package[name]=archive.read('objects/'+h)
            if hashlib.sha256(package[name]).hexdigest()!=h:raise ValueError('Frozen survey file changed: '+name)
        parse([dict(name=n,content=base64.b64encode(v).decode('ascii')) for n,v in package.items()])
        aerial={}
        if imagery_folder and set(ctx.get('imagery',{}))=={'raster','receipt'}:
            for key,name in [('raster','Aerial.tif'),('receipt','acquisition.json')]:
                h=ctx['imagery'][key]['sha256'];data=archive.read('objects/'+h)
                if hashlib.sha256(data).hexdigest()!=h:raise ValueError('Frozen imagery changed')
                aerial[name]=data
    folder.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=folder.parent) as tmp:
        stage=Path(tmp)/'survey';stage.mkdir()
        for name,data in package.items():(stage/name).write_bytes(data)
        if aerial:
            imagery_folder.mkdir(parents=True,exist_ok=False)
            for name,data in aerial.items():(imagery_folder/name).write_bytes(data)
        stage.rename(folder)
    return folder


def directory(key):return core.folder(key)/'intake_evidence'


def perform(key,action,body):
    m=core.model(key);base=directory(key)
    if action in ('replay','survey-copy'):
        if not (base/'latest.json').is_file():raise ValueError('Inspect and freeze this edition first / 请先查看并冻结此版本的资料')
        entry=read(base/'latest.json');result=replay(local(entry),entry['sha256'])
        if result['edition']!=key:raise ValueError('Frozen edition differs')
        if action=='survey-copy':
            bundle=base/'survey_copies'/unique_id();bundle.parent.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(dir=bundle.parent) as work:
                stage=Path(work)/'bundle';survey_copy(ROOT/entry['path'],stage/'Survey',stage/'Imagery');stage.rename(bundle)
            folder=bundle/'Survey'
            return dict(folder=rel(folder),imagery=rel(bundle/'Imagery') if (bundle/'Imagery').is_dir() else None,archive_sha256=entry['sha256'])
        return result
    ctx,register=build(m);fingerprint=digest(ctx)
    if action=='inspect':return dict(register=register,token=fingerprint,frozen=(base/'latest.json').is_file())
    if action not in ('note','freeze') or body.get('token')!=fingerprint:raise ValueError('Refresh the evidence inventory / 请刷新资料清单')
    if action=='note':
        from .intake_boundary import iso
        from .intake_register import CATEGORIES
        core.require_idle(m)
        if m.get('active_project') or m.get('summary'):raise ValueError('Add metadata to an editable edition / 请在可编辑版本中补充元数据')
        source=next((r for r in ctx['sources'] if r['sha256']==body.get('source_sha256') and r.get('role')!='source_metadata_note'),None)
        if not source or body.get('category') not in CATEGORIES:raise ValueError('Select a registered source and evidence type')
        local(source);note=dict(source_sha256=source['sha256'],category=body['category'])
        for field in ('date','footprint','datum','unit','version'):
            value=body.get(field,'')
            if not isinstance(value,str) or len(value)>500:raise ValueError('Invalid evidence metadata')
            if value.strip():note[field]=value.strip()
        if len(note)==2 or ('date' in note and not iso(note['date'])):raise ValueError('Add documented metadata and use an ISO date / 请填写有依据的资料信息，日期格式为 YYYY-MM-DD')
        path=base/'metadata'/(digest(note)+'.json');save(path,note);entry=item(path,'source_metadata_note')
        notes=[r for r in m.get('intake_source_notes',[]) if r.get('source_key')!=[note['category'],source['sha256']]]
        notes.append(dict(entry,source_key=[note['category'],source['sha256']]))
        if notes!=m.get('intake_source_notes'):
            m['intake_source_notes']=notes;m['revision']+=1;m.pop('pending_review',None);core.persist(m,'RECORD_SOURCE_METADATA')
        return dict(id=key,source=entry)
    core.require_idle(m);base.mkdir(exist_ok=True)
    target=base/(fingerprint+'.zip');temp=base/(unique_id()+'.partial')
    try:
        if not target.exists():
            seen=set()
            with ZipFile(temp,'x',ZIP_DEFLATED,compresslevel=1) as archive:
                for ref in ctx['sources']:
                    path=local(ref);h=ref['sha256']
                    if h not in seen:archive.write(path,'objects/'+h);seen.add(h)
                archive.writestr('intake.json',json.dumps(dict(context=ctx,register_hash=digest(register)),ensure_ascii=False))
            replay(temp);temp.rename(target)
        else:replay(target)
        entry=item(target,'frozen_hydraulic_intake');save(base/'latest.json',entry)
        return dict(archive=entry,register_hash=digest(register),files=len(ctx['sources']))
    finally:temp.unlink(missing_ok=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Rebuild the hydraulic intake from a portable archive offline.')
    parser.add_argument('archive',type=Path)
    parser.add_argument('--sha256',help='Expected archive SHA-256 from the freeze receipt')
    args=parser.parse_args()
    result=replay(args.archive,args.sha256)
    print(json.dumps({k:v for k,v in result.items() if k!='register'},indent=2))
