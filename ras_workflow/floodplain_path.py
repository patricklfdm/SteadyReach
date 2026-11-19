"""A bounded terrain-connectivity screen between same-side overbanks of two cuts."""
import math

import numpy as np
from scipy.ndimage import label

from .revision_inputs import bank_xy


def corridor(row, other, side, sampler, stages, search_distance_ft):
    bank_pairs = [bank_xy(r) for r in (row, other)]
    if any(pair is None for pair in bank_pairs):
        return dict(status='BANKS_UNAVAILABLE')
    end = 0 if side == 0 else -1
    inner = np.asarray([pair[side] for pair in bank_pairs], float)
    ends = np.array([r['cutline_xy'][end] for r in (row, other)], float)
    limbs = ends-inner
    widths = np.linalg.norm(limbs, axis=1)
    if min(widths) <= 0 or search_distance_ft <= 0:
        return dict(status='UNRESOLVED_EXTENT')
    outer = ends.copy()
    outer[0] += limbs[0]/widths[0]*search_distance_ft/sampler.factor
    # Reject crossed section ends or folded sampling strips.
    cross = lambda u,v: u[0]*v[1]-u[1]*v[0]
    edges = np.roll(np.array([inner[0],outer[0],outer[1],inner[1]]),-1,axis=0)-[inner[0],outer[0],outer[1],inner[1]]
    turns = [cross(edges[i],edges[(i+1)%4]) for i in range(4)]
    if not (min(turns)>0 or max(turns)<0):
        return dict(status='AMBIGUOUS_CORRIDOR')
    cell = sampler.cell_ft/sampler.factor
    n = max(3, 1+math.ceil(max(np.linalg.norm(inner[1]-inner[0]),np.linalg.norm(outer[1]-outer[0]))/cell))
    m = max(3, 1+math.ceil(max(np.linalg.norm(outer-inner,axis=1))/cell))
    if n*m>500_000:
        return dict(status='CORRIDOR_SAMPLE_LIMIT')
    along = np.linspace(0,1,n)[:,None,None]
    across = np.linspace(0,1,m)[None,:,None]
    starts = inner[0]*(1-along)+inner[1]*along
    stops = outer[0]*(1-along)+outer[1]*along
    points = starts*(1-across)+stops*across
    z = sampler.sample(points.reshape(-1,2)).reshape(n,m)
    outside = (across.ravel()*np.linalg.norm(outer[0]-inner[0]))>widths[0]
    def connected(level):
        groups,_ = label(np.isfinite(z) & (z<level))
        source = groups[0,outside]
        target = groups[-1]
        return bool(np.intersect1d(source[source>0],target[target>0]).size)
    lower = connected(min(stages))
    sloping = connected(np.linspace(*stages,n)[:,None])
    status = ('LOW_ROUTE_AT_BOTH_STAGES' if lower else 'STAGE_DEPENDENT_LOW_ROUTE' if sloping
              else 'INCOMPLETE_DEM' if not np.isfinite(z).all() else 'NO_CONNECTED_LOW_ROUTE_IN_STRIP')
    return dict(status=status,at_lower_stage=lower,at_interpolated_stage=sloping,
                stages_ft=list(stages),grid_shape=[n,m],missing_cells=int((~np.isfinite(z)).sum()),
                corners_xy=[inner[0].tolist(),outer[0].tolist(),outer[1].tolist(),inner[1].tolist()])
