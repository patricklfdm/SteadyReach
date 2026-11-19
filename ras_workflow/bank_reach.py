"""Rank morphological bank pairs along a reach with explicit continuity evidence."""
import copy
import math
import numpy as np
from pyproj import CRS

from .banks import propose, channel_origin
from .common import digest, finite

SETTINGS = dict(window_ft=6., center_search_fraction=.1, distance_penalty=1.)
METHOD = 'reach_bank_dynamic_programming_v3'


def _pair(row, indices, cost, source='local_slope_breaks'):
    x = row['station_ft']
    left, right = indices
    anchor, _ = channel_origin(row, np.asarray(x))
    return dict(indices=[left, right], stations=[x[left], x[right]],
                offsets=[x[left]-anchor, x[right]-anchor], width=x[right]-x[left],
                cost=float(cost), source=source)


def _options(row, proposal, fixed):
    if proposal['reasons']==['INVALID_OR_NODATA_PROFILE']:
        return []
    x = row['station_ft']
    if fixed:
        banks = row.get('bank_stations_ft')
        if not banks or not all(finite(v) for v in banks) or not x[0]<banks[0]<banks[1]<x[-1]:
            return []
        indices = [int(np.argmin(np.abs(np.asarray(x)-value))) for value in banks]
        value = _pair(row, indices, 0., 'saved_user_banks')
        anchor, _ = channel_origin(row, np.asarray(x))
        value.update(stations=list(banks), offsets=[v-anchor for v in banks], width=banks[1]-banks[0])
        return [value]
    bottom = proposal.get('channel_minimum_index')
    result = []
    for left in proposal['left']:
        for right in proposal['right']:
            if not left['index']<bottom<right['index']:
                continue
            cost = 0.
            hillside=[]
            for side, value in [('left',left),('right',right)]:
                best = max(c['score'] for c in proposal[side])
                cost += math.log(best/value['score'])+.7*(3-value['scale_support'])
                # A high valley wall can produce a stronger break than the
                # near-channel shoulder. Apply a soft penalty only when a
                # competing inner break is independently visible at two scales.
                toe=x[bottom]
                inner=[v for v in proposal[side] if v['scale_support']>=2
                       and abs(v['station_ft']-toe)*2<abs(value['station_ft']-toe)
                       and .5<=v['relief_ft']<value['relief_ft']/4]
                if inner:
                    alt=max(inner,key=lambda v:v['score'])
                    cost+=min(4.,math.log(value['relief_ft']/alt['relief_ft']))
                    hillside.append(dict(side=side,outer_ft=value['station_ft'],inner_ft=alt['station_ft']))
            pair=_pair(row,[left['index'],right['index']],cost)
            pair['hillside_comparisons']=hillside
            result.append(pair)
    return result


def _transition(a, b, distance):
    # Finite soft penalties allow genuine widening instead of forcing uniform banks.
    scale = max(distance, .5*(a['width']+b['width']), 1.)
    lateral = sum(abs(x-y) for x,y in zip(a['offsets'],b['offsets']))/scale
    width = abs(math.log(a['width']/b['width']))
    return min(lateral,2.)+.5*min(width,2.)


def _path(rows, options, factor, weight):
    """Dynamic programming on the finite list of candidate pairs at each section."""
    costs = [option['cost'] for option in options[0]]
    parents = []
    for index in range(1,len(rows)):
        distance = math.dist(rows[index-1]['center_xy'],rows[index]['center_xy'])*factor
        next_costs, previous = [], []
        for value in options[index]:
            alternatives = [cost+weight*_transition(old,value,distance)
                            for cost,old in zip(costs,options[index-1])]
            best = int(np.argmin(alternatives))
            next_costs.append(value['cost']+alternatives[best])
            previous.append(best)
        costs = next_costs
        parents.append(previous)
    selected = [int(np.argmin(costs))]
    for previous in reversed(parents):
        selected.append(previous[selected[-1]])
    return list(reversed(selected))


def _segments(rows, options, faces):
    segments, active = [], []
    for index,row in enumerate(rows):
        boundary = index>0 and (row.get('reach_id')!=rows[index-1].get('reach_id')
            or (rows[index-1]['rs']==faces.get('us_xs_rs') and row['rs']==faces.get('ds_xs_rs')))
        if boundary or not options[index]:
            if active:segments.append(active)
            active = []
        if options[index]:active.append(index)
    if active:segments.append(active)
    return segments


