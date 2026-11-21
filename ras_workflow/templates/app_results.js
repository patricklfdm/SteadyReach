'use strict';
function guidanceTarget(node,key){node.id='qa-tool-'+key;return node;}
function renderTaskRecovery(parent,m){
 const plan=m.calculation_recovery,job=m.job||{};
 if(!m.errors?.length&&!plan)return;
 if(m.errors?.length)parent.append(el('p',m.errors.join('\n'),'warning'));
 const retry=async(route,body={})=>{await api(route,{id:m.id,revision:m.revision,...body});await open(m.id);};
 if(plan){
  if(plan.mode==='RESTORE_EVIDENCE'){
   parent.append(el('p',tr('Restore the matching approved files, then reopen the project. ','请恢复匹配的已确认文件，然后重新打开项目。')+plan.error,'warning'));
  }else if(plan.mode==='REVIEW_INPUTS'){
   parent.append(button('Review inputs before restarting','重新开始前核对输入',showFinalReview));
  }else if(plan.mode==='RESTORE_RESULT'){
   parent.append(button('Recover saved solver result without recalculating','恢复已保存求解结果（无需重算）',()=>retry('recover-run',{mode:plan.mode,task:m.task}),'primary'));
  }else if(plan.mode==='RESUME_COMPUTATION'){
   parent.append(el('p',tr('The saved inputs and original confirmation match. Resume the approved computation after checking the error above.','已核验封存输入和原确认记录。请查看错误详情，然后继续本次已确认的计算。')),
    button('Confirm and resume approved computation','确认继续已批准的计算',()=>retry('recover-run',{mode:plan.mode,task:m.task,confirmed:true}),'primary'));
  }
  return;
 }
 if(m.feedback_spec||!['FAILED','INTERRUPTED'].includes(job.status)&&m.status!=='INTERRUPTED')return;
 const steps={
  prepare:['Retry terrain and input preparation','重试地形与输入准备'],analyze:['Retry parsing saved materials','重新解析已保存资料'],
  acquire:['Retry public data lookup','重试公共资料查询'],'automatic-prepare':['Retry automatic draft preparation','重试自动准备草稿'],
  report:['Retry reports from saved results','用已保存结果重试报告'],delivery:['Retry delivery from saved results','用已保存结果重试交付'],
  'native-export':['Retry native table export','重试原生结果表导出'],'next-review':['Prepare the next review again','重新准备下一轮复核']};
 if(steps[job.action])parent.append(button(...steps[job.action],()=>retry(job.action)));
 else if(job.action==='catalog'&&m.selected_catalog)parent.append(button('Retry the selected catalog record','重试所选资料目录',()=>retry('catalog-import',{url:m.selected_catalog})));
 else if(job.action==='study'||job.action==='check-batch'){
  const batch=job.action==='check-batch',entry=batch?m.active_check_batch?.plan:m.active_study?.study;
  if(entry)parent.append(button('Resume the previously confirmed batch','继续此前确认的批次',()=>retry(batch?'checks-start':'study-start',{token:entry.sha256,confirmed:true,retry:true})));
 }
}
function renderDeliveryRecovery(parent,delivery){
 if(!delivery?.error)return;
 parent.append(el('p',tr('Calculation and reports are saved. Resolve the export error below, then retry delivery without solving. A temporary map-service failure may only need a retry.','计算和报告已保存。请处理下方导出错误，再单独重试交付包，无需重新求解。地图服务临时故障可先重试。'),'warning'),
  el('p',delivery.error,'warning'),button('Retry delivery without solving','重试交付包（不重新求解）',async()=>{await api('delivery',{id:current.id});await open(current.id);}));
}

