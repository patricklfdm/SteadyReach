'use strict';
function checkStepName(name){return {geometry:tr('Two geometry alternatives','两种几何候选'),sensitivity:tr('Documented-range sensitivity','有依据范围的敏感性'),spacing:tr('Nested section spacing','嵌套断面加密'),delivery:tr('Reports and both delivery packages','报告及两种交付包')}[name]||name;}
function checkAssessment(value){return {COMPARISON_REQUIRES_REVIEW:tr('Sensitivity comparison needs interpretation','敏感性对比需判读'),NOT_CONVERGED:tr('Not converged at the screening threshold','未达到筛查收敛阈值'),STABLE_AT_REVIEW_THRESHOLD:tr('Stable at the screening threshold; scope limits remain','达到筛查稳定阈值，适用范围限制仍保留')}[value]||value;}
function renderCheckBatchProgress(parent,data){
 const q=data.question_result;
 if(q){
  const label={INSUFFICIENT_EVIDENCE:tr('Evidence or applicable ranges are missing.','仍缺少证据或适用的试算范围。'),FIELD_REVIEW_BEFORE_ANOTHER_BATCH:tr('Stop here and review the affected sections before further trials.','先停止试算，核实受影响的断面后再决定。'),STOP_WITHIN_TESTED_RANGE:tr('Stop this investigation within the tested ranges.','可结束本次已测试范围内的检查。')};
  parent.append(el('h3',label[q.status]),el('p',q.threshold_ft+' ft · '+(q.basis||tr('Workflow screening threshold','流程筛查门槛'))));
  table(parent,[tr('Case and profile','工况与剖面'),tr('Largest stage change','最大水位变化'),tr('Stations above threshold','超过门槛的断面')],q.cases.map(r=>[r.case+' · '+r.profile,r.signed_peak_ft.toFixed(3)+' ft · RS '+r.peak_rs,r.affected.map(v=>'RS '+v.rs).join(', ')||'—']));
 }
 const states={REUSED:tr('Verified saved results','已复用核验结果'),QUEUED:tr('Queued','等待中'),RUNNING:tr('Running','运行中'),COMPLETED:tr('Completed; interpretation required','完成，仍需判读'),UNAVAILABLE:tr('Not available; see limits','无法执行，请查看限制'),INCOMPLETE:tr('Incomplete; saved evidence retained','未完成，已保存证据保留')};
 parent.append(el('h3',tr('Checks and delivery progress','检查与交付进度')));
 table(parent,[tr('Step','步骤'),tr('Progress','进度'),tr('Assessment / reason','检查结果／原因')],Object.entries(data.steps||{}).map(([name,row])=>[checkStepName(name),states[row.status]||row.status,(row.error==='Native check incomplete; saved cases remain available for retry'?tr('Native check incomplete; saved cases can be retried.','原生检查未完成，可接续已保存的工况。'):row.error)||checkAssessment(row.assessment)||checkBatchReason(row.reason)||'—']));
 if(data.status==='COMPLETED_WITH_LIMITATIONS')parent.append(el('p',tr('The confirmed sequence and exports finished. Numerical convergence, missing evidence and hydraulic warnings retain their own review status. No design acceptance is implied.','已确认的流程及导出完成。数值收敛、缺失证据和水力警告保留各自复核状态，不代表设计合格。'),'warning'));
}
function checkBatchReason(reason){return {NO_ADOPTED_RANGES:tr('No adopted source ranges; choose ranges in the sensitivity panel if needed.','没有已采用的来源范围；需要时在敏感性面板选择范围。'),RIVER_SPACING_ONLY:tr('Automated nested spacing currently supports continuous river reaches.','嵌套加密目前支持连续纯河道。'),NO_ELIGIBLE_INTERVALS:tr('No compatible nested intervals within the DEM/layout limits.','DEM／几何限制内没有适用的嵌套区间。')}[reason]||reason;}
function renderCheckBatch(parent){
 if(current.native_review)return;
 const options=current.check_batch_preview?.plan.options||{};
 const box=details(parent,'Prepare checks and delivery together','集中准备检查与交付',!!current.check_batch_preview);box.id='qa-tool-check-batch';
 box.append(el('p',tr('Prepare documented sensitivity ranges and warning-based nested spacing for this exact baseline. Review the full preview and confirm once; the program runs the available checks in order and refreshes reports plus Complete/Minimal packages. It does not select a preferred boundary or replace the baseline geometry.','为当前基准集中准备有依据的敏感性范围和警告驱动的嵌套加密。核对完整预览并确认一次，程序顺序运行适用检查，随后更新报告和 Complete／Minimal 包；不自动选择边界值或替换基准几何。')));
 const range=check(box,'Include already adopted parameter ranges','纳入已经采用的参数范围',options.sensitivity??true,()=>reset());
 const spacing=check(box,'Include automatic nested spacing (river reaches)','纳入自动嵌套加密（纯河道）',options.spacing??(current.model_type==='river'),()=>reset());
 const isRiver=current.model_type==='river';
 const integrate=check(box,'Reuse individually verified cases from this baseline','复用本基准已核验的相同试算',options.integrated??true,()=>reset());
 const geometry=isRiver?check(box,'Compare fixed and rotated geometry at the selected width','按所选宽度比较固定方向与允许旋转两种几何',options.geometry??false,()=>reset()):null;
 const grid=el('div',undefined,'grid');box.append(grid);
 const questions=[['combined','Choose checks together','组合选择'],['boundary','How far does boundary influence extend?','边界影响传到哪条断面？'],['roughness','Where does roughness affect stage?','糙率会改变哪些断面的水位？']];
 if(isRiver)questions.push(['spacing','Does section refinement stabilize stage?','加密后水位是否稳定？'],['geometry','Does changing extent or orientation alter flow?','断面范围或方向是否影响过流？']);
 const question=field(grid,'checks-question','Question to answer','本次要回答的问题',options.question||'combined','select',questions);
 const threshold=field(grid,'checks-threshold','Optional project stage threshold (ft)','项目水位门槛（ft，选填）',options.threshold_ft??'','number');threshold.min=0;threshold.step='any';
 const basis=field(grid,'checks-threshold-basis','Source or reason for this threshold','门槛来源或用途依据',options.threshold_basis||'','text');
 function scopeQuestion(){
  const q=question.value,specific=q!=='combined',param=['boundary','roughness'].includes(q);
  if(specific){range.checked=param;spacing.checked=q==='spacing';if(geometry)geometry.checked=q==='geometry';}
  for(const control of [range,spacing,geometry])if(control)control.disabled=specific;
  threshold.disabled=basis.disabled=!param;
 }
 scopeQuestion();question.addEventListener('change',()=>{reset();scopeQuestion();});
 const scope=isRiver?field(grid,'checks-scope','Spacing coverage','加密范围',options.spacing_scope??'automatic','select',[['automatic','Recommended intervals','建议区间'],['all','Whole reach, check both refinements','全河段连续两级加密']],reset):null;
 const limit=field(grid,'checks-intervals','Maximum selected intervals','最多选择区间',options.maximum_intervals??12,'number');limit.min=1;limit.max=100;
 const rounds=field(grid,'checks-rounds','Added-section coverage rounds (0–3)','新增断面覆盖修正轮数（0–3）',options.maximum_rounds??2,'number');rounds.min=0;rounds.max=3;
 const width=field(grid,'checks-width','Maximum correction width (ft)','修正总宽度上限（ft）',options.maximum_width_ft??2000,'number');width.min=120;width.max=2000;
 const budget=field(grid,'checks-budget','Optional maximum new native calculations','本批次最多新增计算次数（选填）',options.calculation_budget??'','number');budget.min=0;budget.max=100;
 const guidance=el('p');box.append(guidance);
 const previewBox=el('div');let proposal=current.check_batch_preview||null;
 box.addEventListener('steadyreach-recommend-checks',event=>{
  const r=event.detail;if(!r)return;
  reset();question.value='combined';scopeQuestion();range.checked=r.sensitivity;spacing.checked=r.spacing;integrate.checked=true;
  if(geometry)geometry.checked=r.geometry;if(scope)scope.value=r.spacing_scope;
  if(r.maximum_width_ft)width.value=r.maximum_width_ft;
  guidance.textContent=r.field_first?tr('Field evidence is still needed. Obtain it first if it could change the model; run these checks to diagnose the current inputs.','仍需现场证据。若新资料会改变模型，优先取证；此批次可诊断当前输入。'):tr('Check selections reflect this edition.','已按本版证据选择检查。');
  notify(tr('Review the selected checks, then prepare the preview.','已按评估选择检查，可修改后生成预览。'));
 });
 function reset(){proposal=null;current.check_batch_preview=null;previewBox.replaceChildren();}
 for(const input of [limit,rounds,width,budget,threshold,basis])input.addEventListener('input',reset);
 box.append(button('Prepare checks and delivery preview','生成检查与交付预览',async()=>{
  const id=current.id;
  const response=await api('checks-prepare',{id,revision:current.revision,sensitivity:range.checked,spacing:spacing.checked,geometry:!!geometry?.checked,integrated:integrate.checked,spacing_scope:scope?.value||'automatic',
   question:question.value,threshold_ft:['boundary','roughness'].includes(question.value)&&threshold.value!==''?Number(threshold.value):null,threshold_basis:basis.value,
   maximum_intervals:Number(limit.value),maximum_rounds:Number(rounds.value),maximum_width_ft:Number(width.value),calculation_budget:budget.value===''?null:Number(budget.value)});
  if(current?.id!==id)throw Error(tr('Project changed; reopen this preview.','项目已改变，请重新打开预览。'));
  proposal=response;current.check_batch_preview=response;show();notify(tr('Preview saved. Inspect the ranges, sections and calculation limit; no solver has started.','预览已保存。请核对范围、断面及计算上限；尚未启动求解。'));
 }),previewBox);
 function show(){
  previewBox.replaceChildren();if(!proposal)return;
  const plan=proposal.plan;
  table(previewBox,[tr('Step','步骤'),tr('Available','是否适用'),tr('Maximum native calculations','最多原生计算次数')],plan.steps.map(s=>[checkStepName(s.id),s.status==='READY'?tr('Ready for confirmation','待确认'):s.status==='REUSED'?tr('Verified existing result','采用已核验结果'):checkBatchReason(s.reason),s.maximum_calculations]));
  previewBox.append(el('p',tr('Total limit: ','总上限：')+plan.maximum_calculations+tr(' real case calculations, followed by report/package export. Saved manual controls are retained; all test ranges and new banks remain conditional.',' 个真实工况计算，随后导出报告／交付包。保留人工控制；试算范围与新增岸站仍属条件性输入。'),'warning'));
  if(plan.deferred_parameters?.length){const d=details(previewBox,'Ranges not selected automatically','未自动选择的范围');table(d,[tr('Parameter','参数'),tr('Reason','原因')],plan.deferred_parameters.map(r=>[typeof sensitivityParameterLabel==='function'?sensitivityParameterLabel(r.path):r.path,r.reason]));}
  for(const step of plan.steps){
   if(step.reused?.length)previewBox.append(el('p',tr('Verified cases reused','已核验并复用的工况')+' · '+step.reused.map(r=>r.changes.map(c=>c.path+'='+c.value).join(', ')).join(' / ')));
   const sub=proposal.studies?.[step.id];if(!sub)continue;
   if(step.id==='geometry'){
    table(previewBox,[tr('Alternative','方案'),tr('Changed sections','改动断面'),tr('New banks','新岸站'),tr('Open issues','待处理')],sub.cases.map(c=>[c.id,c.changes.length,c.banks.length,c.unresolved.length]));continue;
   }
   if(step.id==='spacing'){const d=details(previewBox,'Inspect spacing positions, banks and limits','查看加密位置、岸站及限制');renderSpacingPreview(d,sub);}
   else{const d=details(previewBox,'Inspect sensitivity ranges and sources','查看敏感性范围及来源',true);
    table(d,[tr('Parameter','参数'),tr('Low','下限'),tr('High','上限')],step.parameters.map(r=>[typeof sensitivityParameterLabel==='function'?sensitivityParameterLabel(r.path):r.path,r.low,r.high]));
    for(const topic of sub.measurement_topics||[])d.append(el('p',topic.range_basis||''));}
  }
  if(plan.status==='BUDGET_EXCEEDED'){previewBox.append(el('p',tr('Stopped before running. The selected checks could require ','启动前已停止。本次选择最多可能需要 ')+plan.maximum_calculations+tr(' calculations; your limit is ',' 次计算，当前约定上限为 ')+plan.options.calculation_budget+tr('. Narrow the question or review a new limit.','。请缩小检查范围或重新核对上限。'),'warning'));return;}
  if(plan.status!=='REVIEW_REQUIRED'){previewBox.append(el('p',tr('No checks can run from this preview. Review the unavailable items above.','本预览没有可运行检查，请处理上方不适用事项。'),'warning'));return;}
  const consent=check(previewBox,'I confirm these ranges, added sections, inferred banks, limits and the automatic delivery refresh','我确认这些范围、新增断面、推定岸站、上限及自动更新交付包',false,()=>{});
  previewBox.append(button('Confirm and run checks → deliverables','确认执行检查 → 生成交付包',async()=>{
   if(!proposal||!consent.checked)throw Error(tr('Review and confirm the complete batch first.','请先核对并确认完整批次。'));
   await api('checks-start',{id:current.id,revision:current.revision,token:proposal.token,confirmed:true});await open(current.id);
  },'primary'));
 }
 if(proposal)show();
 const progress=current.check_batch_progress;
 if(progress)renderCheckBatchProgress(box,progress);
 if(current.active_check_batch&&(['QUEUED','INCOMPLETE'].includes(progress?.status)||current.status==='INTERRUPTED'))box.append(button('Resume checks and delivery','继续未完成的检查与交付',async()=>{
  await api('checks-start',{id:current.id,revision:current.revision,token:current.active_check_batch.plan.sha256,retry:true,confirmed:true});await open(current.id);
 }));
}
