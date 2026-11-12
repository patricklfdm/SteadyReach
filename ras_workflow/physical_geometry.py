"""Explainable terrain screening, never proof of hydraulic connectivity or acceptance."""
import numpy as np
from .common import ROOT, digest, finite, intact, item, read, safe_path, save
from .geometry_qa import intersects

SETTINGS=dict(low_band_fraction=.25,min_low_area_width_ft=5.,adjacent_width_ratio=2.5,bed_step_fraction=.2)


def screen(geometry):
    rows=geometry.get('cross_sections',[]);issues=[];structure=geometry.get('structure',{})
    def add(code,indices,en,zh,evidence=None):
        issues.append(dict(code=code,sections=indices,severity='REVIEW',en=en,zh=zh,evidence=evidence or {}))
    profiles={}
    for i,row in enumerate(rows):
        try:
            x=np.asarray(row['station_ft'],float);z=np.asarray(row['elevation_ft'],float)
            if len(x)!=len(z) or len(x)<3 or not np.isfinite(x).all() or not np.isfinite(z).all() or not (np.diff(x)>0).all():continue
        except (ValueError,TypeError,KeyError):continue
        profiles[i]=(x,z)
        # Multiple low zones at a terrain-relative level; this is NOT a water level.
        level=float(z.min()+SETTINGS['low_band_fraction']*np.ptp(z));mask=z<=level
        spans=[];start=None
        for k,v in enumerate(mask.tolist()+[False]):
            if v and start is None:start=k
            if not v and start is not None:
                if x[k-1]-x[start]>=SETTINGS['min_low_area_width_ft']:spans.append([float(x[start]),float(x[k-1])])
                start=None
        if len(spans)>1:add('MULTIPLE_TERRAIN_LOW_AREAS',[i],'Separate low areas need channel/overbank connectivity review.','多个低地区域需要复核主槽/漫滩连通性。',dict(screening_elevation_ft=level,low_spans_ft=spans,not_a_water_level=True))
        banks=row.get('bank_stations_ft')
        if isinstance(banks,list) and len(banks)==2 and all(finite(v) for v in banks):
            bz=np.interp(banks,x,z);low=float(min(bz));sides=[side for side,value in [('left',z[0]),('right',z[-1])] if value<low]
            if sides:add('LOW_SECTION_ENDS',[i],'Section ends lie below an adopted bank elevation. Inspect wider terrain before deciding the extent.','断面端点低于采用的岸站高程，需查看更宽地形后确定范围。',dict(sides=sides,reference_elevation_ft=low))
        lengths=row.get('reach_lengths_ft')
        if not row.get('reach_length_basis'):
            add('FLOW_PATH_BASIS_REQUIRED',[i],'Record how left overbank, channel and right overbank reach lengths follow effective flow paths.','记录左滩、主槽及右滩流程长度如何对应有效流路。',dict(reach_lengths_ft=lengths))
    for i in range(len(rows)-1):
        if i not in profiles or i+1 not in profiles:continue
        if rows[i].get('reach_id')!=rows[i+1].get('reach_id'):continue
        if rows[i].get('rs')==structure.get('us_xs_rs') and rows[i+1].get('rs')==structure.get('ds_xs_rs'):continue
        a,b=profiles[i],profiles[i+1];widths=[a[0][-1]-a[0][0],b[0][-1]-b[0][0]]
        if max(widths)/min(widths)>SETTINGS['adjacent_width_ratio']:add('ABRUPT_SECTION_WIDTH',[i,i+1],'Review abrupt section-width change and floodplain coverage.','复核断面宽度突变及漫滩覆盖。',dict(widths_ft=list(map(float,widths))))
        delta=abs(float(a[1].min()-b[1].min()))
        if delta>SETTINGS['bed_step_fraction']*min(widths):add('ABRUPT_TERRAIN_CHANGE',[i,i+1],'Inspect terrain transition and consider additional sampled sections; do not interpolate hydraulic results.','检查地形突变，考虑新增实采断面，不插值生成水力结果。',dict(minimum_elevation_change_ft=delta))
    stations=[r.get('rs') for r in rows]
    if structure and not geometry.get('functional_section_basis'):
        add('FUNCTIONAL_PLACEMENT_REVIEW_REQUIRED',[],'Record the basis for upstream approach, inlet/outlet faces and downstream expansion recovery, including boundary distance. Section count alone does not establish functional coverage.','需记录上游接近段、进出口及下游扩散恢复断面的布置依据和边界距离，断面数量本身不能证明功能覆盖。')
    for key,up in [('us_xs_rs',True),('ds_xs_rs',False)]:
        rs=structure.get(key)
        if rs in stations:
            i=stations.index(rs)
            if (up and i==0) or (not up and i==len(rows)-1):add('STRUCTURE_FUNCTIONAL_SECTION_COVERAGE',[i],'No further exterior section beyond the structure face; review contraction/expansion and boundary extent.','结构外侧断面以外没有更多断面，需复核收缩/扩散功能及边界范围。')
    lines=geometry.get('flowlines',[])
    if not lines:add('FLOW_ALIGNMENT_NOT_BOUND',[],'A reviewed flow alignment is required to assess section crossings and direction.','需要绑定经复核流线，才能评估断面穿越和方向。')
    else:
        for i,row in enumerate(rows):
            cut=row.get('cutline_xy') or [];crossings=[];ambiguous=False
            def valid_line(xy):
                return isinstance(xy,list) and len(xy)>=2 and all(isinstance(p,(list,tuple)) and len(p)==2 and all(finite(v) for v in p) for p in xy)
            if not valid_line(cut):
                add('FLOW_ALIGNMENT_CROSSING_COUNT',[i],'A valid cutline is needed for crossing review.','需要有效断面线才能复核穿越次数。',dict(intersections=None));continue
            # Count intersection points, merging shared-vertex hits.
            for line in lines:
                if row.get('reach_id') and line.get('id')!=row['reach_id']:continue
                xy=line.get('xy',[])
                if line.get('role','channel')!='channel':continue
                if not valid_line(xy):ambiguous=True;continue
                for a,b in zip(cut,cut[1:]):
                    for c,d in zip(xy,xy[1:]):
                        if not intersects(a,b,c,d):continue
                        a,b,c,d=map(lambda p:np.asarray(p,float),(a,b,c,d));u=b-a;v=d-c;den=u[0]*v[1]-u[1]*v[0]
                        if abs(den)<1e-9:ambiguous=True;continue
                        else:
                            w=c-a;point=a+u*((w[0]*v[1]-w[1]*v[0])/den)
                        if not any(np.linalg.norm(point-p)<1e-6 for p in crossings):crossings.append(point)
            if len(crossings)!=1 or ambiguous:add('FLOW_ALIGNMENT_CROSSING_COUNT',[i],'The cutline should cross its reviewed main flow alignment once. Review alignment and section direction.','断面应一次穿过对应的经复核主流线，请复核流线和断面方向。',dict(intersections=len(crossings),ambiguous_overlap_or_invalid_line=ambiguous))
    return dict(schema_version='physical_geometry_screen_1.0',settings=SETTINGS,geometry_fingerprint=digest(geometry),issues=issues,
        status='REVIEW_REQUIRED',limitation='Terrain-only screening; thresholds are internal aids, not design criteria or demonstrated conveyance connectivity.')