function renderRevisionComparison(parent,comparison){
 const box=details(parent,'Comparison with previous calculation','与上次计算对比',true);
 const format=value=>Number.isFinite(value)?value.toFixed(4):'—';
 if(comparison.status!=='COMPARISON_NOT_ACCEPTANCE'){
  box.append(el('p',tr('Comparison needs attention. ','对比需要处理。')+(comparison.error||comparison.status),'warning'));
  return;
 }
 const old=comparison.diagnostics?.previous,now=comparison.diagnostics?.current;
 const review=comparison.review;
 if(review){
  const metric=(d,key)=>d?.severity?.[key]??'—';
  table(box,[tr('Review before choosing an edition','选用版本前核对'),tr('Previous','上次'),tr('Current','本次')],[
   [tr('Native warnings (all profiles)','原生警告（全部工况）'),metric(old,'WARNING'),metric(now,'WARNING')],
   [tr('Native errors','原生错误'),metric(old,'ERROR'),metric(now,'ERROR')],
   [tr('Wet ends across profiles','各工况过水端点数'),old?.wet_ends?.length??'—',now?.wet_ends?.length??'—']]);
  for(const item of review.actions)box.append(el('p',tr(item.en,item.zh),'warning'));
  const peak=review.maximum_at_verified_center;
  if(peak)box.append(el('p',peak.profile+' · RS '+peak.station+tr(' · signed WSE change ',' · 水位变化（含方向）')+format(peak.change)+' ft'));
  if(review.increased_control_codes.length)box.append(el('small',review.increased_control_codes.join(', ')));
  if(now?.wet_ends?.length){
   const wet=details(box,'Locate current wet ends','定位本次过水端点');
   table(wet,[tr('Profile','工况'),'RS',tr('Side','岸侧'),tr('Water above endpoint (ft)','高于端点（ft）')],now.wet_ends.map(e=>
    [e.profile,e.station,e.side==='left'?tr('Left','左'):tr('Right','右'),format(e.excess_ft)]));
  }
 }
 const context=comparison.input_context;
 if(context?.status==='VERIFIED'){
  const geometry=context.geometry;
  box.append(el('p',tr('Verified input snapshots · sections ','已核验输入快照 · 断面数 ')+geometry.previous_count+' → '+geometry.current_count+
   tr(' · changed shapes/parameters ',' · 几何／参数改变 ')+geometry.changed_sections+tr(' · moved centers ',' · 中心移动 ')+geometry.moved_centers+
   tr(' · moved bank pairs ',' · 岸站平面位置移动 ')+geometry.moved_bank_pairs));
   if(context.interpretation==='MULTIPLE_INPUT_CHANGES')box.append(el('p',tr('Geometry and other model inputs changed together. Do not interpret this as an isolated section-spacing convergence test.','几何和其他模型输入同时改变，不能把本次对比作为仅改变断面间距的收敛检验。'),'warning'));
  if(context.input_changes.length){const inputs=details(box,'Changed hydraulic inputs','水力输入变化',true);table(inputs,[tr('Input','输入'),tr('Previous','上次'),tr('Current','本次')],context.input_changes.map(r=>[r.field,JSON.stringify(r.previous),JSON.stringify(r.current)]));}
  const location=details(box,'Section correspondence and bank movement','断面对应及岸站移动');
  table(location,['RS',tr('Center shift ft','中心位移 ft'),tr('Rotation degrees','方向变化 °'),tr('Left/right bank shift ft','左右岸平面位移 ft'),tr('Changed fields','变化字段')],
   geometry.sections.filter(r=>r.changed_fields.length||r.location_status!=='SAME_CENTER').map(r=>[r.station,format(r.center_shift_ft),format(r.rotation_degrees),(r.bank_plan_shifts_ft||[]).map(format).join(' / '),r.changed_fields.join(', ')]));
  if(geometry.unverified_centers)box.append(el('p',geometry.unverified_centers+tr(' section centers lack verified geographic correspondence.',' 条断面中心缺少可核验的地理对应。'),'warning'));
   if(geometry.unverified_bank_pairs)box.append(el('p',geometry.unverified_bank_pairs+tr(' bank pairs lack comparable map positions.',' 组岸站缺少可核验的平面位置对应。'),'warning'));
 }else box.append(el('p',tr('Input/location correspondence is unavailable: ','输入／位置对应尚不可用：')+(context?.error||tr('No sealed geometry snapshots.','缺少封存几何快照。')),'warning'));
 if(comparison.overbank_changes){
  const group=details(box,'Q100 left and right floodplain flow shares','Q100 左右漫滩流量占比变化');
  const share=comparison.overbank_changes;
  if(share.rows.length){
   const pair=values=>values.map(v=>v.toFixed(2)).join(' / ');
   table(group,['RS',tr('Previous L / R (%)','上次 左／右（%）'),tr('Current L / R (%)','本次 左／右（%）'),tr('Change (percentage points)','变化（百分点）')],share.rows.map(r=>[r.station,pair(r.previous_percent),pair(r.current_percent),pair(r.delta_points)]));
  }else group.append(el('p',tr('No comparable native shares at verified common centers.','相同中心位置缺少可比较的原生漫滩流量占比。'),'muted'));
 }
 const labels={upstream_wse_ft:tr('Upstream WSE (ft)','上游水位（ft）'),downstream_wse_ft:tr('Downstream WSE (ft)','下游水位（ft）'),
  max_channel_velocity_fts:tr('Maximum channel velocity (ft/s)','最大主槽流速（ft/s）'),max_channel_froude:tr('Maximum channel Froude number','最大主槽弗劳德数'),
  headwater_wse_ft:tr('Headwater WSE (ft)','进口上游水位（ft）'),tailwater_wse_ft:tr('Tailwater WSE (ft)','出口下游水位（ft）'),
  inlet_velocity_fts:tr('Inlet velocity (ft/s)','进口流速（ft/s）'),roadway_flow_software_cfs:tr('Roadway flow (cfs)','道路越流（cfs）')};
 table(box,[tr('Profile','工况'),tr('Metric','指标'),tr('Previous','上次'),tr('Current','本次'),tr('Change','变化')],
  comparison.rows.map(row=>[row.profile,labels[row.metric]||row.metric,format(row.previous),format(row.current),
    row.location_changed?tr('Endpoint changed','端部断面已改变'):row.location_status==='UNVERIFIED'?tr('Location unverified','位置未核验'):format(row.change)]));
 for(const profile of comparison.profiles||[]){
  const maximum=profile.maximum;
  if(!maximum){box.append(el('p',profile.profile+tr(' has no matched section IDs.',' 没有匹配的断面编号。'),'warning'));continue;}
  box.append(el('p',profile.profile+' · '+profile.matched_sections+tr(' matched sections. Maximum absolute WSE change ',' 条匹配断面，最大绝对水位差 ')+
   format(Math.abs(maximum.change))+' ft · RS '+maximum.station,profile.exceeds_review_threshold?'warning':'status'));
  const same=profile.maximum_at_verified_centers;
  box.append(el('p',same?tr('At verified unchanged centers: ','经核验中心未移动的断面：')+profile.verified_center_count+tr(' sections · maximum |ΔWSE| ',' 条 · 最大绝对水位差 ')+format(Math.abs(same.change))+' ft · RS '+same.station:tr('No verified unchanged-center comparison.','没有可核验的同中心位置对比。'),same?'muted':'warning'));
  if(profile.added_stations.length||profile.removed_stations.length)box.append(el('p',tr('Added / removed section IDs — ','增加／移除断面编号 — ')+profile.added_stations.join(', ')+' / '+profile.removed_stations.join(', ')));
 }
 const unmatched=[...(comparison.unmatched_previous_profiles||[]),...(comparison.unmatched_current_profiles||[])];
 if(unmatched.length)box.append(el('p',tr('Unmatched profiles — ','未匹配工况 — ')+unmatched.join(', '),'warning'));
 if(comparison.cross_sections?.length){
  const sections=details(box,'Water-level changes at every matched section','全部匹配断面的水位变化');
  table(sections,[tr('Profile','工况'),'RS',tr('Previous WSE (ft)','上次水位（ft）'),tr('Current WSE (ft)','本次水位（ft）'),'Δ ft'],
   comparison.cross_sections.map(row=>[row.profile,row.station,format(row.previous),format(row.current),format(row.change)]));
 }
 if(old?.status==='VERIFIED'&&now?.status==='VERIFIED'){
  table(box,[tr('Diagnostic coverage','诊断覆盖'),tr('Previous','上次'),tr('Current','本次')],[
   [tr('Native warning coverage','原生警告覆盖'),old.warning_coverage,now.warning_coverage],
   [tr('Native messages','原生信息条数'),old.native_messages??'—',now.native_messages??'—'],
   [tr('Combined diagnostic records','合并诊断记录'),old.issue_count,now.issue_count]]);
  const codes=[...new Set([...Object.keys(old.counts),...Object.keys(now.counts)])].sort();
  const counts=details(box,'Diagnostic changes by category','按类别查看诊断变化');
  const amount=(d,code)=>d.counts[code]??(code.startsWith('NATIVE_')&&d.severity==null?'—':0);
  table(counts,[tr('Category','类别'),tr('Previous','上次'),tr('Current','本次')],codes.map(code=>[code,amount(old,code),amount(now,code)]));
 }else box.append(el('p',tr('Diagnostic comparison is incomplete. ','诊断对比尚不完整。')+[old?.error,now?.error].filter(Boolean).join(' '),'warning'));
 box.append(el('p',tr('Matched section IDs use hash-verified native water levels. Review any changed section positions. The workflow flags changes above ','匹配断面编号采用已核验哈希的原生水位。请核对断面位置改动。工作流将超过 ')+
  comparison.threshold_ft+tr(' ft for review. This threshold supports screening. Hydraulic convergence, source adequacy and engineering acceptance require separate assessment.',' ft 的变化标为待复核，此阈值用于筛查。水力收敛、资料充分性与工程验收仍需分别判断。')));
}

