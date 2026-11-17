"""Evidence-bound, resumable input completion. No solver runs inside this module.

Source projects remain immutable. Approval creates a separate conditional project;
only an explicit, validated user decision permits the run entry point to resume.
"""
import copy
import os
from .common import ROOT, digest, finite, intact, item, lock, read, rel, safe_path, save, sha, unique_id, utc
from . import inputs
from .river import is_river, add_fields, boundary_errors

WAITING = 'WAITING_FOR_INPUT'
CLASSES = ['reported', 'user_reported_measurement', 'as_built', 'terrain_derived', 'inferred', 'assumed']
REFERENCE = 'https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/7.0/modeling-culverts/culvert-data-and-coefficients/manning-s-roughness-coefficient'


def control(project):
    path = safe_path(ROOT, project)
    p = path.parent / 'intake_state.json'
    if not p.exists(): return None
    c = read(p)
    if c.get('project') != rel(path): raise ValueError('Intake control belongs to another project')
    session = safe_path(ROOT, c['session'])
    s = read(session)
    if s['project'] != rel(path): raise ValueError('Intake session belongs to another project')
    return s


def resolve(project):
    path = safe_path(ROOT, project)
    seen = set()
    for _ in range(20):
        if rel(path) in seen: raise ValueError('Cyclic intake continuation')
        seen.add(rel(path)); s = control(path)
        if not s or s['status'] != 'APPLIED': return path
        approval = read(safe_path(ROOT, s['approval']['path']))
        if not intact([s['approval']] + approval['files'] + approval['sources']):
            raise ValueError('Approved intake inputs/evidence changed; prepare a new review')
        path = safe_path(ROOT, s['approved_project'])
    raise ValueError('Too many intake continuations')


def _get(obj, parts):
    try:
        for p in parts: obj = obj[int(p)] if isinstance(obj, list) else obj.get(p)
        return obj
    except (TypeError, ValueError, IndexError, AttributeError): return None


def _set(obj, parts, value):
    for p in parts[:-1]:
        if isinstance(obj, list): obj = obj[int(p)]
        else: obj = obj.setdefault(p, {})
    p = parts[-1]
    if isinstance(obj, list): obj[int(p)] = value
    else: obj[p] = value


def blank_geometry(model_type='culvert'):
    # Serialization conventions only; every engineering value starts unknown.
    return dict(schema_version='1.0', model_type=model_type, boundaries={}, hydraulic_unit='international_ft', vertical_datum=None,
                horizontal_crs=None, flow_regime=None, cross_sections=[], boundary_slopes={},
                structure=dict(road={},groups=[]) if model_type=='river' else dict(road=dict(profile_mode=None), groups=[{}]), provenance=[])


def normalize_geometry(g):
    """Accept incomplete drafts, but reject containers that the form cannot edit."""
    if not isinstance(g,dict):raise ValueError('Geometry must be an object')
    g=copy.deepcopy(g)
    for key in ['boundary_slopes','boundaries','structure']:
        if g.get(key) is None:g[key]={}
        if not isinstance(g[key],dict):raise ValueError(key+' must be an object')
    s=g['structure']
    if s.get('road') is None:s['road']={}
    if not isinstance(s['road'],dict):raise ValueError('road must be an object')
    for parent,key,limit in [(g,'cross_sections',500),(s,'groups',10)]:
        if parent.get(key) is None:parent[key]=[]
        if not isinstance(parent[key],list) or len(parent[key])>limit or not all(isinstance(x,dict) for x in parent[key]):
            raise ValueError(key+' must be a list of objects (maximum '+str(limit)+')')
    if g.get('provenance') is None:g['provenance']=[]
    if not isinstance(g['provenance'],list):raise ValueError('provenance must be a list')
    return g


