"""Bilingual river-only reports using the same verified data and render pipeline."""
from docx.shared import Inches
from .common import ROOT, sha
from .report import document, table
from .report_navigation import finish


def build(data, plots, folder, language='en', detail='full', details=None):
    cn=language=='zh-CN';full=detail=='full';tr=lambda en,zh:zh if cn else en
    s=data['summary'];h=s['hydraulics'];g=data.get('geometry') or {};c=s['configuration']
    scenario=next(v for v in c['scenarios'] if v['id']==h['scenario_id'])
    d=document(c['title']+tr(' River Reach Analysis',' 河段水力分析'))
    d.core_properties.language='zh-CN' if cn else 'en-US'
    n=lambda v:'—' if v is None else f'{v:.3f}'
    def p(en,zh):d.add_paragraph(tr(en,zh))
    def picture(entry,caption):
        d.add_picture(str(ROOT/entry['path']),width=Inches(6.65))
        d.paragraphs[-1].paragraph_format.keep_with_next=True
        d.add_paragraph(caption,'Caption')
    p('One-dimensional steady flow in a single river reach. HEC-RAS completed the calculation; hydraulic QA, input adequacy and engineering acceptance are reported separately.',
      '本报告为单一河段的一维恒定流分析。HEC-RAS 已完成计算，水力 QA、输入充分性和工程接受状态分别列示。')
    if c['case_kind']=='software_validation':
        p('SOFTWARE VERIFICATION ONLY. Geometry and flows are synthetic numerical test inputs. These results do not describe Pagosa Springs or any real site.',
          '仅用于软件验证。几何与流量为合成数值测试输入，结果不代表 Pagosa Springs 或任何实际场地。')
    table(d,[tr('Assessment','判断层次'),tr('Status','状态')],[
        [tr('Calculation','计算执行'),h['calculation_status']],
        [tr('Input adequacy','输入充分性'),h['input_adequacy_status']],
        [tr('Hydraulic QA','水力 QA'),h['hydraulic_qa_status']],
        [tr('Engineering acceptance','工程接受'),h['engineering_acceptance_status']]],[1.8,4.9])
    d.add_heading(tr('Results at a glance','主要结果'),1)
    table(d,[tr('Profile','工况'),'Q cfs',tr('Upstream WSE ft','上端水位 ft'),tr('Downstream WSE ft','下端水位 ft'),tr('Max channel V ft/s','最大主槽流速 ft/s')],
        [[v['profile_id'],n(v['flow_cfs']),n(v['metrics']['upstream_wse_ft']),n(v['metrics']['downstream_wse_ft']),n(v['metrics']['max_channel_velocity_fts'])] for v in h['profiles']],
        [1.15,.85,1.5,1.5,1.7])
    p('Water levels use '+str(h['datum'])+' and international feet. The endpoint values refer to the first and last modeled cross sections. They are not water levels inside the excluded bridges.',
      '水位采用 '+str(h['datum'])+' 高程基准、国际英尺单位。上端及下端数值分别对应模型第一条和最后一条断面，不是被排除桥梁内部的水位。')
    p('The modeled reach excludes bridge structures. A boundary placed next to a bridge can still be influenced by its backwater; boundary elevations or slopes must have a defensible basis.',
      '模型不包含桥梁结构。靠近桥梁的边界仍可能受壅水影响，边界水位或坡降必须有适用依据。')
    if h.get('channel_geometry_basis')=='conditional_surface_dem':
        p('Channel geometry uses a conditional surface-DEM approximation. Hydroflattened water surfaces do not resolve submerged bed elevations. Obtain channel survey data before using this model for design conclusions.',
          '河槽采用地表 DEM 条件性近似。水面平整化地形不能表达水下河床高程，形成设计结论前需补充河槽测量。')
    qa=data.get('diagnostics') or {};issues=qa.get('issues',[])
    d.add_heading(tr('Checks requiring attention','待处理检查'),1)
    p(str(len(issues))+' open diagnostic items are recorded. Numerical completion does not close engineering review.',
      '记录了 '+str(len(issues))+' 项未闭合诊断。数值计算完成不代表工程复核闭合。')
    if issues:
        table(d,[tr('Profile and station','工况与断面'),tr('Finding','问题'),tr('Next action','后续动作')],
            [[str(v.get('profile') or 'All')+' / '+str(v.get('station') or '—'),v['code'],v.get('recommended_action','Review native output')] for v in issues[:(100 if full else 4)]],[1.15,1.9,3.65])
        if not full and len(issues)>4:p('The full report lists the remaining diagnostics.','其余诊断见完整报告。')
    else:p('No issues were returned by the implemented checks. Calibration, boundary sensitivity and engineering interpretation remain separate requirements.',
           '已实施检查未返回问题；校准、边界敏感性及工程判断仍需分别完成。')
    d.add_heading(tr('Interpretation and next steps','解释与后续步骤'),1)
    p('Confirm channel survey and present bed conditions, discharge applicability, roughness, boundary influence and section-spacing sensitivity. A 1D steady model does not reproduce the time history of a flood or a two-dimensional floodplain velocity field.',
      '需确认河槽测量及现状河床、流量适用性、糙率、边界影响和断面间距敏感性。一维恒定流模型不能还原洪水随时间变化过程或二维漫滩流速场。')
    if full:
        d.add_page_break();d.add_heading(tr('Inputs and model extent','输入与模型范围'),1)
        loc=c.get('location') or {}
        table(d,[tr('Input','输入'),tr('Adopted value','采用值')],[
            [tr('Site marker latitude longitude','位置标记纬度与经度'),str(loc.get('latitude'))+', '+str(loc.get('longitude'))],
            [tr('Horizontal CRS','平面坐标系'),g.get('horizontal_crs',c.get('delivery',{}).get('horizontal_crs','See native input'))],
            [tr('Vertical datum','高程基准'),h['datum']],
            [tr('Flow regime','流态'),h.get('flow_regime')],
            [tr('Channel representation','河槽表示'),h.get('channel_geometry_basis')],
            [tr('Section count','断面数'),len(data['sections'])],
            [tr('Channel Manning n','主槽 Manning n'),n(scenario.get('channel_n'))],
            [tr('Overbank Manning n','漫滩 Manning n'),n(scenario.get('overbank_n'))]],[2.0,4.7])
        for side in ('upstream','downstream'):
            b=(h.get('boundaries') or {}).get(side,{})
            if side=='upstream' and h.get('flow_regime')=='subcritical':continue
            value=(h.get('boundary_slopes') or {}).get(side) if b.get('type')=='normal_depth' else b.get('stages_ft')
            p(side.title()+' boundary: '+str(b.get('type'))+'; '+str(value)+(' ft/ft' if b.get('type')=='normal_depth' else ' ft WSE in profile order'),
              ('上游' if side=='upstream' else '下游')+'边界：'+str(b.get('type'))+'；'+str(value)+(' ft/ft' if b.get('type')=='normal_depth' else ' ft，按工况顺序的绝对水位'))
        table(d,[tr('Profile','工况'),'Q cfs',tr('Source','来源')],[[v['id'],n(v['flow_cfs']),str(v.get('source'))] for v in scenario['profiles']],[1.2,1.,4.5])
        p('Roughness basis: '+str(scenario.get('parameter_source')),'糙率依据：'+str(scenario.get('parameter_source')))
        if plots.get('terrain',{}).get('image'):
            d.add_page_break();d.add_heading(tr('Terrain and reach location','地形与河段位置'),1)
            picture(plots['terrain']['image'],tr('Terrain and model sections from the bound inputs. Ground elevation is not inundation.','由本次绑定输入绘制的地形与模型断面，地面高程不代表淹没范围。'))
    d.add_page_break();d.add_heading(tr('Water surface profile','水面线'),1)
    picture(plots['longitudinal'],tr('Computed water surface, energy grade and channel Froude number. Section order is not a distance scale.','计算水位、能量线及主槽弗劳德数，断面顺序不代表距离比例。'))
    if full:
        d.add_heading(tr('Cross section results','断面结果'),1)
        for v in h['profiles']:
            d.add_heading(v['profile_id'],2)
            table(d,['RS','WSE ft','EGL ft','V ft/s','Fr'],[[r['rs']]+[n(r['profiles'][v['profile_id']][k]) for k in ('wse_ft','egl_ft','velocity_fts','froude')] for r in data['sections']],[1.1,1.4,1.4,1.4,1.4])
        for panel in plots['sections']:
            d.add_page_break();picture(panel['image'],tr('Section ground, selected banks and calculated water surfaces.','断面地形、已选岸站及计算水位。'))
        d.add_page_break();d.add_heading(tr('Evidence and reproducibility','证据与复现'),1)
        p('Run: '+h['run_id'],'运行标识：'+h['run_id'])
        p('HEC-RAS output SHA-256: '+h['raw_hdf']['sha256'],'HEC-RAS 输出 SHA-256：'+h['raw_hdf']['sha256'])
        p('Raw result: '+h['raw_hdf']['path'],'原始结果：'+h['raw_hdf']['path'])
        p('Input snapshots, parameter confirmation and the source manifest preserve the adopted values and their origin. Open the native project to inspect all geometry and warnings.',
          '输入快照、参数确认及来源清单保留采用值与来源，可打开原生工程检查完整几何和警告。')
        table(d,[tr('Evidence','证据'),tr('Recorded source','来源文件')],[[v.get('role','source'),v['path']] for v in data['sources'][:20]],[1.2,5.5])
    return finish(d,cn,full)