def propose_reach(geometry, locked=None):
    """Return suggestions without mutating saved banks or granting model approval."""
    rows = geometry['cross_sections']
    fixed = set(locked) if locked is not None else {i for i,r in enumerate(rows) if r.get('bank_stations_ft')}
    local = [propose(row,SETTINGS) for row in rows]
    result = copy.deepcopy(local)
    options = [_options(row,p,index in fixed) for index,(row,p) in enumerate(zip(rows,local))]
    summary = dict(method=METHOD, settings=SETTINGS,
                   section_count=len(rows), section_ids=[dict(index=i,reach_id=r.get('reach_id'),rs=r.get('rs')) for i,r in enumerate(rows)],
                   continuity_weight=1., tested_weights=[.5,1.,2.], locked_indices=sorted(fixed),
                   interpolated_indices=[], changed_local_choices=[], weight_sensitive_indices=[])
    try:
        crs = CRS.from_user_input(geometry.get('horizontal_crs'))
        if not crs.is_projected:raise ValueError()
        factor = crs.axis_info[0].unit_conversion_factor/.3048
        if not all(len(r.get('center_xy',[]))==2 and all(finite(v) for v in r['center_xy']) for r in rows):
            raise ValueError()
    except (ValueError,TypeError):
        summary['status']='LOCAL_CANDIDATES_ONLY_MISSING_PLAN_GEOMETRY'
        return result,summary
    faces = geometry.get('structure') or {}
    # A single missing interior pair may use two independently supported neighbors.
    # No extrapolation across structures, reach boundaries or multiple missing rows.
    for index in range(1,len(rows)-1):
        if options[index] or index in fixed or local[index]['reasons']==['INVALID_OR_NODATA_PROFILE']:
            continue
        neighbors = [index-1,index+1]
        if not all(options[i] and (i in fixed or local[i]['selected_indices']) for i in neighbors):
            continue
        triplet = rows[index-1:index+2]
        if len({r.get('reach_id') for r in triplet})!=1:
            continue
        if any(r['rs'] in (faces.get('us_xs_rs'),faces.get('ds_xs_rs')) for r in triplet):
            continue
        distances = [math.dist(rows[index]['center_xy'],rows[i]['center_xy']) for i in neighbors]
        if min(distances)<=0 or max(distances)>2*min(distances):
            continue
        near = [min(options[i],key=lambda v:v['cost']) for i in neighbors]
        fraction = distances[0]/sum(distances)
        offsets = [(1-fraction)*a+fraction*b for a,b in zip(near[0]['offsets'],near[1]['offsets'])]
        row = rows[index]
        x,z = np.asarray(row['station_ft']),np.asarray(row['elevation_ft'])
        anchor,_ = channel_origin(row,x)
        indices = [int(np.argmin(abs(x-(anchor+offset)))) for offset in offsets]
        left,right = indices
        bottom = local[index].get('channel_minimum_index')
        if not 0<left<bottom<right<len(x)-1 or min(z[indices])-min(z[left:right+1])<.5:
            continue
        candidate = _pair(row,indices,2.,'neighbor_bank_interpolation')
        candidate['neighbors'] = [dict(rs=rows[i]['rs'],stations=choice['stations']) for i,choice in zip(neighbors,near)]
        options[index]=[candidate]
        summary['interpolated_indices'].append(index)
    input_hash = signature(geometry,fixed)
    for segment in _segments(rows,options,faces):
        selected = [_path([rows[i] for i in segment],[options[i] for i in segment],factor,w) for w in [.5,1.,2.]]
        for position,index in enumerate(segment):
            if index in fixed:continue
            if not local[index].get('selected_indices') and len(segment)==1:
                continue
            value = options[index][selected[1][position]]
            reasons = list(local[index]['reasons'])
            alternatives=[q for opt in options[index] for q in opt.get('hillside_comparisons',[])]
            if alternatives:reasons.append('COMPARE_INNER_SHOULDER_AND_VALLEY_WALL')
            # A stable path may still hide an almost equally supported bank on one side.
            # Compare constrained alternatives with both selected neighbors held fixed.
            next_cost = []
            near = [(position-1,index-1),(position+1,index+1)]
            for candidate in options[index]:
                score = candidate['cost']
                for at, adjacent in near:
                    if 0 <= at < len(segment):
                        neighbor = options[adjacent][selected[1][at]]
                        distance = math.dist(rows[index]['center_xy'],rows[adjacent]['center_xy'])*factor
                        score += _transition(candidate,neighbor,distance)
                next_cost.append((score,candidate))
            winner_cost = next(s for s,c in next_cost if c is value)
            side_evidence = {}
            for side_index, side in enumerate(('left','right')):
                competitors = [(s,c) for s,c in next_cost if c['indices'][side_index]!=value['indices'][side_index]]
                match = next((b for b in local[index][side] if b['index']==value['indices'][side_index]),{})
                gap = None
                alternate = None
                if competitors:
                    score,alt = min(competitors,key=lambda pair:pair[0])
                    gap = round(score-winner_cost,4)
                    alternate = alt['stations'][side_index]
                support = match.get('scale_support',0)
                side_evidence[side]=dict(selected_ft=value['stations'][side_index],alternate_ft=alternate,
                                         conditional_cost_margin=gap,scale_support=support,
                                         distinct=support==3 and (gap is None or gap>=1.))
            if local[index].get('selected_indices')!=value['indices']:
                reasons.append('REACH_CONTINUITY_CHANGED_LOCAL_CHOICE')
                summary['changed_local_choices'].append(index)
            sensitive = len({p[position] for p in selected})>1
            if sensitive:
                reasons.append('CONTINUITY_WEIGHT_SENSITIVE')
                summary['weight_sensitive_indices'].append(index)
            if value['source']=='neighbor_bank_interpolation':
                reasons.append('INTERPOLATED_BANKS_REQUIRE_LOCAL_REVIEW')
            if not local[index].get('selected_indices'):
                reasons.append('WEAK_LOCAL_BANK_EVIDENCE')
            result[index].update(method=summary['method'], selected_indices=value['indices'],
                confidence='LOW' if sensitive or reasons!=['DISTINCT_SLOPE_BREAKS_REVIEW_REQUIRED'] else 'MEDIUM',
                evidence_class='assumed' if value['source']=='neighbor_bank_interpolation' else 'inferred',
                reasons=list(dict.fromkeys(reasons)), reach_inputs_hash=input_hash,
                continuity=dict(weight=1.,tested_weights=[.5,1.,2.],segment_rs=[rows[i]['rs'] for i in segment],
                    source=value['source'],interpolation_neighbors=value.get('neighbors',[]),
                    selected_local_cost=value['cost'], weight_sensitive=sensitive, side_evidence=side_evidence,
                    hillslope_candidates=list({(q['side'],q['outer_ft'],q['inner_ft']):q for q in alternatives}.values())),
                basis='Morphological candidates ranked jointly along the reach using slope breaks, scale support and a soft bank-continuity cost. Saved user banks act as fixed controls. Isolated missing interior pairs may use labelled neighbor interpolation. Inspect local splits, terraces and uncertain banks.',
                basis_zh='结合坡折、多尺度支持和岸线连续性，对全河段候选共同排序。已存人工岸站作为固定控制；孤立缺失的内部断面可采用带标注的邻断面插值。请核对局部分汊、阶地及不确定岸站。')
    # Preserve the existing, explicitly assumed end-section extrapolation route.
    trial = copy.deepcopy(geometry)
    for i,row in enumerate(trial['cross_sections']):
        picks = result[i].get('selected_indices')
        if i not in fixed and picks:
            row['bank_stations_ft']=[row['station_ft'][j] for j in picks]
    from .conditional_estimates import continuity_banks
    for i,row in enumerate(rows):
        if i not in fixed and not result[i].get('selected_indices'):
            continued = continuity_banks(trial,i)
            if continued:
                result[i]=dict(continued,reach_inputs_hash=input_hash)
    summary.update(status='PROPOSED_REQUIRES_FINAL_REVIEW',input_hash=input_hash,
                   proposed_pairs=sum(bool(p.get('selected_indices')) for i,p in enumerate(result) if i not in fixed),
                   unresolved_indices=[i for i,p in enumerate(result) if i not in fixed and not p.get('selected_indices')])
    return result,summary


