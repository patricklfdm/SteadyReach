"""Map and section actions with explicit local selections, no signature fields."""
from .common import ROOT,read,save,item,rel,finite,utc,lock
from . import app_core as core,intake,geometry_editor as editor,geometry_workflow

def perform(key,action,body):
    m=core.model(key);core.require_idle(m)
    if not m.get('session') or m.get('native_review'):raise ValueError('These operations edit a DEM-derived draft only')
    sp=ROOT/m['session'];d=read(sp.parent/'draft.json')
    if action=='expand-terrain':
        from .app_terrain_extent import expand
        return expand(key,body)
    if action.startswith('auto-'):
        from .app_geometry_auto import perform as automatic
        return automatic(m,action[5:],body)
    if action.startswith('repair-'):
        from .app_section_repair import perform as repair
        return repair(m,action[7:],body)
    if action.startswith('bank-proposal-'):
        from .bank_reassessment import perform as reassess
        return reassess(m,action[len('bank-proposal-'):],body)
    if action=='map':
        from .app_acquisition import overlay
        return overlay(m,editor.map_view(sp,body.get('bounds')))
    if body.get('revision') is not None and body['revision']!=m['revision']:raise ValueError('Inputs changed; reload the map / 参数已变更，请刷新地图')
    if action=='picks':
        import math
        picks=body.get('picks',{});allowed={'upstream','downstream','inlet','outlet','road','river'}
        if set(picks)-allowed:raise ValueError('Unknown map point type')
        for kind,points in picks.items():
            if not isinstance(points,list) or len(points)>(1 if kind in ('inlet','outlet') else 100) or any(not isinstance(p,list) or len(p)!=2 or not all(finite(v) for v in p) for p in points):raise ValueError('Invalid map points')
        if 'group_index' in body:
            from .app_parameters import objects
            gi=body['group_index'];groups=objects(m)[4]['structure']['groups']
            if type(gi)!=int or not 0<=gi<len(groups):raise ValueError('Unknown opening group')
            m.setdefault('group_map_picks',{})[str(gi)]={k:picks.get(k,[]) for k in ('inlet','outlet')}
        m['map_picks']=picks
        gap=body.get('wall_gap_ft')
        if gap not in (None,'') and (not finite(gap) or gap<0):raise ValueError('Nonnegative wall spacing required')
        m['wall_gap_ft']=None if gap in (None,'') else gap
        params=body.get('parameters',{})
        if set(params)-{'section_width_ft','section_spacing_ft'} or any(not finite(v) or v<=0 for v in params.values()):raise ValueError('Positive sampling dimensions required')
        m['sampling_parameters']=params
    elif action=='estimate':
        from .app_parameters import sample_road
        sample_road(m)
    elif action=='add':intake.edit_structure(sp,d['revision'],body['kind'])
    elif action=='generate':
        setup=editor.setup_view(sp);meta=m['metadata'];candidate=setup.get('metadata_candidate') or {}
        unit=meta.get('dem_vertical_unit') or candidate.get('unit');datum=meta.get('dem_vertical_datum') or candidate.get('datum')
        paths=candidate.get('source_paths',[])
        if not paths:
            record=sp.parent/'metadata_selection.json'
            save(record,dict(unit=unit,datum=datum,source='User-selected DEM interpretation; supporting metadata unavailable',engineering_review='NOT_PERFORMED'))
            paths=[rel(record)]
        params=dict(setup.get('defaults',{}));params.update(body.get('parameters',{}))
        payload=dict(policy=core.POLICY,reviewer=None,basis='User-selected exterior reach anchors and sampling parameters; conditional DEM-derived geometry.',
            mode='alignment',replace_existing=body.get('replace_existing',False),
            vertical_review=dict(unit=unit,datum=datum,basis='Displayed DEM metadata and local parameter selection; no vertical datum shift.',source_paths=paths),
            parameters=params,external_reaches=body['external_reaches'],direction_basis='User placed anchors from upstream to downstream on the displayed map.')
        editor.configure(sp,d['revision'],payload)
    elif action=='banks':
        from .geometry_qa import section_fingerprint,spatial_issues
        selections=body.get('sections',[])
        if not selections:raise ValueError('Select at least one section')
        # Validate the complete batch before saving any row.
        with lock(sp.parent/'session.lock'):
            _,_,packet,draft=intake._load(sp);_,geometry=intake._objects(packet,draft)
            rows=geometry['cross_sections'];seen=set();issues=spatial_issues(rows)
            for selected in selections:
                index=selected['index'];banks=selected['bank_indices']
                if type(index)!=int or index in seen or not 0<=index<len(rows):raise ValueError('Unknown or duplicate section')
                seen.add(index);row=rows[index];x=row.get('station_ft') or [];z=row.get('elevation_ft') or []
                if selected['fingerprint']!=section_fingerprint(row):raise ValueError('Section changed; reload its current profile')
                if not isinstance(banks,list) or len(banks)!=2 or not all(type(i)==int for i in banks) or not 0<banks[0]<banks[1]<len(x)-1:raise ValueError('Choose ordered interior left/right sampled bank points')
                if len(x)!=len(z) or not all(finite(v) for v in x+z):raise ValueError('NoData sections cannot be accepted')
                if any(index in q['sections'] for q in issues):raise ValueError('Resolve intersecting or invalid section cutlines first')
            for selected in selections:
                index=selected['index'];row=rows[index];row['bank_stations_ft']=[row['station_ft'][i] for i in selected['bank_indices']]
                row['terrain_review']=dict(decision='ACCEPT',reviewer=None,basis='Local selection of displayed bank positions; no engineering review asserted.',
                    fingerprint=section_fingerprint(row),created_utc=utc(),identity='LOCAL_SELECTION_NO_ENGINEERING_REVIEW',policy=core.POLICY)
                draft['answers'].pop(f'g.cross_sections.{index}.bank_stations_ft',None)
            draft.update(geometry=geometry,consent=False,revision=draft['revision']+1)
            save(sp.parent/'events'/('bank_selection_'+str(draft['revision'])+'.json'),dict(sections=selections,policy=core.POLICY))
            save(sp.parent/'draft.json',draft)
    else:raise ValueError('Unsupported geometry action')
    m['revision']+=1;core.persist(m,'GEOMETRY_'+action.upper(),dict(section_count=len(body.get('sections',[]))))
    return core.view(key)
