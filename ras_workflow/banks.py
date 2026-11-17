"""Explainable morphological bank proposals; never bankfull levels or approval.

Outward steep-to-flat slope breaks are ranked on a median-smoothed profile.
Parameters are screening controls, not hydraulic constants or surveyed geometry.
"""
import numpy as np
from .common import finite

DEFAULTS = dict(window_ft=3., min_relief_ft=.5, min_slope_drop=.08,
                center_search_fraction=.25, competing_score_ratio=.75, distance_penalty=0.)


def channel_origin(row, stations):
    """Locate the saved channel anchor on the full, possibly extended cutline."""
    center = row.get('center_xy')
    line = row.get('cutline_xy')
    if center is None or line is None:
        return float((stations[0] + stations[-1]) / 2), 'section_midpoint'
    try:
        points = np.asarray(line, dtype=float)
        anchor = np.asarray(center, dtype=float)
        if points.ndim != 2 or points.shape[1] != 2 or anchor.shape != (2,):
            raise ValueError()
        if not np.isfinite(points).all() or not np.isfinite(anchor).all():
            raise ValueError()
        segments = np.diff(points, axis=0)
        lengths = np.linalg.norm(segments, axis=1)
        total = float(lengths.sum())
        if not np.isfinite(total) or total <= 0:
            raise ValueError()
        best = None
        offset = 0.
        for start, vector, length in zip(points, segments, lengths):
            if length > 0:
                fraction = float(np.clip(np.dot(anchor-start, vector)/(length*length), 0., 1.))
                distance = float(np.linalg.norm(anchor-start-fraction*vector))
                candidate = (distance, offset+fraction*length)
                if best is None or candidate[0] < best[0]:
                    best = candidate
            offset += length
        station = stations[0] + best[1]/total*(stations[-1]-stations[0])
        return float(station), 'saved_channel_anchor'
    except (ValueError, TypeError):
        return float((stations[0] + stations[-1]) / 2), 'section_midpoint'