let lastResultPage={project:null,key:'overview'};
function resultPages(parent){
 const navigation=el('div',undefined,'result-pages');
 navigation.setAttribute('role','tablist');navigation.setAttribute('aria-label',tr('Result views','结果视图'));parent.append(navigation);
 const pages={},tabs={};
 const names={overview:['Summary','结果总览'],review:['Hydraulic review','水力复核'],delivery:['Reports and maps','报告与地图']};
 function select(key){
  for(const [name,panel] of Object.entries(pages)){
   panel.hidden=name!==key;tabs[name].setAttribute('aria-selected',String(name===key));tabs[name].tabIndex=name===key?0:-1;
  }
  lastResultPage={project:current.id,key};rememberView({project:current.id,page:'results',resultTab:key});
 }
 for(const [key,labels] of Object.entries(names)){
  const control=el('button',tr(...labels));control.type='button';control.id='result-tab-'+key;control.setAttribute('role','tab');
  const panel=el('section');panel.id='result-panel-'+key;panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',control.id);panel.tabIndex=0;
  control.setAttribute('aria-controls',panel.id);control.onclick=()=>select(key);
  panel.addEventListener('steadyreach-show-panel',()=>select(key));
  control.onkeydown=event=>{
   const keys=Object.keys(names),i=keys.indexOf(key);
   const next={Home:0,End:keys.length-1,ArrowLeft:(i+keys.length-1)%keys.length,ArrowRight:(i+1)%keys.length}[event.key];
   if(next===undefined)return;event.preventDefault();select(keys[next]);tabs[keys[next]].focus();
  };
  tabs[key]=control;pages[key]=panel;navigation.append(control);parent.append(panel);
 }
 select(lastResultPage.project===current.id?lastResultPage.key:'overview');
 return pages;
}
function renderResultTools(parent,delivery){
 renderNextReview(parent);
 const advanced=details(parent,'Investigate the results and compare scenarios','深入核查结果与比较工况');
 if(current.model_type==='river'&&!current.native_review){renderWarningStudy(advanced);renderFloodplain(advanced);renderRiverComparison(advanced);renderRiverObservations(advanced);renderFieldFeedback(advanced);}
 renderCheckBatch(advanced);
 renderResultAtlas(advanced);
 renderStudy(advanced);
 renderSpacing(advanced);
 renderCoverage(advanced);
 if(current.delivery?.mapped&&!current.exports_need_refresh)delivery.append(button('Open QGIS review copy','打开 QGIS 复核副本',async()=>{const r=await api('qgis-preview',{id:current.id});notify(tr('Opened a separate preview copy: ','已打开独立复核副本：')+r.path);}));
 const box=details(delivery,'Complete native outputs / refresh deliverables','补齐原生输出／更新交付包',!!current.exports_need_refresh||['UNAVAILABLE','COMPLETE_WITH_DIFFERENCES'].includes(current.automatic_native_outputs?.status));box.id='qa-tool-native';
 const deliveryAnchor=el('div');guidanceTarget(deliveryAnchor,'delivery');box.append(deliveryAnchor);
 if(current.model_type==='river')box.append(el('p',tr('The workflow exports the full native warning table for the river reach. There are no culvert group tables.','工作流导出整个河段的原生警告表，纯河道没有涵孔组表。')));
 else box.append(el('p',tr('After a new calculation, SteadyReach automatically exports every computed culvert group/profile and the full native warning table, then cross-checks them before reporting. Hydraulic interpretation still needs review.','新计算结束后，SteadyReach 自动导出各工况、各孔组明细及完整原生警告表，交叉核验后纳入报告。水力含义仍需工程判断。')));
 const automatic=current.automatic_native_outputs;
 const exported=['COMPLETE','COMPLETE_WITH_DIFFERENCES'].includes(automatic?.status);
 if(exported)box.append(el('p',tr('Automatic export complete: ','自动导出完成：')+(current.model_type==='river'?'':automatic.group_tables+tr(' group tables; ',' 份孔组表；'))+automatic.warning_messages+tr(' native messages.',' 条原生信息。'),'status'));
 else {box.append(el('p',tr('Native export is pending. The saved computation remains available.','原生导出待补齐，已保存计算结果仍可使用。'),'warning'));if(automatic?.error)box.append(el('p',automatic.error,'warning'));}
 if(automatic?.display_differences)box.append(el('p',automatic.display_differences+tr(' display/machine differences require review. Original HDF/COM values are unchanged.',' 项原生显示／机器值差异待复核，原始 HDF／COM 数值未改变。'),'warning'));
 const retryBox=details(box,'Retry native export without solving','重试原生导出（不重新求解）',!exported);
 retryBox.append(el('p',tr('Save and close HEC-RAS first. The action uses a separate copy, briefly opens native output windows and uses the clipboard. Keep Windows signed in and avoid copying other content during export. Reports and both packages update automatically; the original run is retained.','请先保存并关闭 HEC-RAS。此操作使用独立副本，会短暂打开原生输出窗口并使用剪贴板；请保持 Windows 登录，导出时暂勿复制其他内容。报告及两种交付包会自动更新，原运行保留。')),
 button('Export native outputs and update deliverables','自动导出原生结果并更新交付包',async()=>{await api('native-export',{id:current.id});await open(current.id);},'primary'));
 const guide=details(box,'How to export missing native tables','如何导出缺失的原生表');
 if(current.model_type==='river')guide.append(el('p',tr('Open a review copy in HEC-RAS. View → Summary Errors, Warnings and Notes: choose this plan, all computed profiles and the complete river/reach, then export its text. No structure output is required.','用 HEC-RAS 打开复核副本，View → Summary Errors, Warnings and Notes 选择本计划、全部工况和完整河段并导出文本。纯河道无需结构表。')));
 else guide.append(el('p',tr('Open a review copy of this run in HEC-RAS 7.0.1. View → Summary Errors, Warnings and Notes: select the computed plan, all requested profiles and the full river/reach; export its text. For each Culvert Output group/profile, use Copy to Clipboard (Data and Headings), paste into a UTF-8 .txt file, and keep the header and blank fields. Import the texts together.','用 HEC-RAS 7.0.1 打开本次运行的复核副本。View → Summary Errors, Warnings and Notes：选择本次计划、全部工况及完整河段，导出文本。每组／工况的 Culvert Output 使用 Copy to Clipboard (Data and Headings)，粘贴到 UTF-8 .txt，保留表头及空白字段，然后集中导入。')));
 const files=field(guide,'native-output-files','Warning / group text files','警告／孔组文本文件','','file');files.multiple=true;files.accept='.txt';
 const scope=check(guide,'The warning export includes this run’s complete river/reach and every computed profile','警告文本覆盖本次运行完整河段及全部计算工况',false,()=>{});
 guide.append(button('Import and cross-check exports','导入并交叉核验',async()=>{if(!files.files.length)throw Error(tr('Select text exports first.','请先选择文本文件。'));await api('native-outputs',{id:current.id,revision:current.revision,run_hash:current.summary.sha256,all_profiles:scope.checked,files:await encodeFiles(files.files)});await open(current.id);notify(tr('Exports checked and saved as a new result edition. Original calculation retained. Refresh deliverables next.','导出已核验并保存为新结果版本，原计算保留。接下来更新交付包。'));}));
 if(current.native_supplement){const s=current.native_supplement;box.append(el('p',s.rows.length+tr(' group tables · ',' 份孔组表 · ')+(s.warnings?.records.length||0)+tr(' native messages',' 条原生信息'),'status'));if(s.missing_groups.length)box.append(el('p',tr('Still missing: ','仍缺：')+JSON.stringify(s.missing_groups),'warning'));table(box,['Profile','Group','Q cfs','V US ft/s','V DS ft/s','Control'],s.rows.map(r=>[r.profile,r.native_group,r.flow_cfs,r.inlet_velocity_fts,r.outlet_velocity_fts,r.control]));box.append(el('small',tr('Cross-checked native text at display precision. Blank road-flow fields remain unknown.','已交叉核验的原生文本，精度以原生显示为准；道路流量空白仍为未知。')));}
 if(current.exports_need_refresh)box.append(el('p',tr('The earlier reports/packages are retained but belong to the previous edition.','旧报告和交付包仍保留，属于上一版本。'),'warning'));
 box.append(button('Update reports and both packages','更新报告及两种交付包',async()=>{await api('delivery',{id:current.id});await open(current.id);},'primary'));

}

function renderStudyProgress(parent,progress){
 const states={QUEUED:tr('Queued','等待中'),IN_PROGRESS:tr('Computing / exporting reports','计算／导出报告中'),COMPUTED:tr('Computed','已计算'),BLOCKED:tr('Needs input','待处理'),FAILED:tr('Failed','失败'),SKIPPED:tr('Unused after batch stopped','批次停止后未使用')};
 const names={baseline:tr('Baseline','基准'),refinement_1:tr('First refinement','第一级加密'),refinement_2:tr('Second refinement','第二级加密')};
 table(parent,[tr('Case','工况'),tr('Sections','断面数'),tr('Progress','进度')],progress.map(row=>[names[row.id]||(row.parameter_path?sensitivityParameterLabel(row.parameter_path)+' = '+row.parameter_value:row.id),row.section_count??'—',states[row.status]||row.status]));
 for(const row of progress)if(row.error)parent.append(el('p',row.id+' · '+row.error,'warning'));
}

