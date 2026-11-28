"""Current-run delivery uses, ordered by verified prerequisites. Read only."""
from collections import Counter

from .common import ROOT, digest, finite, intact, item, read, safe_path, unique_id, utc
from .result_guidance import BALANCE, NATIVE_GAPS, WET, text
from .revision_inputs import station_key
from .river_review import response

RULE_VERSION = 9
LEVELS = [
    text('Evidence insufficient', '计算证据不足'),
    text('Internal diagnosis', '可供内部诊断'),
    text('Conditional engineering review', '可有条件交工程师复核'),
    text('Technical package ready for sign-off review', '技术资料可提交签审'),
]
USE_GUIDE = [
    (text('Identify the missing run evidence and restore the matching files.', '定位缺失的计算证据，恢复与本次运行匹配的文件。'),
     text('Water levels, velocities and maps need a verified calculation before interpretation.', '待本次计算得到核验，再解读水位、流速和地图。')),
    (text('Use the model internally to trace warnings, compare inputs and plan measurements.', '在团队内部核查警告、对照输入，确定补测位置。'),
     text('Hold external flood levels, capacity and design decisions until the controlling gaps below are resolved.', '对外引用洪水位、判断过流能力和设计取值，须先解决下列限制。')),
    (text('Send the model and reports to an engineer for conditional technical review, with the assumptions and study limits attached.', '可将模型和报告连同假设、研究范围交给工程师做条件性技术复核。'),
     text('Design adoption and sign-off still require resolution or documented acceptance of the outstanding limitations.', '设计取值和签发须由负责工程师处理仍存的限制并记录适用条件。')),
    (text('Submit this exact technical package and evidence to the responsible engineer for sign-off review.', '可将本版本技术包和证据提交负责工程师签审。'),
     text('Release for the stated design purpose requires the responsible engineer’s approval.', '按拟定设计用途正式出具成果，仍需负责工程师签发。')),
]

FULL = {'ALL_COMPUTED_PROFILES_VERIFIED_SINGLE_REACH', 'ALL_REQUESTED_PROFILES_USER_CONFIRMED',
        'EXPORTED_SCOPE_OPERATOR_ATTESTED'}
EVIDENCE_ERRORS = (ValueError, OSError, KeyError, TypeError)


def finding(code, ceiling, target, en, zh, **facts):
    return dict(code=code, ceiling=ceiling, target=target, reason=text(en, zh), facts=facts)


def classify(findings):
    level = min((r['ceiling'] for r in findings), default=3)
    return dict(level=level, title=LEVELS[level], levels=LEVELS, findings=sorted(findings,key=lambda r:r['ceiling']),
                use_guide=dict(allowed=USE_GUIDE[level][0], deferred=USE_GUIDE[level][1]),
                engineering_acceptance='NOT_ASSESSED', rule_version=RULE_VERSION)


def event_tailwaters(rows):
    """Report measured boundary intervals only for the verified event to which they belong."""
    result=[]
    for row in rows:
        if row.get('role')!='boundary':continue
        h,u=row.get('observed_ft'),row.get('uncertainty_ft')
        usable=(row.get('event_eligible') and not row.get('issues') and row.get('source')
                and row.get('event') and row.get('date') and row.get('model_datum') and (row.get('location') or {}).get('rs')
                and row.get('kind') in ('stage','gage_height','boundary_stage')
                and finite(h) and finite(u) and u>0 and finite(row.get('flow_cfs')) and row['flow_cfs']>0)
        result.append(dict(event=row.get('event'),date=row.get('date'),rs=(row.get('location') or {}).get('rs'),
                           flow_cfs=row.get('flow_cfs'),datum=row.get('model_datum'),source=row.get('source'),
                           issues=row.get('issues',[]),interval_ft=[h-u,h+u] if usable else None))
    return result


