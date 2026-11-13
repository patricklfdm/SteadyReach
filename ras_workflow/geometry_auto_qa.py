"""Preview-only QA repair. Preserve existing section samples when extending ends."""
import copy,math
import numpy as np
from .common import ROOT,read,intact,digest,finite
from .geometry_qa import spatial_issues,section_fingerprint
from .banks import annotate


def terrain_owned(row,s):
    stamp=row.get('terrain_sampling') or {}
    return stamp.get('raster',{}).get('sha256')==s.source['sha256'] and stamp.get('vertical_unit')==s.unit and stamp.get('vertical_datum')==s.datum and stamp.get('spatial_fingerprint')==digest({k:row.get(k) for k in ('cutline_xy','station_ft','elevation_ft','center_xy')})


def extend(row,s,water,maximum):
    """Add DEM points only beyond saved ends; shift station labels, not original geometry."""
    if len(row['cutline_xy'])!=2:raise ValueError('Curved cutline: explicit geometry review required')
    x=np.asarray(row['station_ft'],float);z=np.asarray(row['elevation_ft'],float);a,b=np.asarray(row['cutline_xy'],float);v=(b-a)/np.linalg.norm(b-a)
    if not np.isfinite(z).all():raise ValueError('Existing samples contain NoData')
    width=x[-1]-x[0];remaining=(maximum-width)/2
    if remaining<=0:return None,dict(status='MAX_WIDTH_ALREADY_REACHED')
    tails=[];lengths=[];notes=[]
    for point,sign,height in ((a,-1,z[0]),(b,1,z[-1])):
        if height>water:tails.append((np.array([]),np.array([])));lengths.append(0.);continue
        distances=np.linspace(0,remaining,max(3,min(400,math.ceil(remaining/max(2.,s.cell_ft))+1)))
        heights=s.sample(point+sign*distances[:,None]/s.factor*v)
        valid=np.isfinite(heights);end=None
        for j in range(1,len(distances)-1):
            if not valid[j]:break
            if heights[j]>water and valid[j+1] and heights[j+1]>water:end=j+1;break
        if end is None:return None,dict(status='NO_DRY_END_WITHIN_BOUND',side='left' if sign<0 else 'right',tested_extension_ft=float(distances[-1]),nodata=bool(not valid.all()))
        length=float(distances[end]);tails.append((distances[1:end+1],heights[1:end+1]));lengths.append(length)
    if not any(lengths):return None,dict(status='ENDS_ALREADY_ABOVE_PRIOR_WSE')
    # Keep every original point. Bound only new exterior sample counts to HEC-RAS's limit.
    budget=500-len(x)
    if budget<4:return None,dict(status='ORIGINAL_SECTION_NEAR_POINT_LIMIT')
    parts=[];remaining_budget=budget
    for index,(distance,height) in enumerate(tails):
        if not len(distance):parts.append((distance,height));continue
        reserve=sum(min(2,len(t[0])) for t in tails[index+1:])
        keep=min(remaining_budget-reserve,max(2,int(budget*len(distance)/max(1,sum(len(t[0]) for t in tails)))))
        ids=np.unique(np.linspace(0,len(distance)-1,min(keep,len(distance))).astype(int));parts.append((distance[ids],height[ids]))
        remaining_budget-=len(ids)
    (ld,lz),(rd,rz)=parts;left,right=lengths
    out=copy.deepcopy(row);out.update(station_ft=np.r_[left-ld[::-1],x-x[0]+left,width+left+rd].tolist(),
        elevation_ft=np.r_[lz[::-1],z,rz].tolist(),cutline_xy=[(a-left/s.factor*v).tolist(),(b+right/s.factor*v).tolist()])
    shift=left-x[0]
    if out.get('bank_stations_ft'):out['bank_stations_ft']=[v+shift for v in out['bank_stations_ft']]
    for name in ('ineffective_left','ineffective_right'):
        if out.get(name):out[name][0]+=shift
    if out.get('manning_segments'):
        # This adapter has not established how external material continues.
        return None,dict(status='EXPLICIT_ROUGHNESS_SUBDIVISIONS_NEED_REVIEW')
    out.pop('terrain_review',None);s.stamp(out)
    return out,dict(status='EXTENSION_CANDIDATE',left_added_ft=left,right_added_ft=right,old_points_preserved=True,station_label_shift_ft=shift,
        bank_plan_positions_preserved=bool(row.get('bank_stations_ft')),threshold_prior_wse_ft=water)


