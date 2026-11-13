"""Source-linked opening associations, derivations and early spatial screening.

All functions that suggest/check are read-only. Saving an association does not
adopt its numbers. No geometry is repaired and no solver is launched here.
"""
import copy
import math
import re
from collections import defaultdict
from .common import ROOT, digest, finite, intact, lock, read, save, unique_id, utc
from pyproj.exceptions import CRSError


def faces(g):
    rows=g.get('cross_sections',[]);s=g.get('structure',{})
    selected=[next((r for r in rows if s.get(k) is not None and r.get('rs')==s[k]),None) for k in ('us_xs_rs','ds_xs_rs')]
    def valid(r):
        return r and len(r.get('cutline_xy') or [])>=2 and len(r.get('station_ft') or [])>=2 and all(isinstance(p,list) and len(p)==2 and all(finite(v) for v in p) for p in r['cutline_xy']) and all(finite(v) for v in r['station_ft']) and math.dist(r['cutline_xy'][0],r['cutline_xy'][-1])>0
    if all(valid(r) for r in selected):return selected
    transitions=[i for i in range(len(rows)-1) if rows[i].get('reach_id')=='upstream' and rows[i+1].get('reach_id')=='downstream']
    candidate=rows[transitions[0]:transitions[0]+2] if len(transitions)==1 else [None,None]
    return candidate if all(valid(r) for r in candidate) else [None,None]


def linear_factor(g):
    from pyproj import CRS
    crs=CRS.from_user_input(g['horizontal_crs'])
    if not crs.is_projected:raise ValueError('A projected geometry CRS is required / 需要投影坐标系')
    return crs.axis_info[0].unit_conversion_factor/.3048


def dependency(m,g,field):
    data=dict(crs=g.get('horizontal_crs'),datum=g.get('vertical_datum'))
    if '.groups.' in field:
        i=int(field.split('.')[3]);b=g['structure']['groups'][i]
        data.update(mapping=[r for r in m.get('opening_mapping',[]) if r['group']==i],count=b.get('count'),survey=m.get('survey_settings'),map_picks=m.get('group_map_picks',{}).get(str(i)),gap=m.get('wall_gap_ft'),span=b.get('span_ft'))
        if 'invert' in field:data['height']=b.get('rise_ft')
        if field.endswith(('.centers_ft','.distance_us_ft')):data['faces']=[{k:r.get(k) for k in ('rs','cutline_xy','station_ft')} if r else None for r in faces(g)]
    elif '.cross_sections.' in field:
        i=int(field.split('.')[2]);data.update(centers=[r.get('center_xy') for r in g['cross_sections'][i:i+2]],flowlines=g.get('flowlines'))
    else:
        data.update(source=m.get('source_analysis'),survey=m.get('survey_settings'),faces=[{k:r.get(k) for k in ('rs','cutline_xy','station_ft')} if r else None for r in faces(g)])
    return digest(data)


def station(face,xy):
    a,b=face['cutline_xy'][0],face['cutline_xy'][-1]
    v=[b[i]-a[i] for i in (0,1)];den=sum(x*x for x in v)
    if den<=0:raise ValueError('Zero-length face cutline')
    t=sum((xy[i]-a[i])*v[i] for i in (0,1))/den
    return face['station_ft'][0]+t*(face['station_ft'][-1]-face['station_ft'][0])


def offset(face,xy,factor):
    a,b=face['cutline_xy'][0],face['cutline_xy'][-1];dx,dy=b[0]-a[0],b[1]-a[1]
    return abs(dx*(xy[1]-a[1])-dy*(xy[0]-a[0]))/math.hypot(dx,dy)*factor