def next_actions(findings, alternatives, selection, field_search):
    """Order decisions without counting an unadopted alternative against the baseline."""
    actions=[]
    for row in [*findings,*alternatives]:
        code=row['code'];facts=row['facts'];target=row['target']
        reason=row['reason'];order=8;impact=0
        if row['ceiling'] is not None and row['ceiling']<2:
            order=0
        elif code=='BOUNDARY_INFLUENCE':
            focus=facts.get('area_case') or facts
            local=focus.get('area') or {}
            if local.get('affected'):
                row=dict(row,facts={**facts,**focus,**local})
            order=1 if local.get('affected') else 4
            impact=abs(local.get('delta_ft') or facts.get('delta_ft') or 0)
            if field_search:
                target='field-search'
                reason=text('Obtain independent control at the sensitive boundary before repeating this range.',
                            '先取得敏感边界的独立控制依据，再重算边界范围。')
        elif code=='FIELD_RESIDUAL':
            order=2;impact=abs(facts.get('peak_ft') or 0)
        elif code=='GEOMETRY_FLOW_PATH':
            if not findings:continue
            order=3 if facts.get('station') in selection['selected'] else 6
            before,after=facts.get('baseline_share_pct'),facts.get('alternative_share_pct')
            if finite(before) and finite(after):impact=abs(after-before)
        elif code in ('FIELD_SUPPORT','BED_BASIS'):
            order=5
            if field_search:target='field-search'
        elif code in ('WET_ENDS','SPACING','BOUNDARY_SCOPE'):
            order=7
        actions.append((order,-impact,dict(row,target=target,reason=reason,
                       scope='CANDIDATE' if row['ceiling'] is None else 'ADOPTED')))
    return [entry for _,_,entry in sorted(actions,key=lambda v:v[:2])]


def unverified(reason):
    return classify([finding('NATIVE_IDENTITY',0,'native','Restore the native calculation evidence.',
                             '恢复可核验的原生计算结果。',error=reason)])


def packages(model, path, hyd):
    from .app_core import current_refreshed_reports, report_refresh_binding
    from .site_delivery import latest
    has_studies = any(value for field,value in report_refresh_binding(model).items() if field!='summary')
    if model.get('exports_need_refresh') or ((has_studies or model.get('latest_reports_binding')) and not current_refreshed_reports(model)):
        return dict(status='STALE')
    current = model.get('latest_delivery')
    if not current and model.get('engine_state'):
        current = read(safe_path(ROOT,model['engine_state'])).get('delivery')
    if not current or current.get('status') not in ('READY_FOR_REVIEW','READY_NATIVE_ONLY'):
        return dict(status='INCOMPLETE')
    receipt = latest(path)  # Rehash both package trees and check their internal native/GIS references.
    if (not receipt or receipt['summary']!=model['summary'] or receipt['run_id']!=hyd['run_id']
        or any(current.get(k)!=receipt.get(k) for k in ('summary','run_id','complete','minimal','mapped','status'))):
        return dict(status='EDITION_MISMATCH')
    mapped = receipt.get('mapped') is True and receipt['status']=='READY_FOR_REVIEW'
    counts = {}
    for kind in ('complete','minimal'):
        entry = receipt[kind]['manifest']
        directory = safe_path(ROOT,receipt[kind]['path'])
        if safe_path(ROOT,entry['path'])!=directory/'PACKAGE_MANIFEST.json':
            raise ValueError('Manifest path does not match the package')
        files = read(ROOT/entry['path'])['files']
        names = {e['path'] for e in files}
        if not any(e['path'].startswith('HEC_RAS/') and e['path'].lower().endswith('.hdf')
                   and e['sha256']==hyd['raw_hdf']['sha256'] for e in files):
            raise ValueError(kind+' package lacks the displayed native result')
        if mapped:
            required = {'GIS/Aerial.tif','GIS/Contours.shp','HEC_RAS/Terrain/Terrain.hdf','Graph/Exhibit_EN.pdf'}
            if kind=='complete':
                required |= {'GIS_Project.qgz','Graph/Exhibit_CN.pdf'}
                required |= {'Reports/Report_'+language+ext for language in ('EN','CN') for ext in ('.pdf','.docx')}
            if required-names or not any(n.lower().endswith('.rasmap') for n in names):
                raise ValueError(kind+' mapped artifacts missing: '+str(sorted(required-names)))
        counts[kind]=len(files)
    return dict(status='VERIFIED_MAPPED' if mapped else 'VERIFIED_NATIVE_ONLY',files=counts,
                visual_review=receipt.get('visual_review'),receipt=receipt['receipt'])