def fields(c, g, scenario):
    result = []
    def add(key, en, cn, kind='number', unit='', options=None, required=True, help_en='', help_cn=''):
        root, *parts = key.split('.')
        value = _get(c if root == 'c' else g, parts)
        result.append(dict(key=key, label=dict(en=en, zh=cn), kind=kind, unit=unit,
                           options=options or [], required=required, value=value,
                           help=dict(en=help_en, zh=help_cn), suggestions=[]))
    for i, s in enumerate(c.get('scenarios', [])):
        if s['id'] != scenario: continue
        for j, p in enumerate(s.get('profiles', [])):
            base=f'c.scenarios.{i}.profiles.{j}'
            add(base+'.flow_cfs',p['id']+' discharge',p['id']+' 设计流量',unit='cfs',
                help_en='Supply the applicable hydrologic report value; terrain alone cannot determine this flood.',
                help_cn='提供适用于本站的水文报告值；仅凭地形不能确定设计洪水。')
            add(base+'.source',p['id']+' flow source',p['id']+' 流量来源',kind='text')
        if c.get('native_project'):continue
        for name,en,cn in [('channel_n','Channel Manning n','主槽糙率'),('overbank_n','Overbank Manning n','左右滩地糙率'),('culvert_n','Culvert Manning n','涵洞糙率')]:
            if name=='culvert_n' and is_river(g):continue
            add(f'c.scenarios.{i}.'+name,en,cn,unit='Manning n')
            if name == 'culvert_n':
                for condition,cn_condition,lo,normal,hi in [
                    ('Straight concrete culvert, free of debris','顺直混凝土涵洞，已确认无杂物',.010,.011,.013),
                    ('Concrete culvert with bends/connections and some debris','混凝土涵洞，有弯折/连接及少量杂物',.011,.013,.014)]:
                    result[-1]['suggestions'].append(dict(value=normal,range=[lo,hi],unit='Manning n',
                        evidence_class='assumed',basis='USACE HEC-RAS 7.0, Table 6-1; '+condition,
                        condition=dict(en=condition,zh=cn_condition),url=REFERENCE,checked='2026-10-15',
                        limitation=dict(en='Reference range for partly full closed conduits. Confirm material and condition; not a site measurement.',
                                        zh='部分充满封闭管涵的文献参考范围。需确认材质和状态，不是本站测量。')))
        add(f'c.scenarios.{i}.parameter_source','Roughness basis','糙率采用依据','text')
    if c.get('native_project'): return result
    for name in ['river','reach']:
        add('g.'+name,name.title()+' model name','模型河流名' if name=='river' else '模型河段名','text',help_en='ASCII name, 1–16 characters, without comma or newline.',help_cn='使用 1–16 个 ASCII 字符，不含逗号或换行；这是模型名称。')
    add('g.horizontal_crs','Projected coordinate system','平面投影坐标系','text',help_en='For example EPSG:xxxx from reviewed survey/DEM metadata.',help_cn='填写测量/DEM 元数据中核实的 EPSG 编号或 WKT，不可猜测。')
    add('g.vertical_datum','Elevation datum','高程基准','text',help_en='All geometry elevations must already use this datum and international feet.',help_cn='全部几何高程必须已统一至此基准，并使用国际英尺。')
    add('g.functional_section_basis','Functional section and boundary placement basis','功能断面及边界布置依据','text',required=False,
        help_en=('Identify the reach endpoints, floodplain coverage and boundary influence.' if is_river(g) else 'Identify approach, inlet/outlet and expansion-recovery sections and why the boundary extent is adequate. This records a review basis, not automatic acceptance.'),help_cn=('说明河段端点、漫滩覆盖和边界影响。' if is_river(g) else '说明接近段、进出口、扩散恢复断面的河站号，以及边界范围的依据。仅记录复核理由，不自动认定合格。'))
    add('g.flow_regime','Steady flow regime','恒定流流态','choice',options=['subcritical','mixed'],
        help_en='Subcritical requires a downstream boundary; mixed requires both. Legacy geometry without this field retains mixed flow. Native imports preserve their selected plan.',
        help_cn='缓流需下游边界；混合流需上下游边界。旧几何未记录此字段时沿用混合流。原生导入保留所选计划。')
    if 'flow_regime' not in g:result[-1]['value']='mixed'
    if is_river(g):
        add_fields(add,g)
    else:
        for side,cn in [('upstream','上游'),('downstream','下游')]:
            add('g.boundary_slopes.'+side,side.title()+' normal-depth slope',cn+' 正常水深边界坡降',unit='ft/ft',
                required=side=='downstream' or g.get('flow_regime','mixed')!='subcritical',
                help_en='Use the representative remote reach; do not substitute culvert slope.',help_cn='依据远端代表性河段，不能用涵底坡度直接代替。')
        for name,en,cn in [('rs','Structure river station','结构河站号'),('us_xs_rs','Upstream face section station','进口外侧断面站号'),('ds_xs_rs','Downstream face section station','出口外侧断面站号')]:
            add('g.structure.'+name,en,cn,unit='ft')
        add('g.structure.road.profile_mode','Road profile arrangement','路顶剖面方式','choice',options=['shared','distinct'],help_en='Shared uses the same reviewed profile on both faces. Distinct requires both surveyed/derived profiles; their station origins must match their face sections.',help_cn='共用表示两侧采用同一经审核剖面；独立表示分别提供两侧剖面，横向站距基点须匹配对应外侧断面。')
        if 'profile_mode' not in g['structure']['road']:result[-1]['value']='shared'
        for name,en,cn,kind,unit in [
            ('width_ft','Road width','路堤宽度','number','ft'),('distance_us_ft','Road distance from upstream face section','路堤距进口外侧断面','number','ft'),
            ('weir_coefficient','Road overflow coefficient','路堤溢流系数','number','US customary coefficient'),
            ('station_ft','Road crest stations','路顶剖面横向站距','array','ft'),('elevation_ft','Road crest elevations','路顶剖面高程','array','ft')]:
            add('g.structure.road.'+name,en,cn,kind,unit)
        for key,en,cn in [('downstream_station_ft','Downstream road crest stations','下游路顶横向站距'),('downstream_elevation_ft','Downstream road crest elevations','下游路顶高程')]:
            add('g.structure.road.'+key,en,cn,'array','ft',required=g['structure']['road'].get('profile_mode')=='distinct',help_en='Leave empty for a shared profile. For distinct profiles the existing road station/elevation fields describe the upstream side.',help_cn='共用剖面时留空；独立剖面时，前面的路顶站距/高程字段表示上游侧。')
        for i,b in enumerate(g.get('structure',{}).get('groups',[])):
            pre=f'g.structure.groups.{i}.';title=f'Group {i+1}: ';zh=f'涵洞组 {i+1}：'
            add(pre+'name',title+'model name',zh+'模型名称','text',required=False,help_en='Optional ASCII name, at most 12 characters. If omitted, the model uses Group 1, Group 2, etc.',help_cn='可选 ASCII 名称，最多 12 个字符；不填时模型使用 Group 1、Group 2 等标识。')
            add(pre+'shape',title+'opening shape',zh+'孔形','choice',options=['box','circular'])
            add(pre+'count',title+'identical barrel count',zh+'相同孔数','integer')
            for name,en,cn in [('span_ft','clear width / diameter','净宽 / 直径'),('rise_ft','clear height / diameter','净高 / 直径'),
                                ('length_ft','barrel length','涵长'),('us_invert_ft','inlet invert','进口涵底高程'),('ds_invert_ft','outlet invert','出口涵底高程'),
                                ('distance_us_ft','distance from upstream section','距进口外侧断面'),('depth_blocked_ft','blocked depth','底部填塞深度')]:
                add(pre+name,title+en,zh+cn,unit='ft',
                    help_en='Document each opening. Split into separate groups if inverts/dimensions differ. Buried geometry cannot be measured from surface DEM.',
                    help_cn='各孔尺寸或涵底不同时应分组。埋藏几何不能当作地表 DEM 实测值。')
            for name,en,cn in [('entrance_loss','entrance loss coefficient','入口损失系数'),('exit_loss','exit loss coefficient','出口损失系数')]: add(pre+name,title+en,zh+cn)
            for name,en,cn in [('bottom_type','floor form/material','底板形式/材质'),('inlet_description','entrance construction','入口构造')]:add(pre+name,title+en,zh+cn,'text')
            add(pre+'chart_scale',title+'validated inlet chart/scale',zh+'已适配入口图号/尺度','array',help_en='Box: [8,1], [8,2], [10,2]; circular: [1,1]. Select only from applicable inlet evidence.',help_cn='箱涵支持 [8,1]、[8,2]、[10,2]；圆管支持 [1,1]。应依据入口构造选择，不是建议默认值。')
            add(pre+'centers_ft',title+'inlet/outlet center pairs',zh+'各孔进口/出口横向中心位置','matrix','ft',help_en='One inlet,outlet pair per barrel.',help_cn='每孔一行：进口中心站距,出口中心站距。')
            filled=finite(b.get('depth_blocked_ft')) and b['depth_blocked_ft']>0
            add(pre+'mann_top',title+'group roughness override',zh+'本组糙率覆盖值',unit='Manning n',required=False,help_en='Leave absent to use the reviewed scenario culvert roughness.',help_cn='未设置时沿用已审核的工况涵洞糙率。')
            add(pre+'mann_bottom',title+'bottom roughness',zh+'底部糙率',unit='Manning n',required=filled)
            add(pre+'bottom_n_depth_ft',title+'bottom roughness depth',zh+'底部糙率作用深度',unit='ft',required=filled)
            add(pre+'blockage_basis',title+'blockage evidence',zh+'填塞依据','text',required=filled)
    for i,x in enumerate(g.get('cross_sections',[])):
        pre=f'g.cross_sections.{i}.'; title=f'XS {i+1}: ';zh=f'断面 {i+1}：'
        add(pre+'manning_segments',title+'horizontal Manning subdivisions',zh+'横向糙率分区','matrix',required=False,
            help_en='Optional rows: starting station ft, Manning n. Start at the left endpoint and increase; each value extends to the next station. Empty uses the reviewed scenario channel/overbank values.',help_cn='可选，每行：起点站距 ft, Manning n；首行须为左端点，依次递增，作用到下一个起点。留空沿用已审核的工况主槽/漫滩值。')
        for side,en,cn in [('left','left','左'),('right','right','右')]:
            add(pre+'ineffective_'+side,title+en+' edge ineffective area',zh+cn+'侧非有效流区','array',required=False,
                help_en='Optional pair: interior limit station ft, activation elevation ft. Area extends from the '+en+' endpoint to that limit and becomes effective above this elevation. Normal non-permanent edge areas only; do not remove low terrain.',help_cn='可选两个值：内侧边界站距 ft, 激活高程 ft。从'+cn+'端点延伸至边界，高于此高程后参与过流。仅支持普通非永久边缘区域；不可删除低地形代替。')
        add(pre+'reach_length_basis',title+'effective flow-path length basis',zh+'有效流路长度依据','text',required=False,
            help_en='Explain how left overbank, channel and right overbank lengths follow the reviewed flow paths; cite source/figure locations.',help_cn='说明左滩、主槽及右滩长度如何沿经复核流路确定，并注明来源或图件位置。')
        for name,en,cn,kind,unit in [('rs','river station','河站号','number','ft'),('station_ft','stations','横向站距','array','ft'),
                ('elevation_ft','elevations','高程','array','ft'),('bank_stations_ft','left/right banks','左右岸站距','array','ft'),
                ('reach_lengths_ft','left/channel/right reach lengths','左滩/主槽/右滩流程长度','array','ft'),
                ('cutline_xy','projected cutline coordinates','投影断面端点坐标','matrix','CRS units'),
                ('center_xy','reviewed flowline intersection','已复核流线交点坐标','array','CRS units'),
                ('expansion_contraction','expansion/contraction losses','扩散/收缩损失系数','array','')]:
            add(pre+name,title+en,zh+cn,kind,unit,help_en='Left to right looking downstream; sections ordered upstream to downstream. Last section reach lengths are [0,0,0].',
                help_cn='面向下游从左到右；断面按上游到下游排序。最下游断面流程长度为 [0,0,0]。')
    if c.get('terrain',{}).get('mode')=='local':
        for key,en,cn in [('raster','Local DEM path','本地 DEM 路径'),('provenance','Terrain provenance path','地形来源记录路径')]:
            add('c.terrain.'+key,en,cn,'path',help_en='Path relative to the original project JSON, inside this workspace.',help_cn='相对原项目 JSON 的文件路径，必须位于本工作区。')
        add('c.terrain.vertical_unit','DEM vertical unit','DEM 高程单位','choice',options=['m','US survey foot','international foot'])
        add('c.terrain.vertical_datum','DEM vertical datum','DEM 高程基准','text')
    return result