def chainage(line,point):
    """Nearest projection onto a polyline, in its coordinate units."""
    best=None;total=0.
    for a,b in zip(line,line[1:]):
        v=[b[k]-a[k] for k in (0,1)];length=math.hypot(*v)
        if not length:continue
        t=max(0.,min(1.,sum((point[k]-a[k])*v[k] for k in (0,1))/length**2))
        distance=math.dist(point,[a[k]+t*v[k] for k in (0,1)])
        if best is None or distance<best[0]:best=(distance,total+t*length)
        total+=length
    return best[1] if best else None


def surveys(m,g):
    from .app_acquisition import snapshot
    from pyproj import Transformer
    result=[]
    for s in snapshot(m).get('surveys',[]):
        context=s.get('context')
        if not context or not intact([s['source']]):continue
        try:
            t=Transformer.from_crs(context['horizontal_crs'],g['horizontal_crs'],always_xy=True)
            points=[dict(p,xy=list(t.transform(p['x'],p['y']))) for p in s['points']]
            if not all(all(finite(v) for v in p['xy']) for p in points):continue
            result.append(dict(source=s['source'],context=context,points=points,context_hash=digest(context)))
        except (ValueError,KeyError,CRSError):continue
    return result


def association_suggestions(m,g,ss):
    """Recognized codes + operator flow direction, never ID-specific pairing.

    Two equally populated mouth clusters are paired in transverse order.
    LC only supports one 1/2-point lintel per face. Ambiguity is left editable.
    Codes identify candidates, not the meaning of an interior surface.
    """
    us,ds=faces(g);picks=m.get('map_picks',{})
    a=us.get('center_xy') if us else (picks.get('upstream') or [None])[-1]
    b=ds.get('center_xy') if ds else (picks.get('downstream') or [None])[0]
    if not a or not b or math.dist(a,b)==0:return [],['FLOW_DIRECTION_REQUIRED']
    dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy);axis=[dx/length,dy/length]
    groups=g['structure']['groups'];result=[];notes=[];next_group=len(groups)
    available={shape:[i for i,v in enumerate(groups) if v.get('shape')==shape and v.get('count',1)==1] for shape in ('box','circular')}
    if len(ss)!=1:return [],['CHOOSE_SURVEY_SOURCE'] if ss else ['SURVEY_CONTEXT_REQUIRED']
    s=ss[0]
    def along(p):return sum((p['xy'][i]-a[i])*axis[i] for i in (0,1))
    def across(p):return (p['xy'][0]-a[0])*axis[1]-(p['xy'][1]-a[1])*axis[0]
    for code,shape in [('LC','box'),('CROWN','circular')]:
        pp=[p for p in s['points'] if re.sub(r'[^A-Z]','',p.get('code','').upper())==code]
        if not pp:continue
        ordered=sorted(pp,key=along);n=len(pp)//2
        if len(pp)%2 or not n or (shape=='box' and n>2):notes.append('AMBIGUOUS_'+code+'_POINTS');continue
        left,right=ordered[:n],ordered[n:]
        gap=along(right[0])-along(left[-1]);spread=max(along(left[-1])-along(left[0]),along(right[-1])-along(right[0]))
        if gap<=max(spread,0):notes.append('AMBIGUOUS_'+code+'_MOUTHS');continue
        pairs=[(left,right)] if shape=='box' else [( [u],[v]) for u,v in zip(sorted(left,key=across),sorted(right,key=across))]
        for j,(u,v) in enumerate(pairs):
            if j<len(available[shape]):index=available[shape][j]
            elif shape=='box' and len(groups)==1 and not groups[0].get('shape'):index=0
            else:index=next_group;next_group+=1
            result.append(dict(group=index,barrel=0,shape=shape,source=s['source']['sha256'],us=[p['id'] for p in u],ds=[p['id'] for p in v],
                interpretation='location',suggested_interpretation='interior_crown',context_hash=s['context_hash'],basis='Code '+code+'; split along selected flow direction and paired in transverse order. Confirm same barrel and point semantics.'))
    return result,notes


