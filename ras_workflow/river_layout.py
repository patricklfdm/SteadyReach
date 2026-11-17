"""Continuous river candidates between explicit upstream/downstream reach anchors."""
import copy
import numpy as np
from .common import item, save, unique_id, ROOT
from .terrain_auto import adaptive_sections
from .alignment import corridor_grid
from .banks import annotate
from .geometry_qa import spatial_issues


def initial(m, g, c, sampler, length, maximum):
    anchors = m.get('map_picks', {}).get('river', [])
    if len(anchors) < 2:
        raise ValueError('Mark the river upstream → downstream between the two bridges (at least two points; add bend points) / 请先沿流向点选桥间河道，至少两点，弯道处加点')
    a = np.asarray(anchors, float)
    if a.ndim != 2 or a.shape[1] != 2 or not np.isfinite(a).all():
        raise ValueError('Finite river anchor pairs required')
    path = ROOT/m['session']
    source = path.parent/'river_anchor_records'/(unique_id()+'.json')
    save(source, dict(anchors_xy=anchors,crs=sampler.crs.to_string(),basis='User-selected continuous reach, ordered upstream to downstream; excludes bridge structures',model_type='river'))
    line, z, ev = corridor_grid(a, 40., max(5., sampler.cell_ft), sampler.sample, sampler.factor,
                               dict(elevation_weight=1.,uphill_weight=4.,height_scale_ft=10.))
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
    issues=spatial_issues(rows)
    layout=dict(id='river_layout',seed=dict(basis='Continuous terrain-screened river through saved anchors; bridge openings excluded',direction_known=True,sources=[item(source)]),
                anchors=[dict(id='river',anchors_xy=anchors)],parameters=[dict(reach='river',proposed_spacing_ft=spacing)],geometry=candidate,
                issues=issues,warnings=['VERIFY_BRIDGE_BOUNDARY_EFFECTS','VERIFY_SUBMERGED_CHANNEL_GEOMETRY'],
                changed_sections=list(range(len(rows))),missing_heights=sum(v is None for r in rows for v in r['elevation_ft']),can_apply=not issues,
                basis='Adaptive sections and bank candidates from DEM; final user confirmation required')
    return dict(layouts=[layout],failures=[],sources=[sampler.source,item(source)],solver_run=False)