def _source_geometry(path,c):
    if not c.get('geometry'):return None
    gp=safe_path(path.parent,c['geometry'])
    try:return read(gp)
    except (OSError,ValueError):return None


def _snapshot_sources(path,c):
    result=[item(path,'original_project')]
    if c.get('section_workflow'):
        spec_path=safe_path(path.parent,c['section_workflow']['spec'])
        if spec_path.is_file():
            result.append(item(spec_path,'section_generation_spec'))
            spec=read(spec_path)
            if spec.get('alignment_spec'):result.append(item(safe_path(path.parent,spec['alignment_spec'])))
    for key in ['geometry','authorization','intake_candidates']:
        if c.get(key):
            p=safe_path(path.parent,c[key])
            if p.is_file(): result.append(item(p,key))
    for key in ['raster','provenance']:
        if c.get('terrain',{}).get(key):
            p=safe_path(path.parent,c['terrain'][key])
            if p.is_file():result.append(item(p,'terrain_'+key))
    return result


def prepare(project,scenario,refresh=False):
    path,c=inputs.load(project)
    if path.name.endswith('.seed.json') or 'sources' in path.relative_to(ROOT).parts:raise ValueError('Original evidence/seeds cannot be workflow projects')
    if not any(s['id']==scenario for s in c['scenarios']):raise ValueError('Unknown scenario')
    with lock(path.parent/'intake.lock'):
        previous=control(path)
        if previous and not refresh:
            if previous['status']=='CANCELLED':return previous
            if previous['status']=='APPLIED':return prepare(resolve(path),scenario)
            if previous['scenario']!=scenario:raise ValueError('Another scenario awaits input. Finish it or explicitly refresh the intake.')
            if not intact(previous['sources']):raise ValueError('Inputs changed. Preserve the old draft and use intake --refresh.')
            return previous
        folder=path.parent/'intake'/unique_id();folder.mkdir(parents=True)
        sources=_snapshot_sources(path,c);g=_source_geometry(path,c)
        save(folder/'original_project.json',c);save(folder/'original_geometry.json',g)
        packet=dict(schema_version='intake_packet_1.0',id=folder.name,project=rel(path),scenario=scenario,
                    project_id=c['project_id'],location=c.get('location'),sources=sources,
                    original_project=item(folder/'original_project.json'),original_geometry=item(folder/'original_geometry.json'))
        save(folder/'packet.json',packet)
        try:draft_geometry=normalize_geometry(g) if g else blank_geometry(c.get('model_type','culvert'))
        except ValueError:draft_geometry=blank_geometry(c.get('model_type','culvert'))  # Original invalid file remains bound in the packet.
        draft=dict(schema_version='intake_draft_1.0',packet=item(folder/'packet.json'),revision=0,answers={},
                   geometry=draft_geometry,uploads=[],reviewer='',basis='',consent=False)
        save(folder/'draft.json',draft)
        session=dict(schema_version='intake_session_1.0',id=folder.name,project=rel(path),scenario=scenario,
                     status=WAITING,created_utc=utc(),packet=item(folder/'packet.json'),sources=sources,
                     session=rel(folder/'session.json'),draft=rel(folder/'draft.json'),previous_session=previous['session'] if previous else None)
        save(folder/'session.json',session);save(path.parent/'intake_state.json',dict(project=rel(path),session=session['session']))
        state_path=path.parent/'state.json'
        state=read(state_path) if state_path.exists() else dict(project_id=c['project_id'],stages={})
        state.update(status=WAITING,workflow_status=WAITING,intake_session=session['session'],updated_at_utc=utc())
        save(state_path,state)
        return session


