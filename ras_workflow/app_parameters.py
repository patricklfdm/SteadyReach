"""Editable, evidence-labelled proposals and a content-bound pre-solver checkpoint.

Nothing in this module runs HEC-RAS. A proposal is never a site measurement.
"""
import copy
import math
from pathlib import Path
from .common import ROOT, digest, finite, intact, item, lock, read, rel, save, unique_id, utc
from . import intake

BASE = 'https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/6.5/'
ENTRANCE = BASE+'modeling-culverts/culvert-data-and-coefficients/entrance-loss-coefficient'
EXIT = 'https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/6.0/modeling-culverts/culvert-data-and-coefficients/exit-loss-coefficient'
LOSSES = BASE+'basic-data-requirements/geometric-data/energy-loss-coefficients'
CHART = BASE+'modeling-culverts/culvert-data-and-coefficients/fhwa-chart-and-scale-numbers'

def objects(m):
    sp=ROOT/m['session'];_,_,p,d=intake._load(sp,active=False)
    c,g=intake._objects(p,d)
    return sp,p,d,c,g

def proposal(value,basis,zh,classification='assumed',url=None,range_=None):
    r=dict(value=value,evidence_class=classification,basis=basis,condition=dict(en=basis,zh=zh))
    if url:r['url']=url
    if range_ is not None:r['range']=range_
    return r