def evaluate_banks(geometry_path,reference_path,output):
    from .banks import propose
    gp,rp=[safe_path(ROOT,p) for p in [geometry_path,reference_path]];g=read(gp);ref=read(rp)
    if ref.get('geometry')!=item(gp) or not ref.get('sources') or not intact(ref['sources']):raise ValueError('Bank reference geometry/source binding invalid')
    if not ref.get('reviewer') or ref.get('reference_kind') not in ['independent_manual_annotation','surveyed']:raise ValueError('Named independent annotation or survey reference required')
    tolerance=ref.get('tolerance_ft')
    if not finite(tolerance) or tolerance<=0:raise ValueError('Explicit positive bank-error tolerance required')
    annotations=ref.get('sections',[])
    if not annotations or len({str(r['rs']) for r in annotations})!=len(annotations):raise ValueError('Unique nonempty reference sections required')
    records=[]
    for a in annotations:
        matches=[r for r in g['cross_sections'] if str(r['rs'])==str(a['rs'])]
        if len(matches)!=1:raise ValueError('Reference station correspondence is ambiguous')
        row=matches[0];actual=a.get('bank_stations_ft')
        if not isinstance(actual,list) or len(actual)!=2 or not all(finite(x) for x in actual) or not row['station_ft'][0]<actual[0]<actual[1]<row['station_ft'][-1]:raise ValueError('Reference banks must be ordered inside the bound section')
        p=propose(row);ids=p['selected_indices'];estimated=[row['station_ft'][i] for i in ids] if ids else None
        errors=[estimated[i]-actual[i] for i in [0,1]] if estimated else None
        records.append(dict(rs=a['rs'],confidence=p['confidence'],reference_ft=actual,predicted_ft=estimated,error_ft=errors,
            outside_tolerance=any(abs(e)>tolerance for e in errors) if errors else None))
    errors=[abs(e) for r in records for e in (r['error_ft'] or [])];unresolved=sum(r['error_ft'] is None for r in records)
    result=dict(status='EVALUATED_REQUIRES_REVIEW',geometry=item(gp),reference=item(rp),sources=ref['sources'],reference_kind=ref['reference_kind'],records=records,
        evaluated_sections=len(records),total_sections=len(g['cross_sections']),resolved_sections=len(records)-unresolved,
        unlabelled_sections=len(g['cross_sections'])-len(records),unresolved_sections=unresolved,unresolved_fraction=unresolved/len(records),
        confidence_counts={level:sum(r['confidence']==level for r in records) for level in ['HIGH','MEDIUM','LOW','UNRESOLVED']},
        high_confidence_sections=sum(r['confidence']=='HIGH' for r in records),
        mean_abs_error_ft=float(np.mean(errors)) if errors else None,p95_abs_error_ft=float(np.percentile(errors,95)) if errors else None,
        max_abs_error_ft=max(errors) if errors else None,tolerance_ft=tolerance,
        high_confidence_outside_tolerance=sum(r['confidence']=='HIGH' and r['outside_tolerance'] is True for r in records),
        limitation='Accuracy applies only to the supplied independently labelled sections; reference independence is operator-attested, not automatically established.')
    dest=safe_path(ROOT,output)
    if dest.exists():raise ValueError('Use a new evaluation output')
    save(dest,result);return result