def _load(session_path,active=True):
    sp=safe_path(ROOT,session_path);s=read(sp);folder=sp.parent
    if not intact([s['packet']]):raise ValueError('Intake packet changed')
    p=read(ROOT/s['packet']['path']);d=read(folder/'draft.json')
    if d['packet']!=s['packet'] or not intact([p['original_project'],p['original_geometry']]):raise ValueError('Draft or snapshots belong to different evidence')
    if active:
        current=control(s['project'])
        if not current or current['session']!=s['session']:raise ValueError('This intake has been superseded; open the current session')
        if s['status']!=WAITING:raise ValueError('Intake is '+s['status'])
        if not intact([x for x in s['sources'] if x['role']!='terrain_raster']):raise ValueError('Source inputs changed; refresh the intake before reviewing')
    if d['uploads'] and not intact(d['uploads']):raise ValueError('Uploaded evidence changed')
    return sp,s,p,d


def _objects(p,d):
    c=read(ROOT/p['original_project']['path']);g=normalize_geometry(d['geometry'])
    if d.get('section_workflow'):
        receipt=d['section_workflow'];t=copy.deepcopy(receipt['terrain'])
        for key in ['raster','provenance']:
            t[key]=os.path.relpath(safe_path(ROOT/receipt['terrain_base'],t[key]),(ROOT/p['project']).parent)
        c['terrain']=t
    allowed={f['key'] for f in fields(c,g,p['scenario'])}
    if is_river(g):
        # Boundary selectors are stored in answers, while the base geometry may
        # still use the previous type. Retain inactive values without using them;
        # validate only the final selected boundary, including profile count.
        allowed.update({'g.boundaries.upstream.type','g.boundaries.downstream.type',
                        'g.boundaries.downstream.stages_ft',
                        'g.boundary_slopes.upstream','g.boundary_slopes.downstream'})
    for key,a in d['answers'].items():
        if key not in allowed:raise ValueError('Unknown input field: '+key)
        if not isinstance(a,dict):raise ValueError('Answer must be an object: '+key)
        root,*parts=key.split('.');_set(c if root=='c' else g,parts,a.get('value'))
    if g.get('terrain_review_required'):
        from .banks import propose
        for i,row in enumerate(g.get('cross_sections',[])):
            if any(f'g.cross_sections.{i}.'+key in d['answers'] for key in ['station_ft','elevation_ft','center_xy','cutline_xy']):
                row['bank_candidates']=propose(row,(row.get('bank_candidates') or {}).get('settings'))
    for b in g['structure']['groups']:
        for key in ['name','mann_top','mann_bottom','bottom_n_depth_ft','blockage_basis']:
            if b.get(key) in [None,'']:b.pop(key,None)
    return c,g