def _single_scale(row, settings=None):
    p=dict(DEFAULTS)
    if settings:
        if set(settings)-set(p):raise ValueError('Unknown bank screening setting')
        p.update(settings)
    if not all(finite(v) and v>0 for k,v in p.items() if k!='distance_penalty') or not finite(p['distance_penalty']) or p['distance_penalty']<0 or p['center_search_fraction']>.5 or p['competing_score_ratio']>1:
        raise ValueError('Invalid bank screening settings')
    result=dict(method='outward_slope_break_v1',settings=p,evidence_class='inferred',
        selected_indices=None,confidence='UNRESOLVED',reasons=[],left=[],right=[],
        limitation='Terrain morphology only; not bankfull stage or surveyed hydraulic banks. Explicit review required.')
    try:
        x=np.asarray(row['station_ft'],dtype=float);z=np.asarray(row['elevation_ft'],dtype=float)
        if len(x)!=len(z) or len(x)<7 or not np.isfinite(x).all() or not np.isfinite(z).all() or not (np.diff(x)>0).all():raise ValueError()
    except (ValueError,KeyError,TypeError):
        result['reasons']=['INVALID_OR_NODATA_PROFILE'];return result
    width=x[-1]-x[0];mid,origin=channel_origin(row,x)
    result.update(channel_search_origin=origin,channel_anchor_station_ft=mid)
    mask=np.abs(x-mid)<=width*p['center_search_fraction']
    indices=np.flatnonzero(mask)
    if not len(indices):result['reasons']=['NO_CHANNEL_SEARCH_SAMPLES'];return result
    smooth=np.array([np.median(z[np.abs(x-v)<=p['window_ft']/2]) for v in x])
    bottom=int(indices[np.argmin(smooth[indices])]);result['channel_minimum_index']=bottom
    result['channel_search_station_ft']=[float(mid-width*p['center_search_fraction']),float(mid+width*p['center_search_fraction'])]
    def side(sign):
        ids=np.arange(bottom,len(x)) if sign==1 else np.arange(bottom,-1,-1)
        d=np.abs(x[ids]-x[bottom]);v=smooth[ids];w=p['window_ft'];poss=[]
        for k,i in enumerate(ids):
            # The outward slope window also needs a complete smoothing window;
            # otherwise a truncated median invents a break near the section edge.
            if i in (0,len(x)-1) or d[k]<w or d[-1]-d[k]<1.5*w:continue
            inside=(v[k]-np.interp(d[k]-w,d,v))/w
            outside=(np.interp(d[k]+w,d,v)-v[k])/w
            drop=inside-outside;relief=v[k]-smooth[bottom]
            if inside<=p['min_slope_drop'] or drop<p['min_slope_drop'] or relief<p['min_relief_ft']:continue
            poss.append(dict(index=int(i),station_ft=float(x[i]),elevation_ft=float(z[i]),
                inward_slope=float(inside),outward_slope=float(outside),slope_drop=float(drop),
                relief_ft=float(relief),score=float(drop*min(relief/p['min_relief_ft'],4)/(1+p['distance_penalty']*d[k]/w))))
        selected=[]
        for value in sorted(poss,key=lambda r:r['score'],reverse=True):
            if all(abs(value['station_ft']-a['station_ft'])>=w for a in selected):selected.append(value)
            if len(selected)==3:break
        return selected
    result['left']=side(-1);result['right']=side(1)
    if not result['left'] or not result['right']:
        result['reasons'].append('NO_DISTINCT_BANK_ON_ONE_OR_BOTH_SIDES');return result
    left,right=result['left'][0],result['right'][0]
    result['selected_indices']=[left['index'],right['index']]
    result['confidence']='MEDIUM'
    for name in ['left','right']:
        choices=result[name]
        if len(choices)>1 and choices[1]['score']>=choices[0]['score']*p['competing_score_ratio']:
            result['reasons'].append('COMPETING_'+name.upper()+'_BANKS')
    if max(left['relief_ft'],right['relief_ft'])>2*min(left['relief_ft'],right['relief_ft']):
        result['reasons'].append('ASYMMETRIC_BANK_RELIEF')
    if abs(x[bottom]-mid)>.15*width:result['reasons'].append('CHANNEL_MINIMUM_OFF_CENTER')
    for bank,outer in [(left,z[:left['index']]),(right,z[right['index']+1:])]:
        if len(outer) and np.min(outer)<smooth[bottom]+p['min_relief_ft']:
            result['reasons'].append('LOW_OUTER_TERRAIN_OR_MULTIPLE_CHANNELS');break
    if result['reasons']:result['confidence']='LOW'
    else:result['reasons']=['DISTINCT_SLOPE_BREAKS_REVIEW_REQUIRED']
    return result


