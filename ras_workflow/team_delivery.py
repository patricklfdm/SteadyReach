"""Scope a selected release for a client while preserving the internal evidence package."""
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from . import app_core as core, handoff, site_delivery
from .common import ROOT, digest, read, rel, save, sha
from .delivery_pair import check

# Native map/model dependencies are selected from the existing verified Minimal package.
# Additional members require explicit reader-facing names, even if present elsewhere in Complete.
EXHIBITS = {f'Graph/Exhibit_{lang}.{ext}' for lang in ('CN','EN') for ext in ('pdf','png')}
REPORTS = {f'Reports/{name}.{ext}' for name in ('Report_CN','Report_EN','Summary_EN') for ext in ('pdf','docx')}
GIS = {'GIS_Project.qgz','Layouts/Exhibit_CN.qpt','Layouts/Exhibit_EN.qpt','GIS/Model_layers.gpkg'}
GIS.update('GIS/Contours.'+ext for ext in ('dbf','shp','shx','prj','cpg'))
GIS.update('GIS/'+n+suffix for n in ('Aerial.tif','Terrain_source.tif') for suffix in ('','.aux.xml'))


def inventories(key):
    model=core.model(key)
    from .iteration_choice import latest
    choice=latest(model) or {}
    if choice.get('choice') in ('parent','wait','unavailable'):
        raise ValueError('Open the selected working edition / 请打开当前选用的工作版')
    receipt=handoff.bound_package(model)
    if not receipt or model.get('exports_need_refresh') or model.get('summary')!=receipt['summary']:
        raise ValueError('Refresh the delivery for the selected edition / 请更新所选版交付包')
    roots={n:ROOT/receipt[n.lower()]['path'] for n in ('Minimal','Complete')}
    for path in roots.values():
        site_delivery.verify(path)
    pair=check(roots['Complete'],roots['Minimal'])
    records={n:read(p/'PACKAGE_MANIFEST.json')['files'] for n,p in roots.items()}
    run=read(roots['Complete']/'Evidence/run_manifest.original.json')
    native_members={'HEC_RAS/'+Path(e['path']).name for e in run['native_after']
                    if Path(e['path']).suffix.lower() in ('.prj','.p01','.g01','.f01')}
    native_result=read(roots['Complete']/'Evidence/summary.original.json')['hydraulics']['raw_hdf']
    native_members.add('HEC_RAS/'+Path(native_result['path']).name)
    native_members.update({'HEC_RAS/Model.g01.hdf','HEC_RAS/Model.O01','HEC_RAS/Model.rasmap','HEC_RAS/msvcr100.dll',
                           'HEC_RAS/Terrain/Terrain.hdf','HEC_RAS/Terrain/Terrain.Terrain_source.tif',
                           'HEC_RAS/Terrain/Terrain.vrt','CRS/Projection.prj','READ_ME.txt'})
    allow=native_members|REPORTS|EXHIBITS|GIS
    client={n:[r for r in rows if r['path'] in allow] for n,rows in records.items()}
    required={'Reports/Report_EN.pdf','Reports/Report_CN.pdf'}
    if not required.issubset({r['path'] for r in client['Complete']}):
        raise ValueError('Restore both full reports before delivery / 请先恢复中英文完整报告')
    native=read(roots['Complete']/'Evidence/summary.original.json')['hydraulics']['raw_hdf']
    for label,rows in client.items():
        match=[r for r in rows if r['path']=='HEC_RAS/'+Path(native['path']).name and r['sha256']==native['sha256']]
        if len(match)!=1:
            raise ValueError('Native result missing in '+label)
    internal={name:[dict(r,distribution='client' if r['path'] in allow else 'internal') for r in rows]
              for name,rows in records.items()}
    token=digest(dict(edition=receipt['summary'],pair=pair,client=client,internal=internal))
    return dict(run_id=pair['run_id'],summary_sha256=pair['summary_sha256'],hdf_sha256=pair['native_hdf_sha256'],
                client=client,internal=internal,scope_token=token),roots


def preview(key):
    inventory,_=inventories(key)
    return inventory