def proposals(m,c,g):
    """Recompute against the current geometry, never reuse a stale candidate."""
    out={}
    def add(key,value,en,zh,cls='assumed',url=None,range_=None):
        out.setdefault(key,[]).append(proposal(value,en,zh,cls,url,range_))
    add('g.river','River','Editable model identifier; no hydraulic significance.','可修改的模型名称，不代表实测资料。','model_setting')
    add('g.reach','Reach','Editable model identifier; no hydraulic significance.','可修改的模型名称，不代表实测资料。','model_setting')
    # A regime is a user decision, not an automatic inference from bed slope.
    add('g.flow_regime','mixed','Conditional mixed-flow analysis; requires boundaries at both ends.','条件性混合流计算；需要上下游边界。')
    add('g.flow_regime','subcritical','Use only if subcritical flow is applicable throughout the model.','仅在全河段适用缓流分析时采用。')
    for i,s in enumerate(c.get('scenarios',[])):
        if s['id']!=m['scenario']:continue
        add(f'c.scenarios.{i}.channel_n',.030,'Clean, straight minor natural stream without deep pools/rifts. Select only if photographs and channel conditions support this description.','顺直洁净小河槽、无深潭或明显急滩；仅在照片和河槽条件相符时采用。',url=LOSSES,range_=[.025,.033])
        add(f'c.scenarios.{i}.overbank_n',.050,'Floodplain with scattered brush and heavy weeds; vegetation and flow depth affect roughness.','漫滩有零散灌木和茂密杂草；糙率受植被及水深影响。',url=LOSSES,range_=[.035,.070])
    if g.get('model_type')=='river':
        add('g.channel_geometry_basis','conditional_surface_dem','Conditional surface DEM only; submerged bed is unmeasured. This is an explicit approximation requiring survey before engineering acceptance.','仅用地表 DEM 的条件性近似，水下河床未实测；工程接受前需补测。')
        for side in ['upstream','downstream']:
            add('g.boundaries.'+side+'.type','normal_depth','Conditional normal-depth boundary; review bridge backwater and sensitivity.','条件性正常水深边界；核对桥梁壅水影响并检查敏感性。')
    add('g.structure.road.weir_coefficient',3.,'US customary weir coefficient for flow over elevated roadway approaches. Check crest form and submergence; not a low lateral-weir default.','美制单位、抬高道路路堤的堰流系数；核对堰顶形状与淹没，不适合作为低侧堰默认。',url=BASE+'modeling-culverts/culvert-data-and-coefficients/weir-flow-coefficient')
    for i,b in enumerate(g['structure']['groups']):
        pre=f'g.structure.groups.{i}.'
        add(pre+'depth_blocked_ft',0.,'Assume no sediment blockage. Check site photos/inspection; zero is not evidence of a clear barrel.','假设无淤堵；须查看照片或检查资料，0 不代表已证实畅通。')
        add(pre+'exit_loss',1.,'Sudden expansion at a typical culvert exit.','适用于典型涵洞出口突扩。',url=EXIT)
        if b.get('shape')=='box':
            add(pre+'entrance_loss',.5,'Square-edged headwall without wingwalls, or 10–25 degree wingwalls; verify the actual inlet.','直角入口、无翼墙端墙或 10–25° 翼墙；请核对实际构造。',url=ENTRANCE,range_=[.2,.7])
            add(pre+'entrance_loss',.4,'Square crown with 30–75 degree wingwalls. The range covers different constructions, not measurement uncertainty.','顶缘直角、翼墙 30–75°；参考范围对应不同构造，不是测量误差。',url=ENTRANCE,range_=[.2,.7])
            add(pre+'chart_scale',[8,1],'Box inlet with wingwalls flared 30–75 degrees; confirm from drawings/photos.','箱涵翼墙 30–75°；按图纸或照片确认。',url=CHART)
            add(pre+'chart_scale',[8,2],'Box inlet with wingwalls flared 90 or 15 degrees; confirm the actual inlet.','箱涵翼墙 90° 或 15°；核对实际入口。',url=CHART)
        elif b.get('shape')=='circular':
            add(pre+'chart_scale',[1,1],'Concrete circular pipe with square-edged headwall.','混凝土圆管、直角端墙入口。',url=CHART)
            if finite(b.get('span_ft')):add(pre+'rise_ft',b['span_ft'],'Circular diameter equals the entered width.','圆管直径等于已填写净宽。','derived')
    xs=g['cross_sections'];factor=None
    if g.get('horizontal_crs'):
        from pyproj import CRS
        from pyproj.exceptions import CRSError
        try:
            crs=CRS.from_user_input(g['horizontal_crs'])
            if crs.is_projected:factor=crs.axis_info[0].unit_conversion_factor/.3048
        except (ValueError,TypeError,CRSError):pass  # Invalid edits remain editable; the input gate reports them.
    dist=lambda a,b:math.dist(a,b)*factor
    transitions=[i for i in range(len(xs)-1) if xs[i].get('reach_id')=='upstream' and xs[i+1].get('reach_id')=='downstream']
    if len(transitions)==1 and transitions[0]>=1 and transitions[0]+2<len(xs):
        i=transitions[0];u,v=xs[i],xs[i+1]
        for name,val in [('us_xs_rs',u['rs']),('ds_xs_rs',v['rs']),('rs',(u['rs']+v['rs'])/2)]:
            add('g.structure.'+name,val,'Identifiers bracketing the two exterior reaches; verify functional face locations.','按两个外部河段自动匹配河站号；须确认功能断面位置。','derived')
    faces=[next((x for x in xs if x.get('rs') is not None and x.get('rs')==g['structure'].get(k)),None) for k in ('us_xs_rs','ds_xs_rs')]
    if factor and all(faces):
        picks=m.get('map_picks',{});inlet=picks.get('inlet',[]);outlet=picks.get('outlet',[])
        if len(inlet)==len(outlet)==1 and len(g['structure']['groups'])==1:
            b=g['structure']['groups'][0];pre='g.structure.groups.0.'
            length=dist(inlet[0],outlet[0]);up=dist(faces[0]['center_xy'],inlet[0])
            if length>0 and up>0:
                add(pre+'length_ft',round(length,3),'Plan distance between explicitly picked inlet/outlet group centers; assumes a straight barrel. Not surveyed or inferred from road width.','已点选进出口组中心的平面距离，假定顺直涵洞；非实测，也非由路宽代替。','inferred')
                add(pre+'distance_us_ft',round(up,3),'Plan distance from the selected upstream face center to the picked inlet; verify flow alignment.','上游外侧断面中心至已点选进口的平面距离；核对流向。','inferred')
            for side,face,pin,reach in [('us',faces[0],inlet[0],'upstream'),('ds',faces[1],outlet[0],'downstream')]:
                others=[r for r in xs if r is not face and r.get('reach_id')==reach and r.get('center_xy') and r.get('terrain_sampling')]
                if not others or not face.get('terrain_sampling'):continue
                other=min(others,key=lambda r:dist(r['center_xy'],face['center_xy']))
                def channel_bed(r):
                    banks=r.get('bank_stations_ft');a=r.get('station_ft',[]);z=r.get('elevation_ft',[])
                    vals=[v for t,v in zip(a,z) if banks and len(banks)==2 and finite(v) and banks[0]<=t<=banks[1]]
                    return min(vals) if vals else None
                near,far=channel_bed(face),channel_bed(other)
                if near is None or far is None:continue
                a=other['center_xy'];bxy=face['center_xy'];dx,dy=bxy[0]-a[0],bxy[1]-a[1];den=dx*dx+dy*dy
                if den<=0:continue
                t=((pin[0]-a[0])*dx+(pin[1]-a[1])*dy)/den
                # Avoid long extrapolation and arbitrary bounding percentages.
                if not 0<=t<=2:continue
                estimate=round(far+t*(near-far),3)
                add(pre+side+'_invert_ft',estimate,'CONDITIONAL INVERT: extrapolate bed lows within the selected banks of the two nearest exterior DEM sections to the picked mouth, assuming bed and invert connect. Sediment, a drop or burial can invalidate this. The interval is between the near bed and extrapolated bed, NOT bounds on the true invert. Datum: '+g['vertical_datum'],
                    '条件性涵底：将最近两条外部 DEM 断面已选岸站内的低点外推至已点选洞口，假定河床与涵底连续。淤积、跌坎或掩埋可使该假设失效。区间仅为近端河床与外推河床之间，不是真实涵底的上下界。基准：'+g['vertical_datum'],
                    'inferred',range_=sorted([round(near,3),estimate]))
            n=b.get('count');width=b.get('span_ft');gap=m.get('wall_gap_ft')
            if type(n)==int and 1<=n<=25 and finite(width) and width>0 and finite(gap) and gap>=0:
                centers=[]
                for face,pin in zip(faces,[inlet[0],outlet[0]]):
                    a,z=face['cutline_xy'][0],face['cutline_xy'][-1];dx,dy=z[0]-a[0],z[1]-a[1];den=dx*dx+dy*dy
                    fraction=((pin[0]-a[0])*dx+(pin[1]-a[1])*dy)/den
                    center=face['station_ft'][0]+fraction*(face['station_ft'][-1]-face['station_ft'][0])
                    centers.append([round(center+(j-(n-1)/2)*(width+gap),3) for j in range(n)])
                add(pre+'centers_ft',[list(p) for p in zip(*centers)],'Equal parallel openings centered on the picked group centers; uses the entered wall/gap spacing. Modify each barrel if unequal or skewed.','等距平行涵孔，按组中心及已输入墙厚/孔间距布置；不等距或斜交时逐孔修改。')
        sampled=m.get('road_sample')
        if sampled and intact([sampled]):
            road=read(ROOT/sampled['path'])
            if road['context']==road_context(m,g):
                for k in ('station_ft','elevation_ft','distance_us_ft'):
                    add('g.structure.road.'+k,road[k],'DEM samples along the explicitly drawn road-crest line, aligned to the upstream face station axis; check crest coverage and DEM resolution.','沿明确点选的路面高点线采样，并投影至上游断面站距；须检查高点覆盖和 DEM 分辨率。','terrain_derived')
                add('g.structure.road.profile_mode','shared','Assume the drawn crest profile represents both faces; use distinct profiles if they differ.','假定同一条高点线代表两侧；进出口路面不同时改用独立剖面。')
    for i,row in enumerate(xs):
        pre=f'g.cross_sections.{i}.'
        if factor and row.get('center_xy') and (i==len(xs)-1 or xs[i+1].get('center_xy')):
            length=0. if i==len(xs)-1 else round(dist(row['center_xy'],xs[i+1]['center_xy']),3)
            add(pre+'reach_lengths_ft',[length]*3,'Straight center-to-center distance, assumed equal for channel and both overbanks; revise for curved/unequal flow paths.','断面中心直线距离，暂假定左滩/主槽/右滩相同；弯曲或不等长流路请修改。')
        banks=(row.get('bank_candidates') or {}).get('selected_indices')
        if banks and row.get('station_ft') and all(type(j)==int and 0<=j<len(row['station_ft']) for j in banks):
            method=row['bank_candidates']
            add(pre+'bank_stations_ft',[row['station_ft'][j] for j in banks],
                method.get('basis','Terrain break/shape bank candidate; inspect profile and uncertainty flags.'),
                method.get('basis_zh','根据地形坡折及形态生成岸站候选；请查看断面和不确定标记。'),
                'assumed' if method.get('evidence_class')=='assumed' else 'terrain_derived')
            out[pre+'bank_stations_ft'][-1]['bank_method']=method
        add(pre+'expansion_contraction',[.3,.1],'Expansion then contraction for gradual subcritical transitions; not a universal culvert-face default.','顺序为扩散、收缩；适用于缓流渐变段，不能统一代替涵洞突变段。',url=LOSSES)
        add(pre+'expansion_contraction',[.5,.3],'Expansion then contraction for abrupt subcritical transitions; review applicability to mixed flow.','顺序为扩散、收缩；缓流突变段候选，混合流需判断适用性。',url=LOSSES)
    # Bed-slope alternatives use exterior section center elevations and spacing.
    for reach,rows in [('upstream',(xs[:3] if g.get('model_type')=='river' else [x for x in xs if x.get('reach_id')=='upstream'][:3])),('downstream',(xs[-3:] if g.get('model_type')=='river' else [x for x in xs if x.get('reach_id')=='downstream'][-3:]))]:
        if factor and len(rows)>=2:
            slopes=[]
            def bed(r):
                z=r['elevation_ft'];a=r['station_ft'];b=r.get('bank_stations_ft')
                vals=[v for j,v in enumerate(z) if finite(v) and (not b or b[0]<=a[j]<=b[1])]
                return min(vals) if vals else None
            for a,b in zip(rows,rows[1:]):
                za,zb=bed(a),bed(b);length=dist(a['center_xy'],b['center_xy'])
                if za is not None and zb is not None and length>0:slopes.append((za-zb)/length)
            if slopes and all(v>0 for v in slopes):
                val=round(sum(slopes)/len(slopes),6)
                add('g.boundary_slopes.'+reach,val,'Positive exterior bed slopes as a normal-depth energy-slope proxy; range is the sampled adjacent slopes, not a confidence interval. Check boundary distance and sensitivity.','以外部河段正坡降近似正常水深能坡；范围为相邻段坡降，不是置信区间。须检查边界距离及敏感性。',range_=[round(min(slopes),6),round(max(slopes),6)])
    from .app_automation import derived, dependency
    for key, choices in derived(m,g).items():
        if key.endswith('.reach_lengths_ft') or '.groups.' in key:out[key]=choices
        else:out.setdefault(key,[]).extend(choices)
    from .conditional_estimates import construction_candidates, surface_candidates
    for key, choices in construction_candidates(m,g,c).items():
        # Keep alternative inlet scenarios visible for manual editing.
        out.setdefault(key,[]).extend(choices)
    if xs and m.get('terrain',{}).get('raster') and m.get('metadata',{}).get('dem_vertical_datum')==g.get('vertical_datum'):
        from .terrain_auto import Sampler
        try:
            sampler=Sampler(m['terrain'],m['metadata'].get('dem_vertical_unit'),g['vertical_datum'])
            if sampler.crs.equals(CRS.from_user_input(g['horizontal_crs'])):
                for key,choices in surface_candidates(m,g,sampler).items():
                    sourced=[v for v in out.get(key,[]) if v.get('source_derived')]
                    out[key]=sourced+choices
        except (ValueError,OSError):
            pass  # Other source/manual routes remain available.
    for key,choices in out.items():
        for ch in choices:
            ch['automation_context']=dependency(m,g,key)
            ch['candidate']=digest(dict(field=key,choice=ch))
    return out

