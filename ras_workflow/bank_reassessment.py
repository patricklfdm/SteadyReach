"""Bound, editable bank-replacement proposals; never automatic hydraulic approval."""
import copy

from .common import ROOT, digest, read, save, utc, lock, finite, item, intact
from .bank_review import inventory, profile_context
from .geometry_qa import section_fingerprint, spatial_issues

METHOD = 'bank_reassessment_1.0'


def selection_sources(geometry):
    sources=[entry for entry in geometry.get('provenance',[]) if entry.get('role')=='bank_reassessment']
    if sources and not intact(sources):raise ValueError('Bank-selection evidence changed; restore the bound source record')
    return sources


def context(geometry, draft):
    return digest(dict(method=METHOD, geometry=geometry, answers=draft['answers'], revision=draft['revision']))


def proposal_id(proposal):
    return digest({k:v for k,v in proposal.items() if k!='id'})


def propose(geometry, answers, scope='inferred'):
    if scope not in ('inferred','attention'):
        raise ValueError('Unknown bank proposal scope')
    from .bank_reach import propose_reach
    review=inventory(geometry,answers)
    targets={r['index'] for r in review['sections'] if r['needs_attention'] and
             (scope=='attention' or set(r['categories']) & {'inferred','missing'})}
    faces=geometry.get('structure') or {}
    blocked={i for issue in spatial_issues(geometry['cross_sections']) for i in issue['sections']}
    exclusions=[]
    for i in sorted(targets):
        row=geometry['cross_sections'][i]
        reason=('GEOMETRY_CONFLICT' if i in blocked else 'EXPLICIT_ROUGHNESS_SUBDIVISIONS' if row.get('manning_segments')
                else 'STRUCTURE_APPROACH_CONTROL' if row['rs'] in (faces.get('us_xs_rs'),faces.get('ds_xs_rs')) else None)
        if reason:exclusions.append(dict(index=i,rs=row['rs'],reason=reason))
    targets-={r['index'] for r in exclusions}
    if targets:
        proposals,summary=propose_reach(geometry,set(range(len(geometry['cross_sections'])))-targets)
    else:proposals=[];summary=dict(status='NO_ELIGIBLE_SECTIONS')
    changes=[]
    for i in sorted(targets):
        row=geometry['cross_sections'][i];method=proposals[i];indices=method.get('selected_indices')
        values=[row['station_ft'][j] for j in indices] if indices else None
        old=row.get('bank_stations_ft');changed=bool(values and values!=old)
        shifts=[b-a for a,b in zip(old,values)] if old and len(old)==2 and all(finite(v) for v in old) and values else None
        stable=(method.get('confidence')=='MEDIUM' and method.get('evidence_class')=='inferred'
                and method.get('reasons')==['DISTINCT_SLOPE_BREAKS_REVIEW_REQUIRED'])
        changes.append(dict(index=i,rs=row['rs'],reach_id=row.get('reach_id'),before_ft=old,proposed_ft=values,
            bank_indices=indices,shift_ft=shifts,changed=changed,recommended=bool(stable and changed),
            confidence=method.get('confidence','UNRESOLVED'),reasons=method.get('reasons',[]),
            basis=method.get('basis'),basis_zh=method.get('basis_zh'),method=method,
            fingerprint=section_fingerprint(row)))
    return dict(schema_version=METHOD,scope=scope,section_count=len(geometry['cross_sections']),
        rows=changes,excluded=exclusions,summary=summary,
        candidate_count=sum(r['proposed_ft'] is not None for r in changes),
        changed_count=sum(r['changed'] for r in changes),recommended_count=sum(r['recommended'] for r in changes),
        engineering_acceptance='NOT_ASSESSED')


def public(proposal):
    result=copy.deepcopy(proposal)
    for row in result['rows']:row.pop('method',None)
    return result


def saved_preview(sp,geometry,draft):
    path=sp.parent/'bank_reassessment.json'
    if not path.exists():return None
    proposal=read(path)
    if proposal.get('id')!=proposal_id(proposal) or proposal.get('input_hash')!=context(geometry,draft):
        applied_path=sp.parent/'bank_reassessment_applied.json'
        if applied_path.exists():
            applied=read(applied_path)
            if applied.get('proposal_id')==proposal.get('id') and applied.get('after_hash')==context(geometry,draft):
                return dict(status='APPLIED',schema_version=METHOD,scope=proposal['scope'],adopted_count=len(applied['indices']))
        return dict(status='STALE',schema_version=METHOD)
    return dict(status='CURRENT',**public(proposal))


