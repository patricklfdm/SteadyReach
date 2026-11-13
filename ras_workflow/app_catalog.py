"""Import public attachments from an explicitly selected ScienceBase record."""
import re
from pathlib import Path
from urllib.parse import urlsplit
from .common import ROOT,read,save,item,unique_id
from . import app_core as core,app_acquisition as acquisition


def queue(key,body):
    m=core.model(key);core.require_idle(m)
    if body.get('revision')!=m['revision']:raise ValueError('Refresh before selecting a source')
    url=str(body.get('url','')).strip();p=urlsplit(url)
    if p.scheme!='https' or p.hostname not in ('www.sciencebase.gov','sciencebase.gov') or p.username or p.password or p.port or p.query or p.fragment or not re.fullmatch('/catalog/item/[0-9a-f]{24}',p.path):raise ValueError('Choose a public ScienceBase catalog item URL (not File Manager)')
    m['selected_catalog']=url;m['revision']+=1;core.persist(m,'SELECT_PUBLIC_CATALOG',dict(url=url))
    return core.launch(key,'catalog')


def acquire(key):
    from .source_fetch import Download
    m=core.model(key);url=m['selected_catalog'];out=core.folder(key)/'catalog_imports'/unique_id();records=[]
    download=Download(limit=35_000_000,timeout=12)
    try:
        record=download.json(url+'?format=json');save(out/'catalog.json',record)
        for f in record.get('files',[])[:30]:
            name=Path(str(f.get('name','')).replace('\\','/')).name;source_url=f.get('url','')
            if Path(name).suffix.lower() not in ('.csv','.pdf','.txt','.xml','.jpg','.jpeg','.png'):
                records.append(dict(name=name,status='MANUAL_OR_UNSUPPORTED_ATTACHMENT',reason='Archives and unrecognized formats require selection of a site-specific subset'));continue
            if '/manager/' in source_url:
                records.append(dict(name=name,status='PUBLIC_DOWNLOAD_ACTION_REQUIRED',url=url));continue
            try:
                source=acquisition.add_file(m,name,download.get(source_url,limit=10_000_000),source_url)
                records.append(dict(name=name,status='DOWNLOADED',source=source))
            except Exception as e:records.append(dict(name=name,status='DOWNLOAD_FAILED',error=str(e),url=url))
    except Exception as e:records.append(dict(status='CATALOG_FAILED',error=str(e),url=url))
    save(out/'attempt.json',dict(url=url,files=records,downloaded_bytes=download.used,scope='Explicitly selected record; site/event/group applicability remains unverified'))
    m['catalog_attempt']=item(out/'attempt.json');core.persist(m,'PUBLIC_CATALOG_IMPORTED',dict(attempt=m['catalog_attempt']))
    acquisition.analyze(key,network=False)