def preview_file(key,body):
    """Show limited content from one verified member of the current internal inventory."""
    inventory,roots=inventories(key)
    if inventory['scope_token']!=body.get('scope_token'):
        raise ValueError('Refresh the recipient preview / 请刷新收件范围预览')
    package=body.get('package');name=body.get('member')
    if package not in roots:raise ValueError('Choose a package')
    row=next((r for r in inventory['internal'][package] if r['path']==name),None)
    if row is None:raise ValueError('Choose a member listed in the inventory')
    path=handoff.package_member(roots[package],name)
    result=dict(member=row,format='metadata',text=None)
    if row['size_bytes']>12*1024**2:return result
    suffix=path.suffix.lower()
    if suffix in ('.txt','.md','.csv','.json','.xml','.prj'):
        with path.open('rb') as stream:snippet=stream.read(12000).decode('utf-8-sig',errors='replace')
        result.update(format='text',text=snippet[:3000])
    elif suffix=='.pdf':
        from pypdf import PdfReader
        pages=PdfReader(path).pages
        result.update(format='text',pages=len(pages),text=(pages[0].extract_text() or '')[:3000] if pages else '')
    elif suffix=='.docx':
        from docx import Document
        result.update(format='text',text='\n'.join(p.text for p in Document(path).paragraphs[:40])[:3000])
    elif suffix in ('.jpg','.jpeg','.png'):
        import base64,io
        from PIL import Image
        with Image.open(path) as img:
            if img.width*img.height<=25_000_000:
                img.thumbnail((512,350));output=io.BytesIO();img.convert('RGB').save(output,'JPEG')
                result.update(format='image',image='data:image/jpeg;base64,'+base64.b64encode(output.getvalue()).decode('ascii'))
    return result


def export(key,edition,token,review_head):
    scope,roots=inventories(key)
    if scope['scope_token']!=token or edition['run']!=scope['run_id'] or edition['summary_sha256']!=scope['summary_sha256']:
        raise ValueError('Reopen the recipient preview for this run / 请重新核对本次运行的收件范围')
    folder=core.folder(key)
    destination=folder/('Issue_'+digest([token,review_head])[:14])
    public=dict(edition=edition,packages=scope['client'],scope='client')
    internal=dict(edition=edition,source_packages=scope['internal'],scope='internal',review_head=review_head)
    from .team_review import inspect
    internal['decisions']=inspect(key)['history']
    guides={
        'Start_EN.txt':f"SteadyReach | {edition['run']}\nOpen Complete/Reports/Report_EN.pdf to read the project use and limitations. Open the HEC-RAS project in Minimal/HEC_RAS. CLIENT.json lists every technical file by package and SHA-256.\n",
        'Start_zh-CN.txt':f"SteadyReach | {edition['run']}\n打开 Complete/Reports/Report_CN.pdf 查看项目用途与限制。可从 Minimal/HEC_RAS 打开模型。CLIENT.json 列出两个包的文件及 SHA-256。\n"}
    def verify(dest):
        if {p.name for p in dest.iterdir()}!={'Client','Internal'}:raise ValueError('Issue folder changed')
        client=dest/'Client'
        if {p.name for p in client.iterdir()}!={'Complete','Minimal','CLIENT.json',*guides}:raise ValueError('Unexpected outbound attachment')
        if read(client/'CLIENT.json')!=public or read(dest/'Internal/INTERNAL.json')!=internal:
            raise ValueError('Review or scope inventory differs')
        for label,rows in public['packages'].items():
            pack=client/label
            site_delivery.verify(pack)
            expected={r['path'] for r in rows}|{'PACKAGE_MANIFEST.json'}
            actual={p.relative_to(pack).as_posix() for p in pack.rglob('*') if p.is_file()}
            if actual!=expected or read(pack/'PACKAGE_MANIFEST.json')['files']!=rows:
                raise ValueError('Client package differs from the preview / 客户版内容与预览不同')
        for name,body in guides.items():
            if (client/name).read_text(encoding='utf-8')!=body:raise ValueError('Opening guide changed')
    if destination.exists():
        verify(destination)
    else:
        size=sum(row['size_bytes'] for rows in public['packages'].values() for row in rows)
        if shutil.disk_usage(folder).free<size+1024*1024:
            raise ValueError('Insufficient space for the client copy / 客户版副本所需空间不足')
        with TemporaryDirectory(dir=folder) as temporary:
            stage=Path(temporary)/'issue';client=stage/'Client'
            for label,rows in public['packages'].items():
                pack=client/label
                for row in rows:
                    src=handoff.package_member(roots[label],row['path'])
                    target=pack/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(src,target)
                site_delivery.seal(pack)
            save(client/'CLIENT.json',public)
            save(stage/'Internal/INTERNAL.json',internal)
            for name,body in guides.items():
                (client/name).write_text(body,encoding='utf-8')
            verify(stage)
            current=core.model(key)
            if current.get('summary',{}).get('sha256')!=edition['summary_sha256'] or current.get('exports_need_refresh'):
                raise ValueError('Selected edition changed during export')
            stage.rename(destination)
    return dict(client=rel(destination/'Client'),internal=rel(destination/'Internal'),run=edition['run'],
                client_inventory_sha256=sha(destination/'Client/CLIENT.json'),internal_inventory_sha256=sha(destination/'Internal/INTERNAL.json'))
