"""Reader-facing bilingual report composition; engineering states stay explicit."""
from collections import Counter
from docx.shared import Inches, Pt
from .common import ROOT, item, read, safe_path, save, sha, utc

REPORT_VARIANTS = (
    ('en', 'full', 'Report_EN'),
    ('zh-CN', 'full', 'Report_CN'),
    ('en', 'summary', 'Summary_EN'),
)


ISSUES={
 'WET_SECTION_EDGE':('Water reaches a section edge','水位达到断面边缘','Check floodplain width and connected bypass paths before assessing inundation.','先复核断面宽度及连通绕流路径，再判断淹没情况。'),
 'ENERGY_BALANCE_ERROR':('Large local energy residual','局部能量求解残差较大','Review the local profile and geometry; assess refinement without relaxing tolerances.','复核局部水面线与几何，并检查加密影响，不以放宽容差消除问题。'),
 'MINIMUM_ERROR_SOLUTION':('Minimum-error solution used','采用最小误差解','Review the local numerical solution and flow regime.','复核局部数值解及流态。'),
 'CRITICAL_DEPTH_FALLBACK':('Critical-depth fallback','回退到临界水深','Inspect local geometry and the calculated flow transition.','检查局部几何及计算流态转换。'),
 'DOWNSTREAM_EGL_RISE':('Downstream energy-grade rise','下游能量线升高','Check the flow direction and local transition.','检查流向及局部流态转换。'),
 'FLOW_SPLIT_NOT_FULLY_OBSERVED':('Incomplete structure flow split','结构分流结果不完整','Obtain all culvert, road and other-path outputs; a missing value is not zero.','补齐涵洞、道路及其他路径输出；缺值不能视为零流量。'),
 'NATIVE_WARNING_TABLE_INCOMPLETE':('Complete native warning table unavailable','完整原生警告表尚缺','Export and review all native errors, warnings and notes for this run.','导出并复核本次运行的全部原生错误、警告及提示。'),
 'NATIVE_DISPLAY_MACHINE_DIFFERENCE':('Native display differs from machine output','原生显示与机器输出有差异','Review both recorded values; extraction does not certify numerical agreement. Original HDF/COM values remain unchanged.','核对已记录的两个数值；导出不代表数值一致，原始 HDF／COM 数值保持不变。'),
 'STRUCTURE_FLOW_IMBALANCE':('Structure flow imbalance','结构流量不平衡','Check group totals, overflow and other represented paths.','核对孔组总量、越流及其他已建模路径。'),
 'CULVERT_GROUP_DETAIL_NOT_EXTRACTED':('Incomplete culvert-group details','孔组详细输出不完整','Review the native group output tables.','复核原生孔组输出表。'),
 'NATIVE_WET_SECTION_EDGE':('Native warning: low section end','原生警告：断面端点偏低','Inspect the actual terrain and connected flow paths beyond the section; do not raise ground to suppress the warning.','检查断面外实际地形及连通过流路径，不为消除警告抬高地面。'),
 'NATIVE_DIVIDED_FLOW':('Native warning: divided flow','原生警告：分隔水流','Check whether separated wet areas connect along the reach and whether the one-dimensional representation is appropriate.','判断分隔湿区沿河段是否连通，以及一维表达是否适用。'),
 'NATIVE_CONVEYANCE_CHANGE':('Native warning: abrupt conveyance change','原生警告：输水能力突变','Review section spacing, contraction/expansion geometry, banks and ineffective areas.','复核断面间距、收缩扩散几何、岸站及非有效流区。'),
 'NATIVE_MULTIPLE_CRITICAL_DEPTH':('Native note: multiple critical depths','原生提示：多个临界水深','Inspect the native profile and section shape; this note alone is not proof of a hydraulic jump or critical-depth fallback.','结合原生水面线和断面形状复核；此提示本身不证明出现水跃或临界水深回退。')}


def value(v, digits=2, cn=True):
    return ('未取得' if cn else 'Unavailable') if v is None else f'{v:.{digits}f}'