function renderCoverage(parent){
 if(current.native_review||current.model_type!=='river')return;
 const pending=current.pending_study_plan?.analysis_kind==='coverage_repair';
 const box=details(parent,'Automatic wet-end repair batch','湿端自动修订批次',pending||!!current.coverage_result);box.id='qa-tool-coverage';
 box.append(el('p',tr('Confirm a width and calculation limit once. Starting from this saved baseline, each round uses the preceding actual HEC-RAS water levels to extend DEM section ends, then calculates again. Final reports and both mapped packages are exported automatically.',
  '集中确认宽度与计算轮数上限后，程序从本次已保存基准出发，按上轮真实 HEC-RAS 水位延伸 DEM 断面端部，再计算。最后自动生成报告及两种带地图交付包。')));
 const policy=pending?current.pending_study_plan.policy:{};
 const width=field(box,'coverage-width','Maximum total section width (ft)','总断面宽度上限（ft）',policy.maximum_width_ft??2000,'number');width.min=120;width.max=2000;
 const rounds=field(box,'coverage-rounds','Maximum repair calculations','最多修订计算轮数',policy.maximum_rounds??3,'number');rounds.min=1;rounds.max=5;rounds.step=1;
 box.append(el('small',tr('These are search and computation bounds. New exterior terrain uses the existing overbank roughness assumption. Review floodplain connectivity and material suitability before confirming.',
  '以上为搜索及计算上限。新增外部地形沿用已采用的漫滩糙率假设，确认前请判断过流连通性与材料适用性。')));
 let proposal=null;
 const preview=el('div');
 box.append(button('Preview bounded wet-end repair','预览限定范围内的湿端修订',async()=>{
  proposal=await api('study-prepare',{id:current.id,revision:current.revision,kind:'coverage',maximum_rounds:Number(rounds.value),maximum_width_ft:Number(width.value)});
  current.pending_study=proposal.entry;current.pending_study_plan=proposal.plan;current.coverage_preview=proposal.preview;
  showProposal();notify(tr('Preview saved. Review the extent and assumptions, then confirm once.','预览已保存。核对范围与假设后，集中确认一次即可。'));
 }),preview);
 for(const field of [width,rounds])field.addEventListener('input',()=>{proposal=null;preview.replaceChildren(el('p',tr('Bounds changed. Generate a new preview before calculating.','上限已修改，请重新生成预览后计算。'),'warning'));});
 function showProposal(){
  preview.replaceChildren();const p=proposal.preview,policy=proposal.plan.policy;
  preview.append(el('p',p.wet_sections.length+tr(' wet-end sections · ',' 条湿端断面 · ')+p.changes.length+tr(' proposed first-round extensions',' 条首轮延伸建议'),'status'));
  table(preview,['RS',tr('Left added ft','左端增加 ft'),tr('Right added ft','右端增加 ft')],p.changes.map(c=>[c.rs,c.left_added_ft.toFixed(2),c.right_added_ft.toFixed(2)]));
  for(const change of p.changes){
   const row=p.geometry.cross_sections.find(r=>r.rs===change.rs),water=p.water_levels_ft[String(change.rs)]??change.threshold_prior_wse_ft;
   const profile=details(preview,'RS '+row.rs+' · proposed profile','RS '+row.rs+' · 建议剖面');
   const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 700 230');svg.classList.add('repair-profile');svg.setAttribute('role','img');svg.setAttribute('aria-label','Coverage DEM RS '+row.rs);profile.append(svg);
   const x=row.station_ft,z=row.elevation_ft,lo=Math.min(...z,water),hi=Math.max(...z,water),px=v=>55+(v-x[0])/(x.at(-1)-x[0])*615,py=v=>185-(v-lo)/Math.max(1,hi-lo)*155;
   for(let i=0;i<=5;i++){const value=lo+(hi-lo)*i/5;svgEl(svg,'line',{x1:55,x2:670,y1:py(value),y2:py(value),stroke:'#d9e1e7'});svgEl(svg,'text',{x:3,y:py(value)+4}).textContent=value.toFixed(1);}
   for(let i=0;i<=5;i++){const value=x[0]+(x.at(-1)-x[0])*i/5;svgEl(svg,'line',{x1:px(value),x2:px(value),y1:30,y2:185,stroke:'#d9e1e7'});svgEl(svg,'text',{x:px(value),y:201,'text-anchor':'middle'}).textContent=value.toFixed(0);}
   svgEl(svg,'polyline',{points:x.map((v,i)=>[px(v),py(z[i])].join(',')).join(' '),fill:'none',stroke:'#795438','stroke-width':2});
   svgEl(svg,'line',{x1:55,x2:670,y1:py(water),y2:py(water),stroke:'#1679be','stroke-width':2});
   for(const bank of row.bank_stations_ft)svgEl(svg,'line',{x1:px(bank),x2:px(bank),y1:25,y2:190,stroke:'#b83b29','stroke-dasharray':'5 3'});
   svgEl(svg,'text',{x:55,y:215}).textContent=tr('Width / elevation in ft. Blue is preceding water level.','宽度／高程单位 ft。蓝线为上轮水位。');
  }
  if(p.unresolved.length)preview.append(el('p',tr('Fixed-direction proposals still leave these locations for review — ','保持方向的建议仍有以下位置待复核 — ')+p.unresolved.map(r=>'RS '+r.rs).join(', '),'warning'));
  preview.append(el('p',tr('The batch stops when ends are dry, the limit is reached, no compatible extension is available, or a computation fails. Original samples, bank plan positions, section directions, flows, boundaries and roughness are checked each round. Other hydraulic findings remain for review.',
   '端点高于水位、达到轮数上限、没有可用延伸或计算失败时停止。每轮核验原内部采样、岸站实际位置、断面方向、流量、边界及糙率。其他水力问题继续保留待复核。')));
  if(!p.changes.length){preview.append(el('p',tr('No first-round extension can be calculated from this preview. Review the listed locations or retain the computed baseline.','本次预览没有可计算的首轮延伸。请复核所列位置，或保留已计算基准。'),'status'));return;}
  const confirmation=check(preview,'I confirm these bounds and conditional exterior assumptions for the complete batch','我确认以上上限及外部地形条件性假设，授权执行本批次',false,()=>{});
  preview.append(button('Confirm and run repair batch','确认并运行修订批次',async()=>{
   if(!proposal||!confirmation.checked)throw Error(tr('Review and confirm the current preview first.','请先核对并确认当前预览。'));
   await api('study-start',{id:current.id,revision:current.revision,token:proposal.token,confirmed:true});await open(current.id);
  },'primary'),el('small',tr('Up to ','最多 ')+policy.maximum_rounds+tr(' new calculations, within ',' 轮新计算，总宽度限于 ')+policy.maximum_width_ft+' ft.'));
 }
 if(pending&&current.coverage_preview){proposal={plan:current.pending_study_plan,token:current.pending_study.sha256,preview:current.coverage_preview};showProposal();}
 const result=current.coverage_result;
 if(!result)return;
 const states={COVERAGE_RESOLVED_REVIEW_REQUIRED:tr('Section ends are dry. Hydraulic review remains open.','断面端点均高于水位，水力复核仍待完成。'),ROUND_LIMIT_REQUIRES_REVIEW:tr('Round limit reached. Wet ends remain.','达到轮数上限，仍有湿端待处理。'),GEOMETRY_REVIEW_REQUIRED:tr('No further compatible fixed-direction extension. Review geometry.','保持方向下暂无可用延伸，请复核几何。'),INCOMPLETE:tr('Batch incomplete. Review the saved failure and retry.','批次尚未完成，请查看失败记录并重试。')};
 box.append(el('p',states[result.status]||result.status,result.status==='COVERAGE_RESOLVED_REVIEW_REQUIRED'?'status':'warning'));
 table(box,[tr('Case','工况'),tr('Wet sections','湿端断面'),tr('Native messages','原生信息'),tr('Max successive |ΔWSE| ft','逐轮最大 |Δ水位| ft')],result.cases.map(r=>[
  r.reused_baseline?tr('Saved baseline (reused)','已保存基准（复用）'):r.id,r.wet_sections?.length??'—',r.diagnostics?.native_messages??'—',Number.isFinite(r.max_wse_change_ft)?r.max_wse_change_ft.toFixed(6):'—']));
 box.append(el('p',tr('The final case has its own reports and packages below. The original baseline remains available in the main results area. Section-end coverage, spacing convergence and engineering acceptance require their respective reviews.',
  '最终工况的独立报告和交付包见下方，原基准保留在主结果区。断面端点覆盖、断面加密收敛及工程接受需分别判断。')),
  button('Open repair evidence','打开修订证据',()=>api('open-folder',{id:current.id,path:current.latest_coverage.path.replace(/\/[^/]+$/,'')})));
 const exports=current.coverage_exports;
 const finalCase=result.cases.filter(row=>row.status==='COMPUTED').at(-1);
 if(finalCase)box.append(button('Continue from final repair with automatic QA preparation','从最终修订工况继续自动准备',()=>continueStudyCase('coverage',finalCase.id,current.latest_coverage.sha256)));
 if(exports){
  box.append(button('Open final repair reports','打开最终修订报告',()=>api('open-folder',{id:current.id,path:exports.reports})));
  for(const key of ['minimal','complete'])if(exports.delivery?.[key])box.append(button(key==='minimal'?'Open repaired Minimal':'Open repaired Complete',key==='minimal'?'打开修订后最小包':'打开修订后完整包',()=>api('open-folder',{id:current.id,path:exports.delivery[key].path})));
  box.append(el('p',tr('Final delivery status — ','最终交付状态 — ')+exports.delivery?.status));
  if(exports.delivery?.error)box.append(el('p',exports.delivery.error,'warning'));
 }else box.append(el('p',tr('Final exports are pending. If the job stopped, retry the confirmed batch to reuse completed calculations and finish exporting.','最终导出待完成。如任务已停止，可重试已确认批次，复用完成的计算并继续导出。'),'warning'));
}

