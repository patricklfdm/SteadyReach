"""New editable project revisions; solved projects and confirmations are immutable."""
import copy
import os
from .common import ROOT, read, save, item, rel, safe_path, intact, unique_id, utc
from . import app_core as core, intake


def create(key, body):
    parent=core.model(key);core.require_idle(parent)
    if body.get('revision')!=parent['revision']:raise ValueError('Project changed; reload before revising')
    if body.get('confirmed') is not True:raise ValueError('Confirm creating an independent editable revision')
    if parent.get('native_review'):raise ValueError('For native-model edits, edit a copy in HEC-RAS and import its input files as a new project')
    if not parent.get('summary') or not intact([parent['summary']]):raise ValueError('An intact completed calculation is required')
    from .app_parameters import objects
    sp,p,d,c,g=objects(parent)
    source_base=(ROOT/p['project']).parent
    key2='site_'+unique_id().lower();folder=core.folder(key2);folder.mkdir(parents=True)
    c=copy.deepcopy(c);g=copy.deepcopy(g)
    for field in ('raster','provenance'):
        if c.get('terrain',{}).get(field):c['terrain'][field]=os.path.relpath(safe_path(source_base,c['terrain'][field]),folder)
    for field in ('native_project','reference_results','benchmark_preparation'):
        if c.get(field):c[field]=os.path.relpath(safe_path(source_base,c[field]),folder)
    delivery=c.setdefault('delivery',{})
    delivery['additional_sources']=[os.path.relpath(safe_path(source_base,v),folder) for v in delivery.get('additional_sources',[])]
    for field in ('authorization','configuration_approval','intake_candidates','section_workflow'):
        c.pop(field,None)
    c.update(project_id=key2,title=parent['title']+' · revision',geometry='geometry.json',model_proposal_pending=True)
    g.update(approved_for_model=False,status='EDITABLE_REVISION')
    save(folder/'geometry.json',g);save(folder/'initial.json',c)
    session=intake.prepare(folder/'initial.json',parent['scenario'])
    new_sp=ROOT/session['session'];draft=read(new_sp.parent/'draft.json')
    # Preserve explicit values and their origins, never reuse prior consent.
    for field in ('answers','uploads','section_workflow','geometry_edit_sources'):
        if field in d:draft[field]=copy.deepcopy(d[field])
    for answer in draft['answers'].values():answer['confirmed']=False
    draft.update(consent=False,reviewer=None,basis='Editable revision of an existing conditional calculation; confirm all current parameters before a new solve.')
    save(new_sp.parent/'draft.json',draft)
    m=copy.deepcopy(parent)
    for field in ('summary','engine_state','active_project','latest_reports','latest_delivery','previous_delivery','run_confirmation','pending_review','task','run_scenario','exports_need_refresh','pending_study','active_study','latest_study','exit_code'):
        m.pop(field,None)
    m.update(id=key2,title=c['title'],project=rel(folder/'initial.json'),session=session['session'],revision=0,
             status='INPUTS_READY',phase='EDIT_REVISION',errors=[],created_utc=utc(),
             parent_revision=dict(project_id=parent['id'],summary=parent['summary'],app=item(core.folder(parent['id'])/'app.json'),created_utc=utc()))
    core.persist(m,'CREATE_EDITABLE_REVISION',dict(parent=parent['id'],summary=parent['summary']))
    return core.view(key2)


def compare(m,summary):
    parent=m.get('parent_revision')
    if not parent:return None
    if not intact([parent['summary']]):return dict(status='SOURCE_CHANGED',rows=[])
    old=read(ROOT/parent['summary']['path']);a={p['profile_id']:p for p in (old.get('hydraulics') or {}).get('profiles',[])};rows=[]
    for p in (summary.get('hydraulics') or {}).get('profiles',[]):
        prior=a.get(p['profile_id']);
        if not prior:continue
        for field in ('headwater_wse_ft','tailwater_wse_ft','inlet_velocity_fts','roadway_flow_software_cfs'):
            x=prior.get('metrics',{}).get(field);y=p.get('metrics',{}).get(field)
            rows.append(dict(profile=p['profile_id'],metric=field,previous=x,current=y,change=None if x is None or y is None else y-x))
    return dict(status='COMPARISON_NOT_ACCEPTANCE',parent=parent,rows=rows)
