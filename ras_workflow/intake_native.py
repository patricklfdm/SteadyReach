"""Reviewed native-file handoff inside the coordinate input wizard."""
import base64
import copy
import re
from pathlib import Path
from .common import ROOT, intact, item, lock, read, rel, safe_path, save, unique_id, utc
from . import intake, native_review, native_context, inputs


def preview(session_path):
    sp,s,p,d=intake._load(session_path,active=False)
    entry=d.get('native_import')
    if not entry:return None
    if not intact([entry]):raise ValueError('Native import preview changed; upload the source files again')
    packet=read(ROOT/entry['path'])
    if not intact(list(packet['files'].values())):raise ValueError('Native input files changed')
    c,_=intake._objects(p,d)
    try:matches=native_context.reconcile(packet,c,p['scenario']);error=None
    except ValueError as e:matches=[];error=str(e)
    return dict(packet=packet,prior_profile_matches=matches,reconciliation_error=error)


def from_workspace(session_path,body):
    """Explicit local file selection, confined to the workspace and four inputs."""
    value=body.get('project')
    if not isinstance(value,str) or not value.strip():raise ValueError('Enter the native .prj path inside this workspace')
    project=safe_path(ROOT,value.strip())
    if project.suffix.lower()!='.prj':raise ValueError('Select a HEC-RAS .prj input, not a result file')
    total=0
    def bounded(path):
        nonlocal total
        path=safe_path(ROOT,path)
        total+=path.stat().st_size
        if total>15_000_000:raise ValueError('Native input selection exceeds 15 MB')
        return path
    project=bounded(project)
    current=body.get('selected_plan') or native_review.card(native_review.text(project).splitlines(),'Current Plan')
    if not isinstance(current,str):raise ValueError('Select a saved steady plan such as p01')
    current=current.strip().lower()
    if not re.fullmatch(r'p\d{2}',current):raise ValueError('Select a saved steady plan in HEC-RAS first')
    plan=bounded(project.with_suffix('.'+current));lines=native_review.text(plan).splitlines()
    refs=[native_review.card(lines,key) for key in ['Geom File','Flow File']]
    if not re.fullmatch(r'g\d{2}',refs[0]) or not re.fullmatch(r'f\d{2}',refs[1]):
        raise ValueError('Only selected 1D steady geometry and flow inputs are supported')
    paths=[project,plan]+[bounded(project.with_suffix('.'+ref)) for ref in refs]
    sources=[item(p,'explicit_workspace_native_input') for p in paths]
    files=[dict(name=p.name,content=base64.b64encode(p.read_bytes()).decode('ascii')) for p in paths]
    return upload(session_path,dict(revision=body.get('revision'),source=body.get('source'),files=files),sources)


def upload(session_path,body,workspace_sources=None):
    sp=safe_path(ROOT,session_path)
    files=body.get('files')
    if not isinstance(files,list) or len(files)!=4:raise ValueError('Select exactly the .prj, selected .pNN, .gNN and .fNN input files together; no result files')
    source=body.get('source')
    if not isinstance(source,str) or not source.strip():raise ValueError('Describe the source, version and site applicability')
    decoded={};total=0
    for entry in files:
        name=entry.get('name','')
        if not re.fullmatch(r'[A-Za-z0-9_ .-]+\.(?:prj|[pgf]\d{2})',name,re.I) or name!=Path(name).name:
            raise ValueError('Use native input filenames without directory paths')
        if name.casefold() in {n.casefold() for n in decoded}:raise ValueError('Duplicate native input filename')
        raw=base64.b64decode(entry['content'],validate=True);total+=len(raw)
        if total>15_000_000:raise ValueError('Native input upload exceeds 15 MB')
        decoded[name]=raw
    projects=[n for n in decoded if Path(n).suffix.lower()=='.prj']
    if len(projects)!=1:raise ValueError('Select one HEC-RAS project .prj')
    plans=[n for n in decoded if re.fullmatch(r'\.p\d{2}',Path(n).suffix,re.I)]
    if len(plans)!=1:raise ValueError('Select exactly one steady plan .pNN / 请选择唯一的恒定流计划文件')
    selected=Path(plans[0]).suffix[1:].lower()
    if Path(plans[0]).stem.casefold()!=Path(projects[0]).stem.casefold():
        raise ValueError('Selected plan must belong to the selected project / 计划与工程文件名不对应')
    plan_lines=decoded[plans[0]].decode('ascii').splitlines()
    refs=[native_review.card(plan_lines,key) for key in ['Geom File','Flow File']]
    if not re.fullmatch(r'g\d{2}',refs[0]) or not re.fullmatch(r'f\d{2}',refs[1]):
        raise ValueError('Only selected 1D steady geometry and flow inputs are supported')
    expected={projects[0].casefold(),plans[0].casefold(),*[Path(projects[0]).with_suffix('.'+ref).name.casefold() for ref in refs]}
    if {n.casefold() for n in decoded}!=expected:
        raise ValueError('Uploaded files do not match selected plan references / 所选几何、流量文件与计划引用不一致: '+', '.join(refs))
    with lock(sp.parent/'session.lock'):
        sp,s,p,d=intake._load(sp)
        if body.get('revision')!=d['revision']:raise ValueError('Draft changed; reload before importing')
        folder=(ROOT/s['project']).parent/'native_imports'/unique_id()
        rawfolder=folder/'submitted';rawfolder.mkdir(parents=True)
        for name,raw in decoded.items():(rawfolder/name).write_bytes(raw)
        project=next(rawfolder/n for n in decoded if Path(n).suffix.lower()=='.prj')
        review_path=native_review.prepare(project,folder/'review',selected_plan=selected)
        c,_=intake._objects(p,d)
        d['native_import']=item(review_path)
        d['native_workspace_sources']=workspace_sources or []
        d['native_review']=dict(project_id=p['project_id'],title=c['title'],source=source.strip(),reviewer=d.get('reviewer',''),
            native_length_unit='',vertical_datum='',mapping=dict(horizontal_crs='',dem_vertical_unit='',dem_vertical_datum='',basis='',confirmed=False,contour_interval=2.))
        d['consent']=False;d['revision']+=1
        packet=read(review_path)
        save(sp.parent/'events'/(unique_id()+'.json'),dict(action='NATIVE_INPUTS_SELECTED_FROM_WORKSPACE' if workspace_sources else 'NATIVE_INPUTS_UPLOADED_FOR_REVIEW',files=[item(rawfolder/n) for n in decoded],originals=workspace_sources or [],source=source,created_utc=utc(),
            selected_plan=selected,previous_current_plan=packet['previous_current_plan'],plan_title=packet['plan_title']))
        save(sp.parent/'draft.json',d)
    return intake.view(sp)


