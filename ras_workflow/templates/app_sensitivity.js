'use strict';
const sensitivityEdits=new Map();

function sensitivityParameterLabel(path){
 const labels={
  'scenario.channel_n':['Channel Manning n','主槽糙率'],
  'scenario.overbank_n':['Overbank Manning n','漫滩糙率'],
  'boundary_slopes.upstream':['Upstream normal-depth slope','上游正常水深坡降'],
  'boundary_slopes.downstream':['Downstream normal-depth slope','下游正常水深坡降']
 };
 if(labels[path])return tr(...labels[path]);
 const group=String(path||'').match(/^groups\.(\d+)\.depth_blocked_ft$/);
 if(group)return tr('Uniform bottom fill, group ','全涵长底部填塞，第 ')+(Number(group[1])+1)+tr('',' 组');
 const stage=String(path||'').match(/^boundaries\.downstream\.stages_ft\.(\d+)$/);
 if(stage)return tr('Downstream WSE, profile ','下游水位，工况 ')+(Number(stage[1])+1);
 return path;
}

function renderSuggestedSensitivity(parent){
 const box=details(parent,'Suggest ranges from saved inputs','从已保存输入建议试算范围',true),area=el('div'),prepared=el('div');
 box.append(el('p',tr('Collect adopted ranges and matching document candidates without retyping them. Select up to four parameters, review or edit the bounds, then confirm the displayed cases once. Each variant changes only one parameter; geometry and the original calculation stay unchanged.','自动整理已采用范围及数值相符的资料候选，无需重新抄写。最多选择四项参数，核对或修改范围，再统一确认显示的工况。每个变化工况只改一项参数，保留几何和原计算。')));
 let packet=current.suggested_sensitivity,proposal=null,choices=[];
 function invalidate(){proposal=null;delete current.pending_study_plan;delete current.pending_study;prepared.replaceChildren();notify(tr('Ranges changed. Prepare the displayed cases before calculation.','范围已改变，请先准备当前工况再计算。'));}
 function showPlan(value){
  proposal=value;prepared.replaceChildren();const plan=value.plan;
  prepared.append(el('h3',tr('Batch ready for confirmation','批量工况待确认')));
  table(prepared,[tr('Case','工况'),tr('Changes','变化')],plan.cases.map(c=>[c.id,c.changes.map(v=>sensitivityParameterLabel(v.path)+': '+JSON.stringify(v.before)+' → '+JSON.stringify(v.after)).join('; ')||tr('Repeat the saved baseline','重新计算已保存基准')]));
  prepared.append(el('p',plan.cases.length+tr(' actual HEC-RAS runs. Untested interactions, hydraulic findings and engineering acceptance remain open. No model values have been changed.',' 次真实 HEC-RAS 运行；未测试参数组合影响，水力问题及工程接受仍待复核。尚未改动模型数值。'),'warning'));
  for(const topic of plan.measurement_topics||[])prepared.append(el('small',topic.range_basis));
  const confirmed=check(prepared,'I confirm these conditional ranges, their source applicability and the displayed cases','我确认这些条件性范围、资料适用性及显示的工况',false,()=>{});
  prepared.append(button('Confirm and run selected sensitivity cases','确认并计算所选敏感性工况',async()=>{
   if(!proposal||!confirmed.checked)throw Error(tr('Review and confirm this batch first.','请先核对并勾选确认本批工况。'));
   await api('study-start',{id:current.id,revision:current.revision,token:proposal.token,confirmed:true});await open(current.id);
  },'primary'));
 }
 function showRanges(){
  area.replaceChildren();choices=[];if(!packet)return;
  const cacheKey=current.id+'|'+packet.token,edits=sensitivityEdits.get(cacheKey)||{};sensitivityEdits.set(cacheKey,edits);
  for(const message of packet.notes||[])area.append(el('p',message,'warning'));
  for(const row of packet.parameters){
   const card=el('section',undefined,'card');area.append(card);
   card.append(el('h3',row.label[lang==='zh'?'zh':'en']),el('p',tr('Baseline: ','基准值：')+row.value+' '+row.unit));
   if(row.inactive){card.append(el('p',tr('Section-specific roughness overrides this value. Revise those subdivisions before testing roughness.','已有断面分区糙率会覆盖此数值，需修改相应分区后再试算。'),'warning'));continue;}
   const recommended=row.options.find(o=>o.id===row.recommended_id);
   const state=edits[row.path]||(edits[row.path]={selected:!!recommended,option_id:recommended?.id||'',low:recommended?.low??'',high:recommended?.high??''});
   const chosen=check(card,'Include this parameter','计算此参数',state.selected,v=>{state.selected=v;invalidate();});
   const options=[['','Enter an explicit range','手动输入范围'],...row.options.map((o,i)=>[o.id,(o.origin==='ADOPTED_RANGE'?'Adopted range':'Document candidate — confirm applicability')+' '+o.low+'–'+o.high+' ('+(i+1)+')',(o.origin==='ADOPTED_RANGE'?'已采用的范围':'资料候选，须确认适用性')+' '+o.low+'–'+o.high+'（'+(i+1)+'）'])];
   const source=field(card,'suggested-source-'+choices.length,'Range basis','范围依据',state.option_id,'select',options),context=el('p',undefined,'muted');card.append(context);
   const grid=el('div',undefined,'grid');card.append(grid);
   const low=field(grid,'suggested-low-'+choices.length,'Low value','低值',state.low,'number'),high=field(grid,'suggested-high-'+choices.length,'High value','高值',state.high,'number');
   const rangeNotice=el('p',undefined,'warning');card.append(rangeNotice);
   function describe(){
    const option=row.options.find(o=>o.id===state.option_id);
    context.textContent=option?((option.condition||{})[lang==='zh'?'zh':'en']||option.basis):tr('No range is inferred from a percentage. Enter values supported by site evidence.','不按通用百分比推测范围，请填写有场地依据的端值。');
    const outside=low.value.trim()&&high.value.trim()&&(Number(low.value)>row.value||Number(high.value)<row.value);
    rangeNotice.textContent=outside?tr('The selected interval does not bracket the baseline. This tests an alternative scenario; confirm its purpose.','所选范围没有包含基准值，属于替代情景，请确认试算目的。'):tr('Conditional test range, not a measured confidence interval.','条件性试算范围，不是实测置信区间。');
   }
   source.addEventListener('change',()=>{const o=row.options.find(o=>o.id===source.value);state.option_id=source.value;state.low=o?.low??'';state.high=o?.high??'';low.value=state.low;high.value=state.high;state.selected=!!o;chosen.checked=state.selected;describe();invalidate();});
   for(const input of [low,high])input.addEventListener('input',()=>{state.low=low.value;state.high=high.value;describe();invalidate();});
   for(const note of row.notes||[])card.append(el('p',note,'warning'));
   describe();choices.push({row,state,low,high});
  }
  area.append(el('p',tr('Document ranges not previously adopted stay unselected. Selecting them requires confirming the river/site, construction and units in the batch review.','此前未采用的资料范围默认不勾选。选择后需在批次核对时确认河流／场地、构造及单位适用性。')),
   button('Prepare selected cases for one confirmation','准备所选工况并统一确认',async()=>{
    const selected=choices.filter(v=>v.state.selected);
    if(!selected.length||selected.length>packet.maximum_parameters)throw Error(tr('Select one to four parameters.','请选择一至四项参数。'));
    if(selected.some(v=>!v.low.value.trim()||!v.high.value.trim()))throw Error(tr('Enter both bounds for each selected parameter.','请填写每个所选参数的两个范围端值。'));
    const parameters=selected.map(v=>({path:v.row.path,option_id:v.state.option_id||null,low:Number(v.low.value),high:Number(v.high.value)}));
    const result=await api('study-prepare',{id:current.id,revision:current.revision,range_token:packet.token,parameters});
    current.pending_study=result.entry;current.pending_study_plan=result.plan;showPlan(result);
    notify(tr('Cases prepared. Review the values and confirm below; the solver has not started.','工况已准备，请核对下方数值并确认；求解器尚未启动。'));
   },'primary'));
 }
 box.append(button('Suggest ranges from calculation inputs','从计算输入自动整理范围',async()=>{
  packet=await api('study-suggest',{id:current.id,revision:current.revision});current.suggested_sensitivity=packet;proposal=null;delete current.pending_study_plan;delete current.pending_study;prepared.replaceChildren();showRanges();
  notify(tr('Ranges collected. Adopted ranges are selected; other source ranges need your choice. No calculation started.','范围已整理，已采用范围已勾选，其余资料范围待选择；尚未启动计算。'));
 }),area,prepared);
 showRanges();
 if(current.pending_study_plan&&!current.pending_study_plan.analysis_kind){
  showPlan({plan:current.pending_study_plan,token:current.pending_study.sha256});
 }
}