function renderSpacing(parent){
 if(current.native_review||current.model_type!=='river')return;
 const box=details(parent,'Section-spacing trial','断面加密试算',!!current.spacing_result);box.id='qa-tool-spacing';
 box.append(el('p',tr('Recommend intervals from native results, use spacing-related warnings, or select the entire reach for two nested DEM refinements. Review the added sections and inferred banks once, then run the baseline and both refinements sequentially.','按原生结果自动推荐、按加密相关警告定位区间，或选择全河段，准备两级嵌套 DEM 加密。集中核对新增断面和推定岸站后，依次计算基准及两级加密。')));
 const scope=field(box,'spacing-scope','Refinement extent','加密范围',current.pending_study_plan?.scope||'automatic','select',[
  ['automatic','Recommend from native results','根据原生结果自动推荐'],['warnings','Intervals beside spacing-related warnings','加密相关警告相邻区间'],['all','Entire continuous reach','完整连续河段']]);
 const limit=field(box,'spacing-limit','Maximum recommended intervals','推荐区间数量上限',current.pending_study_plan?.selection?.maximum_intervals??12,'number');limit.min=1;limit.max=100;limit.step=1;limit.disabled=scope.value!=='automatic';
 const adaptive=check(box,'Automatically extend added wet sections within the confirmed limits','在确认范围内自动延伸新增湿端断面',current.pending_study_plan?!!current.pending_study_plan.coverage_policy:true,()=>{});
 const rounds=field(box,'spacing-rounds','Maximum coverage correction rounds','覆盖修正轮数上限',current.pending_study_plan?.coverage_policy?.maximum_rounds??2,'number');rounds.min=1;rounds.max=3;rounds.step=1;
 const width=field(box,'spacing-width','Maximum corrected section width (ft)','修正后断面总宽度上限（ft）',current.pending_study_plan?.coverage_policy?.maximum_width_ft??2000,'number');width.min=120;width.max=2000;
 box.append(el('p',tr('Each extra round may run three real cases. Only exterior DEM samples on added sections can change; shared profiles are updated together. Original sections, bank plan positions and hydraulic controls remain fixed.','每个追加轮次可能运行三个真实工况。仅延伸新增断面的外侧 DEM 采样，共有断面同步更新；原始断面、岸站平面位置和水力控制参数保持固定。')));
 const preview=el('div');let proposal=null;
 box.append(button('Prepare nested spacing preview','生成两级加密预览',async()=>{
  proposal=await api('study-prepare',{id:current.id,revision:current.revision,kind:'spacing',scope:scope.value,maximum_intervals:Number(limit.value),coverage_policy:adaptive.checked?{maximum_rounds:Number(rounds.value),maximum_width_ft:Number(width.value)}:null});
  current.pending_study=proposal.entry;current.pending_study_plan=proposal.plan;
  showProposal();notify(tr('Spacing preview saved. Review the proposed sections before confirming calculation.','加密预览已保存，请核对新增断面后确认计算。'));
 }),preview);
 const resetPreview=()=>{proposal=null;preview.replaceChildren();limit.disabled=scope.value!=='automatic';rounds.disabled=width.disabled=!adaptive.checked;};scope.addEventListener('input',resetPreview);limit.addEventListener('input',resetPreview);
 adaptive.addEventListener('change',resetPreview);rounds.addEventListener('input',resetPreview);width.addEventListener('input',resetPreview);rounds.disabled=width.disabled=!adaptive.checked;
 function showProposal(){
  const plan=proposal.plan;if(renderSpacingPreview(preview,plan)===false)return;
  const confirmed=check(preview,'I confirm the sections, inferred banks, assumptions and any displayed automatic correction bounds','我确认断面、推定岸站、假设及显示的自动修正范围',false,()=>{});
  preview.append(button(plan.coverage_policy?'Confirm and run bounded spacing batch':'Confirm and run three spacing cases',plan.coverage_policy?'确认并运行有界加密批次':'确认并计算三个加密工况',async()=>{
   if(!proposal||!confirmed.checked)throw Error(tr('Review and confirm this spacing preview first.','请先核对并勾选确认本次加密预览。'));
   await api('study-start',{id:current.id,revision:current.revision,token:proposal.token,confirmed:true});await open(current.id);
  },'primary'));
 }
 if(current.pending_study_plan?.analysis_kind==='section_spacing'){
  proposal={plan:current.pending_study_plan,token:current.pending_study.sha256};showProposal();
 }
 if(current.spacing_result){
  const r=current.spacing_result,c=r.convergence;
  const wetCases=r.cases.filter(v=>v.wet_sections?.length);
  if(r.coverage_batch){
   const b=r.coverage_batch,labels={COVERAGE_RESOLVED_REVIEW_REQUIRED:tr('Added-section coverage cycle completed; hydraulic review remains open','覆盖循环完成，水力复核仍待完成'),BASELINE_COVERAGE_REVIEW:tr('Baseline ends need review; automatic changes stopped','基准端点需复核，已停止自动改动'),ROUND_LIMIT_REVIEW_REQUIRED:tr('Confirmed correction-round limit reached','已达到确认的修正轮数上限'),RETAINED_OR_GEOMETRY_REVIEW:tr('Original sections or geometry constraints need review','原有断面或几何约束需要复核'),INCOMPLETE:tr('A round is incomplete; resolve its error and retry','本轮未完成，请处理错误后重试')};
   box.append(el('p',labels[b.status]||b.status,b.status==='COVERAGE_RESOLVED_REVIEW_REQUIRED'?'status':'warning'));
   table(box,[tr('Round (0 = initial)','轮次（0 为初始）'),tr('Wet sections: baseline / level 1 / level 2','湿端数：基准／一级／二级'),tr('Numerical spacing status','数值加密状态')],b.round_summaries.map(v=>[v.round,v.wet_sections.map(n=>n??'—').join(' / '),v.status]));
  }
  if(r.deferred_intervals?.length)box.append(el('p',r.deferred_intervals.length+tr(' candidate intervals were deferred by the search limit and remain untested.',' 个候选区间因搜索上限暂缓，仍未测试。'),'warning'));
  if(r.excluded_intervals?.length)box.append(el('p',tr('Full-reach spacing coverage is incomplete. Excluded intervals — ','全河段加密覆盖尚不完整，排除区间 — ')+r.excluded_intervals.map(v=>v.upstream_rs+' → '+v.downstream_rs).join(', '),'warning'));
  box.append(el('p',r.status==='STABLE_AT_REVIEW_THRESHOLD'?tr('Both nested refinements meet the internal water-level threshold.','两次嵌套加密均达到内部水位变化阈值。'):tr('Spacing convergence remains open.','断面加密收敛仍待处理。'),r.status==='STABLE_AT_REVIEW_THRESHOLD'?'status':'warning'));
  if(c)table(box,[tr('Profile','工况'),tr('First refinement max |ΔWSE| ft','第一级最大 |Δ水位| ft'),tr('Second refinement max |ΔWSE| ft','第二级最大 |Δ水位| ft')],c.rows.map(v=>[v.profile,...v.last_two_max_xs_deltas_ft.map(x=>x.toFixed(6))]));
  table(box,[tr('Case','工况'),tr('Sections','断面数'),tr('Native messages','原生信息'),tr('Wet-end sections','湿端断面数')],r.cases.map(v=>[v.id,v.section_count,v.diagnostics?.native_messages??'—',v.wet_sections?new Set(v.wet_sections.map(Number)).size:'—']));
  if(wetCases.length){
   box.append(el('p',tr('Wet section ends make this spacing comparison provisional, even when water-level differences meet the threshold. Use the computed case below to prepare an independent geometry revision. Review its proposed coverage changes, confirm and compute it, then repeat spacing assessment from the revised baseline. The existing nested trial remains unchanged.','湿端使本次加密对比仍属暂定，即使水位差达到阈值也不代表收敛验收完成。可从下方已计算工况自动准备独立几何修订版，核对覆盖建议、确认计算后，再从新基准进行加密评估。现有嵌套试算保留不变。'),'warning'));
   table(box,[tr('Case','工况'),tr('Wet RS retained from baseline','基准已有断面的湿端 RS'),tr('Wet RS added by refinement','加密新增断面的湿端 RS')],wetCases.map(v=>[v.id,v.retained_wet_sections?(v.retained_wet_sections.join(', ')||tr('None','无')):tr('Not classified in this saved result','旧结果未分类'),v.added_wet_sections?(v.added_wet_sections.join(', ')||tr('None','无')):tr('Not classified in this saved result','旧结果未分类')]));
  }
  if(r.cases.length===3&&!r.failed_cases?.length&&r.cases.every(row=>row.status==='COMPUTED'))renderSpacingDiagnostics(box);
  const completed=r.cases.filter(row=>row.status==='COMPUTED'&&row.id!=='baseline');
  if(completed.length){
   const selected=field(box,'spacing-continue-case','Continue from computed case','选择继续使用的已计算工况',completed.at(-1).id,'select',completed.map(row=>[row.id,row.id,row.id]));
   box.append(button('Prepare editable QA revision from selected case','从所选工况自动准备可编辑修订版',()=>continueStudyCase('spacing',selected.value,current.latest_spacing.sha256)));
  }
  box.append(el('p',tr('The 0.10 ft threshold is a workflow screen. Results cover the selected intervals and compare every retained section. Hydraulic warnings, submerged-bed accuracy and engineering acceptance remain open. The baseline deliverables can be refreshed to include this comparison.','0.10 ft 为工作流筛查阈值。结论限于所选区间，并对比全部保留断面。水力警告、水下河床准确性与工程验收仍需判断。可更新基准报告及交付包以纳入本次对比。')),
   button('Open spacing trial files','打开加密试算文件',()=>api('open-folder',{id:current.id,path:current.latest_spacing.path.replace(/\/[^/]+$/,'')})));
  if(r.failed_cases?.length){
   box.append(el('p',tr('Incomplete cases — ','未完成工况 — ')+r.failed_cases.join(', '),'warning'),
    el('p',tr('Retry the confirmed batch after resolving its error. Intact completed cases and reports are reused. Missing reports are regenerated without solving. Changed native evidence blocks reuse; only unfinished calculations may call the solver.','处理错误后可重试已确认批次。完整的已完成工况及报告直接复用；缺失报告单独补生成。原生证据变更会阻止复用，仅尚未完成的计算可能调用求解器。')),
    button('Retry incomplete spacing batch','重试未完成加密批次',async()=>{await api('study-start',{id:current.id,revision:current.revision,token:(r.coverage_batch?.study||r.study).sha256,confirmed:true,retry:true});await open(current.id);}));
  }
 }
}