def native_input_tables(d,n,tr,num):
    from .report import table
    d.add_paragraph(tr('Selected native regime: ','原生计划流态：')+n['regime'])
    rows=[]
    for section in n['sections']:
        rough=section['manning']
        rows.append([section['rs'],'; '.join(num(v[0],2)+': '+format(v[1], '.7g') for v in rough),
            ' / '.join(num(v) for v in section['banks']),tr('Present','已保留') if section['ineffective_areas'] else tr('Absent','无记录')])
    table(d,['RS',tr('Manning n by starting station','起点站距：Manning n'),tr('Left / right bank ft','左 / 右岸站 ft'),tr('Ineffective areas','非有效流区')],rows,[.65,2.65,1.6,1.8])
    def bc(v):
        if v['type']==0:return tr('Not used by this plan','本计划未使用')
        if v['type']==1:return tr('Known WSE ','已知水位 ')+num(v['stage_ft'],3)+' ft'
        return tr('Normal depth, slope ','正常水深，坡降 ')+num(v['slope'],8)+' ft/ft'
    boundaries={}
    for v in n['boundaries']:boundaries.setdefault((bc(v['upstream']),bc(v['downstream'])),[]).append(n['profiles'][v['profile_number']-1]['id'])
    table(d,[tr('Profiles','工况'),tr('Upstream boundary','上游边界'),tr('Downstream boundary','下游边界')],
        [[tr('All profiles','全部工况') if len(names)==len(n['profiles']) else ', '.join(names),*key] for key,names in boundaries.items()],[1.2,2.75,2.75])
    if n.get('model_type')=='river':return
    groups=n['expected_native']['groups']
    table(d,[tr('Group / cells','孔组 / 孔数'),tr('Span × rise ft','净宽 × 高 ft'),tr('Length ft','涵长 ft'),tr('Inlet / outlet invert ft','进 / 出口涵底 ft'),tr('Top / bottom n','顶部 / 底部 n')],
        [[b['name']+' / '+str(b['count']),num(b['span_ft'])+' × '+num(b['rise_ft']),num(b['length_ft']),num(b['us_invert_ft'],3)+' / '+num(b['ds_invert_ft'],3),num(b['culvert_n'],3)+' / '+num(b.get('bottom_n'),3)] for b in groups],[1.2,1.25,.8,2.05,1.4])
    road=n['expected_native'];d.add_paragraph(tr('Road profiles: ','路顶剖面：')+str(len(road['road_profiles']['upstream']))+' / '+str(len(road['road_profiles']['downstream']))+tr(' upstream / downstream points; minimum crest ',' 个上游 / 下游采样点；最低路顶 ')+num(road['road_min_ft'],3)+' ft. '+tr('Raw native inputs retain the full profiles and ineffective-area definitions.','原生输入保留完整路顶及非有效流区定义。'))