def qa_decisions(model, hyd, issues):
    from .qa_session import load
    from .qa_review import validate_decisions, closure_status, issue_key
    if not model.get('active_project'):
        return dict(status='NO_CURRENT_SUBMISSION')
    checkpoint = safe_path(ROOT,model['active_project']).parent/'review_checkpoint.json'
    if not checkpoint.exists():return dict(status='NO_CURRENT_SUBMISSION')
    cp=read(checkpoint)
    if cp.get('summary')!=model['summary'] or cp.get('run_id')!=hyd['run_id'] or not cp.get('session'):
        return dict(status='NO_CURRENT_SUBMISSION')
    _,session,packet=load(safe_path(ROOT,cp['session']))
    if not session.get('submissions'):return dict(status='REVIEW_IN_PROGRESS')
    last=session['submissions'][-1]
    if (not intact([last['spec'],last['closure']]) or session['status']!=last['status']
        or model['summary'] not in packet['sources'] or packet['run_id']!=hyd['run_id']):
        raise ValueError('QA submission no longer matches this calculation')
    spec=read(ROOT/last['spec']['path'])
    validate_decisions(session['packet']['path'],spec)
    rows=[r['issue'] for r in packet['issues'] if r['observation'] not in ('ABSENT_REQUIRES_REVIEW','NOT_COMPARABLE')]
    if Counter(map(issue_key,rows))!=Counter(map(issue_key,issues)):
        return dict(status='DIFFERENT_ISSUE_INVENTORY')
    return dict(status=closure_status(packet,spec['decisions'])['hydraulic_qa_status'],source=last['spec'])


def boundary_findings(studies, hyd, target, inventory, selection, feedback=None):
    from .qa import THRESHOLDS
    profiles=[p['profile_id'] for p in hyd['profiles']]
    signed=response(studies)
    selected = set(selection['selected'])
    cases=[]
    directions=set()
    for study in studies:
        for case in study['cases']:
            changes=case.get('changes',[])
            if len(changes)!=1:continue
            change=changes[0]
            path=change['path']
            if not path.startswith(('boundary_slopes.','boundaries.')):continue
            before,after=change.get('before'),change.get('after')
            if not finite(before) or not finite(after) or before==after:continue
            for row in signed:
                if row['source']!=study['analysis'] or row['case']!=case['id'] or row['paths']!=[path]:continue
                if path.startswith('boundaries.') and path.endswith(tuple('.'+str(i) for i in range(len(profiles)))):
                    if row['profile']!=profiles[int(path.split('.')[-1])]:continue
                profile = row['profile']
                expected = {station_key(rs) for rs in inventory.get(profile,{})}
                points = [(station_key(r['station']),r['delta_wse_ft']) for comp in study['comparisons'] if comp['case']==case['id']
                          for r in comp.get('cross_section_differences',[])
                          if r['profile']==profile and finite(r.get('delta_wse_ft'))]
                stations = [rs for rs,_ in points]
                local = [(rs,delta) for rs,delta in points if rs in selected]
                peak = max(local,key=lambda point:abs(point[1]),default=(None,None))
                local_stats = dict(station=peak[0],delta_ft=peak[1],compared=len(local),
                                   affected=sum(abs(delta)>row['threshold_ft'] for _,delta in local))
                end_rs = selection['stations'][0 if path.split('.')[1]=='upstream' else -1]
                if expected and len(stations)==len(expected) and set(stations)==expected:
                    directions.add((path.split('.')[1],profile,after>before))
                cases.append(dict(profile=row['profile'],case=row['case'],parameter=path,
                    station=station_key(row['peak_rs']),delta_ft=row['signed_peak_ft'],affected=len(row['affected']),
                    compared=row['compared'],threshold_ft=row['threshold_ft'],area=local_stats,
                    boundary_rs=end_rs,boundary_delta_ft=dict(points).get(end_rs)))
    if feedback and feedback['mode']=='event':
        # The low/high profiles are perturbations of EventBase at one discharge.
        profiles=['EventBase']
        downstream=selection['stations'][-1]
        for response_row in feedback['responses']:
            values=response_row['by_rs']
            if set(values)!=set(selection['stations']):raise ValueError('Incomplete native event response')
            threshold=response_row['threshold_ft']
            local={rs:values[rs] for rs in selection['selected']}
            peak=max(values,key=lambda rs:abs(values[rs]))
            local_peak=max(local,key=lambda rs:abs(local[rs]))
            high=response_row['profile']=='TailHigh'
            directions.add(('downstream','EventBase',high))
            cases.append(dict(profile='EventBase',case=response_row['profile'],parameter='boundaries.downstream.stages_ft.0',
                station=peak,delta_ft=values[peak],affected=sum(abs(v)>threshold for v in values.values()),compared=len(values),
                threshold_ft=threshold,boundary_rs=downstream,boundary_delta_ft=values[downstream],assumed=feedback['assumed'],
                area=dict(station=local_peak,delta_ft=local[local_peak],affected=sum(abs(v)>threshold for v in local.values()),compared=len(local))))
    findings=[]
    affected=[r for r in cases if r['affected']]
    if affected:
        worst=max(affected,key=lambda r:abs(r['delta_ft']))
        area_case=max(affected,key=lambda c:abs(c['area']['delta_ft'] or 0))
        findings.append(finding('BOUNDARY_INFLUENCE',2,target,
            'Check tailwater or upstream control against independent evidence before using the affected levels.',
            '核实敏感边界的实测水位或控制条件，再使用受影响断面的水位。',area_case=area_case,**worst))
    regime=hyd.get('flow_regime')
    sides={'subcritical':['downstream'],'supercritical':['upstream'],'mixed':['upstream','downstream']}.get(regime,[])
    missing=[f'{side} / {p}' for side in sides for p in profiles if
             any((side,p,up) not in directions for up in (False,True))]
    if missing or not sides:
        findings.append(finding('BOUNDARY_SCOPE',2,target,'Check the applicable high and low boundary cases.',
            '补查适用边界的高低两个工况。',missing=missing,threshold_ft=THRESHOLDS['sensitivity_hw_ft']))
    return findings,cases


