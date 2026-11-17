"""Source-bound geometry proposals, one consolidated preview, explicit apply then solve review."""
import copy,os
from pyproj import CRS
from .common import ROOT,read,save,item,intact,digest,rel,unique_id,finite,lock,utc
from . import app_core as core,app_parameters as params,geometry_editor as editor,intake
from .terrain_auto import Sampler
from .geometry_qa import spatial_issues,section_fingerprint


def signature(m):return digest(params.binding(m))


def load_pending(m,proposal_id=None):
    sp=ROOT/m['session'];ip=sp.parent/'automatic_geometry/index.json'
    index=read(ip) if ip.exists() else {}
    entry=index.get(proposal_id) if proposal_id else next(reversed(index.values()),None)
    if not entry or not intact([entry]):return None
    proposal=read(ROOT/entry['path'])
    if proposal['signature']!=signature(m) or not intact(proposal['sources']):return None
    return dict(proposal,token=entry['sha256'])


def prepare(m,body):
    sp,_,packet,d,c,g,t,terrain,info=editor.context(ROOT/m['session']);setup=editor.setup_view(sp)
    metadata=m.get('metadata',{});candidate=setup.get('metadata_candidate') or {}
    unit=metadata.get('dem_vertical_unit') or t.get('vertical_unit') or candidate.get('unit')
    datum=metadata.get('dem_vertical_datum') or t.get('vertical_datum') or candidate.get('datum')
    s=Sampler(terrain,unit,datum);mode=body.get('mode','qa' if g['cross_sections'] else 'initial')
    maximum=body.get('maximum_width_ft',1200. if mode=='qa' else 800.);length=body.get('reach_length_ft',400.)
    if not finite(maximum) or not 120<=maximum<=2000 or not finite(length) or not 100<=length<=1000:
        raise ValueError('Use a maximum width of 120–2000 ft and exterior reach search length of 100–1000 ft')
    before=signature(m)
    if mode=='initial':
        if body.get('reference_screen') is not None:
            raise ValueError('Generate initial sections before adding reference coverage controls')
        if g['cross_sections']:raise ValueError('Initial automatic layout applies to an empty draft; existing sections use QA suggestions')
        if g.get('model_type')=='river':
            from .river_layout import initial
        else:
            from .terrain_auto import initial
        proposal=initial(m,g,c,s,length,maximum)
    elif mode=='qa':
        if not g['cross_sections']:raise ValueError('Generate initial sections first')
        if g.get('vertical_datum')!=datum or not s.crs.equals(CRS.from_user_input(g['horizontal_crs'])):
            raise ValueError('Geometry and DEM datum/CRS must match before QA resampling')
        from .geometry_auto_qa import propose
        reference=None
        if body.get('reference_screen') is not None:
            from .section_reference import prepare as prepare_reference
            reference=prepare_reference(m,g,body['reference_screen'])
        proposal=propose(m,g,s,maximum,reference_screen=reference)
    else:raise ValueError('Unknown geometry proposal mode')
    proposal.update(id=unique_id(),mode=mode,signature=before,created_utc=utc(),revision=m['revision'],draft_revision=d['revision'],
        bounds=dict(reach_length_ft=length,maximum_width_ft=maximum),terrain=dict(unit=unit,datum=datum,raster=terrain['raster']),engineering_acceptance='NOT_ASSESSED')
    if signature(core.model(m['id']))!=before:raise ValueError('Inputs changed during proposal generation; try again')
    folder=sp.parent/'automatic_geometry'/proposal['id'];save(folder/'proposal.json',proposal)
    with lock(sp.parent/'session.lock'):
        ip=sp.parent/'automatic_geometry/index.json';index=read(ip) if ip.exists() else {};index[proposal['id']]=item(folder/'proposal.json');save(ip,index)
    return dict(proposal,token=index[proposal['id']]['sha256'])


