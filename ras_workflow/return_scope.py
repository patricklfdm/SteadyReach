"""Reuse confirmed hydraulic inputs from the exact parent of a field return."""
from .common import ROOT,digest,intact,read,safe_path
from .intake_register import refs


def signature(f,base):
    value=f.get('value');answer=f.get('answer') or {};source=answer.get('candidate_record') or {}
    if f['key'] in ('c.terrain.raster','c.terrain.provenance') and isinstance(value,str) and value:
        value=str(safe_path(base,value))
    return digest(dict(value=value,unit=f.get('unit'),evidence=f.get('evidence_class'),basis=f.get('basis'),
                       origins=sorted({r['sha256'] for r in refs(source)}),range=source.get('range'),
                       missing=f.get('missing'),basis_date=source.get('date')))


def assess(m,fields):
    returned=m.get('intake_return')
    if not returned:return None
    ref=returned.get('confirmation');previous=returned.get('review');summary=returned.get('summary')
    if (not ref or not previous or not summary or (m.get('parent_revision') or {}).get('summary')!=summary
            or not intact([ref,previous,summary]) or read(ROOT/ref['path']).get('review')!=previous):
        return dict(mode='FULL_REVIEW',reason='PARENT_CONFIRMATION_UNAVAILABLE')
    original=read(ROOT/previous['path']);parent=(m.get('parent_revision') or {}).get('project_id')
    if (not parent or original.get('inputs',{}).get('project_id')!=parent or
        read(ROOT/ref['path']).get('reviewed_fingerprint')!=original.get('fingerprint')):
        return dict(mode='FULL_REVIEW',reason='PARENT_CONFIRMATION_UNAVAILABLE')
    old={f['key']:f for f in original['fields']}
    prior=safe_path(ROOT,returned['parent_project']).parent;current=safe_path(ROOT,m['project']).parent
    from .intake_register import field_kind
    def notes(sources):
        return {(tuple(r['source_key']),r['sha256']) for r in sources if r.get('role')=='source_metadata_note' and r.get('source_key')}
    updated={source for source,_ in notes(m.get('intake_source_notes',[])) ^ notes(original['inputs'].get('sources',[]))}
    parent_sources={r['sha256']:r['path'] for r in original['inputs'].get('sources',[])}
    terrain_hash=(m.get('terrain') or {}).get('raster',{}).get('sha256')
    def uses_source(row,h):
        if h in {r['sha256'] for r in refs(row.get('answer') or {})}:return True
        if h==terrain_hash and (field_kind(row['key'])=='terrain' or row.get('evidence_class')=='terrain_derived'):return True
        cited=parent_sources.get(h)
        return bool(cited and cited in str(row.get('basis') or ''))
    direct=set(returned['fields']);changed=[];retained=[]
    for row in fields:
        k=row['key'];before=old.get(k);reason=None
        if k in direct:reason='RETURNED'
        elif before is None or signature(before,prior)!=signature(row,current):reason='VALUE_OR_SOURCE_CHANGED'
        elif any(uses_source(row,h) for _,h in updated):reason='SOURCE_METADATA_CHANGED'
        elif row.get('derived_update_available'):
            def alternatives(f):
                return {digest((c.get('value'),c.get('range'),c.get('evidence_class'),sorted({s['sha256'] for s in refs(c)})))
                        for c in f.get('parameter_candidates',[]) if c.get('automation_context')}
            if not before.get('derived_update_available') or alternatives(row)!=alternatives(before):reason='DERIVATION_CHANGED'
        if not reason and k.endswith('.bank_stations_ft') and k.rsplit('.',1)[0]+'.elevation_ft' in direct:reason='SECTION_PROFILE_CHANGED'
        if reason:changed.append(dict(key=k,reason=reason))
        else:retained.append(k)
    return dict(mode='CHANGES_ONLY',affected=changed,retained=retained,removed=sorted(set(old)-{r['key'] for r in fields}),
                mode_of_return=returned['mode'],sources=returned['sources'],parent_confirmation=ref['sha256'])