def context(session_path):
    sp,s,p,d=intake._load(session_path);c,g=intake._objects(p,d)
    if not d.get('native_import') or not intact([d['native_import']]):raise ValueError('Upload and inspect native inputs first')
    from .geometry_editor import context as terrain_context
    *_,terrain,info=terrain_context(sp)
    checkpoint=sp.parent/'terrain_checkpoint.json'
    if checkpoint.is_file():provenance=item(checkpoint)
    else:
        provenance=item(safe_path((ROOT/p['project']).parent,c['terrain']['provenance']))
    sources=s['sources']+[s['packet'],p['original_project'],p['original_geometry'],d['native_import'],item(sp.parent/'draft.json'),provenance,terrain['raster']]+d['uploads']+d.get('native_workspace_sources',[])
    metadata=read(checkpoint).get('metadata',{}) if checkpoint.exists() else {}
    for product in metadata.get('products',[]):
        for value in product.values() if isinstance(product,dict) else []:
            if isinstance(value,dict) and {'path','sha256','size_bytes'}<=set(value):sources.append(value)
        result=product.get('result') if isinstance(product,dict) else None
        if result:
            if not intact([result]):raise ValueError('Terrain metadata evidence changed')
            sources.extend(read(safe_path(ROOT,result['path'])).get('sources',[]))
    return dict(configuration=c,scenario_id=p['scenario'],sources=sources,
        terrain=dict(raster=terrain['raster'],provenance=provenance))


def approve(session_path,body):
    sp=safe_path(ROOT,session_path);original=read(sp)['project']
    with lock((ROOT/original).parent/'project.lock'),lock(sp.parent/'session.lock'):
        sp,s,p,d=intake._load(sp)
        if body.get('revision')!=d['revision']:raise ValueError('Draft changed; review the latest revision')
        if body.get('confirmed') is not True:raise ValueError('Explicit conditional native-input approval is required')
        decision=copy.deepcopy(d.get('native_review',{}));decision['approve']=True
        cp=native_review.approve(ROOT/d['native_import']['path'],decision,context(sp))
        c=read(cp);gate,_=inputs.gate(cp,c,c['scenarios'][0]);inputs.dependencies(cp,c)
        if gate['status']=='BLOCKED':raise ValueError('; '.join(gate['blocking_items']))
        receipt=item(cp.parent/'import_receipt.json')
        s.update(status='APPLIED',approved_project=rel(cp),approval=receipt,finished_utc=utc(),handoff='REVIEWED_NATIVE_INPUTS')
        save(sp,s)
        save(sp.parent/'events'/(unique_id()+'.json'),dict(action='APPROVE_NATIVE_HANDOFF',project=rel(cp),approval=receipt,created_utc=utc()))
        return dict(status='APPLIED',project=rel(cp),engineering_acceptance='NOT_ASSESSED')