def propose(row, settings=None):
    """Compare three explicit smoothing scales; disagreement lowers confidence."""
    base=_single_scale(row,settings)
    if base['reasons']==['INVALID_OR_NODATA_PROFILE']:return base
    window=base['settings']['window_ft']
    scales=[_single_scale(row,dict(base['settings'],window_ft=window*f)) for f in [.5,1.,2.]]
    result=dict(base,method='outward_slope_break_multiscale_v3',
        scale_windows_ft=[window*f for f in [.5,1.,2.]],scale_results=scales)
    reasons=[r for r in base['reasons'] if r not in ['DISTINCT_SLOPE_BREAKS_REVIEW_REQUIRED','NO_DISTINCT_BANK_ON_ONE_OR_BOTH_SIDES']]
    for side in ['left','right']:
        candidates=[]
        for si,scale in enumerate(scales):
            for candidate in scale[side]:
                candidates.append(dict(candidate,scale_index=si))
        clusters=[]
        for candidate in sorted(candidates,key=lambda v:v['score'],reverse=True):
            if any(abs(candidate['station_ft']-c['station_ft'])<window for c in clusters):continue
            nearby=[v for v in candidates if abs(v['station_ft']-candidate['station_ft'])<=window*.75]
            support=sorted({v['scale_index'] for v in nearby})
            value={k:v for k,v in candidate.items() if k!='scale_index'}
            value.update(scale_support=len(support),support_windows_ft=[result['scale_windows_ft'][i] for i in support])
            clusters.append(value)
        result[side]=sorted(clusters,key=lambda v:(v['scale_support'],v['score']),reverse=True)[:3]
    if any(not result[side] or result[side][0]['scale_support']<2 for side in ['left','right']):
        result.update(selected_indices=None,confidence='UNRESOLVED',reasons=reasons+['NO_SCALE_STABLE_BANK_PAIR'])
        return result
    result['selected_indices']=[result[side][0]['index'] for side in ['left','right']]
    if any(not scale['selected_indices'] or any(abs(row['station_ft'][scale['selected_indices'][j]]-
            row['station_ft'][result['selected_indices'][j]])>window for j in [0,1]) for scale in scales):
        reasons.append('SCALE_SENSITIVE_BANKS')
    for side in ['left','right']:
        choices=result[side]
        if len(choices)>1 and choices[1]['scale_support']==choices[0]['scale_support'] and choices[1]['score']>=choices[0]['score']*base['settings']['competing_score_ratio']:
            reasons.append('COMPETING_'+side.upper()+'_BANKS')
    result['reasons']=list(dict.fromkeys(reasons)) or ['DISTINCT_SLOPE_BREAKS_REVIEW_REQUIRED']
    result['confidence']='LOW' if reasons else 'MEDIUM'
    return result


def annotate(geometry, settings=None):
    from .geometry_qa import spatial_issues
    issues=spatial_issues(geometry['cross_sections'])
    for i,row in enumerate(geometry['cross_sections']):
        row['bank_candidates']=propose(row,settings)
        row['geometry_issues']=[q for q in issues if i in q['sections']]
        if row['bank_candidates']['confidence']=='UNRESOLVED':
            row['geometry_issues'].append(dict(code=row['bank_candidates']['reasons'][0],severity='REVIEW_REQUIRED',sections=[i]))
        row['review_status']='DRAFT_REQUIRES_REVIEW'
    rows=geometry['cross_sections']
    from .bank_reach import refresh
    refresh(geometry)
    faces=geometry.get('structure') or {}
    for i in range(1,len(rows)):
        a,b=rows[i-1:i+1]
        if a.get('reach_id')!=b.get('reach_id') or (faces.get('us_xs_rs') is not None and faces.get('ds_xs_rs') is not None and a.get('rs')==faces['us_xs_rs'] and b.get('rs')==faces['ds_xs_rs']):continue
        picks=[r['bank_candidates']['selected_indices'] for r in [a,b]]
        if any(v is None for v in picks):continue
        widths=[r['station_ft'][v[1]]-r['station_ft'][v[0]] for r,v in zip([a,b],picks)]
        if min(widths)>0 and max(widths)/min(widths)>2.5:
            for row,neighbor in [(a,i),(b,i-1)]:
                p=row['bank_candidates'];p['confidence']='LOW'
                p['reasons']=list(dict.fromkeys(p['reasons']+['BANK_WIDTH_DISCONTINUITY']))
                p.setdefault('continuity_checks',[]).append(dict(neighbor_index=neighbor,width_ratio=max(widths)/min(widths),screening_threshold=2.5))
    geometry['geometry_qa']=dict(issues=issues,uncertain_sections=[i for i,r in enumerate(geometry['cross_sections']) if r['bank_candidates']['confidence'] in ['LOW','UNRESOLVED'] or r['geometry_issues']],
        required_review_sections=list(range(len(geometry['cross_sections']))))
    geometry['terrain_review_required']=True
    return geometry
