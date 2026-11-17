"""Read-only warning review from sealed native sections and computed profiles."""
import math
import h5py

from .common import ROOT, finite, read
from .qa import BASE, number
from .qa_locator import intervals
from .revision_inputs import bound_inputs, indexed, station_key, point


def wet_parts(x, z, water):
    if len(x) != len(z) or len(x) < 2 or not all(finite(v) for v in x+z):
        raise ValueError('Native section samples are missing or nonfinite')
    if x[-1] <= x[0] or any(b < a for a,b in zip(x,x[1:])):
        raise ValueError('Native section stations are not ordered')
    if water is None:
        return None
    # Duplicate stations represent vertical walls. Zero-width intersections
    # have no displayed width; a crest exactly at WSE remains a separation.
    return [v for v in intervals(x,z,water) if v[1] > v[0]]


def line_point(line, fraction):
    lengths=[math.dist(a,b) for a,b in zip(line,line[1:])]
    distance=sum(lengths)*fraction
    for i,length in enumerate(lengths):
        if length and (distance<=length or i==len(lengths)-1):
            return [a+(b-a)*distance/length for a,b in zip(line[i],line[i+1])]
        distance-=length
    return list(line[-1])


def line_slice(line, start, end):
    lengths=[math.dist(a,b) for a,b in zip(line,line[1:])]
    total=sum(lengths);distance=0
    points=[line_point(line,start)]
    for i,length in enumerate(lengths[:-1]):
        distance+=length
        if start*total<distance<end*total:points.append(list(line[i+1]))
    points.append(line_point(line,end))
    return points


def local_map(row, source):
    if not source:
        return None
    line=source.get('cutline_xy') or []
    sx=source.get('station_ft') or []
    if len(line)<2 or not all(point(p) for p in line) or len(sx)<2 or not all(finite(v) for v in (sx[0],sx[-1])):
        return None
    if any(abs(a-b)>.01 for a,b in zip((sx[0],sx[-1]),(row['station_ft'][0],row['station_ft'][-1]))):
        return None
    if sum(math.dist(a,b) for a,b in zip(line,line[1:]))<=0:
        return None
    lo,hi=row['station_ft'][0],row['station_ft'][-1]
    convert=lambda value:line_point(line,(value-lo)/(hi-lo))
    return dict(cutline_xy=line,banks_xy=[convert(v) for v in row['banks_ft']]
        if all(finite(v) and lo<=v<=hi for v in row['banks_ft']) else None,
        wet_segments_xy=[line_slice(line,(a-lo)/(hi-lo),(b-lo)/(hi-lo)) for a,b in row['wet_intervals_ft']]
        if row['wet_intervals_ft'] is not None else None)


def assemble(rows, diagnostics, geometry=None):
    """Match every message uniquely, retaining unlocated messages explicitly."""
    geom=indexed((geometry or {}).get('cross_sections',[]))
    issues=(diagnostics or {}).get('issues',[])
    used=set();panels=[]
    for i,row in enumerate(rows):
        native=dict(row)
        native['wet_intervals_ft']=wet_parts(row['station_ft'],row['elevation_ft'],row['wse_ft'])
        native['left_excess_ft']=None if row['wse_ft'] is None else max(0,row['wse_ft']-row['elevation_ft'][0])
        native['right_excess_ft']=None if row['wse_ft'] is None else max(0,row['wse_ft']-row['elevation_ft'][-1])
        found=[]
        for issue in issues:
            try:matches=(issue.get('profile')==row['profile'] and station_key(issue.get('station'))==station_key(row['rs']))
            except (ValueError,TypeError):matches=False
            evidence=issue.get('evidence',{})
            matches=matches and all(not evidence.get(k) or evidence[k]==row[k] for k in ('river','reach'))
            if matches:found.append(issue);used.add(issue['id'])
        native['issues']=found
        native['map']=local_map(native,geom.get(station_key(row['rs'])))
        neighbors=[]
        for relation,j in [('upstream',i-1),('downstream',i+1)]:
            if 0<=j<len(rows) and all(rows[j][k]==row[k] for k in ('profile','river','reach')):
                other=rows[j]
                neighbors.append(dict(relation=relation,section_id=other['section_id'],rs=other['rs'],
                    wse_ft=other['wse_ft'],egl_ft=other['egl_ft'],velocity_fts=other['velocity_fts'],froude=other['froude'],
                    channel_length_between_ft=other['channel_length_ft'] if relation=='upstream' else row['channel_length_ft']))
        native['neighbors']=neighbors
        native['needs_attention']=bool(found or (native['wet_intervals_ft'] is not None and len(native['wet_intervals_ft'])>1)
            or (native['left_excess_ft'] or 0)>0 or (native['right_excess_ft'] or 0)>0 or row['wse_ft'] is None)
        panels.append(native)
    return dict(sections=panels,unlocated_issues=[v for v in issues if v['id'] not in used],
        diagnostic_count=len(issues),located_diagnostic_count=len(used),
        attention_section_profiles=sum(v['needs_attention'] for v in panels),
        separated_wet_section_profiles=sum(v['wet_intervals_ft'] is not None and len(v['wet_intervals_ft'])>1 for v in panels),
        warning_coverage=(diagnostics or {}).get('warning_coverage','UNAVAILABLE'))


