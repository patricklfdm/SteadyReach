"""Local, explicit batch section repair. Suggestions are geometry, not hydraulics."""
import copy
import numpy as np
from .common import ROOT, digest, intact, item, lock, read, save, unique_id, utc
from . import app_core as core, geometry_editor as editor, intake
from .geometry_qa import spatial_issues, section_fingerprint, intersects
from .banks import annotate


def association_context(m):
    return digest({k:m.get(k) for k in ('opening_mapping','group_map_picks','survey_settings','source_analysis')})


def context_matches(v,m):
    if v.get('association_context'):return v['association_context']==association_context(m)
    return not m.get('opening_mapping') and not m.get('group_map_picks')  # unchanged legacy preview


def crossing(a,b):
    return any(intersects(*a[i:i+2],*b[j:j+2]) for i in range(len(a)-1) for j in range(len(b)-1))


def wet_edge(m,sp,d,g,body):
    """Bounded DEM search against prior water levels, never a new hydraulic result."""
    from .qa_locator import collect
    parent=m.get('parent_revision')
    if not parent or not intact([parent['summary']]):raise ValueError('Create a revision of an intact computed project first')
    h=read(ROOT/parent['summary']['path'])['hydraulics'];old=collect(h)
    maximum={}
    for r in old['rows']:
        if r['left_excess_ft'] or r['right_excess_ft']:maximum[float(r['rs'])]=max(maximum.get(float(r['rs']),float('-inf')),r['wse_ft'])
    ui=next(i for i,r in enumerate(g['cross_sections']) if r['rs']==g['structure']['us_xs_rs'])
    protected={ui-1,ui,ui+1,ui+2};changes=[];trials=[]
    for i,row in enumerate(g['cross_sections']):
        if float(row['rs']) not in maximum:continue
        if i in protected:
            trials.append(dict(rs=row['rs'],status='STRUCTURE_APPROACH_REQUIRES_EXPLICIT_EDIT'));continue
        if len(trials)>=12:break
        width=editor.transform_section(row,g['horizontal_crs'],{})[2]['width_ft'];water=maximum[float(row['rs'])];trial=dict(rs=row['rs'],prior_wse_ft=water,status='NO_BOUNDED_EXTENSION_FOUND',attempts=[])
        for ratio in (1.25,1.5,2.):
            parameters=dict(width_ft=width*ratio,sampling_ft=max(1.,width*ratio/499))
            pv=editor.preview(sp,d['revision'],i,section_fingerprint(row),parameters)['preview']
            z=pv['after']['elevation_ft'];above=not pv['nodata_samples'] and min(z[0],z[-1])>water
            trial['attempts'].append(dict(width_ft=parameters['width_ft'],nodata=pv['nodata_samples'],endpoints_above_prior_wse=above,spatial_issues=len(pv['spatial_issues'])))
            if above:
                changes.append(dict(index=i,rs=row['rs'],fingerprint=section_fingerprint(row),parameters=pv['parameters']))
                trial['status']='DEM_EXTENSION_CANDIDATE_REQUIRES_BATCH_PREVIEW';break
        trials.append(trial)
    return dict(changes=changes,trials=trials,source=parent['summary'],solver_run=False,
        limitation='Widths tested at 1.25, 1.5 and 2 times the saved width, at most 500 samples. No raised terrain, no altered structure approach. Prior WSE is only a screening threshold; a fresh solve and flow-path review remain necessary.')


