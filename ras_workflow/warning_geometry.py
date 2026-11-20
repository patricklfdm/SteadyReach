"""Terrain-only alternatives for native warning review on a continuous river."""
from copy import deepcopy
import math

import numpy as np
from .geometry_qa import spatial_issues
from .section_joint import _crosses, flow_crossing


CONTROLS = ('manning_segments', 'ineffective_left', 'ineffective_right')


def crossing(cut, line):
    hits = []
    for a, b in zip(cut, cut[1:]):
        if not _crosses([a, b], line):
            continue
        location = flow_crossing([a, b], line)
        if location is None:
            return None
        if not any(abs(location - old) < 1e-5 for old in hits):
            hits.append(location)
    return hits[0] if len(hits) == 1 else None


def along(cut):
    return np.r_[0., np.cumsum(np.linalg.norm(np.diff(cut, axis=0), axis=1))]


def coordinates(cut, chain, stations):
    return np.column_stack([np.interp(stations, chain, cut[:, axis]) for axis in (0, 1)])


def extend_ends(geometry, stages, sampler, maximum, clearance, allow_bends):
    """Keep original samples. Bend only beyond the old endpoint, in an inferred floodplain direction."""
    output = deepcopy(geometry)
    rows = output['cross_sections']
    centers = np.array([r['center_xy'] for r in rows])
    line = geometry['flowlines'][0]['xy']
    step = sampler.cell_ft / sampler.factor
    changed, excluded = [], []
    for i, row in enumerate(rows):
        water = stages[float(row['rs'])]
        for j, side in ((0, 'left'), (-1, 'right')):
            if row['elevation_ft'][j] > water + clearance:
                continue
            record = dict(rs=row['rs'], side=side)
            if any(row.get(k) for k in CONTROLS):
                excluded.append(dict(**record, reason='SECTION_SPECIFIC_CONTROLS'))
                continue
            cut = np.asarray(row['cutline_xy'], float)
            end = cut[j]
            tangent = end - cut[1 if j == 0 else -2]
            tangent /= np.linalg.norm(tangent)
            directions = [tangent]
            if allow_bends:
                for radius in (2, 4, 8, len(rows)):
                    dx, dy = centers[min(i+radius, len(rows)-1)] - centers[max(0, i-radius)]
                    directions.append(np.array([-dy, dx]))
                neighbors = []
                for k in (i-1, i+1):
                    if 0 <= k < len(rows):
                        adj = np.asarray(rows[k]['cutline_xy'])
                        v = adj[j] - adj[1 if j == 0 else -2]
                        neighbors.append(v / np.linalg.norm(v))
                directions.extend(neighbors)
                if len(neighbors) == 2:
                    directions.append(neighbors[0] + neighbors[1])
            width = row['station_ft'][-1] - row['station_ft'][0]
            distances = np.arange(step, (maximum-width)/sampler.factor, step)
            cap = 500 - len(row['station_ft'])
            if len(distances) < 5 or cap < 2:
                excluded.append(dict(**record, reason='WIDTH_OR_SAMPLE_LIMIT'))
                continue
            candidates = []
            seen = set()
            for direction in directions:
                norm = np.linalg.norm(direction)
                if norm < 1e-8:
                    continue
                unit = direction / norm
                if unit @ tangent < 0:
                    unit = -unit
                angle = math.degrees(math.acos(float(np.clip(unit @ tangent, -1, 1))))
                signature = tuple(np.round(unit, 5))
                if angle > 60 or signature in seen:
                    continue
                seen.add(signature)
                z = sampler.sample(end + distances[:, None]*unit)
                valid = np.flatnonzero(~np.isfinite(z))
                if len(valid):
                    z = z[:valid[0]]
                if len(z) < 5:
                    continue
                dry = np.convolve((z > water+clearance).astype(int), np.ones(5, int), 'valid')
                dry_idx = np.flatnonzero(dry == 5)
                if not len(dry_idx):
                    continue
                last = int(dry_idx[0]) + 4
                point = end + distances[last]*unit
                extension = [end, point]
                if _crosses(extension, line) or any(_crosses(extension, other['cutline_xy'])
                                                     for k, other in enumerate(rows) if k != i):
                    continue
                proposed = ([point.tolist()]+cut.tolist() if j == 0 else cut.tolist()+[point.tolist()])
                if spatial_issues([{'cutline_xy': proposed}]):
                    continue
                # Preserve the sampled extrema. Skip an extension that cannot fit all DEM samples.
                if last+1 > cap:
                    continue
                candidates.append((angle, last, proposed, z[:last+1]))
                if angle < .0001:
                    break
            if not candidates:
                excluded.append(dict(**record, reason='NO_NONCROSSING_SAMPLED_EXTENT'))
                continue
            angle, last, proposed, z = min(candidates, key=lambda o: (o[0], o[1]))
            dist = distances[:last+1]*sampler.factor
            x = np.asarray(row['station_ft'])
            if j == 0:
                row['station_ft'] = np.r_[x[0]+dist[-1]-dist[::-1], x+dist[-1]].tolist()
                row['elevation_ft'] = z[::-1].tolist()+row['elevation_ft']
                row['bank_stations_ft'] = (np.asarray(row['bank_stations_ft'])+dist[-1]).tolist()
            else:
                row['station_ft'] = np.r_[x, x[-1]+dist].tolist()
                row['elevation_ft'].extend(z.tolist())
            row['cutline_xy'] = proposed
            sampler.stamp(row)
            changed.append(dict(**record, length_ft=float(dist[-1]), angle_deg=angle))
    return output, changed, excluded