function renderSpacingPreview(preview,plan){
 preview.replaceChildren();
  const reasonLabels={SECTION_SPECIFIC_CONTROLS:tr('Section-specific roughness/ineffective areas','断面特定糙率／非有效流区'),BENT_CUTLINE:tr('Bent cutline requires interpretation','折线断面需判读'),BELOW_TWO_CELL_NESTED_SPACING:tr('Two refinement levels would be below DEM spacing limit','两级加密小于 DEM 间距限值'),NATIVE_STATION_PRECISION:tr('Native station precision limit','原生断面编号精度限制'),DEM_OR_LAYOUT_CONSTRAINT:tr('DEM coverage or cutline-layout constraint','DEM 覆盖或断面布置限制'),CONFIRMED_SEARCH_LIMIT:tr('Outside selected interval count','超过所选区间数量'),SECTION_COUNT_LIMIT:tr('500-section limit','500 条断面上限')};
  if(plan.selection){
   preview.append(el('p',tr('Native-result selection is a review proposal, not a diagnosis. Energy loss >1 ft or weighted velocity-head change >0.5 ft supports a spacing check; channel Froude values crossing below 0.9 and above 1.1 flag a transition for interpretation. Solver-difficulty warnings are considered first.','原生结果推荐用于复核，不作原因诊断。能量损失大于 1 ft 或加权流速水头变化大于 0.5 ft 提示间距检查；主槽弗劳德数跨越 0.9 以下和 1.1 以上提示流态判读。优先考虑求解困难警告。')));
   if(plan.selection.unlocated_spacing_issues?.length)preview.append(el('p',plan.selection.unlocated_spacing_issues.length+tr(' spacing messages could not be located; review native evidence.',' 条加密相关信息无法定位，请复核原生证据。'),'warning'));
  }
  for(const [key,en,zh] of [['excluded_intervals','Excluded intervals: geometry/data decision needed','排除区间：需要几何／资料判断'],['deferred_intervals','Deferred by the search limit; not tested','因搜索上限暂缓：尚未测试']])if(plan[key]?.length){const list=details(preview,en,zh);table(list,['RS → RS',tr('Reason','原因')],plan[key].map(v=>[v.upstream_rs+' → '+v.downstream_rs,(reasonLabels[v.reason_code]||v.reason||tr('Geometry constraint','几何限制'))]));}
  if(plan.excluded_intervals?.length||plan.deferred_intervals?.length)preview.append(el('p',tr('Some intervals remain outside this trial. A stable result will apply only to the selected changes.','部分区间不在本次试算内；结果稳定也仅适用于所选加密改动。'),'warning'));
  if(plan.status==='NO_ELIGIBLE_INTERVALS'){
   preview.append(el('p',tr('No complete two-level trial can be prepared within these constraints. Review the exclusions or prepare an editable geometry revision. No calculation was started.','在当前约束内无法准备完整的两级试算。请查看排除原因，或准备可编辑几何修订版。未启动计算。'),'warning'));return false;
  }
  table(preview,[tr('Case','工况'),tr('Sections','断面数'),tr('Added this level','本级新增')],plan.cases.map(c=>[c.id,c.section_count,c.added_sections.length]));
  if(plan.map_geometry){
   const map=details(preview,'Section plan view','断面平面位置');
   map.append(el('p',tr('Gray retained sections · orange first refinement · blue second refinement · magenta flowline.','灰色为保留断面，橙色为第一级新增，蓝色为第二级新增，紫红色为流线。')));
   const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 700 520');svg.classList.add('repair-profile');svg.setAttribute('role','img');svg.setAttribute('aria-label',tr('Nested section positions','嵌套加密断面位置'));map.append(svg);
   const groups=[{rows:plan.map_geometry.retained,color:'#6d7c83'},...plan.cases.filter(c=>c.added_sections.length).map((c,i)=>({rows:c.added_sections,color:i?'#1679be':'#bc7019'}))];
   const points=groups.flatMap(g=>g.rows.flatMap(r=>r.cutline_xy)),xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
   const lo=[Math.min(...xs),Math.min(...ys)],hi=[Math.max(...xs),Math.max(...ys)],scale=Math.min(650/(hi[0]-lo[0]),470/(hi[1]-lo[1]));
   const pt=p=>[350+(p[0]-(lo[0]+hi[0])/2)*scale,260-(p[1]-(lo[1]+hi[1])/2)*scale].join(',');
   for(const group of groups)for(const row of group.rows)svgEl(svg,'polyline',{points:row.cutline_xy.map(pt).join(' '),fill:'none',stroke:group.color,'stroke-width':1});
   svgEl(svg,'polyline',{points:plan.map_geometry.flowline.map(pt).join(' '),fill:'none',stroke:'#aa245d','stroke-width':2});
  }
  const intervals=details(preview,'Selected intervals and warning locations','所选区间及警告位置');
  table(intervals,['RS → RS',tr('Channel length (ft)','主槽长度（ft）'),tr('Selection basis','选择依据')],plan.intervals.map(v=>[
   v.upstream_rs+' → '+v.downstream_rs,v.channel_length_ft.toFixed(2),v.reasons.join(', ')||tr('Full-reach selection','已选择全河段')]));
  const observed=plan.intervals.flatMap(v=>(v.observations||[]).map(o=>[v.upstream_rs+' → '+v.downstream_rs,o.profile,...[o.energy_loss_ft,o.velocity_head_change_ft,o.upstream_froude,o.downstream_froude].map(n=>Number.isFinite(n)?n.toFixed(4):'—')]));
  if(observed.length){const values=details(preview,'Computed evidence for recommended intervals','推荐区间的计算依据');table(values,['RS → RS',tr('Profile','工况'),tr('Energy loss ft','能量损失 ft'),tr('Velocity-head change ft','流速水头变化 ft'),'Fr US','Fr DS'],observed);}
  for(const c of plan.cases.filter(c=>c.added_sections.length)){
   const area=details(preview,c.id+' · added sections',c.id+' · 新增断面');
   for(const row of c.added_sections){
    const profile=details(area,'RS '+row.station+' · '+row.width_ft.toFixed(1)+' ft','RS '+row.station+' · '+row.width_ft.toFixed(1)+' ft');
    profile.append(el('p',tr('Adjacent sections / inferred banks (ft) — ','相邻断面／推定岸站（ft）— ')+row.bracket.join(' / ')+' · '+row.banks_ft.map(v=>v.toFixed(2)).join(' / ')));
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 700 230');svg.classList.add('repair-profile');svg.setAttribute('role','img');svg.setAttribute('aria-label','DEM RS '+row.station);profile.append(svg);
    const x=row.station_ft,z=row.elevation_ft,lo=Math.min(...z),hi=Math.max(...z),px=v=>55+(v-x[0])/(x.at(-1)-x[0])*615,py=v=>185-(v-lo)/Math.max(1,hi-lo)*155;
    for(let i=0;i<=5;i++){const y=30+i*31;svgEl(svg,'line',{x1:55,x2:670,y1:y,y2:y,stroke:'#d9e1e7'});svgEl(svg,'text',{x:3,y:y+4}).textContent=(hi-(hi-lo)*i/5).toFixed(1);}
    for(let i=0;i<=5;i++){const value=x[0]+(x.at(-1)-x[0])*i/5;svgEl(svg,'line',{x1:px(value),x2:px(value),y1:30,y2:185,stroke:'#d9e1e7'});svgEl(svg,'text',{x:px(value),y:201,'text-anchor':'middle'}).textContent=value.toFixed(0);}
    svgEl(svg,'polyline',{points:x.map((v,i)=>[px(v),py(z[i])].join(',')).join(' '),fill:'none',stroke:'#795438','stroke-width':2});
    for(const bank of row.banks_ft)svgEl(svg,'line',{x1:px(bank),x2:px(bank),y1:25,y2:190,stroke:'#b83b29','stroke-dasharray':'5 3'});
    svgEl(svg,'text',{x:55,y:215}).textContent=tr('Station / elevation in ft','横距与高程单位均为 ft');
    profile.append(el('p',tr('Projected cutline — ','投影断面线 — ')+row.cutline_xy.map(p=>p.map(v=>v.toFixed(2)).join(', ')).join(' → ')));
   }
  }
  preview.append(el('p',tr('Added elevations are sampled from the DEM. Banks use adjacent bank fractions, added loss coefficients use the upstream interval, and the original three reach-length totals are partitioned. Review these assumptions together. Changes to these proposals require a new geometry revision.','新增高程来自 DEM；岸站按相邻断面岸站比例推定，新增损失系数沿用上游区间，原左漫滩／主槽／右漫滩总流程长度按交点位置分配。请集中审核这些假设；需要改动时先创建几何修订版。'),'warning'));
  preview.append(el('p',tr('New section ends are screened against the maximum baseline WSE interpolated along the saved flowline. Bounded rotations/extensions use fresh DEM samples. The three real calculations will check the resulting water levels again.','新增断面端点按沿已保存流线插值的基准最大水位筛查；有限方向／宽度调整采用真实 DEM 采样，随后三个真实工况再次检查水位。')));
  if(plan.coverage_policy){const p=plan.coverage_policy;preview.append(el('p',tr('Confirmed automatic bounds: ','本次自动化确认范围：')+p.maximum_rounds+tr(' correction rounds, ',' 轮修正，')+p.maximum_width_ft+tr(' ft maximum total width; at most ',' ft 总宽度上限；最多 ')+(3*(1+p.maximum_rounds))+tr(' case calculations. Stops when ends are covered, baseline sections need changes, geometry cannot extend, a calculation fails, or the round limit is reached. All rounds remain saved.',' 个工况计算。端点覆盖完成、原始断面需改动、几何无法延伸、计算失败或达到轮数上限时停止，保留全部轮次。'),'warning'));}
 return true;
}