def resolve(m,g,associations=None):
    """Validate saved point associations against current files and CRS context."""
    ss=surveys(m,g);by_hash={s['source']['sha256']:s for s in ss};resolved=[];errors=[];seen=set();used=set()
    for r in associations if associations is not None else m.get('opening_mapping',[]):
        try:
            i,j=r['group'],r.get('barrel',0)
            if type(i)!=int or type(j)!=int or not 0<=i<10 or not 0<=j<25 or (i,j) in seen:raise ValueError('Unknown/duplicate group or barrel')
            seen.add((i,j));s=by_hash.get(r['source'])
            if not s or r.get('context_hash')!=s['context_hash']:raise ValueError('Survey source/coordinate interpretation changed; review associations again')
            meaning=r.get('interpretation','location')
            if meaning not in ('location','invert','interior_crown'):raise ValueError('Unknown survey interpretation')
            ends=[]
            for side in ('us','ds'):
                ids=r.get(side,[])
                if not isinstance(ids,list) or not 1<=len(ids)<=8 or len(set(ids))!=len(ids):raise ValueError('Choose 1–8 unique point IDs per mouth')
                points=[]
                for pid in ids:
                    matches=[p for p in s['points'] if p['id']==str(pid)]
                    if len(matches)!=1:raise ValueError('Missing or duplicate survey ID: '+str(pid))
                    key=(r['source'],str(pid))
                    if key in used:raise ValueError('A survey point cannot define two different mouths: '+str(pid))
                    used.add(key);points+=matches
                factor={'m':1/.3048,'US survey foot':(1200/3937)/.3048,'international foot':1}[s['context']['vertical_unit']]
                ends.append(dict(xy=[sum(p['xy'][k] for p in points)/len(points) for k in (0,1)],z=sum(p['z'] for p in points)/len(points)*factor,points=points))
            resolved.append(dict(**r,ends=ends,survey=s))
        except (ValueError,KeyError,TypeError) as e:errors.append(dict(group=r.get('group'),message=str(e)))
    return resolved,errors