def validate_layout(previous, candidate):
    """Check the channel, banks and reach-length partition independently of the proposal."""
    from .revision_inputs import bank_xy
    old = {r['rs']:r for r in previous['cross_sections']}
    rows = candidate['cross_sections']
    if spatial_issues(rows) or not set(old)<=set(r['rs'] for r in rows):
        return False
    if any(previous.get(k)!=candidate.get(k) for k in ('boundaries','boundary_slopes','flow_regime','structure','flowlines')):
        return False
    line=candidate['flowlines'][0]['xy']
    positions=[crossing(r['cutline_xy'],line) for r in rows]
    if any(v is None for v in positions) or any(a>=b for a,b in zip(positions,positions[1:])):
        return False
    pending=[]
    for r in reversed(rows):
        pending.append(r['reach_lengths_ft'])
        a=old.get(r['rs'])
        if a is None:
            continue
        if not np.allclose(np.sum(pending,axis=0),a['reach_lengths_ft'],rtol=0,atol=1e-4):
            return False
        pending=[]
        if any(r.get(k)!=a.get(k) for k in ('center_xy','expansion_contraction',*CONTROLS)):
            return False
        if not np.allclose(bank_xy(a),bank_xy(r),rtol=0,atol=1e-5):
            return False
        def channel(row):
            x=np.asarray(row['station_ft']);z=np.asarray(row['elevation_ft'])
            l,r=row['bank_stations_ft']
            interior=(x>l+1e-5)&(x<r-1e-5)
            return np.column_stack([np.r_[0.,x[interior]-l,r-l],np.r_[np.interp(l,x,z),z[interior],np.interp(r,x,z)]])
        before,after=channel(a),channel(r)
        if before.shape!=after.shape or not np.allclose(before,after,rtol=0,atol=1e-5):
            return False
    return not pending


def controls(row):
    cut = np.asarray(row['cutline_xy'], float)
    x = row['station_ft']
    station = x[0] + along(cut)/along(cut)[-1]*(x[-1]-x[0])
    banks = np.array([x[0], *row['bank_stations_ft'], x[-1]])
    return cut, station, banks