function renderStudy(parent){
 if(current.native_review)return;
 const box=details(parent,'Optional sensitivity batch','可选：敏感性批量计算');box.id='qa-tool-sensitivity';
 renderSuggestedSensitivity(box);
 const manual=details(box,'Or enter a single range manually','或手动输入单项范围');
 manual.append(el('p',tr('Choose explicit low/high values for one parameter. The baseline and changed cases will run sequentially after one confirmation, with automatic water-level comparison. Bounds are assumptions, not measured uncertainty.','选择一个参数并填写明确的低／高值，统一确认后自动依次计算基准与变化工况并对比水位。范围属于假设，不是实测误差。')));
 const options=[['scenario.channel_n','Channel Manning n','主槽糙率'],['scenario.overbank_n','Overbank Manning n','漫滩糙率'],['boundary_slopes.upstream','Upstream normal-depth slope','上游正常水深坡降'],['boundary_slopes.downstream','Downstream normal-depth slope','下游正常水深坡降']];
 if(current.model_type==='river'){
  const r=current.results||{},b=r.boundaries||{};
  for(let i=options.length-1;i>=0;i--){const key=options[i][0];if(key.startsWith('boundary_slopes.')){const side=key.split('.')[1];if(b[side]?.type!=='normal_depth'||side==='upstream'&&r.flow_regime==='subcritical')options.splice(i,1);}}
  if(b.downstream?.type==='known_stage')for(const [i,p]of (r.metrics||[]).entries())options.push(['boundaries.downstream.stages_ft.'+i,p.profile_id+' downstream WSE (ft)',p.profile_id+' 下游绝对水位（ft）']);
 }
 for(const g of current.results?.metrics?.[0]?.culvert_groups||[])options.push(['groups.'+g.group_id+'.depth_blocked_ft','Group '+(g.group_id+1)+' uniform bottom fill (ft)','第 '+(g.group_id+1)+' 组全涵长底部填塞（ft）']);
 const path=field(manual,'study-field','Parameter','参数',options[0][0],'select',options),low=field(manual,'study-low','Low value','低值','','number'),high=field(manual,'study-high','High value','高值','','number');
 if(current.model_type==='river')manual.append(el('small',tr('Known-stage sensitivity uses absolute water-surface elevations in the model datum. Select ranges supported by the boundary evidence; bridge backwater is not removed by ending the reach before the bridge.','已知水位敏感性采用模型高程基准下的绝对水位。范围需有边界依据；把模型截在桥前不会消除桥梁壅水。')));
 else manual.append(el('small',tr('For blockage, HEC-RAS applies the fill depth throughout the barrel. Do not use a local inlet-photo depth without deciding whether that assumption is appropriate. No generic percentage range is filled automatically.','填塞深度会作用于整根涵管。入口照片中的局部淤堵不能未经判断直接等同于全涵长填塞；不会自动填入通用百分比范围。')));
 const preview=el('div');manual.append(preview);let proposal=null;
 for(const input of [path,low,high])input.addEventListener('input',()=>{proposal=null;preview.replaceChildren();});
 manual.append(button('Prepare and review batch','准备并核对批量工况',async()=>{if(!low.value.trim()||!high.value.trim())throw Error(tr('Enter both bounds.','请填写两个范围端值。'));proposal=await api('study-prepare',{id:current.id,revision:current.revision,parameters:[{path:path.value,low:Number(low.value),high:Number(high.value)}]});current.pending_study=proposal.entry;current.pending_study_plan=proposal.plan;preview.replaceChildren();table(preview,['Case','Changes'],proposal.plan.cases.map(c=>[c.id,c.changes.map(v=>v.path+': '+JSON.stringify(v.before)+' → '+JSON.stringify(v.after)).join('; ')]));preview.append(el('p',tr('Only these cases will be calculated. Reports are generated for each case; GIS packages are kept with the original baseline to avoid repeated map exports.','只计算显示的这些工况；每个工况生成报告，GIS 交付包保留原基准，避免重复出图。')),button('Confirm displayed cases and calculate','确认显示工况并计算',async()=>{if(!proposal)throw Error('Prepare the current range again');await api('study-start',{id:current.id,revision:current.revision,token:proposal.token,confirmed:true});await open(current.id);},'primary'));}));
 if(current.study_result&&current.study_result.analysis_kind!=='section_spacing'){const r=current.study_result;box.append(el('p',r.status==='COMPARISON_REQUIRES_REVIEW'?tr('Conditional comparison — review required','条件性比较，仍需复核'):r.status,'status'));table(box,[tr('Parameter','参数'),tr('Tested response','测试响应'),current.model_type==='river'?tr('Max |Δ upstream WSE| ft','最大上游水位差 ft'):tr('Max |ΔHW| ft','最大涵前水位差 ft'),tr('Max |ΔXS WSE| ft','最大断面水位差 ft')],r.measurement_priorities.map(p=>[sensitivityParameterLabel(p.parameter_path)||p.id,p.priority==='SENSITIVE_IN_TESTED_RANGE'?tr('Sensitive within tested range','所测试范围内较敏感'):p.priority==='SMALL_RESPONSE_IN_TESTED_RANGE'?tr('Small response within tested range','所测试范围内响应较小'):p.priority,p.max_abs_hw_change_ft,p.max_abs_matched_xs_change_ft]));if(r.failed_cases.length)box.append(el('p',tr('Failed/incomplete cases: ','失败／未完成工况：')+r.failed_cases.join(', '),'warning'));box.append(button('Open study results','打开敏感性结果',()=>api('open-folder',{id:current.id,path:current.latest_study.path.replace(/\/[^/]+$/,'')})));}
}