def derived(m,g):
    """One entry per group; nonidentical members are not averaged together."""
    from .app_parameters import proposal
    mapped,errors=resolve(m,g);us,ds=faces(g);out={}
    try:factor=linear_factor(g) if g.get('horizontal_crs') else None
    except (ValueError,CRSError):factor=None
    grouped=defaultdict(list)
    for r in mapped:grouped[r['group']].append(r)
    def add(key,val,basis,zh,cls,records):
        choice=proposal(val,basis,zh,cls)
        choice.update(automation=True,dependencies=digest(dict(mapping=m.get('opening_mapping'),geometry=g)),
            sources=[r['survey']['source'] for r in records],identified_points=[dict(group=r['group'],barrel=r['barrel'],us=r['us'],ds=r['ds'],interpretation=r['interpretation']) for r in records])
        out.setdefault(key,[]).append(choice)
    for i,rs in grouped.items():
        if i>=len(g['structure']['groups']):continue
        group=g['structure']['groups'][i];count=group.get('count');pre=f'g.structure.groups.{i}.';rs.sort(key=lambda r:r['barrel'])
        if type(count)!=int or [r['barrel'] for r in rs]!=list(range(count)):continue
        from pyproj import CRS
        lengths=[]
        for r in rs:
            unit=CRS.from_user_input(r['survey']['context']['horizontal_crs']).axis_info[0].unit_conversion_factor/.3048
            xy=[[sum(p[k] for p in e['points'])/len(e['points']) for k in ('x','y')] for e in r['ends']]
            lengths.append(math.dist(*xy)*unit)
        # Shared geometry is only proposed when member values agree at displayed precision.
        if lengths and max(lengths)-min(lengths)<.001:
            add(pre+'length_ft',round(lengths[0],6),'Straight plan distance between associated inlet/outlet points; not surveyed barrel length.','已关联进出口测点的平面直线距离；并非涵身实测长度。','inferred',rs)
        if us and ds and factor:
            centers=[[round(station(f,e['xy']),6) for f,e in zip((us,ds),r['ends'])] for r in rs]
            add(pre+'centers_ft',centers,'Orthogonal projection of associated mouth centers onto each selected face station axis. Inspect skew and spacing before adoption.','将各洞口中心正交投影到对应外侧断面的站距轴；采用前检查斜交及孔间距。','derived',rs)
            distances=[offset(us,r['ends'][0]['xy'],factor) for r in rs]
            if max(distances)-min(distances)<.001:
                add(pre+'distance_us_ft',round(distances[0],6),'Perpendicular distance from inlet to upstream face line; conditional approach-length proxy, not barrel-axis distance.','进口至上游断面线的垂距，作为条件性接近段长度；不等于沿涵轴的距离。','inferred',rs)
        for side,k in [('us',0),('ds',1)]:
            values=[];classes=[];formulas=[]
            for r in rs:
                if r['survey']['context']['vertical_datum']!=g.get('vertical_datum'):break
                z=r['ends'][k]['z'];meaning=r['interpretation'];height=group.get('rise_ft')
                if meaning=='invert':val=z;cls='reported';formula='mean(identified interior invert elevations), units converted to international ft'
                elif meaning=='interior_crown' and finite(height) and height>0:
                    val=z-height;cls='assumed';formula='mean(identified interior crown/low-chord elevations in international ft) − entered clear height. Assumes the point is interior and height applies at this mouth; exterior crown, wall thickness and sediment can invalidate this'
                else:break
                values.append(val);classes.append(cls);formulas.append(formula)
            if len(values)==count and max(values)-min(values)<.001:
                cls='assumed' if 'assumed' in classes else 'reported'
                add(pre+side+'_invert_ft',round(values[0],6),formulas[0]+'; datum '+g['vertical_datum'],
                    ('已指认为内涵底测点的平均值，换算国际英尺。' if cls=='reported' else '假设测点为内顶／低梁底：测点平均高程换算国际英尺后减去净高；外顶、壁厚、淤积可能使推导失效。')+' 基准：'+g['vertical_datum'],cls,rs)
    if factor and us and ds:
        for i,b in enumerate(g['structure']['groups']):
            if grouped.get(i):continue
            picks=m.get('group_map_picks',{}).get(str(i),{})
            u,v=picks.get('inlet',[]),picks.get('outlet',[])
            if len(u)!=1 or len(v)!=1:continue
            pre=f'g.structure.groups.{i}.';n=b.get('count');width=b.get('span_ft');gap=m.get('wall_gap_ft')
            add(pre+'length_ft',round(math.dist(u[0],v[0])*factor,6),'Straight plan distance between user-selected mouth centers; assumes a straight barrel.','按用户点选进出口中心的平面直线距离，假定涵身顺直。','inferred',[])
            add(pre+'distance_us_ft',round(offset(us,u[0],factor),6),'Perpendicular inlet-to-face distance from selected map points; conditional approach-length proxy.','点选进口至上游断面线的垂距，条件性接近段长度。','inferred',[])
            if type(n)==int and 1<=n<=25 and (n==1 or finite(width) and finite(gap) and gap>=0):
                centers=[station(f,p[0]) for f,p in zip((us,ds),(u,v))]
                offsets=[0.] if n==1 else [(j-(n-1)/2)*(width+gap) for j in range(n)]
                add(pre+'centers_ft',[[round(c+shift,6) for c in centers] for shift in offsets],
                    'Projected user-selected group centers; multiple members assume equal parallel spacing using the entered clear gap.','将点选组中心投影到断面；同组多孔假定平行等距，使用已填孔间净距。','inferred',[])
    if us and factor:
        for s in surveys(m,g):
            road=[p for p in s['points'] if p.get('code','').strip().upper() in ('RDCL','ROAD_CREST','CREST')]
            if len(road)<2 or s['context']['vertical_datum']!=g.get('vertical_datum'):continue
            road.sort(key=lambda p:station(us,p['xy']))
            a=[round(station(us,p['xy']),6) for p in road]
            if any(y-x<=.001 for x,y in zip(a,a[1:])):continue
            zfactor={'m':1/.3048,'US survey foot':(1200/3937)/.3048,'international foot':1}[s['context']['vertical_unit']]
            for name,value in [('station_ft',a),('elevation_ft',[round(p['z']*zfactor,6) for p in road]),('distance_us_ft',round(offset(us,road[len(road)//2]['xy'],factor),6))]:
                choice=proposal(value,'Survey RDCL/CREST points projected onto the upstream face. Assumes these points describe the overtopping crest with adequate lateral coverage; road centerline is not necessarily the crest.',
                    '将 RDCL／CREST 测点投影到上游站距轴；假定这些点描述越流高点且横向覆盖充分。路中线未必是堰顶。','inferred')
                choice.update(automation=True,sources=[s['source']],identified_points=[p['id'] for p in road],datum=g['vertical_datum'])
                out.setdefault('g.structure.road.'+name,[]).append(choice)
            choice=proposal('shared','Assume this identified road crest profile represents both faces. Use distinct profiles when their station origins/elevations differ.',
                '假定已辨认的路顶剖面适用于两侧；站距基点或高程不同时使用独立剖面。','assumed')
            choice.update(automation=True,sources=[s['source']])
            out.setdefault('g.structure.road.profile_mode',[]).append(choice)
    # Curved channel distance follows the saved flowline. Overbanks remain a
    # clearly labelled equal-length assumption until their own paths are known.
    if factor:
        lines={r['id']:r['xy'] for r in g.get('flowlines',[]) if len(r.get('xy',[]))>1}
        for i,(a,b) in enumerate(zip(g['cross_sections'],g['cross_sections'][1:])):
            line=lines.get(a.get('reach_id'))
            if line is None or a.get('reach_id')!=b.get('reach_id') or not a.get('center_xy') or not b.get('center_xy'):continue
            ca,cb=chainage(line,a['center_xy']),chainage(line,b['center_xy'])
            if ca is None or cb is None:continue
            length=abs(ca-cb)*factor
            if length>0:add(f'g.cross_sections.{i}.reach_lengths_ft',[round(length,3)]*3,
                'Channel length along the saved flowline between section centers; both overbanks temporarily assumed equal. Review floodplain flow paths.',
                '沿已保存流线计算断面间主槽长度；暂假定左右滩地相同，需核对漫滩过流路径。','assumed',[])
    for key,choices in out.items():
        for ch in choices:ch['automation_context']=dependency(m,g,key)
    return out


def preflight(m,g,include_suggestions=True):
    """Early checks work with partial inputs. No full input form is required."""
    from .geometry_qa import spatial_issues
    rows=g.get('cross_sections',[]);us,ds=faces(g);issues=[dict(q,blocking=True,message=q['code'],zh='断面线相交或无效') for q in spatial_issues(rows)]
    mapped,errors=resolve(m,g)
    for e in errors:issues.append(dict(code='STALE_OPENING_MAPPING',sections=[],groups=[e['group']],blocking=True,message=e['message'],zh='洞口测点关联已变化，请重新核对'))
    tentative=False
    if not mapped and not m.get('opening_mapping') and include_suggestions:
        suggestions,_=association_suggestions(m,g,surveys(m,g));mapped,_=resolve(m,g,suggestions);tentative=bool(mapped)
    groups=g.get('structure',{}).get('groups',[]);by_group=defaultdict(list)
    for r in mapped:by_group[r['group']].append(r)
    positions=[]
    for i,b in enumerate(groups):
        centers=b.get('centers_ft');association=by_group[i]
        if us and ds and association:
            proposed=[[station(f,e['xy']) for f,e in zip((us,ds),r['ends'])] for r in association]
        else:
            proposed=None;picks=m.get('group_map_picks',{}).get(str(i),{})
            if us and ds and len(picks.get('inlet',[]))==len(picks.get('outlet',[]))==1:
                n=b.get('count');width=b.get('span_ft');gap=m.get('wall_gap_ft')
                if type(n)==int and (n==1 or finite(width) and finite(gap) and gap>=0):
                    centers=[station(f,picks[k][0]) for f,k in zip((us,ds),('inlet','outlet'))]
                    shifts=[0.] if n==1 else [(j-(n-1)/2)*(width+gap) for j in range(n)]
                    proposed=[[c+shift for c in centers] for shift in shifts]
        # Inspect saved model centers AND anticipated projections before adopting them.
        for origin,values in [('saved',centers),('proposed',proposed)]:
            if not values or not finite(b.get('span_ft')):continue
            for j,pair in enumerate(values):
                if not isinstance(pair,list) or len(pair)!=2 or not all(finite(v) for v in pair):continue
                positions.append((i,j,b['span_ft'],pair,origin))
        if finite(b.get('us_invert_ft')) and finite(b.get('ds_invert_ft')) and b['ds_invert_ft']>b['us_invert_ft']:
            issues.append(dict(code='ADVERSE_INVERT',sections=[],groups=[i],blocking=False,message=f'Group {i+1}: outlet invert is higher by {b["ds_invert_ft"]-b["us_invert_ft"]:.3f} ft. Verify source/flow direction; do not flatten automatically.',zh=f'组 {i+1} 出口涵底高于进口；核对资料与流向，不自动改平。'))
        if us and finite(b.get('distance_us_ft')) and finite(b.get('length_ft')):
            reach=(us.get('reach_lengths_ft') or [None,None,None])[1]
            if finite(reach) and b['distance_us_ft']+b['length_ft']>=reach:
                issues.append(dict(code='BARREL_OUTSIDE_REACH',sections=[rows.index(us)],groups=[i],blocking=True,message=f'Group {i+1}: approach + barrel length reaches/passes the downstream section. Check face placement and flow-path length.',zh=f'组 {i+1} 接近段加涵长已达或超过下游断面；检查功能断面与流程长度。'))
    for origin in ('saved','proposed'):
        for k,face in enumerate((us,ds)):
            if not face:continue
            pp=sorted([p for p in positions if p[4]==origin],key=lambda p:p[3][k]);index=rows.index(face)
            for p in pp:
                if p[3][k]-p[2]/2<face['station_ft'][0] or p[3][k]+p[2]/2>face['station_ft'][-1]:
                    issues.append(dict(code='OPENING_OUTSIDE_SECTION',sections=[index],groups=[p[0]],blocking=origin=='saved' or not tentative,message=f'Group {p[0]+1}: opening outside RS {face["rs"]} ({origin}).',zh=f'组 {p[0]+1} 涵孔超出断面范围。'))
            for a,b in zip(pp,pp[1:]):
                gap=b[3][k]-a[3][k]-(a[2]+b[2])/2
                if gap<-.001:
                    issues.append(dict(code='PROJECTED_OPENINGS_OVERLAP',sections=[index],groups=[a[0],b[0]],blocking=origin=='saved' or not tentative,
                        gap_ft=round(gap,6),origin=origin,tentative=tentative,
                        message=f'RS {face["rs"]}: groups {a[0]+1}/{b[0]+1} overlap by {-gap:.3f} ft ({origin}). Check associations, section direction and flow path.',zh=f'RS {face["rs"]}：组 {a[0]+1}/{b[0]+1} 投影重叠 {-gap:.3f} ft；核对测点配对、断面方向和过流路径。'))
    for i,r in enumerate(rows):
        if not r.get('elevation_ft') or any(not finite(v) for v in r['elevation_ft']):
            issues.append(dict(code='SECTION_NODATA',sections=[i],groups=[],blocking=True,message=f'RS {r.get("rs")}: missing DEM elevations.',zh=f'RS {r.get("rs")} 存在缺失高程。'))
    if m.get('session'):
        from .app_parameters import objects
        d=objects(m)[2]
        for key,a in d.get('answers',{}).items():
            record=a.get('candidate_record') or {}
            if record.get('automation_context') and record['automation_context']!=dependency(m,g,key):
                issues.append(dict(code='DERIVED_INPUT_CHANGED',field=key,sections=[],groups=[],blocking=True,message='Dependencies changed: '+key+'. Recompute or explicitly edit this input.',zh='推导依据已变化：'+key+'；请重新采用候选或明确修改。'))
    return dict(issues=issues,blocking_count=sum(bool(q['blocking']) for q in issues),tentative_associations=tentative,
        scope='Geometry screening, not hydraulic acceptance; unresolved source semantics remain for user judgment.')


def view(m,g):
    ss=surveys(m,g);suggested,notes=association_suggestions(m,g,ss)
    checks=preflight(m,g)
    return dict(mapping=m.get('opening_mapping',[]),suggested=suggested,notes=notes,checks=checks,
        surveys=[dict(source=s['source'],context=s['context'],context_hash=s['context_hash'],points=s['points']) for s in ss],
        groups=[dict(index=i,**r) for i,r in enumerate(g['structure']['groups'])])


def perform(key,body):
    from . import app_core as core,intake
    from .app_parameters import objects
    m=core.model(key);core.require_idle(m)
    if body.get('revision')!=m['revision']:raise ValueError('Inputs changed; reload / 参数已变化，请刷新')
    sp,p,d,c,g=objects(m);records=body.get('mapping')
    if not isinstance(records,list) or len(records)>100:raise ValueError('At most 100 opening associations')
    canonical=[]
    for r in records:
        canonical.append({k:r[k] for k in ('group','barrel','source','us','ds','interpretation','context_hash','shape') if k in r})
    resolved,errors=resolve(m,g,canonical)
    if errors:raise ValueError('; '.join(e['message'] for e in errors))
    groups=copy.deepcopy(g['structure']['groups'])
    if canonical and max(r['group'] for r in canonical)>=len(groups):
        if body.get('create_groups') is not True:raise ValueError('Confirm creating the displayed additional groups')
        for i in range(len(groups),max(r['group'] for r in canonical)+1):
            rr=[r for r in canonical if r['group']==i]
            if not rr or len({r.get('shape') for r in rr})!=1 or rr[0].get('shape') not in ('box','circular'):raise ValueError('New groups need an explicit shape')
            groups.append(dict(shape=rr[0]['shape'],count=len(rr)))
    for i in {r['group'] for r in canonical}:
        rr=sorted(r.get('barrel',0) for r in canonical if r['group']==i)
        count=groups[i].get('count')
        if count is None:
            if body.get('create_groups') is not True:raise ValueError('Confirm the displayed barrel count')
            groups[i]['count']=len(rr);groups[i]['shape']=next(r.get('shape') for r in canonical if r['group']==i)
        if rr!=list(range(groups[i]['count'])):raise ValueError('Associate every member of the selected group, or split differing barrels into groups')
    with lock(sp.parent/'session.lock'):
        if read(sp.parent/'draft.json')['revision']!=d['revision']:raise ValueError('Draft changed')
        # Only add explicitly confirmed groups. Existing parameters/banks remain intact.
        old=copy.deepcopy(d);g['structure']['groups']=groups;d['geometry']=g;d['revision']+=1;d['consent']=False
        save(sp.parent/'events'/('opening_association_'+unique_id()+'.json'),dict(before=old,mapping=canonical,created_utc=utc()))
        save(sp.parent/'draft.json',d)
    m['opening_mapping']=canonical;m['revision']+=1;core.persist(m,'ASSOCIATE_OPENINGS',dict(mapping=canonical))
    return core.view(key)
