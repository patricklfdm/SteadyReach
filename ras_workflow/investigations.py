"""Issue-specific investigation guides and reviewed, source-bound study preparation."""
from .common import ROOT, finite, intact, item, read, rel, safe_path, save, sha, utc

GUIDES={
 'WET_SECTION_EDGE':('DOMAIN','Inspect terrain beyond both ends and connected bypass; preview wider sections before adoption.','检查断面两端以外地形及连通绕流；采用更宽断面前先预览。','Comparable resampling/rerun plus wet-edge and flow-path review.','可比重采样/重算，并复核湿边缘与过流路径。'),
 'ENERGY_BALANCE_ERROR':('LOCAL_GEOMETRY','Inspect neighbouring profiles, functional sections and flow regime; compare repeated refinement.','检查相邻剖面、功能断面及流态，并比较连续加密结果。','At least three comparable nested meshes/section sets and native warning review.','至少三套可比嵌套断面及完整原生警告复核。'),
 'CRITICAL_DEPTH_FALLBACK':('FLOW_REGIME','Check native standard-step messages, cross-section shape and boundary applicability.','检查原生标准步警告、断面形状及边界适用性。','Distinct-run comparison and evidence explaining the transition.','独立运行对比及流态转换解释证据。'),
 'DOWNSTREAM_EGL_RISE':('BOUNDARY','Inspect direction, control transitions and boundary evidence; test only justified slope ranges.','检查流向、控制转换及边界依据，仅测试有依据的坡降范围。','Same-flow boundary comparison and all-section energy review.','同流量边界对比与全断面能量复核。'),
 'NATIVE_WARNING_TABLE_INCOMPLETE':('NATIVE_EXPORT','Use the native warning export assistant; retain observed project and filter scope.','使用原生警告导出助手，保留实际项目及筛选范围。','Verified full-scope native export; a solver log does not substitute.','核验完整范围原生导出；求解日志不能替代。'),
 'FLOW_SPLIT_NOT_FULLY_OBSERVED':('OUTPUT_COVERAGE','Obtain culvert groups, roadway and other-path flow from the same native run.','取得同次原生运行的各孔组、道路及其他路径流量。','Source-bound group output and complete flow balance; null is not zero.','绑定来源的孔组输出及完整流量平衡；缺值不作零。')}


def guide(issue):
    values=GUIDES.get(issue['code'],('EVIDENCE','Inspect the bound original evidence and record a specific hypothesis.','检查绑定的原始证据，记录具体待检验假设。','Comparable rerun or explicit supporting evidence, followed by review.','可比重算或明确支持证据，再进行复核。'))
    return dict(kind=values[0],action_en=values[1],action_zh=values[2],closure_en=values[3],closure_zh=values[4],
        auto_closed=False,parameters=['boundary_slopes.upstream','boundary_slopes.downstream','scenario.channel_n','scenario.overbank_n','scenario.culvert_n'])