function renderNextReview(parent){
 if(current.native_review)return;
 const record=current.next_review;
 const box=details(parent,'Prepare a follow-up check','准备后续复核',!!record?.preview);box.id='qa-tool-next-review';
 const reasons={
  WET_SECTION_ENDS:tr('Actual water levels exceed section ends. A bounded DEM extension preview is ready below.','实际水位超出断面端点，下方已准备限定范围的 DEM 延伸预览。'),
  NO_WET_SECTION_ENDS:tr('No positive wet-end exceedance was found in the verified outputs. Applicable sensitivity and spacing previews are ready below; other hydraulic warnings remain for review.','已核验输出未检出端点被水位超出的情况。下方已准备适用的敏感性和加密预览，其他水力警告仍需复核。'),
  NO_COMPATIBLE_EXTENSION:tr('Wet ends remain, but no compatible fixed-direction extension is available. Review the geometry or additional terrain.','仍有湿端，但没有可用的固定方向延伸方案，请复核几何或补充地形。'),
  STRUCTURE_GEOMETRY_REVIEW:tr('Wet ends in a structure model require an editable geometry review.','结构模型的湿端需要在可编辑修订版中复核几何。'),
  EXISTING_PREVIEW:tr('Your existing preview is retained. Continue in its review panel below.','已保留现有预览，请在下方对应面板继续。'),
  EXISTING_COVERAGE_RESULT:tr('A repair result already exists. Continue from its final case below to avoid repeating the earlier baseline.','已有修订结果，请从下方最终工况继续，避免重复处理旧基准。')};
 if(record){
  if(record.status==='CONFIRMED_SEPARATELY')box.append(el('p',tr('The suggested batch was confirmed separately. Its progress and results appear below.','建议批次已经单独确认，进度和结果见下方。'),'status'));
  else{
   box.append(el('p',reasons[record.reason]||tr('Automatic review preparation needs attention.','自动复核准备需要处理。'),record.status==='PREVIEW_READY'?'status':'warning'));
   if(record.error)box.append(el('p',record.error,'warning'));
   if(record.action==='coverage'&&record.options)box.append(el('p',tr('Proposed first-round extensions: ','首轮建议延伸：')+record.changes+tr(' · at most ',' 条 · 最多 ')+record.options.maximum_rounds+tr(' calculations · total section width limit ',' 轮计算 · 总断面宽度上限 ')+record.options.maximum_width_ft+' ft'));
   const joint=record.joint_revision;
   if(record.action==='coverage'&&record.unresolved?.length)box.append(el('p',tr('Unresolved fixed-direction locations: ','固定方向延伸尚未解决的位置：')+record.unresolved.length,'warning'));
   if(joint){
    const ready=joint.status==='DRAFT_READY';
    const message=ready?tr('A separate joint direction and width draft was prepared automatically. Review its map, banks and complete parameters before calculating.','已自动准备独立的方向与宽度联合修订草稿。请检查地图、岸站及完整参数，再确认计算。'):
     joint.status==='EDITED_REVISION'?tr('The prepared revision has since been edited. Your edits are retained; review its current values.','已准备的修订版随后有过编辑。修改已保留，请以草稿当前参数为准。'):
     joint.status==='COMPUTED_REVISION'?tr('The prepared revision has already been calculated. Open its results to continue.','已准备的修订版已完成计算，请打开该结果继续。'):
     joint.status==='REVISION_PROCESSING'?tr('The independent revision is processing. Open it to follow progress; the original results remain available.','独立修订版正在处理，打开即可查看进度；原计算结果仍可使用。'):
     tr('Joint preparation needs attention. Saved results and any independent draft remain available.','联合准备需要处理，已有结果及已建立的独立草稿仍保留。');
    box.append(el('p',message,ready?'status':'warning'));
    if(ready)box.append(el('p',tr('Staged geometry: ','几何已写入草稿：')+tr(joint.geometry_applied?'yes':'no',joint.geometry_applied?'是':'否')+tr(' · proposed changes: ',' · 建议修改：')+joint.changes+tr(' · rotations: ',' · 其中旋转：')+joint.rotations+tr(' · remaining review items: ',' · 仍需复核：')+(joint.unresolved||[]).length));
    if(joint.error)box.append(el('p',joint.error,'warning'));
    if(joint.project_id&&!['UNAVAILABLE','SOURCE_CHANGED'].includes(joint.status))box.append(button('Open the prepared geometry revision','打开已准备的几何修订',async()=>{await open(joint.project_id);},'primary'));
   }
   box.append(el('p',tr('Preparation starts no additional solver run. Inspect the preview and its assumptions, then use its confirmation control. Existing results and packages remain available.','准备过程不启动追加求解。请查看预览及假设，再使用对应的确认按钮。已有结果与交付包仍可使用。'),'muted'));
   if(record.preview)box.append(button('Inspect the prepared review','查看已准备的复核',()=>openGuidanceTool(record.action==='coverage'?'coverage':'check-batch')));
  }
 }else box.append(el('p',tr('Prepare the applicable next review from this saved calculation. No additional solver run starts.','根据已保存计算准备适用的下一项复核，不启动追加求解。')));
 if(!record||['PREPARATION_FAILED','UNAVAILABLE'].includes(record.status))box.append(button('Prepare next review automatically','自动准备下一项复核',async()=>{await api('next-review',{id:current.id,revision:current.revision});await open(current.id);}));
 else if(record.action==='coverage'&&record.unresolved?.length&&(!record.joint_revision||record.joint_revision.status==='PREPARATION_FAILED'&&!record.joint_revision.entry))box.append(button('Prepare joint geometry suggestions','准备联合几何建议',async()=>{await api('next-review',{id:current.id,revision:current.revision});await open(current.id);}));
}