def apply(m,body):
    v=load_pending(m,body.get('proposal_id'))
    if not v or v['token']!=body.get('token'):raise ValueError('Proposal is stale or changed; generate a current preview')
    if body.get('confirmed') is not True:raise ValueError('Confirm the displayed direction, extent and changes before adopting')
    layouts=[x for x in v['layouts'] if x['id']==body.get('layout_id')]
    if len(layouts)!=1 or not layouts[0]['can_apply']:raise ValueError('Choose a candidate without blocking geometry conflicts')
    layout=layouts[0];sp,p,d,c,old=params.objects(m);g=copy.deepcopy(layout['geometry']);changed=layout['changed_sections']
    if v['mode']=='qa':
        selected=body.get('section_indices',changed)
        if not isinstance(selected,list) or not selected or any(type(i)!=int or i not in changed for i in selected) or len(set(selected))!=len(selected):raise ValueError('Choose current proposed section changes')
        for i,r in enumerate(old['cross_sections']):
            if i not in selected:g['cross_sections'][i]=copy.deepcopy(r)
        changed=selected
    banks=body.get('banks',{})
    if not isinstance(banks,dict) or banks and body.get('confirm_banks') is not True:raise ValueError('Confirm the displayed bank candidates or leave them for later')
    for key,pair in banks.items():
        if not str(key).isdigit() or int(key) not in changed:raise ValueError('Bank selection must belong to a proposed section')
        row=g['cross_sections'][int(key)];x=row['station_ft']
        if not isinstance(pair,list) or len(pair)!=2 or not all(finite(v) for v in pair) or not x[0]<pair[0]<pair[1]<x[-1]:raise ValueError('Choose interior ordered bank points')
        snapped=[min(x,key=lambda z:abs(z-v)) for v in pair]
        if any(abs(a-b)>.00051 for a,b in zip(pair,snapped)):raise ValueError('Banks must match displayed sampled points; refresh the bank preview')
        row['bank_stations_ft']=snapped
    if spatial_issues(g['cross_sections']):raise ValueError('Selected combination creates spatial conflicts; choose another proposal')
    from .app_automation import preflight
    if v['mode']=='qa' and any(q['blocking'] and q['code']!='DERIVED_INPUT_CHANGED' for q in preflight(m,g)['issues']):raise ValueError('Proposed geometry still has blocking dependent-input conflicts')
    folder=sp.parent/'automatic_geometry'/v['id'];entry=item(folder/'proposal.json')
    g.update(approved_for_model=False,status='EDITABLE_AUTOMATIC_PROPOSAL')
    g.setdefault('provenance',[]).extend(v['sources']+[entry])
    invalid=set()
    # Explicitly chosen banks belong to the adopted geometry. Drop any older
    # automatic answer, including an unchanged station after one-sided extension,
    # so the final-review refresh cannot replace that choice with a new candidate.
    invalid.update(f'g.cross_sections.{key}.bank_stations_ft' for key in banks)
    if v['mode']=='initial':
        if g.get('model_type')!='river':
            for key in ('rs','us_xs_rs','ds_xs_rs'):g['structure'][key]=None;invalid.add('g.structure.'+key)
            for key in ('station_ft','downstream_station_ft','distance_us_ft'):
                if key in g['structure']['road']:g['structure']['road'][key]=None;invalid.add('g.structure.road.'+key)
            for i,group in enumerate(g['structure']['groups']):
                for key in ('centers_ft','distance_us_ft'):
                    group[key]=None;invalid.add(f'g.structure.groups.{i}.{key}')
        invalid.update(k for k in d['answers'] if k.startswith(('c.terrain.','g.cross_sections.')) or k in ('g.horizontal_crs','g.vertical_datum'))
        # Same terrain receipt format as the existing section-generation path.
        provenance=folder/'terrain_provenance.json';save(provenance,dict(proposal=entry,terrain=v['terrain']))
        local=dict(mode='local',raster=os.path.relpath(ROOT/v['terrain']['raster']['path'],folder),provenance=provenance.name,vertical_unit=v['terrain']['unit'],vertical_datum=v['terrain']['datum'],create_native=c['terrain'].get('create_native',False))
        d['section_workflow']=dict(status='WAITING_FOR_SECTION_REVIEW',sources=v['sources']+[entry,item(provenance)],terrain=local,terrain_base=rel(folder),section_count=len(g['cross_sections']))
    else:
        # Keep unrelated saved coefficients, lengths and their assumption/source labels.
        # Only an answer whose materialized value changes would overwrite this proposal.
        for i in changed:
            prefix=f'g.cross_sections.{i}.'
            invalid.update(k for k in d['answers'] if k.startswith(prefix) and
                old['cross_sections'][i].get(k[len(prefix):])!=g['cross_sections'][i].get(k[len(prefix):]))
    for i in changed:g['cross_sections'][i].pop('terrain_review',None)
    with lock(sp.parent/'session.lock'):
        if read(sp.parent/'draft.json')['revision']!=d['revision']:raise ValueError('Draft changed; preview again')
        save(sp.parent/'events'/('before_automatic_'+unique_id()+'.json'),read(sp.parent/'draft.json'))
        d.update(geometry=g,revision=d['revision']+1,consent=False,section_review_drafts={})
        d['answers']={k:a for k,a in d['answers'].items() if k not in invalid};d.setdefault('geometry_edit_sources',[]).extend(v['sources']+[entry]);save(sp.parent/'draft.json',d)
    if v['mode']=='initial':m['map_picks']=dict(m.get('map_picks',{}),**{r['id']:r['anchors_xy'] for r in layout['anchors']})
    m['revision']+=1;m.pop('pending_review',None);m.pop('run_confirmation',None)
    core.persist(m,'APPLY_AUTOMATIC_GEOMETRY',dict(proposal=entry,layout=layout['id'],changed_sections=changed,confirmed_banks=list(banks),invalidated_answers=sorted(invalid)))
    return core.view(m['id'])


def perform(m,action,body):
    core.require_idle(m)
    if m.get('active_project') or m.get('native_review'):raise ValueError('Create an editable revision first; completed/native projects are preserved')
    if body.get('revision')!=m['revision']:raise ValueError('Project changed; reload before proposing geometry')
    if action=='status':return dict(pending=load_pending(m))
    if action=='prepare':return prepare(m,body)
    if action=='apply':return apply(m,body)
    raise ValueError('Unknown automatic geometry action')
