"""Continuous river candidates between explicit upstream/downstream reach anchors."""
import copy
import numpy as np
from .common import item, read, save, unique_id, ROOT, intact
from pyproj import Transformer
from .terrain_auto import adaptive_sections
from .alignment import corridor_grid
from .banks import annotate
from .geometry_qa import spatial_issues


def trace(anchors, sampler):
    """Use explicit bends when supplied. Screen two-endpoint routes at two widths."""
    from scipy.spatial import cKDTree

    weights = dict(elevation_weight=1., uphill_weight=4., height_scale_ft=10.)
    grid = max(5., sampler.cell_ft)
    if len(anchors) != 2:
        return corridor_grid(anchors, 40., grid, sampler.sample, sampler.factor, weights)

    chord = (anchors[1] - anchors[0]) * sampler.factor
    length = np.linalg.norm(chord)
    inner_width = float(np.clip(.24 * length, 80., 800.))
    outer_width = inner_width * 1.5
    # Both grids use the same resolution. Bound their memory and avoid treating
    # a coarsened search across a very long reach as evidence of channel position.
    grid = max(grid, (np.max(abs(chord)) + 2 * outer_width) / 440.)
    if length < 6 * grid or grid > max(25., 2 * sampler.cell_ft):
        raise ValueError('Check reach extent and add bend anchors / 请核对河段范围并补充弯道锚点')
    narrow, _, _ = corridor_grid(anchors, inner_width, grid, sampler.sample, sampler.factor, weights)
    line, heights, evidence = corridor_grid(anchors, outer_width, grid, sampler.sample, sampler.factor, weights)
    shift = max(cKDTree(narrow).query(line)[0].max(), cKDTree(line).query(narrow)[0].max()) * sampler.factor
    tolerance = max(30., 4 * grid)
    relative = (line - anchors[0]) * sampler.factor
    fractions = np.clip(relative @ chord / length**2, 0., 1.)
    near_edge = np.linalg.norm(relative - fractions[:, None] * chord, axis=1).max() >= outer_width - 2 * grid

    # Require two flanks with finite, higher terrain at distributed interior
    # sections. A repeatable shortest path on a flat surface is ambiguous.
    chain = np.r_[0., np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))] * sampler.factor
    at = np.linspace(.1, .9, 17) * chain[-1]
    def point(distances):
        return np.column_stack([np.interp(distances, chain, column) for column in line.T])
    centers = point(at)
    tangent = point(at + 2 * grid) - point(at - 2 * grid)
    normal = np.column_stack([-tangent[:, 1], tangent[:, 0]])
    normal /= np.maximum(np.linalg.norm(normal, axis=1)[:, None], 1e-12)
    offsets = np.linspace(.15, .75, 7) * outer_width / sampler.factor
    bed = sampler.sample(centers)
    sides = []
    for sign in (-1, 1):
        xy = centers[:, None, :] + sign * normal[:, None, :] * offsets[None, :, None]
        z = sampler.sample(xy.reshape(-1, 2)).reshape(len(at), -1)
        sides.append((np.isfinite(z).sum(axis=1) >= 4) & ((z >= bed[:, None] + 1.).sum(axis=1) >= 2))
    supported = int(np.count_nonzero(sides[0] & sides[1]))
    evidence['endpoint_search'] = dict(half_widths_ft=[inner_width, outer_width], grid_ft=float(grid),
        path_difference_ft=float(shift), tolerance_ft=float(tolerance), touches_search_edge=bool(near_edge),
        supported_flanks=supported, flank_checks=len(at),
        needs_bend_anchor=bool(shift > tolerance or near_edge or supported < 12))
    return line, heights, evidence