def prepare(packet_path,project,scenario,specification,output):
    from .qa_session import packet_check
    from . import study, inputs
    pp=safe_path(ROOT,packet_path);packet=packet_check(pp);sp=safe_path(ROOT,specification);spec=read(sp)
    path,c=inputs.load(project)
    if c['project_id']!=packet['project_id']:raise ValueError('Investigation project differs from QA packet')
    # The exact current configuration must be the reviewed baseline, not a later edit.
    summaries=[];summary_paths=[]
    for e in packet.get('sources',[]):
        if e['path'].endswith('/summary.json') and intact([e]):
            s=read(ROOT/e['path'])
            if (s.get('hydraulics') or {}).get('run_id')==packet['run_id']:summaries.append(s);summary_paths.append(ROOT/e['path'])
    if not summaries or any(s['configuration']!=c or s['hydraulics'].get('scenario_id')!=scenario for s in summaries):raise ValueError('Project/scenario no longer matches the QA baseline')
    from .report_data import collect
    current_geometry=read(safe_path(path.parent,c['geometry']))
    for summary_path in summary_paths:
        bound=collect(summary_path)
        if not bound['geometry_source'] or bound['geometry']!=current_geometry:raise ValueError('Current geometry differs from the bound QA baseline')
    keys=spec.get('issue_keys',[])
    if not keys or not set(keys)<={r['key'] for r in packet['issues']}:raise ValueError('Choose issues from the bound QA packet')
    if not spec.get('reviewer') or not spec.get('hypothesis') or not spec.get('sources') or not intact(spec['sources']):raise ValueError('Reviewer, hypothesis and intact range evidence required')
    if not spec.get('ranges'):raise ValueError('Explicit supported parameter ranges required; no automatic percentages')
    topics=[];cases=[];seen=set()
    for i,r in enumerate(spec['ranges']):
        parameter=r['path'];low=r.get('low');high=r.get('high')
        if parameter not in guide(dict(code=''))['parameters']:raise ValueError('Unsupported investigation parameter')
        if parameter in seen:raise ValueError('Duplicate parameter range')
        seen.add(parameter)
        if not finite(low) or not finite(high) or low>=high or not r.get('basis') or not r.get('measurement_action'):raise ValueError('Each range needs ordered finite bounds, basis and measurement action')
        topic='parameter_'+str(i+1);topics.append(dict(id=topic,evidence_status='EXPLICIT_CONDITIONAL_RANGE',range_basis=r['basis'],measurement_action=r['measurement_action']))
        for label,value in [('low',low),('high',high)]:cases.append(dict(id=topic+'_'+label,topic=topic,changes=[dict(path=parameter,value=value,basis=r['basis'])]))
    folder=safe_path(ROOT,output);folder.mkdir(parents=True,exist_ok=False)
    plan=dict(id='qa_investigation',case_kind=c['case_kind'],purpose=spec['hypothesis'],sources=[item(pp),item(sp)]+spec['sources'],measurement_topics=topics,cases=cases)
    save(folder/'study_spec.json',plan)
    result=study.prepare(path,scenario,folder/'study_spec.json',folder/'study')
    binding=dict(status='DRAFT_REQUIRES_REVIEW',created_utc=utc(),packet=item(pp),request=item(sp),study=item(result),issue_keys=keys,
        reviewer=spec['reviewer'],new_solver_calls=0,review_command='workflow.py study-run --study "'+rel(result)+'" --review "'+rel(result.parent/'review.template.json')+'"',
        limitation='Preparing cases does not approve or run them. Complete the named study review before execution; issue closure remains separate.')
    save(folder/'investigation.json',binding);return binding


def analyze(binding_path,review_path):
    from .study import analyze as analyze_study
    from .qa_review import load_summary,trends
    from .qa import diagnostics,verified_profiles
    bp=safe_path(ROOT,binding_path);binding=read(bp)
    if not intact([binding['packet'],binding['request'],binding['study']]):raise ValueError('Investigation evidence changed')
    result=analyze_study(binding['study']['path'],review_path)
    plan=read(ROOT/binding['study']['path']);journal=read((ROOT/binding['study']['path']).parent/'execution.json')
    records={r['id']:r for r in journal['cases']};baseline=records.get('baseline',{})
    observations=[]
    if baseline.get('status')=='COMPUTED':
        _,_,hyd=load_summary(baseline['summary']['path']);old=diagnostics(hyd,bp.parent/'analysis_qa'/'baseline')
        for comp in result['comparisons']:
            _,_,new=load_summary(records[comp['case']]['summary']['path'])
            if new['run_id']==hyd['run_id']:raise ValueError('Study comparison reused the same solver run')
            current=diagnostics(new,bp.parent/'analysis_qa'/comp['case'])
            observations.append(dict(case=comp['case'],changes=next(c['changes'] for c in plan['cases'] if c['id']==comp['case']),
                trends=trends(old['issues'],current['issues'],comp,verified_profiles(new),current['warning_coverage'])))
    output=dict(status='INVESTIGATION_REQUIRES_REVIEW',binding=item(bp),analysis=item((ROOT/binding['study']['path']).parent/'analysis.json'),
        measurement_priorities=result['measurement_priorities'],case_observations=observations,failed_cases=result['failed_cases'],
        hydraulic_qa='REVIEW_REQUIRED',engineering_acceptance='NOT_ASSESSED',auto_closed_issue_count=0)
    save(bp.parent/'investigation_analysis.json',output);return output