def suggest(g,m=None,protected=()):
    """Bounded component search; rotate only, never silently reduce width."""
    rows=copy.deepcopy(g['cross_sections'])
    from .app_automation import preflight
    screen=lambda geom: preflight(m,geom)['issues'] if m is not None else spatial_issues(geom['cross_sections'])
    repair_codes={'INTERSECTING_SECTIONS','PROJECTED_OPENINGS_OVERLAP','OPENING_OUTSIDE_SECTION'}
    issues=[q for q in screen(g) if q['code'] in repair_codes or q.get('blocking') and q.get('sections')]
    if any(q['code'] not in repair_codes for q in issues):
        return dict(changes=[],issues=issues,reason='Invalid cutline: edit its coordinates before trying rotations.')
    remaining={i for q in issues for i in q['sections']};changes=[]
    angles=[0]+[a for n in range(5,31,5) for a in (n,-n)]
    while remaining:
        component={min(remaining)}
        while True:
            expanded=component|{i for q in issues if component.intersection(q['sections']) for i in q['sections']}
            if expanded==component:break
            component=expanded
        remaining-=component
        if len(component)>6:continue  # bounded interactive search; manual batch preview remains available
        ids=sorted(component);options={}
        for i in ids:
            options[i]=[]
            for angle in ([0] if i in protected else angles):
                cut,center,p=editor.transform_section(rows[i],g['horizontal_crs'],dict(rotation_deg=angle))
                candidate=copy.deepcopy(g);candidate['cross_sections']=copy.deepcopy(rows);candidate['cross_sections'][i].update(cutline_xy=cut.tolist(),center_xy=center.tolist())
                projection_bad=any(i in q.get('sections',[]) and q['code'] in {'PROJECTED_OPENINGS_OVERLAP','OPENING_OUTSIDE_SECTION'} for q in screen(candidate))
                if not projection_bad and not any(crossing(cut,r['cutline_xy']) for j,r in enumerate(rows) if j not in component):
                    options[i].append((angle,cut,center,p))
        # Precompute compatibility rather than repeatedly testing full geometry.
        compatible={}
        for ii,i in enumerate(ids):
            for j in ids[ii+1:]:
                for a,oa in enumerate(options[i]):
                    for b,ob in enumerate(options[j]):compatible[i,a,j,b]=not crossing(oa[1],ob[1])
        best=None;best_cost=float('inf');visited=0
        def search(pos,chosen,cost):
            nonlocal best,best_cost,visited
            visited+=1
            if visited>50000 or cost>=best_cost:return
            if pos==len(ids):best=chosen.copy();best_cost=cost;return
            i=ids[pos]
            for a,op in enumerate(options[i]):
                if all(compatible[j,b,i,a] for j,b in chosen.items()):
                    chosen[i]=a;search(pos+1,chosen,cost+abs(op[0]));chosen.pop(i)
        search(0,{},0)
        if best is not None:
            for i,a in best.items():
                angle,cut,center,p=options[i][a]
                if angle:
                    changes.append(dict(index=i,rs=rows[i].get('rs'),fingerprint=section_fingerprint(g['cross_sections'][i]),parameters=p))
                    rows[i].update(cutline_xy=cut.tolist(),center_xy=center.tolist())
    candidate=copy.deepcopy(g);candidate['cross_sections']=rows
    return dict(changes=changes,issues=screen(candidate),reason='Rotations within ±30°, unchanged width and center. Confirm flow alignment and floodplain coverage in the DEM preview.')