def assess(model, path, summary, diagnostics, studies, guidance):
    findings=[]
    hyd=summary['hydraulics']
    is_river=hyd.get('model_type')=='river'
    editable=not model.get('native_review')
    revise='revision' if editable else 'qa'
    spatial='floodplain' if editable and is_river else 'atlas'
    sensitivity='sensitivity' if editable else 'qa'
    issues=(diagnostics or {}).get('issues',[])
    sources=list(guidance.get('sources',[]))+[summary['hydraulic_results'],hyd['raw_hdf'],hyd['raw_controller']]
    if diagnostics:sources+=diagnostics['sources']
    errors=list(guidance.get('source_errors',[]))
    try:delivery=packages(model,path,hyd)
    except EVIDENCE_ERRORS as error:delivery=dict(status='UNVERIFIED',error=str(error))
    if delivery.get('receipt'):sources.append(delivery['receipt'])
    try:review=qa_decisions(model,hyd,issues)
    except EVIDENCE_ERRORS as error:review=dict(status='UNVERIFIED',error=str(error))
    if review.get('source'):sources.append(review['source'])
    verified_review=review['status']=='CLOSED_WITH_RECORDED_CONDITIONS'
    river={}
    if is_river and editable:
        from .river_review_report import collect
        try:
            river,refs=collect(path,summary)
            sources.extend(refs)
            if model.get('latest_geometry_comparison') and 'comparison' not in river:
                errors.append('Geometry comparison belongs to another result or is incomplete.')
        except EVIDENCE_ERRORS as error:errors.append(str(error))
    feedback=None
    if summary.get('configuration',{}).get('field_feedback'):
        from .field_results import collect as collect_feedback
        try:
            feedback,feedback_refs=collect_feedback(summary)
            sources.extend(feedback_refs)
        except EVIDENCE_ERRORS as error:errors.append(str(error))
    from .survey_import import verified_sources
    try:sources.extend(verified_sources(model))
    except EVIDENCE_ERRORS as error:errors.append(str(error))
    if errors:
        findings.append(finding('EVIDENCE_GAPS',1,'qa','Recover unavailable or changed evidence.',
                                '恢复缺失或已改变的证据。',errors=errors))
    if delivery['status']!='VERIFIED_MAPPED':
        findings.append(finding('MAPPED_DELIVERY',1,'delivery','Refresh or repair the matching mapped packages.',
                               '更新或修复与当前计算对应的两种制图交付包。',**delivery))
    if not diagnostics or diagnostics.get('warning_coverage') not in FULL or any(r['code'] in NATIVE_GAPS for r in issues):
        findings.append(finding('WARNING_COVERAGE',1,'native','Complete the native warning and output evidence.',
                                '补齐原生警告表及输出证据。'))
    if any(r['code']=='FLOW_SPLIT_NOT_FULLY_OBSERVED' for r in issues):
        findings.append(finding('FLOW_SPLIT_COVERAGE',1,'qa','Check culvert, roadway and other flow paths in the same run. An unreported discharge remains unknown.',
                                '核对同次计算的涵洞、路面及其他过流路径。缺失流量须保留为未知。',codes=['FLOW_SPLIT_NOT_FULLY_OBSERVED']))
    other_gaps=sorted({r['code'] for r in issues if r['severity']=='EVIDENCE_GAP' and r['code'] not in NATIVE_GAPS|BALANCE})
    if other_gaps:
        findings.append(finding('OUTPUT_EVIDENCE',1,'qa','Inspect the missing diagnostic evidence listed here.',
                                '请核查下列诊断缺少的证据。',codes=other_gaps))
    balance=[r for r in issues if r['code']!='FLOW_SPLIT_NOT_FULLY_OBSERVED' and (r['code'] in BALANCE or r['severity']=='ERROR')]
    if balance:
        findings.append(finding('OUTPUT_CONSISTENCY',1,'qa','Resolve native output or flow consistency before sharing results.',
                                '交出计算结果前，先解决流量或原生输出不一致。',codes=sorted({r['code'] for r in balance})))
    gate=summary.get('gate') or {}
    if hyd.get('case_kind')!='site_conditional' or gate.get('blocking_items') or gate.get('status')!='READY_CONDITIONAL':
        findings.append(finding('SITE_SCOPE',1,revise,'Verify the site input gate and the scope of this calculation.',
                                '核实场地输入检查及本次计算用途。',scope=hyd.get('case_kind')))
    changed=river.get('changed_ends',[])
    candidate_findings=[]
    for row in changed:
        share=row.get('share');before=row.get('baseline_share')
        candidate_findings.append(finding('GEOMETRY_FLOW_PATH',None,spatial,'Check the candidate’s newly wet floodplain before adopting it.',
            '采用该候选前核实新过水断面的漫滩连通、道路开口和岸站。',station=station_key(row['rs']),case=row['case'],
            side=row['side'],baseline_share_pct=before,alternative_share_pct=share,end_excess_ft=row['stage']-row['end'],
            changed_ends=len(changed)))
    from .qa import verified_profiles
    from .assessment_area import current as current_area, area as full_area
    inventory=verified_profiles(hyd)
    try:
        selection=current_area(model,inventory)
        if model.get('assessment_area'):sources.append(model['assessment_area'])
    except EVIDENCE_ERRORS as error:
        selection=full_area(inventory)
        findings.append(finding('AREA_EVIDENCE',1,'qa','Restore the saved area of interest or select it again.',
                                '恢复已存关注范围，或重新选择。',error=str(error)))
    boundary,cases=boundary_findings(studies,hyd,sensitivity,inventory,selection,feedback)
    findings.extend(f for f in boundary if f['code']=='BOUNDARY_INFLUENCE')
    wet=sorted({station_key(r['station']) for r in issues if r['code'] in WET and r.get('station') is not None},key=float,reverse=True)
    if wet:
        findings.append(finding('WET_ENDS',2,'coverage' if editable and is_river else revise,
            'Check connected floodplain and section extent before extending or rotating cutlines.',
            '先核对连通漫滩和断面端点，再决定延伸或旋转。',stations=wet))
    findings.extend(f for f in boundary if f['code']!='BOUNDARY_INFLUENCE')
    if (issues and not verified_review) or review['status'] in ('UNVERIFIED','DIFFERENT_ISSUE_INVENTORY','REVIEW_IN_PROGRESS'):
        findings.append(finding('ISSUE_REVIEW',2,'qa','Review the current warning ledger and preserve its dispositions.',
                                '复核当前警告和对应的处置记录。',records=len(issues),review=review['status']))
    if is_river:
        spacing=next((s for s in reversed(studies) if s.get('convergence')),None)
        all_intervals=spacing and len(spacing.get('intervals') or [])==spacing['cases'][0].get('section_count',0)-1
        if (not all_intervals or len(spacing['cases'])<3 or spacing['convergence']['status']!='STABLE_AT_REVIEW_THRESHOLD'
            or spacing.get('excluded_intervals') or spacing.get('deferred_intervals')
            or (spacing.get('end_coverage') or {}).get('status')!='ENDS_ABOVE_COMPUTED_WATER'):
            findings.append(finding('SPACING',2,'spacing' if editable else 'qa','Review spacing, both refinements and wet ends.',
                                '核对断面加密的连续两级水位变化、未测区间和湿端。',
                                status=spacing['convergence']['status'] if spacing else 'NOT_TESTED'))
        if hyd.get('channel_geometry_basis') not in ('surveyed_channel','combined_survey_and_dem'):
            findings.append(finding('BED_BASIS',2,revise,'Verify the submerged channel bed with survey evidence.',
                                    '用测量资料核实水下河床。',basis=hyd.get('channel_geometry_basis')))
    elif gate.get('input_adequacy_status')=='CONDITIONAL_UNVERIFIED':
        findings.append(finding('STRUCTURE_INPUTS',2,revise,'Verify structure dimensions, inverts and road levels for the intended use.',
                                '按交付用途核实结构尺寸、涵底和道路高程。'))
    from .river_observations import holdout_stages
    reviewed_events=list(river.get('events',[]))
    if feedback:
        from .field_results import verified_observations
        if feedback['mode']=='event':
            reviewed_events.extend(verified_observations(feedback))
        if feedback['mode']=='geometry' and feedback['decision'] in ('request_survey','review_2d'):
            findings.append(finding('FLOW_PATH_DISPOSITION',2,'floodplain','Resolve the recorded floodplain condition before sign-off.',
                                    '送签前复核已记录的漫滩条件。',station=feedback['comparison']['station'],condition=feedback['condition']))
    from .validation_plan import usable
    scope=summary.get('configuration',{}).get('production_scope') or {}
    measured,missing_accuracy,exceeds=holdout_stages(usable(reviewed_events,scope))
    if is_river and not measured:
        findings.append(finding('FIELD_SUPPORT',2,'observations' if editable else 'qa',
            'Document an independent measured event before submitting a site performance claim for sign-off.',
            '如需送审场地水位预测，补充独立事件的非边界实测水位，并核对位置与基准。',
            screened=len(river.get('screen',[]))))
    elif measured:
        outside=missing_accuracy+exceeds
        if outside:
            largest=max(outside,key=lambda r:abs(r['residual_ft']))
            findings.append(finding('FIELD_RESIDUAL',2,'observations' if editable else 'qa',
                'Review held-out residuals and measurement uncertainty for the intended site use.',
                '核对独立事件的逐站偏差、测量不确定度以及拟用范围。',records=len(outside),
                missing_uncertainty=len(missing_accuracy), outside_uncertainty=len(exceeds), peak_ft=largest['residual_ft'],station=(largest.get('location') or {}).get('rs'),
                observations=[{k:r.get(k) for k in ('event','date','location','flow_cfs','residual_ft','uncertainty_ft','source')}
                              for r in outside]))
    if feedback and feedback['assumed']:
        findings.append(finding('ASSUMED_FIELD_FEEDBACK',2,'field-feedback','Replace assumed field feedback with dated field records.','用有日期的现场记录替换假设反馈。'))
    result=classify(findings)
    local_findings=[f for f in findings if f['code']!='BOUNDARY_INFLUENCE']
    local_cases=[c for c in cases if c['area']['affected']]
    if local_cases:
        worst=max(local_cases,key=lambda c:abs(c['area']['delta_ft']))
        local_findings.append(finding('BOUNDARY_INFLUENCE',2,sensitivity,'Review boundary influence within the selected reach.',
            '核查边界对所选河段的影响。',**{**worst,**worst['area']}))
    selection.update(level=classify(local_findings)['level'],blocking_codes=[f['code'] for f in local_findings])
    codes={r['code'] for r in findings}
    checks=dict(geometry=is_river and bool(wet) and len(hyd['profiles'])==1 and hyd['profiles'][0]['profile_id'].lower()=='q100',
                sensitivity=bool({'BOUNDARY_SCOPE','BOUNDARY_INFLUENCE'} & codes),
                spacing='SPACING' in codes,spacing_scope='all',maximum_width_ft=river.get('comparison_width_ft'),
                field_first=bool({'BOUNDARY_INFLUENCE','BED_BASIS','FIELD_SUPPORT'} & codes or candidate_findings))
    result.update(area=selection,candidate_findings=candidate_findings,next_actions=next_actions(findings,candidate_findings,selection,is_river and editable),recommended_checks=checks,assessed_utc=utc(),summary=model['summary'],run_id=hyd['run_id'],profiles=[p['profile_id'] for p in hyd['profiles']],input_adequacy=gate.get('input_adequacy_status'),
        bed_basis=hyd.get('channel_geometry_basis'),diagnostics=dict(records=len(issues) if diagnostics else None,
        native_messages=sum(1 for r in issues if (r.get('evidence') or {}).get('native_message')) if diagnostics else None,
        warning_coverage=(diagnostics or {}).get('warning_coverage'),by_severity=dict(Counter(r['severity'] for r in issues))),
        qa=review,delivery=delivery,boundary_cases=cases,event_tailwaters=event_tailwaters(reviewed_events),changed_ends=changed,holdout_observations=len(measured),
        sources=list({e['path']:e for e in sources}.values()))
    from .purpose_acceptance import evaluate
    origin=summary.get('configuration',{}).get('revision_origin')
    comparison=None
    if origin:
        from .app_revision import compare
        try:
            comparison=compare(dict(parent_revision=origin),summary)
        except EVIDENCE_ERRORS:
            comparison=None
    result['purpose_decision']=evaluate(summary,reviewed_events,comparison)
    from .edition_brief import build as edition_brief
    from .review_decisions import site_steps
    result['review_steps']=site_steps(scope,reviewed_events,studies) if is_river else []
    result['edition_brief']=edition_brief(summary,result['purpose_decision'],reviewed_events,result['review_steps'],comparison,studies)
    result['evidence_hash'] = digest({k:v for k,v in result.items() if k!='assessed_utc'})
    return result


