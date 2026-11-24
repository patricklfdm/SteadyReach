"""First-page handoff from the same sealed data used for the report tables."""
from .common import finite


def sensitivity_peak(data):
    from .river_review import response
    studies=[p for p in data.get('studies') or [] if 'cases' in p and 'comparisons' in p]
    rows=response(studies)
    return max(rows,key=lambda r:abs(r['signed_peak_ft']),default=None)


def add(document,data,cn):
    s=data['summary'];h=s['hydraulics']
    tr=lambda en,zh:zh if cn else en
    document.add_heading(tr('Scope and decision','用途与复核决定'),2)
    decision=data.get('purpose_decision')
    if decision:
        lang='zh' if cn else 'en'
        document.add_paragraph(decision[lang])
        for row in decision['rows']:
            document.add_paragraph(row[lang])
        if (decision['criteria'] or {}).get('basis'):
            document.add_paragraph(tr('Project basis','项目依据')+' · '+decision['criteria']['basis'])
        document.add_paragraph(decision['note_'+lang])
    run=h.get('run_id')
    qa=h.get('hydraulic_qa_status') or tr('Pending review','待复核')
    document.add_paragraph((tr('Run ','运行 ')+run+'  ·  ' if run else '')+tr('Hydraulic QA ','水力 QA ')+str(qa))
    if s['configuration'].get('case_kind')=='software_validation':
        document.add_paragraph(tr('Use for software regression with the stated reference inputs.','可用于给定参考输入的软件回归。'))
        return
    document.add_paragraph(tr('Use these profiles to review water levels at the modeled flows and compare alternatives. Engineering acceptance requires review of the site evidence and the accuracy needed for the intended use.',
                              '可据此核对指定流量下的水位、比较备选方案。工程接受取决于场地资料及拟定用途所需精度。'))
    if h.get('channel_geometry_basis')=='conditional_surface_dem':
        document.add_paragraph(tr('Material assumption: surface DEM elevations stand in for the submerged channel. Verify channel bathymetry at the controlling sections.',
                                  '重要假设为使用地表 DEM 近似水下河床。请核对控制断面的河床测量。'))
    else:
        key='channel_geometry_basis'
        if h.get(key) in ('surveyed_channel','combined_survey_and_dem'):
            document.add_paragraph(tr('Check the survey dates, bed elevations and boundary stage transfer against the event being assessed.',
                                      '请按待评估事件核对测量日期、河床高程及边界水位传递。'))
    diag=data.get('diagnostics')
    if diag:
        severe=sorted(diag.get('issues',[]), key=lambda r:({'ERROR':0,'WARNING':1}.get(str(r.get('severity')).upper(),2)))
        stations=list(dict.fromkeys(str(a['station']) for a in severe if a.get('station') is not None))
        if stations:
            document.add_paragraph(tr('Start hydraulic review at ','优先核对 ')+', '.join('RS '+r for r in stations[:3])+tr('. See the grouped findings for the full station list.','。完整站号见分组检查结果。'))
    river_checks=data.get('river_checks') or {}
    if river_checks.get('screen') or river_checks.get('events'):
        from .river_observations import holdout_stages
        measured,missing,exceeds=holdout_stages(river_checks.get('events',[]))
        if measured:
            row=max(measured,key=lambda r:abs(r['residual_ft']))
            text=tr('Largest modeled minus observed stage in registered holdouts','已登记留出事件中最大的计算减实测水位差')
            text+=f" · {row['date']} · RS {row['location']['rs']} · {row['residual_ft']:+.3f} ft"
            text+=tr(f" (n = {len(measured)}).",f"（共 {len(measured)} 笔可比读数）。")
            if missing:
                text+=tr(f" Readings without stated vertical uncertainty: {len(missing)}.",f"其中 {len(missing)} 笔缺少垂直测量不确定度。")
            if exceeds:
                text+=tr(f" Readings outside the stated measurement uncertainty: {len(exceeds)}.",f"其中 {len(exceeds)} 笔偏差超过所填测量不确定度。")
            document.add_paragraph(text)
        else:
            document.add_paragraph(tr('Field observations are registered. A comparable held-out event stage is still needed.',
                                      '已登记现场资料，仍需可比的留出事件水位。'))
    comparison=river_checks.get('extent_review') or {}
    change=comparison.get('max_wse_change')
    if change:
        document.add_paragraph(tr('Largest change between the two selected runs','所选两个版本的最大水位变幅')+
                               f" · RS {change['station']} · {change['signed_ft']:+.3f} ft")
    peak=sensitivity_peak(data)
    if peak:
        document.add_paragraph(tr('Largest tested parameter sensitivity','已测试参数中的最大水位变幅')+
            f" · {peak['profile']} / {peak['case']} · RS {peak['peak_rs']} · {peak['signed_peak_ft']:+.3f} ft")
    elif not change:
        document.add_paragraph(tr('Site sensitivity has yet to be quantified in this edition.','本版尚无可量化的场地敏感性结果。'))
    decision=comparison.get('decision')
    if decision:
        labels={'request_survey':('Field survey requested','已登记补测'),'keep_first':('First run retained','保留首个计算'),
                'defer':('Decision deferred','暂缓取舍'),'prefer_second':('Second run preferred','倾向第二方案')}
        document.add_paragraph(tr(*labels[decision['choice']])+' · RS '+decision['station']+' · '+
                               (decision.get('preferred_run') or decision['reference_run']))
        if decision.get('reason'):document.add_paragraph(decision['reason'])
    revision=data.get('revision_comparison') or {}
    context=revision.get('input_context') or {}
    if context.get('status')=='VERIFIED':
        updates=', '.join(r['field'] for r in context['input_changes'][:3])
        count=context['geometry']['changed_sections']
        row=max((r for r in revision['cross_sections'] if r.get('location_status')=='SAME_CENTER' and finite(r.get('change'))),
                key=lambda r:abs(r['change']),default=None)
        message=tr('Reissue compared with its parent','本次重发与父版本对比')+' · '+str(count)+tr(' shared sections with geometry changes',' 个共有断面几何有变更')
        if updates:message+=' · '+updates
        if row:message+=tr(' · largest same-center WSE change',' · 同位置最大水位变化')+f" {row['change']:+.3f} ft @ RS {row['station']} ({row['profile']})"
        document.add_paragraph(message)
    if h.get('model_type')=='culvert':
        document.add_paragraph(tr('Check the source of the opening sizes, barrel lengths and invert elevations before using the computed headwater or overtopping results.',
                                  '引用涵前水位或道路漫顶结果前，请核对开口尺寸、涵长及两端涵底的原始依据。'))