def perform(m,action,body):
    if body.get('revision')!=m['revision']:raise ValueError('Inputs changed; reload / 参数已变更，请刷新')
    sp=ROOT/m['session']
    _,_,p,d,c,g,_,_,_=editor.context(sp)
    from .app_automation import preflight
    if action=='status':
        pending=None;ip=sp.parent/'section_batch_index.json'
        for entry in reversed(list((read(ip) if ip.exists() else {}).values())):
            if not intact([entry]):continue
            v=read(ROOT/entry['path'])
            if v['app_revision']==m['revision'] and v['draft_revision']==d['revision'] and v['geometry_hash']==digest(g) and context_matches(v,m):
                pending=v;break
        return dict(pending_preview=pending,revision=m['revision'],draft_revision=d['revision'],issues=preflight(m,g)['issues'],
            sections=[dict(index=i,rs=r.get('rs'),fingerprint=section_fingerprint(r),parameters=editor.transform_section(r,g['horizontal_crs'],{})[2]) for i,r in enumerate(g['cross_sections'])])
    if action=='suggest':return suggest(g,m)
    if action=='wet-edge':return wet_edge(m,sp,d,g,body)
    if action=='preview':
        changes=body.get('changes');seen=set();previews=[]
        if not isinstance(changes,list) or not 1<=len(changes)<=50:raise ValueError('Choose 1–50 sections to preview')
        candidate=copy.deepcopy(g)
        for change in changes:
            i=change.get('index')
            if type(i)!=int or not 0<=i<len(g['cross_sections']) or i in seen:raise ValueError('Unknown or duplicate section')
            seen.add(i)
            # Reuse the real raster sampler and its datum/unit/source checks.
            v=editor.preview(sp,d['revision'],i,change.get('fingerprint'),change.get('parameters'))['preview']
            previews.append(v);candidate['cross_sections'][i]=v['after']
        issues=preflight(m,candidate)['issues']
        relevant=[q for q in issues if q.get('blocking') and seen.intersection(q['sections'])]
        result=dict(id=unique_id(),app_revision=m['revision'],draft_revision=d['revision'],geometry_hash=digest(g),
            previews=previews,issues=issues,affected_issues=relevant,nodata_samples=sum(v['nodata_samples'] for v in previews),created_utc=utc(),
            policy=core.POLICY,engineering_acceptance='NOT_ASSESSED')
        result['association_context']=association_context(m)
        result['can_apply']=not relevant and not result['nodata_samples']
        path=sp.parent/'section_batch_edits'/result['id']/'preview.json';save(path,result)
        with lock(sp.parent/'session.lock'):
            if read(sp.parent/'draft.json')['revision']!=d['revision']:raise ValueError('Draft changed during preview; reload')
            ip=sp.parent/'section_batch_index.json';entries=read(ip) if ip.exists() else {}
            entries[result['id']]=item(path);save(ip,entries)
        return result
    if action!='apply':raise ValueError('Unsupported section repair action')
    if body.get('confirmed') is not True:raise ValueError('Explicitly confirm the displayed DEM preview')
    with lock(sp.parent/'session.lock'):
        _,_,p,d=intake._load(sp);_,g=intake._objects(p,d)
        ip=sp.parent/'section_batch_index.json';entries=read(ip) if ip.exists() else {}
        entry=entries.get(body.get('preview_id'))
        if not entry or not intact([entry]):raise ValueError('Preview missing or changed; preview again')
        v=read(ROOT/entry['path'])
        if v['app_revision']!=m['revision'] or v['draft_revision']!=d['revision'] or v['geometry_hash']!=digest(g) or not context_matches(v,m):raise ValueError('Preview is stale; preview current inputs again / 预览已过期，请重新预览')
        if not v['can_apply'] or v['nodata_samples'] or v['affected_issues']:raise ValueError('Resolve intersections and NoData before applying')
        sources=[s for pv in v['previews'] for s in pv['sources']]
        if not intact(sources):raise ValueError('DEM or metadata changed; preview again')
        old=copy.deepcopy(d);clear=set();moved=[]
        prior_reviews={r.get('rs'):copy.deepcopy(r.get('terrain_review')) for r in g['cross_sections']}
        for pv in v['previews']:
            i=pv['index'];g['cross_sections'][i]=copy.deepcopy(pv['after'])
            for k in ['cutline_xy','center_xy','station_ft','elevation_ft','bank_stations_ft']:clear.add(f'g.cross_sections.{i}.'+k)
            ref_changed=not np.allclose([pv['before']['station_ft'][0],pv['before']['station_ft'][-1]],[pv['after']['station_ft'][0],pv['after']['station_ft'][-1]],atol=1e-6,rtol=0)
            if pv['geometry_moved']:
                moved.append(i);g['functional_section_basis']=None;clear.add('g.functional_section_basis')
                center_moved=not np.allclose(pv['before']['center_xy'],pv['after']['center_xy'],rtol=0,atol=1e-6)
                for j in ([i-1,i] if center_moved else []):
                    if 0<=j<len(g['cross_sections'])-1:
                        for k in ['reach_lengths_ft','reach_length_basis']:
                            g['cross_sections'][j][k]=None;clear.add(f'g.cross_sections.{j}.'+k)
            if pv['geometry_moved'] or ref_changed:
                for k in ['manning_segments','ineffective_left','ineffective_right']:
                    if g['cross_sections'][i].get(k):g['cross_sections'][i][k]=None;clear.add(f'g.cross_sections.{i}.'+k)
                if pv['before'].get('rs') in [g['structure'].get('us_xs_rs'),g['structure'].get('ds_xs_rs')]:
                    for j,b in enumerate(g['structure']['groups']):
                        b['centers_ft']=None;clear.add(f'g.structure.groups.{j}.centers_ft')
                        if pv['before'].get('rs')==g['structure'].get('us_xs_rs'):
                            b['distance_us_ft']=None;clear.add(f'g.structure.groups.{j}.distance_us_ft')
                    if pv['before'].get('rs')==g['structure'].get('us_xs_rs'):
                        g['structure']['road']['distance_us_ft']=None;clear.add('g.structure.road.distance_us_ft')
                    for k in ['station_ft','downstream_station_ft']:
                        if k in g['structure']['road']:g['structure']['road'][k]=None;clear.add('g.structure.road.'+k)
        # A changed batch can affect relative section lengths and prior bank review.
        # Clear after the full replacement so a later row cannot resurrect old values.
        for key in clear:
            if key.endswith(('.reach_lengths_ft','.reach_length_basis')):
                _,_,i,k=key.split('.');g['cross_sections'][int(i)][k]=None
        for r in g['cross_sections']:r.pop('terrain_review',None)
        current_issues=preflight(m,g)['issues']
        if any(q.get('blocking') and set(moved).intersection(q.get('sections',[])) for q in current_issues):raise ValueError('Current spatial checks fail; generate a fresh preview')
        annotate(g)
        for r in g['cross_sections']:
            prior=prior_reviews.get(r.get('rs'))
            if prior and prior.get('fingerprint')==section_fingerprint(r):r['terrain_review']=prior
        g.setdefault('provenance',[]).extend(sources+[entry])
        d.update(geometry=g,revision=d['revision']+1,consent=False,section_review_drafts={})
        d['answers']={k:val for k,val in d['answers'].items() if k not in clear}
        d.setdefault('geometry_edit_sources',[]).extend(sources+[entry])
        save(sp.parent/'events'/('batch_resample_'+unique_id()+'.json'),dict(before=old,preview=entry,policy=core.POLICY,created_utc=utc(),invalidated_fields=sorted(clear)))
        save(sp.parent/'draft.json',d)
    m['revision']+=1;core.persist(m,'APPLY_SECTION_DEM_PREVIEW',dict(preview=entry,moved_sections=moved))
    return core.view(m['id'])