def adopt(geometry,draft,proposal,indices):
    """Validate every selection before applying to copies; no original mutation."""
    if proposal.get('id')!=proposal_id(proposal) or proposal.get('input_hash')!=context(geometry,draft):
        raise ValueError('Bank proposal is stale; prepare it again / 岸站候选已过期，请重新生成')
    if not isinstance(indices,list) or not indices or any(type(i)!=int for i in indices) or len(set(indices))!=len(indices):
        raise ValueError('Choose distinct proposed sections / 请选择不重复的候选断面')
    candidates={r['index']:r for r in proposal['rows']}
    for i in indices:
        row=candidates.get(i)
        if not row or not row['changed'] or not row['proposed_ft']:
            raise ValueError('Selected section has no changed valid candidate')
        if row['fingerprint']!=section_fingerprint(geometry['cross_sections'][i]):
            raise ValueError('Section changed; prepare a new proposal')
    g=copy.deepcopy(geometry);d=copy.deepcopy(draft)
    for i in indices:
        candidate=candidates[i];row=g['cross_sections'][i];field=f'g.cross_sections.{i}.bank_stations_ft'
        previous=dict(value=row.get('bank_stations_ft'),method=row.get('bank_candidates'),answer=d['answers'].get(field))
        row['bank_stations_ft']=copy.deepcopy(candidate['proposed_ft'])
        row['bank_candidates']=dict(copy.deepcopy(candidate['method']),profile_context=profile_context(row),
            reassessment=dict(proposal_id=proposal['id'],banks_ft=copy.deepcopy(candidate['proposed_ft']),previous=previous))
        row['terrain_review']=dict(decision='ACCEPT',reviewer=None,created_utc=utc(),
            identity='BATCH_MORPHOLOGY_SELECTION_NO_ENGINEERING_REVIEW',fingerprint=section_fingerprint(row),
            basis='User adopted displayed terrain/continuity bank candidates; interpretation flags remain. No engineering acceptance.')
        d['answers'][field]=dict(value=copy.deepcopy(candidate['proposed_ft']),confirmed=False,
            evidence_class=candidate['method'].get('evidence_class','inferred'),
            basis=candidate['basis'] or 'Current-profile morphological bank candidate; conditional interpretation.',
            bank_reassessment=dict(proposal_id=proposal['id'],previous=previous))
    from .bank_reach import refresh
    refresh(g)
    d.update(geometry=g,consent=False,revision=d['revision']+1)
    return g,d


def perform(m,action,body):
    from . import app_core as core,intake
    if m.get('active_project') or m.get('native_review'):
        raise ValueError('Create an editable revision before proposing bank changes')
    if body.get('revision')!=m['revision']:
        raise ValueError('Project changed; reload before proposing or adopting banks')
    sp=ROOT/m['session']
    with lock(sp.parent/'session.lock'):
        _,_,packet,draft=intake._load(sp);_,geometry=intake._objects(packet,draft)
        path=sp.parent/'bank_reassessment.json'
        if action=='prepare':
            proposal=propose(geometry,draft['answers'],body.get('scope','inferred'))
            proposal.update(input_hash=context(geometry,draft),created_utc=utc(),project_id=m['id'])
            proposal['id']=proposal_id(proposal);save(path,proposal)
            return dict(status='CURRENT',**public(proposal))
        if action!='apply':raise ValueError('Unknown bank reassessment action')
        proposal=read(path)
        if body.get('proposal_id')!=proposal.get('id') or body.get('confirmed') is not True:
            raise ValueError('Review and adopt the displayed bank proposal first')
        _,updated=adopt(geometry,draft,proposal,body.get('indices'))
        record=sp.parent/'events'/('bank_reassessment_'+str(updated['revision'])+'.json')
        save(record,dict(proposal=proposal,selected_indices=body['indices'],engineering_acceptance='NOT_ASSESSED'))
        updated.setdefault('geometry_edit_sources',[]).append(item(record,'bank_reassessment'))
        save(sp.parent/'draft.json',updated)
        save(sp.parent/'bank_reassessment_applied.json',dict(proposal_id=proposal['id'],indices=body['indices'],
            after_hash=context(updated['geometry'],updated),created_utc=utc()))
    m['revision']+=1;m.pop('pending_review',None)
    core.persist(m,'ADOPT_BANK_REASSESSMENT',dict(count=len(body['indices']),proposal_id=proposal['id']))
    return core.view(m['id'])