def _suggestions(c,p,rows):
    if not c.get('intake_candidates'):return []
    candidate_path=safe_path((ROOT/p['project']).parent,c['intake_candidates']);r=read(candidate_path)
    if r.get('schema_version')!='intake_candidates_1.0' or r.get('project_id')!=p['project_id'] or r.get('location')!=p['location']:
        raise ValueError('Candidate suggestions must match this exact site ID and location')
    by_key={x['key']:x for x in rows};used=[item(candidate_path)]
    for v in r.get('suggestions',[]):
        if v['target'] not in by_key:raise ValueError('Unknown candidate target')
        f=by_key[v['target']]
        if v.get('unit','')!=f['unit'] or v.get('evidence_class') not in CLASSES or not v.get('basis') or not intact(v.get('sources',[])):
            raise ValueError('Suggestion requires matching units and intact source evidence')
        current_datum=by_key.get('g.vertical_datum',{}).get('value')
        if 'invert' in f['key'] and (not v.get('datum') or v['datum']!=current_datum):
            raise ValueError('Invert suggestion needs a matching reviewed datum')
        if v.get('range') is not None and (len(v['range'])!=2 or not all(finite(x) for x in v['range']) or v['range'][0]>v['range'][1]):
            raise ValueError('Suggestion range must be finite and ordered')
        f['suggestions'].append(copy.deepcopy(v));used+=v['sources']
    return used


def view(session_path):
    sp,s,p,d=_load(session_path,active=False);c,g=_objects(p,d);rows=fields(c,g,p['scenario'])
    suggestion_error=None
    try:_suggestions(c,p,rows)
    except (ValueError,OSError,KeyError,TypeError) as e:suggestion_error=str(e)
    for f in rows:
        a=d['answers'].get(f['key']);f['answer']=a
        f['missing']=f['value'] is None or f['value']=='' or f['value']==[]
        for suggestion in f['suggestions']:suggestion['id']=digest(suggestion)
    from .geometry_qa import spatial_issues,section_fingerprint
    geometry_review=dict(required=g.get('terrain_review_required',False),sections=g.get('cross_sections',[]),
        issues=spatial_issues(g.get('cross_sections',[])),fingerprints=[section_fingerprint(r) for r in g.get('cross_sections',[])])
    from .physical_geometry import screen
    geometry_review['physical_screen']=screen(g)
    checkpoint=sp.parent/'geometry_checkpoint.json'
    from .geometry_editor import setup_view
    from .intake_native import preview as native_preview
    return dict(session=s,project_id=p['project_id'],title=c['title'],scenario=p['scenario'],location=c.get('location'),geometry_review=geometry_review,
                terrain_setup=setup_view(session_path) if s['status']==WAITING else None,native_import=native_preview(session_path),
                geometry_checkpoint=read(checkpoint) if checkpoint.exists() else None,
                fields=rows,draft=d,suggestion_error=suggestion_error,check=validate(session_path,d,require_consent=False),
                section_count=len(g.get('cross_sections',[])),group_count=len(g.get('structure',{}).get('groups',[])))