def road_context(m,g):
    return digest(dict(picks=m.get('map_picks'),metadata=m['metadata'],crs=g.get('horizontal_crs'),
        faces=[g['structure'].get(k) for k in ('us_xs_rs','ds_xs_rs')],sections=[{k:r.get(k) for k in ('rs','center_xy','cutline_xy','station_ft')} for r in g['cross_sections']],raster=m.get('terrain',{}).get('raster')))

def sample_road(m):
    """Only the operator-selected surface line is sampled; no buried geometry."""
    import numpy as np
    import rasterio
    from pyproj import CRS
    from . import app_core as core, geometry_editor
    from .sensitivity import VERTICAL_FACTORS
    sp,p,d,c,g=objects(m);points=np.asarray(m.get('map_picks',{}).get('road',[]),float)
    if points.ndim!=2 or len(points)<2 or points.shape[1]!=2:raise ValueError('Pick at least two road crest points, left to right looking downstream / 请面向下游从左到右点选路面高点线')
    face=next((r for r in g['cross_sections'] if r['rs']==g['structure'].get('us_xs_rs')),None)
    if face is None:raise ValueError('Select the upstream/downstream face candidates first / 请先采用进出口功能断面候选')
    _,_,_,_,_,_,_,terrain,info=geometry_editor.context(sp)
    crs=CRS.from_user_input(info['crs'])
    if not crs.equals(CRS.from_user_input(g['horizontal_crs'])):raise ValueError('Map and geometry CRS differ')
    unit=m['metadata'].get('dem_vertical_unit');datum=m['metadata'].get('dem_vertical_datum')
    if unit not in VERTICAL_FACTORS or datum!=g['vertical_datum']:raise ValueError('Confirm matching DEM and geometry elevation datums first')
    factor=crs.axis_info[0].unit_conversion_factor/.3048
    distance=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    if not np.isfinite(distance).all() or (np.diff(distance)<=0).any():raise ValueError('Road line contains duplicate/invalid points')
    chain=np.linspace(0,distance[-1],min(499,max(3,math.ceil(distance[-1]*factor/2)+1)))
    xy=np.column_stack([np.interp(chain,distance,points[:,i]) for i in (0,1)])
    a=np.array(face['cutline_xy'][0]);b=np.array(face['cutline_xy'][-1]);v=b-a
    stations=face['station_ft'][0]+((xy-a)@v)/(v@v)*(face['station_ft'][-1]-face['station_ft'][0])
    if (np.diff(stations)<=.001).any():raise ValueError('Draw the road crest from left to right without turning back; revise the selected line / 路面线需面向下游从左向右，不能折返')
    with rasterio.open(ROOT/terrain['raster']['path']) as dem:
        elevations=np.ma.vstack(list(dem.sample(xy,masked=True)))[:,0].astype(float).filled(np.nan)*VERTICAL_FACTORS[unit]
    if not np.isfinite(elevations).all():raise ValueError('Road line contains DEM NoData; adjust it or provide surveyed elevations')
    downstream=next((r for r in g['cross_sections'] if r['rs']==g['structure'].get('ds_xs_rs')),None)
    if downstream is None:raise ValueError('Select the downstream face first')
    along=np.array(downstream['center_xy'])-np.array(face['center_xy']);delta=xy[len(xy)//2]-np.array(face['center_xy'])
    fraction=float(delta@along/(along@along))
    if not 0<fraction<1:raise ValueError('Road crest must lie between the selected face sections / 路面线必须位于进出口外侧断面之间')
    offset=float(abs(v[0]*delta[1]-v[1]*delta[0])/np.linalg.norm(v)*factor)
    result=dict(context=road_context(m,g),station_ft=np.round(stations,3).tolist(),elevation_ft=np.round(elevations,3).tolist(),
        distance_us_ft=round(offset,3),sources=[terrain['raster']],sample_xy=xy.tolist(),unit='international_ft',datum=datum)
    path=core.folder(m['id'])/'map_estimates'/unique_id()/'road.json';save(path,result);m['road_sample']=item(path)

def rows(m, context=None):
    sp,p,d,c,g=context or objects(m);extra=proposals(m,c,g);result=intake.fields(c,g,m['scenario']);intake._suggestions(c,p,result)
    for f in result:
        answer=d['answers'].get(f['key'],{});f['answer']=answer
        missing=f['value'] in (None,'',[])
        cls=answer.get('evidence_class')
        if not cls:
            cls='missing' if missing else 'terrain_derived' if f['key'].startswith('g.cross_sections.') and g.get('flowlines') else 'source_input_unverified'
        f['evidence_class']=cls;f['basis']=answer.get('basis','Original input / generated terrain; verify its applicability.')
        f['missing']=missing
        f['parameter_candidates']=[dict(candidate=digest(s),**s) for s in f['suggestions']]+extra.get(f['key'],[])
    from .app_acquisition import enrich
    result=enrich(m,result)
    for f in result:
        prior=f['answer'].get('candidate_record',{})
        f['derived_update_available']=bool(prior.get('automation_context') and any(v.get('automation_context') and v['value']!=f['value'] for v in f['parameter_candidates']))
    return result

def choose(m,selections,missing_only=False):
    from . import app_core as core
    sp,p,d,c,g=objects(m);available={f['key']:f for f in rows(m)};used=[]
    if not selections:raise ValueError('Choose at least one candidate / 请先选择候选值')
    for selected in selections:
        f=available.get(selected['field']);choice=next((s for s in (f or {}).get('parameter_candidates',[]) if s['candidate']==selected['candidate']),None)
        if choice is None:raise ValueError('Candidate changed; reload before selecting / 候选值已改变，请刷新')
        if missing_only and not f['missing']:continue
        d['answers'][f['key']]=dict(value=choice['value'],evidence_class=choice['evidence_class'],basis=choice['basis'],confirmed=False,candidate_record=choice)
        if any(digest(s)==choice['candidate'] for s in f['suggestions']):d['answers'][f['key']]['suggestion']=choice['candidate']
        used.append(dict(field=f['key'],candidate=choice))
    selected_groups={int(v['field'].split('.')[3]) for v in used if v['field'].startswith('g.structure.groups.') and v['field'].endswith('.centers_ft')}
    if selected_groups:
        from .app_automation import preflight
        candidate_geometry=intake._objects(p,d)[1]
        blocked=[q for q in preflight(m,candidate_geometry)['issues'] if q.get('blocking') and selected_groups.intersection(q.get('groups',[])) and q['code'] in ('PROJECTED_OPENINGS_OVERLAP','OPENING_OUTSIDE_SECTION')]
        if blocked:raise ValueError('Resolve opening projection conflicts before adopting centers / 请先解决涵孔投影冲突，再采用孔位： '+blocked[0]['message'])
    d.update(reviewer=None,basis='Displayed candidate selected for conditional computation; no engineering acceptance.')
    intake.save_draft(sp,d);m['revision']+=1;core.persist(m,'SELECT_CANDIDATES',dict(selected=used))
    return core.view(m['id'])

def reviewed_draft(m):
    """Prepare final bank decisions in memory; final confirmation is the only consent."""
    from .geometry_qa import section_fingerprint
    sp,p,d,c,g=objects(m)
    for row in g['cross_sections']:
        row['terrain_review']=dict(decision='ACCEPT',reviewer=None,policy='local_computation_v1',
            basis='Bank positions and complete parameters presented at final calculation confirmation; not engineering acceptance.',fingerprint=section_fingerprint(row))
    # The geometry is materialized to bind the exact displayed values.
    d['geometry']=g
    d.update(reviewer=None,basis='Complete displayed parameters, estimates and bank positions confirmed for a conditional local calculation; engineering acceptance is not asserted.')
    return sp,d

def binding(m):
    sources=[item(ROOT/m['project'])]+m.get('attachments',[])+m.get('input_choices',[])
    if m.get('road_sample'):sources.append(m['road_sample'])
    if m.get('source_analysis'):sources.append(m['source_analysis'])
    if m.get('terrain',{}).get('raster'):sources.append(m['terrain']['raster'])
    if m.get('native_review'):
        p=read(ROOT/m['native_review']);sources+=[item(ROOT/m['native_review'])]+list(p['files'].values())
        data=dict(native=p)
    else:
        sp,p,d,c,g=objects(m);sources+=[item(sp.parent/'draft.json'),item(sp.parent/'packet.json')]+p['sources']
        if d.get('section_workflow'):sources+=d['section_workflow']['sources']
        sources+=d.get('geometry_edit_sources',[])
        data=dict(configuration=c,geometry=g,answers=d['answers'],map_picks=m.get('map_picks'),survey_settings=m.get('survey_settings'),opening_mapping=m.get('opening_mapping'),group_map_picks=m.get('group_map_picks'))
    if not intact(sources):raise ValueError('Input/source file changed or disappeared. Review its current copy / 输入或来源文件已改变，请重新核对')
    data.update(project_id=m['id'],revision=m['revision'],metadata=m['metadata'],gis=m['gis'],sources=sources)
    return data

def attention(m, fields, automatic=False):
    """Keep unresolved interpretations visible at the single run confirmation."""
    from .app_acquisition import snapshot
    notices = []
    if m.get('model_type')=='river':
        notices.append(dict(code='RIVER_SCOPE',en='Confirm the exact reach ends and bridge influence. Surface DEM does not measure submerged channel geometry. Normal-depth or known-stage values need an applicable basis.',zh='确认河段两端及桥梁影响。地表 DEM 不能实测水下河槽；正常水深或已知水位边界需有适用依据。'))
    if automatic or m.get('automatic_preparation'):
        notices.append(dict(code='AUTOMATIC_GEOMETRY_REVIEW',
            en='Check the crossing, upstream/downstream direction and floodplain coverage on the DEM. Automatic layout and section widening use terrain screening. Hydraulic suitability still requires review.',
            zh='请在 DEM 上核对设施位置、上下游方向及漫滩覆盖。自动布置和断面扩宽采用地形筛查，仍需判断水力适用性。'))
    uncertain = []
    for field in fields:
        method = field.get('answer', {}).get('candidate_record', {}).get('bank_method')
        if method and method.get('confidence') in ('LOW', 'UNRESOLVED'):
            uncertain.append(field)
    if uncertain:
        notices.append(dict(code='UNCERTAIN_BANK_INTERPRETATION',
            en=f'{len(uncertain)} bank pairs have competing, scale-sensitive or continuity-based interpretations. Inspect their profiles and edit the bank positions as needed.',
            zh=f'{len(uncertain)} 组岸站存在候选竞争、尺度敏感或连续性外推。请查看相应剖面并修改不适用的位置。',
            fields=[field['key'] for field in uncertain]))
    documents = snapshot(m).get('documents', [])
    incomplete = [d for d in documents if d.get('status') != 'INSPECTED' or d.get('warnings')]
    if incomplete:
        names = [d['source'].get('original_name', Path(d['source']['path']).name) for d in incomplete]
        notices.append(dict(code='SOURCE_EXTRACTION_LIMITS',
            en='Inspect source files with extraction limits or unverified image text. ' + ', '.join(names),
            zh='下列资料存在提取限制或未经核实的图像文字，请查看原件。' + '、'.join(names)))
    return notices


def review(m):
    from . import app_core as core
    core.require_idle(m)
    automatic_settled=True
    if m.get('automatic_preparation') and not m.get('active_project') and not m.get('native_review'):
        from .app_autoprepare import fill
        automatic_settled=fill(m, owned_only=True)['dependencies_settled']
    data=binding(m)
    if m.get('native_review'):
        errors=core.check(m);fields=[];native=core.native_preview(m)
    else:
        sp,d=reviewed_draft(m);errors=intake.validate(sp,d,require_consent=False,direct_start=True)['errors']
        fields=rows(m);native=None
        from .app_automation import preflight
        for q in preflight(m,data['geometry'])['issues']:
            if q['blocking']:errors.append(dict(code=q['code'],en=q['message'],zh=q['zh']))
    if not automatic_settled:
        errors.append(dict(code='AUTOMATIC_INPUTS_UNSETTLED',en='Automatic values did not settle. Review conflicting dependencies before calculation.',zh='自动推导尚未稳定，请核对关联参数后再计算。'))
    packet=dict(schema_version='parameter_review_1',project_id=m['id'],revision=m['revision'],fingerprint=digest(data),
        inputs=data,fields=fields,native=native,errors=errors,ready=not errors,created_utc=utc(),engineering_acceptance='NOT_ASSESSED',
        attention=[] if native else attention(m, fields))
    path=core.folder(m['id'])/'reviews'/unique_id()/'parameters.json';save(path,packet)
    m['pending_review']=item(path);core.persist(m,'OPEN_FINAL_PARAMETER_REVIEW',dict(review=m['pending_review']))
    return dict(**packet,review_token=m['pending_review']['sha256'],path=rel(path))

def verify(m,token):
    entry=m.get('pending_review')
    if not entry or not intact([entry]) or token!=entry['sha256']:raise ValueError('Open the complete parameter review before confirming / 请先打开完整参数核对页')
    packet=read(ROOT/entry['path'])
    if packet['fingerprint']!=digest(binding(m)):raise ValueError('Parameters changed after review; review them again / 参数已改变，请重新核对确认')
    if not packet['ready']:raise ValueError('Required inputs remain unresolved / 必要输入尚未补齐')
    return packet

def confirm(m,token):
    from . import app_core as core
    packet=verify(m,token)
    # Final bank acceptance changes only the persisted review stamps. Record both hashes.
    if not m.get('native_review'):
        sp,d=reviewed_draft(m)
        with lock(sp.parent/'session.lock'):
            if read(sp.parent/'draft.json')['revision']!=d['revision']:raise ValueError('Draft changed')
            d['revision']+=1;save(sp.parent/'draft.json',d)
    receipt=dict(action='CONFIRM_DISPLAYED_PARAMETERS_AND_RUN',review=m['pending_review'],reviewed_fingerprint=packet['fingerprint'],
        execution_fingerprint=digest(binding(m)),created_utc=utc(),engineering_acceptance='NOT_ASSESSED',identity='LOCAL_USER_ACTION_NO_NAME_REQUIRED')
    path=core.folder(m['id'])/'reviews'/unique_id()/'confirmation.json';save(path,receipt)
    m['run_confirmation']=item(path);core.persist(m,'CONFIRM_PARAMETERS',dict(confirmation=m['run_confirmation']))
    return receipt

def verify_execution(m):
    entry=m.get('run_confirmation')
    if not entry or not intact([entry]):raise ValueError('Explicit parameter confirmation is required before the solver')
    r=read(ROOT/entry['path'])
    if not intact([r['review']]) or r['execution_fingerprint']!=digest(binding(m)):
        raise ValueError('Confirmed inputs changed before execution; confirm the current parameters again')
    return r