def build(data, plots, folder, language='en', detail='full', details=None):
    from .report import document, table, detail_appendix
    if language not in ('en','zh-CN'):raise ValueError('Unsupported report language')
    if detail not in ('full','summary'):raise ValueError('Unsupported report detail')
    cn=language=='zh-CN';full=detail=='full'
    s=data['summary'];c=s['configuration'];h=s['hydraulics'];profiles=h['profiles'];g=data['geometry']
    qa_state=((data.get('context') or {}).get('review') or {}).get('closure',{}).get('hydraulic_qa_status','REVIEW_REQUIRED')
    tr=lambda en,zh:zh if cn else en
    num=lambda v,d=2:value(v,d,cn)
    title=c['title']+(tr(' Steady Flow Hydraulic Report',' 恒定流水力计算报告') if full else tr(' Steady Flow Executive Summary',' 恒定流执行摘要'))
    d=document(title)
    d.core_properties.language='zh-CN' if cn else 'en-US'
    d.add_paragraph(tr('Conditional calculation for review','条件性计算供复核') if c['case_kind']=='site_conditional' else tr('Reference model validation','参考模型验证'),'Subtitle')
    def p(en,zh):return d.add_paragraph(tr(en,zh))
    def page(en,zh):
        heading=d.add_heading(tr(en,zh),1);heading.paragraph_format.page_break_before=True
    figure_number=0
    def picture(entry,caption_en,caption_cn,width=6.65):
        import re
        nonlocal figure_number
        figure_number+=1
        caption_en='Figure '+str(figure_number)+' '+re.sub(r'^Figure \d+\s*','',caption_en)
        caption_cn='图 '+str(figure_number)+' '+re.sub(r'^图\s*\d+\s*','',caption_cn)
        pp=d.add_paragraph();pp.paragraph_format.keep_with_next=True
        run=pp.add_run();run.add_picture(str(ROOT/entry['path']),width=Inches(width))
        # Explicit alternative text also survives DOCX import and accessibility checks.
        inline=run._r.xpath('.//wp:docPr')
        if inline:inline[0].set('descr',tr(caption_en,caption_cn))
        d.add_paragraph(tr(caption_en,caption_cn),'Caption')
    p('This report explains the calculated water levels, the model inputs and the issues that need review before the results can support a site decision.',
      '本报告说明计算水位、采用的模型条件，以及结果用于现场决策前仍需复核的问题。')
    if c['case_kind']=='site_conditional':
        p('HEC-RAS completed the calculation under the stated conditional inputs. Hydraulic QA status: '+qa_state+'. These results do not establish design adequacy or absence of flooding.',
          'HEC-RAS 已按所列条件性输入完成计算。水力 QA 状态：'+qa_state+'。当前结果不能据以认定设计合格或场地不存在淹没。')
    else:p('This is a reference-model calculation. Reproducing an example is software evidence and does not certify a real site.',
           '这是参考模型计算。复现示例属于软件验证证据，不构成真实场地安全结论。')
    d.add_heading(tr('Results at a glance','主要结果'),1)
    table(d,[tr('Profile','工况'),tr('Flow cfs','流量 cfs'),tr('HW ft','涵前水位 ft'),tr('TW ft','涵后水位 ft'),tr('Road margin ft','道路余高 ft')],
        [[r['profile_id'],num(r['flow_cfs'],1),num(r['metrics']['headwater_wse_ft']),num(r['metrics']['tailwater_wse_ft']),num(r['metrics']['road_freeboard_ft'])] for r in profiles],[.8,1.,1.6,1.6,1.7])
    p('Elevations use '+h.get('unit','international ft')+' and datum '+str(h['datum'])+'. HW and TW refer to the exterior sections identified below. Display rounding is not a statement of survey accuracy.',
      '高程单位为 '+h.get('unit','international ft')+'，高程基准为 '+str(h['datum'])+'。涵前和涵后水位对应下文标识的外部断面；小数位数不代表测量精度。')
    p('Road margin is the modeled minimum road crest minus exterior headwater. A positive margin alone does not establish that all floodplain or bypass paths remain dry.',
      '道路余高为模型最低路顶高程减涵前外部断面水位。余高为正，仍不能单独证明所有漫滩和绕流路径均无淹没。')
    if data.get('language_review') and not cn:
        d.add_paragraph('Language review pending: some user-entered construction or blockage notes below remain in their original language. This edition is not a fully translated English engineering narrative. Supply verified English wording in the editable model notes when needed.')
    d.add_heading(tr('What still needs attention','需要关注的问题'),1)
    counts={}
    for r in profiles:
        key=(len(r['qa']['wet_edges']),len(r['qa']['min_error_alerts']),len(r['qa']['critical_matches']))
        counts.setdefault(key,[]).append(r['profile_id'])
    for (wet,energy,critical),names in counts.items():
        which=tr('All profiles','全部工况') if len(names)==len(profiles) else ', '.join(names)
        p(f'{which}: {wet} wet edges, {energy} energy-error alerts and {critical} critical-level matches per profile.',
          f'{which}：每个工况 {wet} 条湿边缘断面、{energy} 处能量误差提示、{critical} 处临界水位匹配。')
    p('Counts refer to sections in each profile. Critical matches alone do not prove a hydraulic jump; detailed locations and actions follow.',
      '数量指各工况中的断面数。临界水位匹配本身不能证明存在水跃；具体位置及处理建议见后文。')
    p('Calculation: COMPUTED. Input adequacy: '+s['gate']['input_adequacy_status']+'. Hydraulic QA: '+qa_state+'. Engineering acceptance: NOT_ASSESSED.',
      '计算：已完成。输入充分性：'+s['gate']['input_adequacy_status']+'。水力 QA：'+qa_state+'。工程接受：尚未评定。')
    generated=data['created_utc'][:19]
    p('Calculation time UTC '+s['finished_at_utc'][:19]+'. Report generated UTC '+generated+'.',
      '计算记录时间 UTC '+s['finished_at_utc'][:19]+'；报告生成时间 UTC '+generated+'。')
    p('Report generation does not rerun HEC-RAS. The cited native run and its input conditions remain the basis of these results.',
      '生成报告不重新运行 HEC-RAS；结果仍对应所引用的原生运行及其输入条件。')
    if s.get('solver_reused'):p('The cited attempt reused verified existing solver output; report generation is not a new solve.','所引尝试复用了核验后的既有求解输出；生成报告不构成新求解。')

    from .report_context import compose
    from .revision_report import compose as revision_compose
    revision_compose(d,data,tr,full)
    if full:compose(d,data,tr,num,full=True)

    if full:
        page('Site and terrain','场地与地形')
        loc=c.get('location') or {}
        p('Site marker: latitude '+str(loc.get('latitude','Unavailable'))+', longitude '+str(loc.get('longitude','Unavailable'))+'. Location source: '+str(loc.get('source','Unavailable'))+'. A coordinate marker is not a surveyed culvert location.',
          '项目位置：纬度 '+str(loc.get('latitude','未提供'))+'，经度 '+str(loc.get('longitude','未提供'))+'；位置来源：'+str(loc.get('source','未提供'))+'。坐标标记不等同于经测量确认的涵洞位置。')
        t=s.get('terrain',{})
        if plots['terrain'].get('image'):
            p('The map uses the actual raster and input snapshots. DEM does not establish buried inverts or barrel length. Section-centre connections do not define a calculated flow path or inundation extent.',
              '地图使用实际栅格及输入快照。DEM 不能证明埋藏涵底或涵长；断面中心连线不等于计算流线或淹没范围。')
            picture(plots['terrain']['image'],'Figure 1 Terrain and model section layout. Red sections have a wet edge in at least one profile; blue marks the other sections.','图 1 地形与模型断面布局。红色断面在至少一个工况中出现湿边缘；深蓝色为其余断面。')
            p('Horizontal CRS: '+plots['terrain']['horizontal_crs']+'. Axis origin: '+str(plots['terrain']['origin'])+'. DEM elevation unit: '+str(t.get('vertical_unit'))+'; datum: '+str(t.get('vertical_datum'))+'.',
              '平面坐标系：'+plots['terrain']['horizontal_crs']+'；图轴相对原点 '+str(plots['terrain']['origin'])+'。DEM 高程单位：'+str(t.get('vertical_unit'))+'；基准：'+str(t.get('vertical_datum'))+'。')
        else:p('This report has no location map: the run-bound report inputs do not supply both verified terrain and mapped section coordinates. Any separately prepared GIS delivery requires its own source and coordinate checks.',
               '本报告未绘制位置图：本次绑定的报告输入未同时提供可核验地形和断面地图坐标。单独准备的 GIS 交付包需另核查其来源和坐标。')
        if t.get('resolution'):p('Raster resolution: '+str(t['resolution'])+' in the original CRS units. Grid resolution is not a measure of elevation accuracy.',
            '栅格分辨率：'+str(t['resolution'])+'（原坐标系单位）。分辨率不能直接视为地形高程精度。')
        if plots['terrain'].get('image'):page('Model inputs','模型输入与适用条件')
        else:d.add_heading(tr('Model inputs','模型输入与适用条件'),1)
        scenario=next((v for v in c.get('scenarios',[]) if v['id']==h['scenario_id']),{})
        if g:p('Adopted steady flow regime: '+str(g.get('flow_regime','mixed'))+'.','采用恒定流流态：'+tr(str(g.get('flow_regime','mixed')),'缓流' if g.get('flow_regime')=='subcritical' else '混合流')+'。')
        p('This is a one-dimensional steady-flow calculation with separately solved flow profiles. It does not simulate a flood hydrograph, evolving storage or a two-dimensional velocity field. Conditional structure estimates below still require field verification.',
          '本报告采用一维恒定流计算结果，各流量工况分别求解，不包含洪峰过程、蓄滞洪演变或二维流速场。结构数据及采用依据如下；条件性估计仍需现场核实。')
        if data.get('native_inputs'):
            native_input_tables(d,data['native_inputs'],tr,num)
        else:table(d,[tr('Parameter','参数'),tr('Adopted value','采用值'),tr('Basis or explanation','依据或说明')],[
            [tr('Channel Manning n','主槽 Manning n'),num(scenario.get('channel_n') if g else None,3),tr('Inspect imported native geometry' if not g else 'Scenario input','原生导入模型须另查原生几何' if not g else '工况输入')],
            [tr('Overbank Manning n','左右滩地 Manning n'),num(scenario.get('overbank_n') if g else None,3),tr('Scenario input for generated models','工况输入（仅生成模型）')],
            [tr('Culvert Manning n','涵内 Manning n'),num(scenario.get('culvert_n') if g else None,3),tr('Check snapshots for group overrides','孔组覆盖值应另查输入快照')],
            [tr('Upstream boundary slope','上游边界坡降'),tr('Not used','未使用') if g and g.get('flow_regime')=='subcritical' else num((g or {}).get('boundary_slopes',{}).get('upstream'),5),tr('Normal-depth boundary input','正常水深边界输入')],
            [tr('Downstream boundary slope','下游边界坡降'),num((g or {}).get('boundary_slopes',{}).get('downstream'),5),tr('Normal-depth boundary input','正常水深边界输入')]],[2.4,1.25,3.05])
        flow_sources={}
        for pp in scenario.get('profiles',[]):flow_sources.setdefault(pp.get('source'),[]).append(pp['id'])
        for source,names in flow_sources.items():
            which=tr('all profiles','全部工况') if len(names)==len(scenario['profiles']) else ', '.join(names)
            p('Flow source ('+which+'): '+str(source or 'Unavailable'),'流量来源（'+which+'）：'+str(source or '未提供'))
        p('Roughness basis: '+str(scenario.get('parameter_source','See native model input records')),'糙率依据：'+str(scenario.get('parameter_source','见原生模型输入记录')))
        if g:
            groups=g.get('structure',{}).get('groups',[])
            p('These are adopted model inputs, not as-built or survey certification. Group evidence classes: '+', '.join(str(b.get('evidence_class','Not recorded')) for b in groups)+'.',
              '所列数值为模型采用值，不是竣工或测量认证。孔组证据类别：'+', '.join(str(b.get('evidence_class','未记录')) for b in groups)+'。')
            if not data.get('native_inputs'):
                table(d,[tr('Group','孔组'),tr('Cells','孔数'),tr('Span / rise ft','净宽/高 ft'),tr('Length ft','涵长 ft'),tr('Inlet / outlet invert ft','进口/出口涵底 ft')],[[b.get('name',f'Group {i+1}'),b.get('count'),num(b.get('span_ft'))+' / '+num(b.get('rise_ft')),num(b.get('length_ft')),num(b.get('us_invert_ft'))+' / '+num(b.get('ds_invert_ft'))] for i,b in enumerate(groups)],[1.,.55,1.3,1.05,2.8])
            for i,b in enumerate(groups):p('Group '+str(i+1)+': '+str(b.get('shape','Unavailable'))+'. Floor: '+str(b.get('bottom_type','Unavailable'))+'. Inlet: '+str(b.get('inlet_description','Unavailable'))+'.',
                '孔组 '+str(i+1)+'：'+str(b.get('shape','未提供'))+'；底板 '+str(b.get('bottom_type','未提供'))+'；入口 '+str(b.get('inlet_description','未提供'))+'。')
            locations=', '.join(r['profile_id']+' RS '+r['headwater_rs']+' / '+r['tailwater_rs'] for r in profiles)
            pairs={(r['headwater_rs'],r['tailwater_rs']) for r in profiles}
            if len(pairs)==1:
                hw,tw=next(iter(pairs));locations=tr('all profiles','全部工况')+' RS '+hw+' / '+tw
            p('HW / TW result sections: '+locations+'. Minimum modeled road crest: '+num(h.get('road_crest_ft'))+' ft.',
              '涵前/涵后结果断面：'+locations+'。最低模型路顶：'+num(h.get('road_crest_ft'))+' ft。')
            reviewed=sum(bool(r.get('terrain_review')) for r in g['cross_sections'])
            p('There are '+str(len(g['cross_sections']))+' exterior sections; '+str(reviewed)+' have individual review records. These record adoption decisions, not survey verification or engineering acceptance.',
              '本次输入有 '+str(len(g['cross_sections']))+' 条外部断面，其中 '+str(reviewed)+' 条保存了逐断面复核记录。复核记录反映输入采用决定，不构成实测证明或工程接受。')
            p('Geometry adoption basis: '+str(c.get('geometry_review','See input authorization records')),'总体采用依据：'+str(c.get('geometry_review','见输入授权记录')))
        else:
            p('This model was imported as a native project. Input tables are read from the bound pre-run files where supported; section and water-level figures use verified native HDF data. No values are borrowed from another project.',
              '本模型由原生工程导入。支持的输入表从绑定的运行前文件读取；断面和水位图来自核验过的原生 HDF。不从其他项目补入参数。')
            if data.get('native_input_error'):p('Some native input tables could not be extracted: '+data['native_input_error'],'部分原生输入表尚不能抽取：'+data['native_input_error'])
    page('Water levels along the reach','沿程水位与流态')
    picture(plots['longitudinal'],('Figure 2 ' if full else '')+'Water surface and energy grade with channel Froude number. Shading marks the exterior HW/TW section interval. Lines connect computed section values only, not a continuous water surface inside the culvert.',
        '图 2 水面线、能量线及主槽 Froude 数。阴影表示涵前/涵后外部断面之间的区间；图线仅连接离散计算值，不表示涵内连续水面。')
    p('The horizontal axis is section order, not physical distance. Froude values below or above 1 indicate subcritical or supercritical tendencies; transitions require review with native warnings and local geometry.',
      '横轴表示断面顺序，不是物理距离。Froude 数小于或大于 1 分别提示缓流或急流特征；流态转换需结合原生警告及局部几何复核。')
    if full:page('Culvert flow, velocities and control outputs','涵洞分流、流速与控制水头')
    table(d,[tr('Profile','工况'),tr('Culvert Q cfs','涵洞总流量 cfs'),tr('Barrel Q cfs','代表单孔 cfs'),tr('Road Q cfs','道路流量 cfs')],[[r['profile_id'],num(r['metrics'].get('culvert_total_flow_cfs')),num(r['metrics'].get('representative_barrel_flow_cfs')),num(r['metrics'].get('roadway_flow_software_cfs'))] for r in profiles],[1.,1.9,1.9,1.9])
    p('A representative barrel value applies to the software group of identical barrels. It is not an independent solution for each opening. Unavailable roadway flow prevents a complete flow-split assessment; it is not replaced with zero.',
      '代表单孔值用于软件中的相同孔组，不代表每孔被独立求解。道路流量未取得时，完整分流判断仍缺依据，不将缺值改为零。')
    if full:
        supplement_rows={(r['profile'],r['group_id']):r for r in (data.get('native_supplement') or {}).get('rows',[])}
        display_groups=[]
        for r in profiles:
            for b in r.get('culvert_groups',[]):
                observed=supplement_rows.get((r['profile_id'],b['group_id']))
                values=observed or b
                display_groups.append([r['profile_id']+' / '+b.get('name',str(b['group_id'])),num(values.get('inlet_velocity_fts')),num(values.get('outlet_velocity_fts')),num(values.get('inlet_control_egl_ft'))+' / '+num(values.get('outlet_control_egl_ft'))])
        if supplement_rows:p('The group table below includes cross-checked native text supplements at their displayed precision. The automatic aggregate table above remains unchanged; missing aggregate/road flow is not reconstructed from rounded group sums.',
                             '下表纳入已交叉核验的原生孔组文本，精度以原生显示为准。上方自动提取的总量表保持不变，不由四舍五入孔组值倒推缺失的总流量或道路流量。')
        table(d,[tr('Profile / group','工况 / 孔组'),tr('Inlet velocity ft/s','入口流速 ft/s'),tr('Outlet velocity ft/s','出口流速 ft/s'),tr('Inlet / outlet control EGL ft','入口/出口控制 EGL ft')],display_groups,[1.7,1.4,1.4,2.2])
        p('Unavailable control heads do not establish inlet or outlet control. Outlet velocity can guide scour review; without bed material, protection and allowable-velocity evidence, it cannot establish erosion safety.',
          '未取得控制水头时，不自行判定入口或出口控制。出口流速可用于安排冲刷复核，但缺少床沙、护砌和允许流速资料时，不能据此判定冲刷安全。')
    if full:
        for k,panel in enumerate(plots['sections']):
            page('Cross section profiles '+str(k+1),'断面剖面 '+str(k+1))
            p('Read left to right looking downstream. Brown lines show native model ground, dotted vertical lines mark adopted banks, and horizontal coloured lines show computed water levels.',
              '面向下游由左至右读取。棕色实线为原生模型地面，竖向点线为采用的左右岸位置，水平彩线为对应工况的计算水位。')
            picture(panel['image'],f'Figure {k+3} Sections RS '+', '.join(panel['stations'])+'. Each panel has its own vertical scale. Bank stations are not levee crests or flood-protection levels.',f'图 {k+3} 断面 RS '+', '.join(panel['stations'])+'。各子图采用独立纵轴刻度，岸站不是堤顶或防洪保证高程。')
            wet=[r for r in profiles if set(r['qa']['wet_edges'])&set(panel['stations'])]
            if wet:
                locations='; '.join(r['profile_id']+' RS '+', '.join(v for v in panel['stations'] if v in r['qa']['wet_edges']) for r in wet)
                p('Wet edges on this page: '+locations+'. Review terrain beyond the section and possible bypass. These horizontal water-level lines do not define a two-dimensional inundation boundary.',
                  '本页湿边缘：'+locations+'。需要核查断面外地形及可能的绕流，不能由图中的水平水位线推导二维淹没边界。')
    page('Review findings and next decisions','复核发现与后续决定')
    if not full:compose(d,data,tr,num,full=False)
    issues=(data['diagnostics'] or {}).get('issues',[])
    for code in dict.fromkeys(v['code'] for v in issues):
        subset=[v for v in issues if v['code']==code];labels=ISSUES.get(code,(code,code,'Review the bound native evidence.','复核所绑定的原生证据。'))
        d.add_heading(tr(labels[0],labels[1]),2)
        locations=list(dict.fromkeys((v.get('profile') or tr('All profiles','全部工况'))+(' / RS '+str(v['station']) if v.get('station') is not None else '') for v in subset))
        p(str(len(subset))+' diagnostic entries. Locations: '+'; '.join(locations)+'. '+labels[2],
          str(len(subset))+' 条诊断记录。位置：'+'；'.join(locations)+'。'+labels[3])
        if code=='ENERGY_BALANCE_ERROR':
            residuals=[r['profile_id']+' RS '+v['rs']+': '+num(v['min_error_ft'],3)+' ft' for r in profiles for v in r['qa']['min_error_alerts']]
            if residuals:p('Recorded local minimum-error residuals: '+'; '.join(residuals)+'. This is a numerical diagnostic, not a water-level uncertainty interval.',
                '记录的局部最小能量误差：'+'；'.join(residuals)+'。这是数值诊断值，不是水位误差区间。')
    if not issues:p('The bound detailed diagnostic inventory is unavailable; retain the profile-level QA flags and obtain the complete native warning table.','尚无可核验的详细诊断清单；保留各工况 QA 标记，并补齐完整原生警告表。')
    p('These are workflow review findings, not regulatory acceptance criteria. Review decisions and further calculations must retain the original thresholds and source evidence.',
      '上述属于工作流复核发现，不是法规验收标准。后续复核和计算应保留原始判据及来源证据。')
    d.add_heading(tr('Sensitivity and comparison coverage','敏感性与对比覆盖'),2)
    for comp in data.get('reference_comparisons',[]):
        d.add_heading(tr('Published reference comparison','公开参考结果对比'),2)
        p('Profile '+comp['profile']+'. Recomputed against the hash-bound original published CSV. Agreement at printed precision is not field calibration or engineering acceptance.',
          '工况 '+comp['profile']+'。已与哈希绑定的公开原始 CSV 重新核算。按显示精度吻合不等于现场率定或工程接受。')
        table(d,[tr('Metric / RS / unit','指标 / 河站 / 单位'),tr('Published','公开值'),tr('This run','本次值'),tr('Difference','差值'),tr('Tolerance','容差')],
            [[r['variable']+' / '+r['station']+' / '+r.get('unit',tr('Not recorded','未记录')),num(r['published'],2),num(r['actual'],6),num(r['delta'],6),num(r['tolerance'],5)] for r in comp['rows']],[2.1,1.,1.2,1.2,1.2])
    if data['comparisons']:
        for comp in data['comparisons']:
            table(d,[tr('Profile','工况'),'Δ HW ft',tr('Max matched Δ WSE ft','匹配断面最大水位差 ft')],[[r['profile'],num(r['delta_hw_ft'],3),num(r['max_matched_xs_delta_wse_ft'],3)] for r in comp['rows']],[1.2,2.,3.5])
            p('Candidate minus baseline. This comparison alone does not establish convergence or a sensitivity envelope.', '差值为候选减基线。单次对比本身不能证明收敛或完整敏感性包络。')
            for row in comp['rows']:
                delta=row['delta_hw_ft'];direction=tr('higher','升高') if delta>0 else tr('lower','降低') if delta<0 else tr('unchanged','不变')
                p(row['profile']+': candidate headwater is '+direction+'; absolute change '+num(abs(delta),3)+' ft. Maximum absolute change at matched sections is '+num(row['max_matched_xs_delta_wse_ft'],3)+' ft. Review changed inputs and geometry correspondence before attributing a cause.',
                  row['profile']+'：候选涵前水位'+direction+'，绝对变化 '+num(abs(delta),3)+' ft；匹配断面最大绝对水位差 '+num(row['max_matched_xs_delta_wse_ft'],3)+' ft。归因前须核对输入变化及几何对应关系。')
        if full:
            for fig in plots['comparisons']:picture(fig,'Verified comparison of matched sections','同源核验后的匹配断面水位差对比')
    else:p('No verified sensitivity or refinement comparison is attached. Numerical convergence and a sensitivity envelope are not established here.',
           '本报告未附可核验的敏感性或加密对比，因此不声称已验证数值收敛或建立敏感性包络。')
    if full:
        if g:
            from .physical_geometry import screen
            physical=screen(g)
            page('Geometry screening and survey priorities','几何筛查与补测重点')
            p('These checks inspect the bound input geometry. They do not establish floodplain connectivity or replace native hydraulic diagnostics. Review the location of each finding before changing a section.',
              '以下检查针对所绑定的输入几何，不证明漫滩连通，也不替代原生水力诊断。修改断面前需核对每项发现的位置。')
            for code in dict.fromkeys(i['code'] for i in physical['issues']):
                selected=[i for i in physical['issues'] if i['code']==code];ids=sorted({j for i in selected for j in i['sections']})
                stations=', '.join(str(g['cross_sections'][j].get('rs')) for j in ids)
                p(selected[0]['en']+' '+('RS '+stations if stations else 'Whole reach.'),selected[0]['zh']+' '+('RS '+stations if stations else '全河段。'))
            p('Internal screening controls: low terrain band = 25% of profile relief; minimum low-zone width = 5 ft; adjacent section-width ratio = 2.5; bed-step alert = 20% of the narrower section width. These are review aids, not design criteria or water levels.',
              '内部筛查参数：低地带取剖面起伏的 25%，低区最小宽度 5 ft，相邻断面宽度比 2.5，槽底突变提示取较窄断面宽度的 20%。这些是复核辅助参数，不是设计标准或水位。')
        page('Section result schedule','断面结果明细')
        p('All values below come from the same native calculation. Negative bank freeboard means the calculated water level exceeds the software bank-station elevation; it does not automatically mean roadway overtopping.',
          '以下数值来自同一次原生计算。负岸顶余高表示计算水位高于该软件岸站点高程，并不自动等同于道路越流。')
        for profile in profiles:
            d.add_heading(profile['profile_id'],2)
            table(d,['RS',tr('WSE ft','水位 ft'),tr('EGL ft','能量线 ft'),tr('Channel V ft/s','槽速 ft/s'),'Fr',tr('Left bank margin ft','左岸余高 ft'),tr('Right bank margin ft','右岸余高 ft')],[[r['rs']]+[num(r['profiles'][profile['profile_id']][k],3) for k in ['wse_ft','egl_ft','velocity_fts','froude','left_freeboard_ft','right_freeboard_ft']] for r in data['sections']],[.75,1.,1.,1.,.65,1.15,1.15])
    page('Sources and interpretation','来源与阅读说明')
    p('HW is exterior headwater elevation; TW is exterior tailwater elevation; EGL includes velocity head. RS identifies a river station and is not necessarily measured chainage. Missing values are unavailable rather than zero.',
      'HW 为涵前外部断面水位，TW 为涵后外部断面水位，EGL 为含流速水头的能量线。RS 为河站标识，未必是实测里程。未取得的数值保持缺失，不视为零。')
    p('This report and its figures are generated from the bound summary, native outputs and input snapshots listed in report_data.json. report_manifest.json records the full file hashes. The report-generation time is separate from the solver run.',
      '本报告与图件依据 report_data.json 中列出的同源汇总、原生输出和输入快照生成。report_manifest.json 保存完整文件哈希。报告生成时间与求解时间分别记录。')
    table(d,[tr('Evidence','证据'),tr('Identifier','标识')],[
        [tr('Native run','原生运行'),h['run_id']],['Summary SHA-256',sha(ROOT/data['sources'][0]['path'])],['HDF SHA-256',h['raw_hdf']['sha256']],
        [tr('Elevation basis','高程基准'),str(h['datum'])+' / '+h.get('unit','international ft')]], [1.4,5.3])
    p('All calculations remain subject to the stated input evidence and unresolved hydraulic QA. A reference example is not field calibration. User/reviewing-engineer approval is required for final site interpretation.',
      '计算适用性受所列输入证据及未闭合水力 QA 限制。参考示例不是现场校准；最终现场解释与工程接受由用户及复核工程师决定。')
    if full:
        from . import __version__
        d.add_heading(tr('Report edition and terminology','报告版本与术语'),1)
        p('Generator version '+__version__+'. Edition time UTC '+generated+'. A new edition changes presentation; the cited calculation and its approvals remain separate.',
          '生成器版本 '+__version__+'；本版生成时间 UTC '+generated+'。新版报告更新呈现方式，所引用的计算及其审核记录单独保留。')
        table(d,[tr('Term','术语'),tr('How to interpret it','阅读说明')],[
            ['WSE / EGL',tr('Water surface / energy grade elevation; both need a stated vertical datum.','水面 / 能量线高程；均须明确高程基准。')],
            ['Fr',tr('Channel Froude number; a screening aid for flow regime, not an acceptance result.','主槽 Froude 数，用于辅助判断流态，不是验收结论。')],
            ['Bank station',tr('Main-channel/overbank division in the model; not a flood-protection crest.','模型主槽与漫滩的分界，不是防洪堤顶。')],
            ['Conditional',tr('Uses explicitly reviewed assumptions whose site accuracy is unverified.','采用经明确审核、但现场准确性尚未核实的假设。')]], [1.4,5.3])
    supplement=data.get('native_supplement')
    if supplement:
        page('Supplementary native outputs','补充原生输出')
        if supplement.get('automatic_receipt'):
            p('SteadyReach automatically exported these native HEC-RAS tables from an exclusively owned process. The receipt binds unchanged native inputs and outputs to this run. Group names, geometry, common water/energy levels and independent first-group results were cross-checked. Export did not rerun the solver. Values retain native display precision; blank fields remain unavailable. Rounded group sums do not prove zero road overflow.',
              'SteadyReach 在独占的 HEC-RAS 进程内自动导出这些原生表格，导出记录将未改变的原生输入与输出绑定到本次运行。已交叉核对孔组名称、几何、公共水位／能量线及独立首组结果。导出操作未重新求解；数值保留原生显示精度，空白仍为未取得。四舍五入孔组流量合计不能证明道路越流为零。')
        else:
            p('These user-supplied native text exports were checked against this run’s geometry, water/energy levels and independent first-group outputs. Text has no embedded run hash; correct run selection still relies on the user. No new solver run. Blanks remain unavailable; rounded group sums do not prove zero road overflow.',
              '这些用户提供的原生文本已与本次几何、水位／能量线及独立首组输出交叉核对。文本自身无运行哈希，正确选择运行仍依赖用户。本次未重新求解；空白仍为未取得，四舍五入孔组流量合计不能证明道路越流为零。')
        table(d,['Profile','Group','Q cfs','V US ft/s','V DS ft/s','Control'],[[r['profile'],r['native_group'],num(r['flow_cfs']),num(r['inlet_velocity_fts']),num(r['outlet_velocity_fts']),r['control']] for r in supplement['rows']],[.8,1.2,1.1,1.1,1.1,1.4])
        p('Warning coverage: '+supplement['warning_scope'],'警告覆盖范围：'+supplement['warning_scope'])
        if supplement.get('display_differences'):
            p('The following native display values differ from machine output by more than half a 0.01 display unit. They remain OPEN QA items, not passed comparisons. Both values are retained; differences larger than one display unit or blank/value conflicts prevent automatic import.',
              '以下原生显示值与机器输出的差异超过 0.01 显示单位的一半，保留为未关闭 QA 项，不记为核对通过。两个数值均保留；超过一个显示单位或空白／有值冲突会阻止自动导入。')
            table(d,[tr('Profile / group','工况／孔组'),tr('Field','字段'),tr('Native display','原生显示'),tr('Machine value','机器值'),tr('Difference','差值')],
                [[r['profile']+' / '+str(r['group_id']+1),r['field'],str(r['native_display']),f"{r['machine_value']:.6f}",f"{r['difference']:.6f}"] for r in supplement['display_differences']],[1.2,1.6,1.1,1.4,1.4])
        if supplement['missing_groups']:p('Unexported group/profile tables: '+str(supplement['missing_groups']),'尚未取得的组／工况表：'+str(supplement['missing_groups']))
        if full and supplement['warnings']:
            for row in supplement['warnings']['records']:
                d.add_heading(row['profile']+' · RS '+row['station']+' · '+row['severity'],2);d.add_paragraph(row['text'])
        p('Hydraulic QA remains open. Source files are included in the Complete package.','水力 QA 保持待复核。原始文本保存在完整交付包。')
    if details:detail_appendix(d,details,cn)
    from .report_navigation import finish
    return finish(d,cn,full)


