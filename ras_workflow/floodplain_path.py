"""A bounded terrain-connectivity screen between same-side overbanks of two cuts."""
import math

import numpy as np
from scipy.ndimage import label

from .revision_inputs import bank_xy


def line_surface(points, corners, sampler):
    """Clip mapped line segments to a convex strip before sampling its DEM in feet."""
    points = np.asarray(points, float)
    corners = np.asarray(corners, float)
    if len(points) < 2 or ((points.max(axis=0) < corners.min(axis=0)) |
                           (points.min(axis=0) > corners.max(axis=0))).any():
        return None
    starts, vectors = points[:-1], np.diff(points, axis=0)
    enter, leave = np.zeros(len(starts)), np.ones(len(starts))
    edges = np.roll(corners, -1, axis=0) - corners
    def cross(a, b):
        return a[..., 0]*b[..., 1] - a[..., 1]*b[..., 0]
    sign = np.sign(cross(edges[0], edges[1]))
    for corner, edge in zip(corners, edges):
        offset = sign*cross(edge, starts-corner)
        rate = sign*cross(edge, vectors)
        parallel = np.abs(rate) < 1e-12
        leave[parallel & (offset < 0)] = -1
        hit = np.divide(-offset, rate, out=np.zeros_like(rate), where=~parallel)
        enter = np.where((rate > 0) & ~parallel, np.maximum(enter, hit), enter)
        leave = np.where((rate < 0) & ~parallel, np.minimum(leave, hit), leave)
    hit = enter <= leave
    if not np.any(hit):
        return None
    a = starts[hit] + vectors[hit]*enter[hit, None]
    b = starts[hit] + vectors[hit]*leave[hit, None]
    steps = np.ceil(np.linalg.norm(b-a, axis=1)*sampler.factor/sampler.cell_ft).astype(int)+1
    if sum(steps) > 20000:
        return dict(status='SAMPLE_LIMIT', range_ft=None)
    xy = np.concatenate([np.linspace(p, q, n) for p, q, n in zip(a, b, steps)])
    z = sampler.sample(xy)
    known = z[np.isfinite(z)]
    return dict(status='COMPLETE' if len(known)==len(z) else 'INCOMPLETE_DEM',
                range_ft=[float(known.min()),float(known.max())] if known.size else None,
                samples=len(z), missing=int(len(z)-len(known)))


def corridor(row, other, side, sampler, stages, search_distance_ft, *, within_cuts=False):
    bank_pairs = [bank_xy(r) for r in (row, other)]
    if any(pair is None for pair in bank_pairs):
        return dict(status='BANKS_UNAVAILABLE')
    end = 0 if side == 0 else -1
    inner = np.asarray([pair[side] for pair in bank_pairs], float)
    ends = np.array([r['cutline_xy'][end] for r in (row, other)], float)
    limbs = ends-inner
    widths = np.linalg.norm(limbs, axis=1)
    if min(widths) <= 0 or (not within_cuts and search_distance_ft <= 0):
        return dict(status='UNRESOLVED_EXTENT')
    if within_cuts:
        # A quadrilateral cannot represent a materially bent or backtracking cut.
        for row_data in (row, other):
            xy = np.asarray(row_data['cutline_xy'], float)
            if len(xy) <= 2:
                continue
            chord = xy[-1]-xy[0]
            length = np.linalg.norm(chord)
            if length == 0:
                return dict(status='BENT_CUT_REVIEW')
            along = (xy-xy[0]) @ (chord/length)
            deviations = np.linalg.norm(xy-xy[0]-along[:,None]*chord/length, axis=1)
            if max(deviations)*sampler.factor > sampler.cell_ft/2 or np.any(np.diff(along)<0):
                return dict(status='BENT_CUT_REVIEW')
    outer = ends.copy()
    if not within_cuts:
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
        source = groups[0] if within_cuts else groups[0,outside]
        target = groups[-1]
        return bool(np.intersect1d(source[source>0],target[target>0]).size)
    lower = connected(min(stages))
    sloping = connected(np.linspace(*stages,n)[:,None])
    status = ('LOW_ROUTE_AT_BOTH_STAGES' if lower else 'STAGE_DEPENDENT_LOW_ROUTE' if sloping
              else 'INCOMPLETE_DEM' if not np.isfinite(z).all() else 'NO_CONNECTED_LOW_ROUTE_IN_STRIP')
    return dict(status=status,at_lower_stage=lower,at_interpolated_stage=sloping,
                stages_ft=list(stages),grid_shape=[n,m],missing_cells=int((~np.isfinite(z)).sum()),
                corners_xy=[inner[0].tolist(),outer[0].tolist(),outer[1].tolist(),inner[1].tolist()])