def initial(m, g, c, sampler, length, maximum):
    anchors = m.get('map_picks', {}).get('river', [])
    sources=[]
    public=None
    entry=m.get('public_reach')
    if not anchors and entry and intact([entry]):
        public=read(ROOT/entry['path'])
        if public['status']=='CHOOSE_REACH':
            index=m.get('reach_option')
            if type(index)!=int or not 0<=index<len(public['options']):
                raise ValueError('Choose the upstream and downstream road names from the mapped reach list / 请在候选河段列表中选择道路组合')
            public=dict(public['options'][index],sources=public['sources'])
        if public['status']=='CANDIDATE':
            sources=[entry]+public['sources']
            if not intact(sources):
                raise ValueError('Mapped reach evidence changed; search again or pick the intended reach')
            transform=Transformer.from_crs(4326,sampler.crs,always_xy=True)
            anchors=[list(transform.transform(*point)) for point in public['anchor_lonlat']]
    if len(anchors) < 2:
        raise ValueError('Mark the river upstream → downstream between the two bridges (at least two points; add bend points) / 请先沿流向点选桥间河道，至少两点，弯道处加点')
    a = np.asarray(anchors, float)
    if a.ndim != 2 or a.shape[1] != 2 or not np.isfinite(a).all():
        raise ValueError('Finite river anchor pairs required')
    path = ROOT/m['session']
    source = path.parent/'river_anchor_records'/(unique_id()+'.json')
    basis=public['basis'] if sources else 'User-selected continuous reach, ordered upstream to downstream; excludes bridge structures'
    save(source, dict(anchors_xy=anchors,crs=sampler.crs.to_string(),basis=basis,sources=sources,model_type='river'))
    line, _, ev = trace(a, sampler)
    endpoint_search = ev.get('endpoint_search') or {}
    needs_bend = endpoint_search.get('needs_bend_anchor', False)
    chain = np.r_[0,np.cumsum(np.linalg.norm(np.diff(line,axis=0),axis=1))*sampler.factor]
    at = np.r_[np.arange(0,chain[-1],max(15.,sampler.cell_ft*3)),chain[-1]]
    line = np.column_stack([np.interp(at,chain,line[:,k]) for k in (0,1)])
    rows, spacing = adaptive_sections(sampler,line,'river',maximum)
    if not 4 <= len(rows) <= 500:
        raise ValueError('Reach must produce 4–500 sections; review extent')
    candidate = copy.deepcopy(g)
    candidate.update(model_type='river',structure=dict(groups=[],road={}),horizontal_crs=sampler.crs.to_string(),vertical_datum=sampler.datum,
                     cross_sections=rows,flowlines=[dict(id='river',xy=line.tolist(),screening=ev)],approved_for_model=False)
    for i,row in enumerate(rows):
        row['rs']=float((len(rows)-i)*100)
        row['rs_basis']='Sequential identifier, not surveyed chainage'
    # Reuse the bounded QA rotation/resampling engine; preserve unresolved conflicts.
    from .geometry_auto_qa import propose
    repaired=propose(m,candidate,sampler,maximum)
    best=repaired['layouts'][0]
    candidate=best['geometry'];rows=candidate['cross_sections'];annotate(candidate)
    from .section_direction import crossing_issues
    issues=spatial_issues(rows)+crossing_issues(candidate)
    layout=dict(id='river_layout',seed=dict(basis='Continuous terrain-screened river through saved anchors; bridge openings excluded',direction_known=True,sources=[item(source)]),
                anchors=[dict(id='river',anchors_xy=anchors)],parameters=[dict(reach='river',proposed_spacing_ft=spacing)],geometry=candidate,
                issues=issues,warnings=['VERIFY_BRIDGE_BOUNDARY_EFFECTS','VERIFY_SUBMERGED_CHANNEL_GEOMETRY'],
                changed_sections=list(range(len(rows))),missing_heights=sum(v is None for r in rows for v in r['elevation_ft']),can_apply=not issues and not needs_bend,
                basis='Adaptive sections and bank candidates from DEM; final user confirmation required')
    layout['joint_search'] = best.get('joint_search', {})
    layout['changes'] = best.get('changes', [])
    if sources:
        layout['public_reach']={key:public[key] for key in ('river','upstream_crossing','downstream_crossing','length_m','buffer_m','inset_m')}
        layout['seed'].update(basis=basis,sources=sources+[item(source)])
        z=sampler.sample(a)
        if not np.isfinite(z).all() or float(z[-1])>float(z[0])+1:
            layout['warnings'].append('REVIEW_MAPPED_FLOW_DIRECTION_AND_DEM_ENDPOINTS')
            layout['can_apply']=False
    if endpoint_search:
        layout['endpoint_search'] = endpoint_search
    return dict(layouts=[layout],failures=[],sources=[sampler.source,item(source)]+sources,solver_run=False)