def validate(session_path,draft=None,require_consent=True,*,direct_start=False):
    sp,s,p,current=_load(session_path,active=False);d=draft or current;errors=[]
    def err(key,en,zh):errors.append(dict(field=key,en=en,zh=zh))
    try:c,g=_objects(p,d)
    except (ValueError,TypeError,KeyError) as e:return dict(ready=False,errors=[dict(field='',en=str(e),zh='输入字段不匹配：'+str(e))])
    from .geometry_qa import spatial_issues,review_errors
    for q in spatial_issues(g.get('cross_sections',[])):
        labels=[i+1 for i in q['sections']]
        err('g.cross_sections.'+str(q['sections'][0])+'.cutline_xy',q['code']+' — cross sections '+str(labels),'断面空间检查：'+q['code']+'，断面 '+str(labels))
    for message in review_errors(g):
        import re
        match=re.match(r'XS (\d+): (.*)',message)
        if match:
            index=int(match[1]);label='Cross section '+str(index+1)+': '+match[2]
            err(f'g.cross_sections.{index}.bank_stations_ft',label,'断面 '+str(index+1)+' 须复核：'+match[2])
        else:err('',message,'断面须复核：'+message)
    if d.get('section_workflow') and not intact(d['section_workflow']['sources']):
        err('','Terrain generation evidence changed; refresh review','地形生成证据改变，请重新发起审核')
    if d.get('geometry_edit_sources') and not intact(d['geometry_edit_sources']):
        err('','Section edit evidence changed; repeat preview and review','断面修改证据改变，请重新预览和复核')
    for f in fields(c,g,p['scenario']):
        v=f['value'];a=d['answers'].get(f['key']);key=f['key']
        if v is None or v=='' or v==[]:
            if f['required']:err(key,'Required input is missing','尚未提供必填信息')
            continue
        if f['kind'] in ['number','integer'] and (not finite(v) or f['kind']=='integer' and type(v)!=int):err(key,'A finite number is required','请输入有效数值；整数项不能包含小数')
        if f['kind'] in ['text','path','choice'] and (not isinstance(v,str) or not v.strip()):err(key,'Text is required','请输入有效文字')
        if f['kind']=='choice' and v not in f['options']:err(key,'Choose a supported option','请选择支持的选项')
        if f['kind']=='array' and (not isinstance(v,list) or not all(finite(x) for x in v)):err(key,'Enter a list of finite numbers','请输入数值列表')
        if f['kind']=='matrix' and (not isinstance(v,list) or not all(isinstance(x,list) and len(x)==2 and all(finite(z) for z in x) for x in v)):
            err(key,'Enter one numeric pair per row','每行需两个有效数值')
        if f['kind']=='path':
            try:
                if not safe_path((ROOT/p['project']).parent,v).is_file():raise ValueError('File not found')
            except (ValueError,TypeError) as e:err(key,str(e),'文件不存在或路径超出工作区')
        if not direct_start and a and (a.get('confirmed') is not True or a.get('evidence_class') not in CLASSES or not isinstance(a.get('basis'),str) or not a['basis'].strip()):
            err(key,'Confirm this value and provide its evidence class and basis','请确认此值，并填写证据类别和来源/估计依据')
        if a and a.get('suggestion'):
            try:
                rows=fields(c,g,p['scenario']);_suggestions(c,p,rows)
                choices=next(x for x in rows if x['key']==key)['suggestions']
                choice=next(x for x in choices if digest(x)==a['suggestion'])
                if a['evidence_class']!=choice['evidence_class']:err(key,'Suggestion evidence class cannot become a measurement','建议值不能改标为实测证据；请另行提供真实来源')
            except (StopIteration,ValueError,OSError,KeyError):err(key,'Suggestion/source changed; review again','建议或来源已改变，请重新审核')
    if errors:return dict(ready=False,errors=errors)
    # Validate the final model independently of the form; temporary in-memory approval
    # only suppresses the draft marker for this check, never an actual authorization.
    try:
        if not c.get('native_project'):
            if any(b.get('evidence_class')=='synthetic' for b in g['structure']['groups']) and c['case_kind']!='software_validation':
                err('','Synthetic geometry cannot become site evidence by approval','合成几何不能通过确认变成本站证据')
            g['provenance']=[p['original_project']];g['approved_for_model']=True;g['status']='CONDITIONALLY_REVIEWED'
            for b in g['structure']['groups']:b['evidence_class']='inferred_or_assumed'
            for e in inputs.geometry_errors(g,c['case_kind']=='software_validation'):err('',e,'几何仍需处理：'+e)
        for scenario in c['scenarios']:
            if scenario['id']!=p['scenario']:continue
            if not scenario.get('profiles'):err('','At least one flow profile is required','至少需要一个流量工况')
            if is_river(g):
                for message in boundary_errors(g,len(scenario.get('profiles',[]))):
                    err('g.boundaries.downstream.stages_ft',message,'边界输入需修正：'+message)
            for profile in scenario.get('profiles',[]):
                if not finite(profile.get('flow_cfs')) or profile['flow_cfs']<=0 or not profile.get('source'):err('','Positive flow and source are required','流量应大于零，并注明来源')
            if not c.get('native_project'):
                for n in (['channel_n','overbank_n'] if is_river(g) else ['channel_n','overbank_n','culvert_n']):
                    if not finite(scenario.get(n)) or not 0<scenario[n]<1:err('',n+' must be between 0 and 1',n+' 必须大于 0、小于 1')
    except (TypeError,ValueError,KeyError,IndexError,AttributeError) as e:err('','Geometry format: '+str(e),'几何格式错误：'+str(e))
    if require_consent and not direct_start:
        if not isinstance(d.get('reviewer'),str) or not d['reviewer'].strip():err('reviewer','Name the person making this decision','请填写作出决定的人员姓名')
        if not isinstance(d.get('basis'),str) or not d['basis'].strip():err('basis','Explain the site applicability and authorization basis','请说明本站适用性和授权依据')
        if d.get('consent') is not True:err('consent','Explicit conditional-use approval is required','请明确确认仅按记录条件使用这些输入')
    return dict(ready=not errors,errors=errors)


def save_draft(session_path,payload):
    sp=safe_path(ROOT,session_path)
    with lock(sp.parent/'session.lock'):
        sp,s,p,d=_load(sp)
        if payload.get('revision')!=d['revision']:raise ValueError('Draft changed in another window; reload before saving')
        answers=payload.get('answers',d['answers'])
        if not isinstance(answers,dict):raise ValueError('Invalid answers')
        proposed=copy.deepcopy(d);proposed.update(answers=answers)
        for k in ['reviewer','basis','consent']:
            if k in payload:proposed[k]=payload[k]
        if 'section_review_drafts' in payload:
            drafts=payload['section_review_drafts']
            if not isinstance(drafts,dict) or len(drafts)>500 or any(not isinstance(k,str) or len(k)!=64 or not isinstance(v,dict) or set(v)-{'bank_indices','reviewer','basis'} for k,v in drafts.items()):
                raise ValueError('Invalid per-section review draft')
            proposed['section_review_drafts']=drafts
        if 'geometry_setup_draft' in payload:
            if not isinstance(payload['geometry_setup_draft'],dict):raise ValueError('Invalid geometry form draft')
            proposed['geometry_setup_draft']=payload['geometry_setup_draft']
        if 'native_review' in payload:
            if not isinstance(payload['native_review'],dict):raise ValueError('Invalid native review draft')
            proposed['native_review']=payload['native_review']
        _objects(p,proposed)  # Unknown field paths never reach a configuration.
        proposed['revision']+=1;proposed['saved_utc']=utc()
        save(sp.parent/'events'/(unique_id()+'.json'),dict(action='SAVE_DRAFT',draft=proposed))
        save(sp.parent/'draft.json',proposed)
        return view(sp)