def midpoint(a, b, line, sampler):
    """Interpolate plan positions at matched banks/vertices, then sample terrain at those locations."""
    pair = [controls(r) for r in (a, b)]
    marks = np.unique(np.round(np.r_[0., 1., 2., 3., *[m for _,s,p in pair for m in np.interp(s,p,[0,1,2,3])]], 8))
    cut = np.mean([coordinates(c, s, np.interp(marks, [0,1,2,3], p)) for c,s,p in pair], axis=0)
    dist = along(cut)*sampler.factor
    banks = np.interp([1., 2.], marks, dist)
    keypoints = np.r_[0., banks, dist[-1]]
    if min(np.diff(keypoints)) < .005 or min(np.diff(dist)) < .001:
        return None
    la, lm, lb = [crossing(c, line) for c in (a['cutline_xy'], cut, b['cutline_xy'])]
    if None in (la,lm,lb) or not la < lm < lb:
        return None
    fraction = (lm-la)/(lb-la)
    lengths = np.asarray(a['reach_lengths_ft'], float)
    if min(fraction, 1-fraction)*lengths[1] <= 2*sampler.cell_ft:
        return None
    grid = np.linspace(0.,dist[-1],min(498,math.ceil(dist[-1]/sampler.cell_ft)+1))[1:-1]
    x = np.sort(np.r_[keypoints, grid[np.min(abs(grid[:, None]-keypoints), axis=1) > .003]])
    z = sampler.sample(coordinates(cut, dist, x))
    if not np.isfinite(z).all():
        return None
    loc = coordinates(np.array(line), along(line), [lm])[0]
    new = dict(rs=(a['rs']+b['rs'])/2, center_xy=loc.tolist(), cutline_xy=cut.tolist(),
               station_ft=x.tolist(), elevation_ft=z.tolist(), bank_stations_ft=banks.tolist(),
               reach_lengths_ft=(lengths*(1-fraction)).tolist(), expansion_contraction=list(a['expansion_contraction']),
               local_chainage_ft=float(lm*sampler.factor), review_status='DRAFT_REQUIRES_REVIEW',
               provenance='DEM midpoint with inferred bank-aligned geometry and proportional reach lengths.')
    if 'reach_id' in a:
        new['reach_id'] = a['reach_id']
    from .bank_review import spacing_metadata
    new['spacing_assumptions'] = dict(bank_basis='Matched bank locations between adjacent cross sections; unmeasured.')
    new['bank_candidates'] = spacing_metadata(new,[a['rs'],b['rs']])
    sampler.stamp(new)
    return new, (lengths*fraction).tolist()


def infill(geometry, targets, sampler, maximum_added=10):
    output = deepcopy(geometry)
    rows = output['cross_sections']
    line = output['flowlines'][0]['xy']
    changes, excluded = [], []
    # Work on original adjacent pairs only. Actual warnings determine the next generation.
    pairs = list(zip(rows, rows[1:]))
    for a,b in sorted(pairs, key=lambda pair: -targets.get(pair[0]['rs'], 0)):
        if a['rs'] not in targets or len(changes) >= maximum_added or len(rows) >= 500:
            continue
        entry = dict(upstream_rs=a['rs'], downstream_rs=b['rs'])
        if any(r.get(k) for r in (a,b) for k in CONTROLS):
            excluded.append(dict(**entry, reason='SECTION_SPECIFIC_CONTROLS'))
            continue
        trial = midpoint(a,b,line,sampler)
        if trial is None:
            excluded.append(dict(**entry, reason='SPACING_TERRAIN_OR_CHANNEL_ORDER'))
            continue
        new, lengths = trial
        if round(new['rs'],2) in {round(r['rs'],2) for r in rows} or spatial_issues([new]) or any(
                _crosses(new['cutline_xy'], r['cutline_xy']) for r in rows):
            excluded.append(dict(**entry, reason='CROSSING_OR_NATIVE_STATION_COLLISION'))
            continue
        offset = next(i for i,r in enumerate(rows) if r is a)
        rows.insert(offset+1, new)
        a['reach_lengths_ft'] = lengths
        changes.append(dict(**entry, station=new['rs'], inferred_banks_ft=new['bank_stations_ft']))
    return output, changes, excluded
