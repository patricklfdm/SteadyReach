"""Bilingual river-only reports using the same verified data and render pipeline."""
import re
from collections import Counter
from pathlib import Path
from docx.shared import Inches
from .common import ROOT, sha
from .report import document, table
from .report_navigation import finish


def roughness_text(value):
    if value is None:
        return '—'
    return f'{value:.7f}'.rstrip('0').rstrip('.')


def build(data, plots, folder, language='en', detail='full', details=None):
    cn=language=='zh-CN';full=detail=='full';tr=lambda en,zh:zh if cn else en
    translations={
        'COMPUTED':'已完成计算','CONDITIONAL_UNVERIFIED':'条件性输入，未独立核实',
        'REVIEW_REQUIRED':'待复核','NOT_ASSESSED':'未评定',
        'mixed':'混合流','subcritical':'缓流','supercritical':'急流',
        'conditional_surface_dem':'地表 DEM 条件性近似','surveyed_channel':'实测河槽',
        'combined_survey_and_dem':'河槽测量与 DEM 组合','normal_depth':'正常水深',
        'known_stage':'已知水位',
        'cross_sections':'断面数',
        'boundary_slopes.downstream':'下游正常水深坡降',
        'boundary_slopes.upstream':'上游正常水深坡降',
        'Entered by the local user for this computation; not independently verified.':'本次由用户填写或采用，未经独立核实。',
    }
    localized=lambda v:translations.get(v,v) if cn else v
    s=data['summary'];h=s['hydraulics'];g=data.get('geometry') or {};c=s['configuration']
    scenario=next(v for v in c['scenarios'] if v['id']==h['scenario_id'])
    title=c['title']
    revisions=re.search(r'(?: · revision)+(?= / coverage repair \d+$|$)',title)
    if revisions:
        count=revisions.group().count(' · revision')
        title=title[:revisions.start()]+tr(' Revision ', ' 修订 ')+str(count)+title[revisions.end():]
    d=document(title+tr(' River Reach Analysis',' 河段水力分析'))
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
        [tr('Calculation','计算执行'),localized(h['calculation_status'])],
        [tr('Input adequacy','输入充分性'),localized(h['input_adequacy_status'])],
        [tr('Hydraulic QA','水力 QA'),localized(h['hydraulic_qa_status'])],
        [tr('Engineering acceptance','工程接受'),localized(h['engineering_acceptance_status'])]],[1.8,4.9])
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
    from .report_content import ISSUES, native_input_tables, value as number_text
    labels=dict(ISSUES)
    labels.update({
        'NATIVE_CRITICAL_DEPTH_FALLBACK': ISSUES['CRITICAL_DEPTH_FALLBACK'],
        'NATIVE_ENERGY_NOT_BALANCED': ISSUES['ENERGY_BALANCE_ERROR'],
        'NATIVE_LARGE_ENERGY_LOSS': ('Large energy loss','能量损失较大','Review local geometry, spacing and flow paths.','复核局部几何、断面间距及过流路径。'),
        'NATIVE_VELOCITY_HEAD_CHANGE': ('Large velocity-head change','流速水头变化较大','Review section transitions and active conveyance.','复核断面过渡和有效过流范围。'),
        'NATIVE_UNCLASSIFIED_MESSAGE': ('Other native message','其他原生提示','Read the complete native warning text and assess its hydraulic significance.','阅读完整原生警告文本，判断其水力意义。'),
    })
    d.add_heading(tr('Checks requiring attention','待处理检查'),1)
    p(str(len(issues))+' open diagnostic items are recorded. Numerical completion does not close engineering review.',
      '记录了 '+str(len(issues))+' 项未闭合诊断。数值计算完成不代表工程复核闭合。')
    if issues:
        counts=Counter(v['code'] for v in issues)
        rows=[]
        for code,count in counts.items():
            label=labels.get(code,(code,code,'Review the complete native evidence.','复核完整原生证据。'))
            stations=', '.join(dict.fromkeys(str(v.get('station') or '—') for v in issues if v['code']==code))
            rows.append([tr(label[0],label[1])+' ('+str(count)+')',stations,tr(label[2],label[3])])
        if full:
            table(d,[tr('Finding and count','问题及条数'),'RS',tr('Next action','后续动作')],rows,[1.8,1.55,3.35])
        else:
            p('See the full report for grouped findings, affected sections and actions.','分组问题、受影响断面及处理建议见完整报告。')
        p('Automated diagnostics can overlap with native warnings. The item count is not a count of independent defects. Preserve and review the full native warning text.',
          '自动诊断可能与原生警告重复，条数不等于独立缺陷数；应保留并复核完整原生警告文本。')
    else:p('No issues were returned by the implemented checks. Calibration, boundary sensitivity and engineering interpretation remain separate requirements.',
           '已实施检查未返回问题；校准、边界敏感性及工程判断仍需分别完成。')
    d.add_heading(tr('Interpretation and next steps','解释与后续步骤'),1)
    p('Confirm channel survey and present bed conditions, discharge applicability, roughness, boundary influence and section-spacing sensitivity. A 1D steady model does not reproduce the time history of a flood or a two-dimensional floodplain velocity field.',
      '需确认河槽测量及现状河床、流量适用性、糙率、边界影响和断面间距敏感性。一维恒定流模型不能还原洪水随时间变化过程或二维漫滩流速场。')
    coverage_studies=[study for study in data.get('studies',[]) if study.get('coverage')]
    studies=[study for study in data.get('studies',[]) if not study.get('coverage')]
    d.add_heading(tr('Completed sensitivity tests','已完成的敏感性测试'),1)
    if studies:
        sensitivity=[]
        for study_index,study in enumerate(studies,1):
            for comparison in study['comparisons']:
                case=next(v for v in study['cases'] if v['id']==comparison['case'])
                changes=tr('Study '+str(study_index),'第 '+str(study_index)+' 批')+' / '+'; '.join(localized(v['path'])+': '+str(v['before'])+' → '+str(v['after']) for v in case['changes'])
                for profile in comparison['rows']:
                    delta=[v for v in comparison['cross_section_differences'] if v['profile']==profile['profile']]
                    largest=max(delta,key=lambda v:abs(v['delta_wse_ft']))
                    magnitude=abs(largest['delta_wse_ft'])
                    sensitivity.append([changes,profile['profile'],f'{magnitude:.6f}',largest['station'] if magnitude else tr('All unchanged','全部不变')])
        table(d,[tr('Changed input','变更输入'),tr('Profile','工况'),tr('Max |ΔWSE| ft','最大 |Δ水位| ft'),'RS'],sensitivity,[3.15,.7,1.4,1.45])
        p('Only completed studies tied to this exact baseline are included. Comparisons were recalculated from hashed native results. Each study baseline reproduces the report water levels. These ranges are conditional tests, not measured confidence intervals. No boundary case is automatically adopted and hydraulic QA remains open.',
          '仅纳入绑定本次基准的已完成测试。差值已按哈希校验的原生结果重新计算，各测试基准重现本报告水位。范围属于条件性测试，不是实测置信区间；不自动采用任何边界方案，水力 QA 仍待闭合。')
        for study_index,study in enumerate(studies,1):
            convergence=study.get('convergence')
            if not convergence:continue
            d.add_heading(tr('Nested section-spacing assessment','嵌套断面加密评估')+' '+str(study_index),2)
            status=tr('Stable at the workflow threshold','达到工作流阈值') if convergence['status']=='STABLE_AT_REVIEW_THRESHOLD' else tr('Convergence remains open','收敛仍待处理')
            excluded=study.get('excluded_intervals',[])
            if excluded:
                locations=', '.join(str(v['upstream_rs'])+'–'+str(v['downstream_rs']) for v in excluded)
                p('Unrefined intervals requiring direction review include RS '+locations+'. Full-reach spacing coverage remains incomplete.',
                  '需复核方向且未加密的区间包括 RS '+locations+'，全河段加密覆盖尚未完整。')
            p(status+'. Both consecutive refinements are checked at every retained section using native water levels.',
              status+'。连续两级加密均采用原生水位核对全部保留断面。')
            table(d,[tr('Profile','工况'),tr('First max |ΔWSE| ft','第一级最大 |Δ水位| ft'),tr('Second max |ΔWSE| ft','第二级最大 |Δ水位| ft')],
                [[r['profile']]+[f'{v:.6f}' for v in r['last_two_max_xs_deltas_ft']] for r in convergence['rows']],[1.1,2.8,2.8])
            table(d,[tr('Case','工况'),tr('Sections','断面数'),tr('Native messages','原生信息'),tr('Wet-end sections','湿端断面数')],
                [[case['id'],case['section_count'],case['diagnostics'].get('native_messages'),len(case['wet_sections'])] for case in study['cases']],[2.1,1.1,1.75,1.75])
            p('The internal threshold is '+str(convergence['threshold_ft'])+' ft. Coverage is limited to the selected refinement intervals. Added elevations were sampled from the same DEM and added banks were inferred from neighboring sections. Hydraulic warnings and physical applicability remain open.',
              '内部阈值为 '+str(convergence['threshold_ft'])+' ft，结论限于所选加密区间。新增高程从同一 DEM 采样，新增岸站按相邻断面推定。水力警告与物理适用性仍需复核。')
    else:
        p('No completed sensitivity study is bound to this exact baseline. Tests from prior geometry revisions are not reused.',
          '未发现绑定本次基准的已完成敏感性测试；不沿用旧几何修订版的测试结果。')
    for batch in coverage_studies:
        result=batch['coverage']
        d.add_heading(tr('Automatic section-extent repair','断面范围自动修订'),1)
        states={
            'COVERAGE_RESOLVED_REVIEW_REQUIRED':tr('Computed section ends are dry. Hydraulic review remains open.','计算断面端点均已高于水位，水力复核继续待完成。'),
            'ROUND_LIMIT_REQUIRES_REVIEW':tr('The confirmed round limit was reached with wet ends remaining.','已达到确认轮数上限，仍有湿端待处理。'),
            'GEOMETRY_REVIEW_REQUIRED':tr('A further feasible fixed-direction extension requires geometry review.','继续处理需要复核几何，现有方向下可采用延伸已用尽。'),
            'INCOMPLETE':tr('The calculation batch is incomplete.','计算批次尚未完成。')}
        d.add_paragraph(states.get(result['status'],result['status']))
        p('The saved baseline was reused. Each repair uses actual preceding water levels and DEM exterior samples within the confirmed width and round bounds. Existing interior samples, bank plan positions and hydraulic controls were verified. Exterior overbank roughness and floodplain connectivity remain conditional.',
          '采用已保存的真实基准。每轮修订依据上轮实际水位，在已确认宽度和轮数范围内补充 DEM 端部采样。已核验原内部采样、岸站实际位置和水力控制。新增漫滩糙率及过流连通性仍属条件性解释。')
        table(d,[tr('Case','工况'),tr('Wet sections','湿端断面'),tr('Native messages','原生信息'),tr('Max successive |ΔWSE| ft','逐轮最大 |Δ水位| ft')],
            [[tr('Saved baseline','已保存基准') if row['id']=='saved_baseline' else row['id'],
              len(row['wet_sections']) if 'wet_sections' in row else '—',
              row.get('diagnostics',{}).get('native_messages','—'),n(row.get('max_wse_change_ft'))] for row in result['cases']],
            [1.6,1.2,1.3,2.6])
    if full:
        if coverage_studies and not d.paragraphs[-1].text:
            spacer=d.paragraphs[-1]._p
            spacer.getparent().remove(spacer)
        d.add_page_break();d.add_heading(tr('Inputs and model extent','输入与模型范围'),1)
        loc=c.get('location') or {}
        table(d,[tr('Input','输入'),tr('Adopted value','采用值')],[
            [tr('Site marker latitude longitude','位置标记纬度与经度'),str(loc.get('latitude'))+', '+str(loc.get('longitude'))],
            [tr('Horizontal CRS','平面坐标系'),g.get('horizontal_crs',c.get('delivery',{}).get('horizontal_crs','See native input'))],
            [tr('Vertical datum','高程基准'),h['datum']],
            [tr('Flow regime','流态'),localized(h.get('flow_regime'))],
            [tr('Channel representation','河槽表示'),localized(h.get('channel_geometry_basis'))],
            [tr('Section count','断面数'),len(data['sections'])],
            [tr('Channel Manning n','主槽 Manning n'),roughness_text(scenario.get('channel_n'))],
            [tr('Overbank Manning n','漫滩 Manning n'),roughness_text(scenario.get('overbank_n'))]],[2.0,4.7])
        for side in ('upstream','downstream'):
            b=(h.get('boundaries') or {}).get(side,{})
            if side=='upstream' and h.get('flow_regime')=='subcritical':continue
            value=(h.get('boundary_slopes') or {}).get(side) if b.get('type')=='normal_depth' else b.get('stages_ft')
            p(side.title()+' boundary: '+str(b.get('type'))+'; '+str(value)+(' ft/ft' if b.get('type')=='normal_depth' else ' ft WSE in profile order'),
              ('上游' if side=='upstream' else '下游')+'边界：'+str(localized(b.get('type')))+'；'+str(value)+(' ft/ft' if b.get('type')=='normal_depth' else ' ft，按工况顺序的绝对水位'))
        table(d,[tr('Profile','工况'),'Q cfs',tr('Source','来源')],[[v['id'],n(v['flow_cfs']),str(localized(v.get('source')))] for v in scenario['profiles']],[1.2,1.,4.5])
        p('Roughness basis: '+str(scenario.get('parameter_source')),'糙率依据：'+str(localized(scenario.get('parameter_source'))))
        d.add_heading(tr('Native input readback','原生输入回读'),2)
        if data.get('native_inputs'):
            native_input_tables(d,data['native_inputs'],tr,lambda v,digits=2:number_text(v,digits,cn))
        else:
            p('Native input appendix unavailable: '+str(data.get('native_input_error')),
              '原生输入附录未取得：'+str(data.get('native_input_error')))
        if plots.get('terrain',{}).get('image'):
            d.add_heading(tr('Terrain and reach location','地形与河段位置'),1)
            picture(plots['terrain']['image'],tr('Terrain and model sections from the bound inputs. Ground elevation is not inundation.','由本次绑定输入绘制的地形与模型断面，地面高程不代表淹没范围。'))
    if full:d.add_page_break()
    d.add_heading(tr('Water surface profile','水面线'),1)
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
        p('Full paths and SHA-256 hashes, including study cases, are retained in report_data.json and the report manifest. Short names below are an index, not substitutes for those identifiers.',
          '完整路径、SHA-256 及敏感性工况证据保留在 report_data.json 和报告清单中；下列短文件名仅供索引。')
        table(d,[tr('Evidence','证据'),tr('Recorded source','来源文件')],[[v.get('role','source'),Path(v['path']).name] for v in data['sources'][:15]],[2.4,4.3])
        for study in studies+coverage_studies:
            p('Sensitivity evidence: '+study['analysis']['path'],'敏感性证据：'+study['analysis']['path'])
    # A trailing spacer paragraph after the final table can spill to a blank page.
    while d.paragraphs and not d.paragraphs[-1].text and not d.paragraphs[-1]._p.xpath('.//w:drawing|.//w:br'):
        node=d.paragraphs[-1]._p
        if node.getnext() is not d._element.body.sectPr:break
        node.getparent().remove(node)
    return finish(d,cn,full)