def generate(summary_path,folder,culvert_details=None,comparisons=(),context=None):
    from .report import render
    from .report_data import collect, figures
    summary_path=safe_path(ROOT,summary_path);folder=safe_path(ROOT,folder)
    if folder.exists() and any(folder.iterdir()):raise ValueError('Report output must be a new or empty directory')
    data=collect(summary_path,comparisons);folder.mkdir(parents=True,exist_ok=True)
    from .report_context import attach
    attach(data,summary_path,context)
    plots=figures(data,folder/'figures')
    plots['zh-CN']=figures(data,folder/'figures'/'zh-CN','zh-CN')
    save(folder/'report_data.json',data);save(folder/'figure_manifest.json',plots)
    details=None
    if culvert_details:
        from .culvert_details import validate
        details=validate(culvert_details,summary_path)
    from . import __version__
    manifest=dict(summary=item(summary_path,'sole_report_data'),schema_version='readable_reports_2.2',created_utc=utc(),generator_version=__version__,edition=folder.name,
        data=item(folder/'report_data.json'),figures=item(folder/'figure_manifest.json'),visual_review='PENDING_HUMAN_PAGE_REVIEW',reports=[],
        supplementary_sources=data['sources'],language_review=data.get('language_review',[]),new_solver_calls_by_report=0)
    if details:manifest['supplementary_sources']+=[item(culvert_details)]+details['sources']
    for language,detail,name in REPORT_VARIANTS:
        builder=build
        if data['summary']['hydraulics'].get('model_type')=='river':
            from .river_report import build as builder
        path=folder/(name+'.docx');builder(data,plots.get(language,plots),folder,language,detail,details).save(path)
        pdf,n,pages=render(path)
        manifest['reports'].append(dict(language=language,detail=detail,docx=item(path),pdf=item(pdf),pages=n,rendered_pages=[item(p) for p in pages],render_evidence=item(path.parent/'qa'/path.stem/'render_manifest.json')))
    manifest['figure_files']=[item(p) for p in sorted((folder/'figures').rglob('*.png'))]
    save(folder/'report_manifest.json',manifest)
    return manifest
