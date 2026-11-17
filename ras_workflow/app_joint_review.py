"""Prepare one independent joint-geometry draft when fixed-direction coverage is insufficient."""
from . import app_core as core, app_parameters as params
from .common import ROOT, digest, finite, intact, item, read, save, utc


def current(reference):
    entry=reference.get('entry')
    if not entry:
        return reference
    if not intact([entry]):
        return dict(status='SOURCE_CHANGED',error='Joint-revision receipt changed')
    record=read(ROOT/entry['path'])
    if not intact(record['sources']):
        return dict(status='SOURCE_CHANGED',error='Joint-revision source calculation changed')
    key=record['project_id']
    try:
        child=core.model(key)
        if core.deletion_record(key).exists() or child.get('status')=='ABANDONED':
            return dict(record,entry=entry,status='UNAVAILABLE',error='Prepared revision was deleted or abandoned')
        if child.get('parent_revision',{}).get('summary')!=record['baseline']:
            raise ValueError('Prepared revision belongs to a different calculation')
        if core.view(key,detail=False)['status']=='PROCESSING':
            return dict(record,entry=entry,status='REVISION_PROCESSING')
        if child.get('summary'):
            if not intact([child['summary']]):raise ValueError('Revision calculation summary changed')
            return dict(record,entry=entry,status='COMPUTED_REVISION')
        if record.get('preparation') and not intact([record['preparation']]):
            raise ValueError('Automatic preparation evidence changed')
        if record.get('signature') and record['signature']!=digest(params.binding(child)):
            return dict(record,entry=entry,status='EDITED_REVISION')
        if child.get('automatic_preparation') and child['automatic_preparation']!=record.get('preparation'):
            if not intact([child['automatic_preparation']]):raise ValueError('Current preparation evidence changed')
            params.binding(child)
            return dict(record,entry=entry,status='EDITED_REVISION')
        return dict(record,entry=entry)
    except (ValueError,OSError,KeyError) as error:
        return dict(status='UNAVAILABLE',error=str(error),entry=entry)


def prepare(parent,maximum_width_ft):
    """Called inside the parent's existing serialized worker, never starts a solver."""
    from . import app_revision, app_autoprepare
    from .qa_review import load_summary
    if parent.get('model_type')!='river' or parent.get('native_review'):
        raise ValueError('Automatic joint follow-up requires a built river model')
    if not parent.get('task'):
        raise ValueError('Prepare the joint revision in the project worker')
    if not finite(maximum_width_ft) or not 120<=maximum_width_ft<=2000:
        raise ValueError('Joint-revision width must be within 120–2000 ft')
    sources=[parent['summary'],item(ROOT/parent['active_project'])]
    if not intact(sources):
        raise ValueError('Joint-revision sources changed')
    _,summary,_=load_summary(ROOT/parent['summary']['path'])
    if read(ROOT/parent['active_project'])!=summary['configuration']:
        raise ValueError('Baseline configuration changed')
    binding=dict(sources=sources,maximum_width_ft=maximum_width_ft)
    path=core.folder(parent['id'])/'joint_reviews'/digest(binding)/'revision.json'
    # Reopening, refreshing or retrying the parent must not overwrite this draft,
    # including one the operator edited or a previous preparation only partly saved.
    if path.exists():
        return current(dict(entry=item(path)))
    view=app_revision.create_draft(parent,{},preparation_task=parent['task'])
    key=view['id']
    record=dict(schema_version='joint_review_1',project_id=key,parent_id=parent['id'],baseline=parent['summary'],
                sources=sources,maximum_width_ft=maximum_width_ft,created_utc=utc(),status='PREPARING',
                solver_started=False,final_confirmation_required=True,engineering_acceptance='NOT_ASSESSED')
    save(path,record)
    child=core.model(key)
    child.update(automatic_options=dict(maximum_width_ft=maximum_width_ft),title=parent['title']+' · QA draft')
    core.persist(child,'PREPARE_JOINT_REVISION',dict(parent=parent['id']))
    try:
        app_autoprepare.execute(key)
        child=core.model(key)
        receipt=child['automatic_preparation']
        if not intact([receipt]):raise ValueError('Automatic preparation receipt changed')
        prepared=read(ROOT/receipt['path'])
        proposal=prepared.get('geometry_proposal') or {}
        layout=next(iter(proposal.get('layouts',[])),{})
        record.update(status='DRAFT_READY',preparation=receipt,signature=digest(params.binding(child)),
                      geometry_applied=prepared['geometry_applied'],changes=len(layout.get('changes',[])),
                      rotations=sum(bool(row.get('rotation_deg')) for row in layout.get('changes',[])),
                      unresolved=layout.get('unresolved',[]),attention=prepared['attention'],
                      terrain_extent=prepared.get('terrain_extent'),error=proposal.get('error'))
    except Exception as error:
        record.update(status='PREPARATION_FAILED',error=str(error))
        child=core.model(key)
        child.update(status='NEEDS_ATTENTION',errors=[str(error)],phase='REVIEW_JOINT_DRAFT')
        core.persist(child,'JOINT_PREPARATION_FAILED',dict(error=str(error)))
    finally:
        child=core.model(key)
        if child.get('task')==parent['task']:
            child.pop('task')
            core.persist(child,'JOINT_PREPARATION_RELEASED',dict(owner_task=parent['task']))
    save(path,record)
    return dict(record,entry=item(path))