def edit_structure(session_path,revision,kind):
    sp=safe_path(ROOT,session_path)
    with lock(sp.parent/'session.lock'):
        sp,s,p,d=_load(sp)
        if revision!=d['revision']:raise ValueError('Stale draft revision')
        if kind=='section':
            xs=d['geometry'].setdefault('cross_sections',[])
            if len(xs)>=500:raise ValueError('At most 500 sections in the input form')
            xs.append({})
        elif kind=='group':
            groups=d['geometry'].setdefault('structure',{}).setdefault('groups',[])
            if len(groups)>=10:raise ValueError('At most 10 groups')
            groups.append({})
        else:raise ValueError('Unsupported geometry edit')
        d['revision']+=1;save(sp.parent/'draft.json',d)
    return view(sp)


def upload(session_path,revision,name,content,kind,basis,evidence_class):
    import base64
    from pathlib import Path
    sp=safe_path(ROOT,session_path)
    if name!=Path(name).name or any(x in name for x in ['/','\\',':']) or name in ['.','..']:raise ValueError('Use a plain file name')
    if not basis or evidence_class not in CLASSES:raise ValueError('Upload needs a source description and evidence class')
    raw=base64.b64decode(content,validate=True)
    if len(raw)>15_000_000:raise ValueError('File exceeds 15 MB; use a local source reference instead')
    if kind not in ['geometry','sections','evidence']:raise ValueError('Unsupported upload type')
    parsed=None
    if kind!='evidence':
        import json
        parsed=json.loads(raw.decode('utf-8-sig'))
        if not isinstance(parsed,dict):raise ValueError('Geometry/section draft must be a JSON object')
        if kind=='geometry' and (parsed.get('schema_version')!='1.0' or parsed.get('hydraulic_unit')!='international_ft'):raise ValueError('Use geometry schema 1.0 and explicit international_ft; no implicit unit conversion')
        if kind=='sections' and (not isinstance(parsed.get('cross_sections'),list) or parsed.get('hydraulic_unit')!='international_ft'):raise ValueError('Section draft must explicitly use international_ft')
        parsed=normalize_geometry(parsed)
        if any(b.get('evidence_class')=='synthetic' for b in parsed['structure']['groups']):raise ValueError('Synthetic geometry is not site evidence')
    with lock(sp.parent/'session.lock'):
        sp,s,p,d=_load(sp)
        if revision!=d['revision']:raise ValueError('Stale draft revision')
        folder=sp.parent/'uploads'/unique_id();folder.mkdir(parents=True)
        target=folder/'source.bin';target.write_bytes(raw);entry=dict(**item(target,'user_upload'),original_name=name,basis=basis,evidence_class=evidence_class,kind=kind)
        if kind=='geometry':d['geometry']=parsed;d['answers']={k:v for k,v in d['answers'].items() if not k.startswith('g.')}
        elif kind=='sections':
            d['geometry']['cross_sections']=parsed['cross_sections']
            for k in ['horizontal_crs','vertical_datum']:
                if parsed.get(k):d['geometry'][k]=parsed[k]
            d['geometry']['terrain_review_required']=bool(parsed.get('terrain_review_required') or any(r.get('bank_candidates') for r in parsed['cross_sections']))
            d['answers']={k:v for k,v in d['answers'].items() if not k.startswith('g.cross_sections.') and k not in ['g.horizontal_crs','g.vertical_datum']}
        d['uploads'].append(entry);d['revision']+=1;save(sp.parent/'draft.json',d)
    return view(sp)