def prior_results(m,g):
    parent=m.get('parent_revision');water={};messages=[];sources=[]
    if not parent:return water,messages,sources,{}
    if not intact([parent['summary']]):raise ValueError('Parent calculation changed; recreate the revision')
    from . import app_core,app_parameters
    from .qa_locator import collect
    old_g=app_parameters.objects(app_core.model(parent['project_id']))[4]
    old={float(r['rs']):r for r in old_g['cross_sections']};summary=read(ROOT/parent['summary']['path']);h=summary['hydraulics']
    for r in collect(h)['rows']:
        if r['left_excess_ft'] or r['right_excess_ft']:water[float(r['rs'])]=max(water.get(float(r['rs']),float('-inf')),r['wse_ft'])
    diagnostics=read(ROOT/h['diagnostics']['path'])
    if summary.get('native_supplement'):
        from .app_outputs import validate,diagnostics as supplemented
        diagnostics=supplemented(h,validate(summary['native_supplement']))
    messages=diagnostics['issues'];sources=[parent['summary'],h['raw_hdf'],h['diagnostics']]
    return water,messages,sources,old


def propose(m,g,s,maximum=1200.):
    from .app_section_repair import suggest
    from .geometry_editor import transform_section
    from .app_automation import preflight
    candidate=copy.deepcopy(g);rows=candidate['cross_sections'];changes=[];unresolved=[]
    ui=next((i for i,r in enumerate(rows) if r['rs']==g['structure'].get('us_xs_rs')),None)
    protected={ui-1,ui,ui+1,ui+2} if ui is not None else set()
    rotations=suggest(g,m)
    for change in rotations['changes']:
        i=change['index'];row=rows[i]
        if i in protected or not terrain_owned(row,s) or any(row.get(k) for k in ('manning_segments','ineffective_left','ineffective_right')):
            unresolved.append(dict(rs=row['rs'],code='PROTECTED_SECTION_OR_FLOW_SUBDIVISION',action='Review this section explicitly; automatic rotation cannot relocate a structure or explicit flow subdivisions'));continue
        cut,center,p=transform_section(row,g['horizontal_crs'],change['parameters']);xy=cut[0]+(np.asarray(row['station_ft'])-row['station_ft'][0])[:,None]/p['width_ft']*(cut[-1]-cut[0]);z=s.sample(xy)
        if not np.isfinite(z).all():unresolved.append(dict(rs=row['rs'],code='ROTATION_NODATA'));continue
        row.update(cutline_xy=cut.tolist(),center_xy=center.tolist(),elevation_ft=z.tolist(),bank_stations_ft=None)
        row.pop('terrain_review',None)
        s.stamp(row);changes.append(dict(rs=row['rs'],action='ROTATE_FROM_SPATIAL_QA',parameters=p,banks_need_confirmation=True))
    water,messages,sources,old=prior_results(m,g)
    for i,row in enumerate(rows):
        rs=float(row['rs'])
        if rs not in water:continue
        before=g['cross_sections'][i];prior=old.get(rs)
        keys=('cutline_xy','center_xy','station_ft','elevation_ft')
        if i in protected or not terrain_owned(before,s) or not prior or any(before.get(k)!=prior.get(k) for k in keys) or any(c['rs']==rs for c in changes):
            unresolved.append(dict(rs=rs,code='PRIOR_WSE_GEOMETRY_CHANGED_OR_PROTECTED',action='Confirm current geometry and compute before using prior WSE'));continue
        after,record=extend(before,s,water[rs],maximum)
        if after is None:unresolved.append(dict(rs=rs,**record));continue
        trial=copy.deepcopy(rows);trial[i]=after
        blockers=[q for q in spatial_issues(trial) if i in q['sections']]
        if blockers:unresolved.append(dict(rs=rs,code='EXTENSION_SPATIAL_CONFLICT',issues=blockers));continue
        rows[i]=after;changes.append(dict(rs=rs,action='EXTEND_WET_ENDS',**record))
    # Route other warnings to explicit review; do not fabricate a geometric cure.
    for issue in messages:
        if issue['code'] not in ('WET_SECTION_EDGE','NATIVE_WET_SECTION_EDGE'):
            unresolved.append(dict(rs=issue.get('station'),code=issue['code'],action=issue.get('recommended_action'),automatically_resolved=False))
    annotate(candidate)
    original={r['rs']:r for r in g['cross_sections']};changed={c['rs'] for c in changes}
    for row in rows:
        if row['rs'] not in changed and original[row['rs']].get('terrain_review'):row['terrain_review']=original[row['rs']]['terrain_review']
    issues=preflight(m,candidate)['issues']
    return dict(layouts=[dict(id='qa_changes',geometry=candidate,anchors=[],changes=changes,changed_sections=[i for i,r in enumerate(rows) if r['rs'] in changed],
        before_sections={str(i):copy.deepcopy(r) for i,r in enumerate(g['cross_sections']) if r['rs'] in changed},
        issues=issues,warnings=['PRIOR_WSE_IS_A_SCREEN_NOT_NEW_HYDRAULICS'],unresolved=unresolved,
        can_apply=bool(changes) and not any(q.get('blocking') for q in issues),basis='QA-driven bounded repair; preserved interior samples on extension; no change of boundary, structures or solver tolerances.')],
        sources=[s.source]+sources,solver_run=False)