def native_rows(hyd):
    controller=read(ROOT/hyd['raw_controller']['path'])
    result=[]
    def text(value):return value.decode().strip()
    with h5py.File(ROOT/hyd['raw_hdf']['path']) as f:
        attrs=f['Geometry/Cross Sections/Attributes'][:]
        output=f['Results/Steady/Output/Geometry Info/Cross Section Attributes'][:]
        identity=[tuple(text(a[k]) for k in ('River','Reach','RS')) for a in attrs]
        observed=[tuple(text(a[k]) for k in ('River','Reach','Station')) for a in output]
        if identity!=observed or len(identity)!=len(set(identity)):
            raise ValueError('Native geometry/result identities differ or repeat')
        if len({v[:2] for v in identity})!=1:
            raise ValueError('Section review currently supports one continuous native reach')
        if any(float(b[2])>=float(a[2]) for a,b in zip(identity,identity[1:])):
            raise ValueError('Native section order is not upstream to downstream')
        info=f['Geometry/Cross Sections/Station Elevation Info'][:]
        points=f['Geometry/Cross Sections/Station Elevation Values'][:]
        if len(info)!=len(attrs):raise ValueError('Native section sample inventory differs')
        for pi,p in enumerate(hyd['profiles']):
            w=f[BASE+'/Cross Sections/Water Surface'][pi]
            e=f[BASE+'/Cross Sections/Energy Grade'][pi]
            if len(w)!=len(attrs) or len(e)!=len(attrs):raise ValueError('Native result/sample count differs')
            for i,(a,(start,count)) in enumerate(zip(attrs,info)):
                if start<0 or count<2 or start+count>len(points):raise ValueError('Native sample slice is invalid')
                xy=points[start:start+count];river,reach,rs=identity[i]
                matches=[v for v in controller['rows'] if v['profile']==p['profile_id'] and v['station']==rs and not v['node_type']]
                if len(matches)!=1:raise ValueError('Ambiguous native section/controller identity')
                m=matches[0]['metrics']
                result.append(dict(section_id=f'{pi}:{i}',river=river,reach=reach,rs=rs,profile=p['profile_id'],
                    station_ft=xy[:,0].astype(float).tolist(),elevation_ft=xy[:,1].astype(float).tolist(),
                    banks_ft=[number(a['Left Bank']),number(a['Right Bank'])],channel_length_ft=number(a['Len Channel']),
                    wse_ft=number(w[i]),egl_ft=number(e[i]),critical_wse_ft=number(m.get('Crit W.S.')),
                    velocity_fts=number(m.get('Vel Chnl')),froude=number(m.get('Froude # Chl')),
                    min_error_ft=number(m.get('Min Error'))))
    return result


def collect(key, body):
    from .result_guidance import load_evidence
    m,path,summary,hyd,diagnostics,errors=load_evidence(key,body)
    if hyd.get('unit')!='international ft':
        raise ValueError('Section review requires the verified international-foot extraction')
    sources=[m['summary'],summary['hydraulic_results'],hyd['raw_hdf'],hyd['raw_controller']]
    geometry=None
    try:
        _,geometry,refs=bound_inputs(summary);sources+=refs
    except (ValueError,KeyError,OSError,TypeError) as error:
        errors.append('Projected section correspondence unavailable: '+str(error))
    result=assemble(native_rows(hyd),diagnostics,geometry)
    if diagnostics:sources+=diagnostics.get('sources',[])
    result.update(status='OBSERVATIONS_NOT_ACCEPTANCE',run_id=hyd['run_id'],sources=sources,source_errors=errors,
        horizontal_crs=(geometry or {}).get('horizontal_crs'),unit=hyd['unit'],
        geometry_changed=False,solver_started=False,warnings_resolved=0,engineering_acceptance='NOT_ASSESSED',
        limitation='Wet intervals are geometric intersections of raw model ground and computed WSE, not active conveyance, flow connectivity or mapped inundation. Missing critical elevations remain unknown.')
    return result