def save_summary(key, body):
    """Save the verified, displayed edition on request, without relying on browser downloads."""
    from .app_core import folder
    from .result_guidance import collect
    language = body.get('language')
    if language not in ('zh','en'):
        raise ValueError('Choose English or Chinese')
    a = collect(key,dict(summary_hash=body.get('summary_hash'),include_assessment=True))['assessment']
    if not a.get('evidence_hash') or a['evidence_hash']!=body.get('assessment_hash'):
        raise ValueError('Assessment changed; reopen results / 评估已变化，请重新打开结果页')
    zh = language=='zh'
    def label(en,cn):
        return cn if zh else en
    d = a['diagnostics']
    lines = ['SteadyReach · '+a['run_id'], 'L'+str(a['level'])+' · '+a['title'][language],
             a['assessed_utc']+' · '+a['summary']['sha256'], '',
             label('Delivery packages','交付包')+' · '+a['delivery']['status'],
             label('Map visual review','地图目视验收')+' · '+str(a['delivery'].get('visual_review') or 'UNVERIFIED'),
             'QA · '+a['qa']['status'],
             label('Native messages / combined diagnostic records','原生信息／综合诊断记录')+
             f" · {d['native_messages']} / {d['records']}",
             label('Engineering sign-off remains with the responsible engineer.','工程签发由负责工程师决定。'),'']
    lines.extend([label('Current use', '当前可用范围')+' · '+a['use_guide']['allowed'][language],
                  label('Hold for review', '暂缓用途')+' · '+a['use_guide']['deferred'][language], ''])
    decision=a.get('purpose_decision')
    if decision:
        lines.append(decision[language])
        lines.extend(r[language] for r in decision['rows'])
        lines.append(decision['note_'+language])
    if a.get('next_actions'):
        lines.append(label('Recommended action order','建议处理顺序'))
        for i,row in enumerate(a['next_actions'],1):
            lines.append(f"{i}. "+row['reason'][language]+' · '+row['scope']+' · '+row['code'])
    for row in a['findings']:
        lines.append(row['reason'][language])
        f = row['facts']
        if row['code']=='GEOMETRY_FLOW_PATH':
            share = lambda value: '—' if value is None else f'{value:.2f}%'
            lines.append(f"RS {f['station']} · {f['side']} · {share(f['baseline_share_pct'])} → {share(f['alternative_share_pct'])} · "+label('new wet end','新增湿端')+f" {f['end_excess_ft']:.3f} ft")
        elif row['code']=='BOUNDARY_INFLUENCE':
            lines.append(f"{f['profile']} · {f['parameter']} · RS {f['station']} · Δ {f['delta_ft']:+.3f} ft · {f['affected']}/{f['compared']} "+label('sections above','条断面超过')+f" {f['threshold_ft']} ft")
        else:
            for field,value in f.items():
                if field=='observations':
                    for obs in value:
                        rs=(obs.get('location') or {}).get('rs')
                        uncertainty=obs.get('uncertainty_ft')
                        u=str(uncertainty)+' ft' if uncertainty and uncertainty>0 else label('accuracy record needed','待补精度记录')
                        lines.append(f"  {obs.get('date')} · RS {rs} · Δ {obs['residual_ft']:+.3f} ft · {u} · {obs.get('source') or '—'}")
                    continue
                if isinstance(value,list):
                    value=', '.join(map(str,value))
                if value is not None and value!='':
                    lines.append(f'  {field} · {value}')
        lines.append('')
    if a.get('event_tailwaters'):
        lines.append(label('Tailwater for the matched observed event','匹配实测事件的尾水'))
        for row in a['event_tailwaters']:
            bounds=row['interval_ft']
            value=(f"{bounds[0]:.3f}–{bounds[1]:.3f} ft" if bounds else
                   label('verified interval unavailable','缺少可核验的区间'))
            lines.append(f"{row['date']} · {row['event']} · RS {row['rs']} · {row['flow_cfs']} cfs · {row['datum']} · {value} · {row['source']}")
        lines.append('')
    scope=a['area']
    lines.append(label('Area of interest','工程关注河段')+f" · RS {scope['selected'][0]}–{scope['selected'][-1]} · L{scope['level']}")
    for case in a['boundary_cases']:
        lines.append(f"{case['profile']} · {case['case']} · "+label('Boundary','计算边界')+
                     f" RS {case['boundary_rs']} Δ {case['boundary_delta_ft']} ft · "+
                     label('Area peak','关注河段峰值')+f" RS {case['area']['station']} Δ {case['area']['delta_ft']} ft")
    for row in a['candidate_findings']:
        f=row['facts']
        lines.append(label('Unadopted candidate','未采用候选')+f" · {f['case']} · RS {f['station']} · {f['side']} · "+
                     f"{f['baseline_share_pct']}% → {f['alternative_share_pct']}% · {f['end_excess_ft']:.3f} ft")
    lines.append(label('Traceable sources','可追溯来源'))
    lines.extend(entry['path']+' · '+entry['sha256'] for entry in a['sources'])
    destination = folder(key)/'assessment_exports'/unique_id()
    destination.mkdir(parents=True)
    path = destination/('Assessment_'+language+'.txt')
    partial = path.with_suffix('.partial')
    partial.write_text('\n'.join(lines)+'\n',encoding='utf-8-sig')
    partial.replace(path)
    return dict(file=item(path),evidence_hash=a['evidence_hash'])