def signature(geometry,fixed):
    sections = [dict(rs=r.get('rs'),reach_id=r.get('reach_id'),center=r.get('center_xy'),cutline=r.get('cutline_xy'),
        stations=r.get('station_ft'),elevations=r.get('elevation_ft'),locked_banks=r.get('bank_stations_ft') if i in fixed else None)
        for i,r in enumerate(geometry['cross_sections'])]
    return digest(dict(method=METHOD,settings=SETTINGS,sections=sections,
        crs=geometry.get('horizontal_crs'),faces={k:(geometry.get('structure') or {}).get(k) for k in ('us_xs_rs','ds_xs_rs')}))


def refresh(geometry, answers=None):
    """Rebuild stale reach proposals while retaining manually owned bank stations."""
    if not geometry.get('flowlines'):
        return
    answers = answers or {}
    rows = geometry['cross_sections']
    fixed = {i for i,row in enumerate(rows) if row.get('bank_stations_ft')
             and not answers.get(f'g.cross_sections.{i}.bank_stations_ft',{}).get('automatic_preparation')}
    if len(fixed)==len(rows):
        # Continuation can change section count/order while retaining all chosen
        # banks. Replace only the reach-level bookkeeping, never rerank controls.
        fingerprint=signature(geometry,fixed)
        previous=geometry.get('bank_reach_summary') or {}
        if previous.get('input_hash')!=fingerprint or previous.get('section_count')!=len(rows):
            geometry['bank_reach_summary']=dict(method='retained_bank_controls_v1',
                status='SAVED_BANKS_NOT_RERANKED', input_hash=fingerprint,
                section_count=len(rows), section_ids=[dict(index=i,reach_id=r.get('reach_id'),rs=r.get('rs')) for i,r in enumerate(rows)],
                locked_indices=sorted(fixed), proposed_pairs=0, unresolved_indices=[],
                previous_proposal=dict(method=previous.get('method'),input_hash=previous.get('input_hash')) if previous else None)
        return
    fingerprint = signature(geometry,fixed)
    old = geometry.get('bank_reach_summary',{})
    if old.get('input_hash')==fingerprint and all(
        i in fixed or (row.get('bank_candidates') or {}).get('reach_inputs_hash')==fingerprint
        for i,row in enumerate(rows)):
        return
    proposals,summary = propose_reach(geometry,fixed)
    for i,row in enumerate(rows):
        if i not in fixed:
            row['bank_candidates']=dict(proposals[i],reach_inputs_hash=fingerprint)
    geometry['bank_reach_summary']=summary