def apply(session_path,revision,*,direct_start=False,mapping_enabled=None):
    sp=safe_path(ROOT,session_path);original=read(sp)['project']
    with lock((ROOT/original).parent/'project.lock'),lock(sp.parent/'session.lock'):
        sp,s,p,d=_load(sp)
        if not intact(s['sources']):raise ValueError('Source inputs changed; refresh the intake before applying')
        if revision!=d['revision']:raise ValueError('Draft changed; review the latest version')
        check=validate(sp,d,direct_start=direct_start)
        if not check['ready']:return dict(status=WAITING,**check)
        c,g=_objects(p,d);sources=s['sources']+[s['packet'],p['original_project'],p['original_geometry']]+d['uploads']
        if direct_start and mapping_enabled is not None:
            if type(mapping_enabled)!=bool:raise ValueError('Explicit GIS boolean required')
            c.setdefault('delivery',{})['mapping_enabled']=mapping_enabled
            if not mapping_enabled:c['terrain']['create_native']=False
        if d.get('section_workflow'):sources+=d['section_workflow']['sources']
        sources+=d.get('geometry_edit_sources',[])
        rows=fields(c,g,p['scenario']);sources+=_suggestions(c,p,rows)
        selected={f['key']:[v for v in f['suggestions'] if digest(v)==d['answers'].get(f['key'],{}).get('suggestion')] for f in rows}
        # Keep native solver/report paths shallow. Sessions retain the approval pointer.
        folder=(ROOT/s['project']).parent/'approved'/unique_id();folder.mkdir(parents=True)
        if direct_start:
            # Keep final confirmation, assumptions and supplied material in Complete,
            # rather than leaving only historical workspace references in a receipt.
            existing=c.setdefault('delivery',{}).get('additional_sources',[])
            original_base=(ROOT/p['project']).parent
            paths=[safe_path(original_base,v) for v in existing]+[safe_path(ROOT,v['path']) for v in d['uploads']]
            c['delivery']['additional_sources']=[os.path.relpath(v,folder) for v in dict.fromkeys(paths)]
        save(folder/'decision.json',dict(decision='START_CONDITIONAL_COMPUTATION' if direct_start else 'APPROVE_CONDITIONAL_INPUTS',project_id=c['project_id'],scenario=p['scenario'],
            reviewer=d['reviewer'],basis=d['basis'],answers=d['answers'],uploads=d['uploads'],reference_candidates={k:v for k,v in selected.items() if v},created_utc=utc(),
            identity='LOCAL_START_ACTION_NO_ENGINEERING_REVIEW' if direct_start else 'OPERATOR_ATTESTED_NOT_DIGITAL_SIGNATURE',engineering_acceptance='NOT_ASSESSED'))
        decision=item(folder/'decision.json');sources.append(decision)
        for key in ['raster','provenance']:
            if c.get('terrain',{}).get(key):c['terrain'][key]=os.path.relpath(safe_path((ROOT/p['project']).parent,c['terrain'][key]),folder)
        for key in ['native_project','reference_results','benchmark_preparation']:
            if c.get(key):c[key]=os.path.relpath(safe_path((ROOT/p['project']).parent,c[key]),folder)
        c.pop('intake_candidates',None)
        c.pop('section_workflow',None)
        if not c.get('native_project'):
            g.update(provenance=g.get('provenance',[])+sources,approved_for_model=True,
                status='CONDITIONAL_RUN_REQUESTED' if direct_start else 'CONDITIONALLY_REVIEWED')
            for i,b in enumerate(g['structure']['groups']):
                edits=[a for k,a in d['answers'].items() if k.startswith(f'g.structure.groups.{i}.')]
                if edits or d['uploads'] or not b.get('evidence_class'):b['evidence_class']='inferred_or_assumed'
            save(folder/'geometry.json',g)
            save(folder/'authorization.json',dict(project_id=c['project_id'],allowed_geometry_sha256=sha(folder/'geometry.json'),
                scope='User-requested conditional computation; no named engineering review' if direct_start else 'User-reviewed conditional input completion',reviewer=d['reviewer'],basis=d['basis'],decision=decision,
                engineering_acceptance='NOT_ASSESSED'))
            c.update(geometry='geometry.json',authorization='authorization.json',geometry_review=d['basis'])
        c.update(configuration_approval='approval_receipt.json',model_proposal_pending=False)
        for scenario in c['scenarios']:
            if scenario['id']==p['scenario']:
                for profile in scenario['profiles']:
                    profile.update(approved_for_model=True,review_status='CONDITIONALLY_REVIEWED')
        save(folder/'project.json',c)
        files=[item(folder/'project.json')]+([item(folder/'geometry.json'),item(folder/'authorization.json')] if not c.get('native_project') else [])
        save(folder/'approval_receipt.json',dict(status='CONDITIONAL_RUN_REQUESTED' if direct_start else 'CONDITIONALLY_AUTHORIZED_NOT_ENGINEERING_ACCEPTED',
            policy='local_computation_v1' if direct_start else 'named_review',sources=sources,files=files,
            reviewer_identity='NOT_REQUESTED' if direct_start else 'OPERATOR_ATTESTED',created_utc=utc(),engineering_acceptance='NOT_ASSESSED'))
        scenario=next(x for x in c['scenarios'] if x['id']==p['scenario'])
        gate,_=inputs.gate(folder/'project.json',c,scenario)
        try:inputs.dependencies(folder/'project.json',c)
        except (ValueError,OSError) as e:gate['blocking_items'].append(str(e))
        if gate['blocking_items']:
            save(folder/'rejected.json',gate)
            return dict(status=WAITING,ready=False,errors=[dict(field='',en=x,zh='仍需补充：'+x) for x in gate['blocking_items']])
        s.update(status='APPLIED',approved_project=rel(folder/'project.json'),approval=item(folder/'approval_receipt.json'),finished_utc=utc())
        save(sp,s)
        return dict(status='APPLIED',project=s['approved_project'],engineering_acceptance='NOT_ASSESSED')


def cancel(session_path,revision,reviewer,reason,confirmed=False):
    sp=safe_path(ROOT,session_path);project=read(sp)['project']
    with lock((ROOT/project).parent/'project.lock'),lock(sp.parent/'session.lock'):
        sp,s,p,d=_load(sp)
        if revision!=d['revision']:raise ValueError('Stale draft revision')
        if confirmed is not True or not reviewer.strip() or not reason.strip():raise ValueError('Explicit cancellation, name and reason required')
        decision=dict(action='CANCEL_WORKFLOW',project=s['project'],reviewer=reviewer,reason=reason,created_utc=utc(),draft=item(sp.parent/'draft.json'))
        save(sp.parent/'cancellation.json',decision);s.update(status='CANCELLED',decision=item(sp.parent/'cancellation.json'),finished_utc=utc());save(sp,s)
        state_path=(ROOT/project).parent/'state.json'
        state=read(state_path) if state_path.exists() else dict(project_id=p['project_id'],stages={})
        state.update(status='CANCELLED',workflow_status='CANCELLED',intake_session=s['session']);save(state_path,state)
        return dict(status='CANCELLED',preserved=True)
