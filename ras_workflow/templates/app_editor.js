'use strict';
// No-model editor and explicit, editable pre-solver checkpoint.
let classEdits={},finalReview=null,dependencyReviewState=null;
const originName=c=>({missing:tr('Missing','缺失'),assumed:tr('ASSUMPTION','假设值'),inferred:tr('ESTIMATE','估计值'),terrain_derived:tr('Terrain-derived candidate','地形推导候选'),derived:tr('Derived candidate','推导候选'),reported:tr('User-reported source value','用户转录资料值'),user_entered:tr('User entry · unverified','用户填写 · 未独立核实'),source_input_unverified:tr('Source input · unverified','原始输入 · 未独立核实'),model_setting:tr('Model identifier','模型标识')}[c]||c);
function parameterInput(parent,f){
 const box=el('section',undefined,'parameter');box.dataset.key=f.key;parent.append(box);
 const kind=f.kind==='choice'?'select':['array','matrix'].includes(f.kind)?'textarea':['number','integer'].includes(f.kind)?'number':'text';
 const options=f.kind==='choice'?[['','Not supplied','尚未填写'],...f.options.map(o=>[o,o,o])]:null;
 const value=Object.hasOwn(edited,f.key)?edited[f.key]:f.value;
 const input=field(box,'input-'+f.key,f.label.en+(f.unit?' · '+f.unit:''),f.label.zh+(f.unit?' · '+f.unit:''),format(value,f.kind),kind,options,v=>{try{edited[f.key]=parseInput(f,v);input.setCustomValidity('');mark();if(finalReview){finalReview=null;invalidateReview();}else if(f.kind==='choice'){task(async()=>{await save();await open(current.id);document.getElementById('input-'+f.key)?.scrollIntoView({block:'center'});},tr('Update dependent fields','更新相关参数'));}}catch(e){input.setCustomValidity(e.message);notify(tr('Invalid input: ','输入无效：')+e.message,true);}});
 const tag=el('span',f.missing&&!f.required?tr('Optional · not supplied','可选 · 未填写'):originName(f.evidence_class),f.evidence_class==='assumed'||f.evidence_class==='inferred'?'tag assumption':'tag');box.append(tag);
 const info=details(box,'Source / change input origin','来源／修改数据类别');const origin=field(info,'origin-'+f.key,'Input origin (optional to change)','数据类别（可修改）',['reported','assumed'].includes(f.evidence_class)?f.evidence_class:'user_entered','select',[
 ['user_entered','User entry / correction','用户填写／修改'],['reported','Copied from supplied material','从资料中转录'],['assumed','Estimate / assumption','估计／假设']],v=>{classEdits[f.key]=v;edited[f.key]=parseInput(f,input.value);tag.textContent=originName(v);tag.className=v==='assumed'?'tag assumption':'tag';mark();if(finalReview){finalReview=null;invalidateReview();}});
 origin.parentElement.classList.add('origin');
 if(f.help?.en)info.append(el('small',tr(f.help.en,f.help.zh)));
 if(f.acquisition){const a=f.acquisition;info.append(el('p',tr('Acquisition route: ','自动获取路径：')+tr(a.route.en,a.route.zh)),el('p',tr(a.next.en,a.next.zh)),el('small',tr('Attempt status: ','尝试状态：')+sourceStatus(a.status)));for(const attempt of a.attempts||[])info.append(el('small',attempt.route+' · '+sourceStatus(attempt.status)+(attempt.count!==undefined?' · '+attempt.count:'')));}
 if(f.acquisition?.status==='FIS_ROW_SELECTED')box.append(el('small',tr('Saved FIS selection · ','已采用 FIS 表行 · ')+f.basis));
 else if(['FIS_STREAM_MISMATCH','FIS_SELECTION_CHANGED','SOURCE_CHANGED'].includes(f.acquisition?.status)&&f.source_conflict)box.append(el('p',sourceStatus(f.acquisition.status),'warning'));
 else if(f.source_conflict)box.append(el('p',tr('Source values differ. Existing value retained; inspect alternatives below.','资料存在不同数值，已保留现值；请展开候选比较。'),'warning'));
 const key=f.key;
 if(/length_ft|invert_ft|road.width_ft|bottom_type|inlet_description/.test(key))info.append(el('p',tr('Use drawings, survey or identifiable photo/map dimensions. If unavailable, enter an explicit assumption above. Surface DEM cannot establish buried geometry; no unsupported numeric range is supplied.','优先用图纸、测量或有尺度的照片／地图。没有时可在上方填入明确假设。地表 DEM 无法确定埋藏几何，因此不提供无依据的数值范围。'),'muted'));
 const suggestions=f.parameter_candidates?.length?details(box,'Reference candidates ('+f.parameter_candidates.length+')','参考候选（'+f.parameter_candidates.length+'）',false):box;for(const s of f.parameter_candidates||[]){
  const row=el('div',undefined,'suggestion');row.append(el('strong',tr('Candidate: ','候选：')+format(s.value,f.kind)),el('p',tr(s.condition?.en||s.basis,s.condition?.zh||s.basis)));
  if(s.range)row.append(el('p',tr('Reference range: ','参考范围：')+s.range.join(' – ')+tr(' · Check the stated conditions; this is not a site uncertainty interval.',' · 请看适用条件，不代表本站误差范围。')));
  if(s.url){const a=el('a',tr('Official reference ↗','官方依据 ↗'));a.href=s.url;a.target='_blank';a.rel='noreferrer';row.append(a);}
  row.append(button('Use this candidate','采用此候选值',async()=>{await save();const fresh=current.intake.fields.find(x=>x.key===f.key)?.parameter_candidates.find(x=>sameCandidate(x,s));if(!fresh)throw Error(tr('Candidate changed. Reopen the current parameters.','候选值已变化，请重新打开当前参数。'));await api('candidate',{id:current.id,revision:current.revision,field:f.key,candidate:fresh.candidate});await open(current.id);notify(tr('Candidate applied; its assumption/source label is retained.','已采用候选值，并保留假设／来源标签。'));document.getElementById('input-'+f.key)?.scrollIntoView({block:'center'});}));suggestions.append(row);
 }
 return input;
}
function invalidateReview(){const b=$('#confirm-run');if(b)b.disabled=true;const c=$('#confirm-parameters');if(c)c.checked=false;const state=$('#review-state');if(state)state.textContent=tr('Edited. Save and refresh this list before confirming.','参数已修改。请保存并刷新清单后再确认。');}
function parameterTable(parent,fields){
 const wrap=el('div',undefined,'scroll'),t=el('table',undefined,'parameter-table'),head=el('tr');for(const title of [tr('Parameter','参数'),tr('Value','数值'),tr('Origin','来源')])head.append(el('th',title));t.append(head);
 for(const f of fields){const row=el('tr'),value=el('td'),text=format(f.value,f.kind);row.append(el('td',tr(f.label.en,f.label.zh)+(f.unit?' · '+f.unit:'')),value,el('td',f.missing&&!f.required?tr('Optional · not supplied','可选 · 未填写'):originName(f.evidence_class)));
  if(text.length>200){const d=details(value,Array.isArray(f.value)?f.value.length+' values — expand':'Show complete value',Array.isArray(f.value)?f.value.length+' 个数值 — 展开':'展开完整内容');d.append(el('pre',text));}else value.textContent=text||'—';t.append(row);
 }wrap.append(t);parent.append(wrap);
}
async function showFinalReview(){
 await saveAll();
 const review=await api('review',{id:current.id});
 current=await api('project/'+current.id);
 if(current.revision!==review.revision)throw Error(tr('Inputs changed during review. Refresh the parameter list.','核对过程中输入发生变化，请刷新参数清单。'));
 finalReview=review;renderFinalReview();
 notify(review.ready?tr('Changes saved. Review the complete inputs and highlighted assumptions before running.','更改已保存。请核对完整输入和标出的假设，再确认运行。'):tr('Changes saved. Resolve the listed inputs before running.','更改已保存。请处理列出的输入问题后再运行。'));
}
function renderFinalReview(){
 const review=finalReview;shell(1);window.scrollTo(0,0);const screen=$('#screen');screen.append(el('h1',tr('Confirm every input before HEC-RAS runs','HEC-RAS 运算前核对全部输入')),
 el('p',tr('Nothing has been solved yet. Edit any field; changes cancel this confirmation. No name, reason, or signature is required.','尚未开始求解。可以修改任意字段，修改后本次确认会失效。无需姓名、理由或签名。')),
 button('← Back to preparation','← 返回准备页面',async()=>{await save();finalReview=null;await open(current.id);}));
 const state=el('p',review.ready?tr('Technical input checks passed. Assumptions remain conditional.','必要输入检查通过。假设仍属于条件性输入。'):tr('Fill the items below, then refresh this list. The solver is paused.','请补齐下列项目并刷新清单，求解器处于等待状态。'),review.ready?'status':'warning');state.id='review-state';screen.append(state);
 if(review.run_readiness){
  const r=review.run_readiness,labels={CHECKED:tr('Checks passed','检查通过'),BLOCKED:tr('Action needed','需处理'),EXTENT_PENDING:tr('Confirm extent after compilation','原生几何编译后核对范围'),NOT_REQUESTED:tr('Not requested','未选择')};
  table(screen,[tr('Before calculating','开算前预检'),tr('Status','状态')],[[tr('HEC-RAS installation and session','HEC-RAS 安装与会话'),labels[r.solver.status]],[tr('Report tools','报告工具'),labels[r.reports.status]],['GIS / Mapper',labels[r.gis.status]]]);
  if(!current.gis)screen.append(button('Include GIS and check again','加入 GIS 并再次预检',async()=>{await saveAll();current.gis=true;mark();await save();await showFinalReview();}));
  if(r.gis.status==='BLOCKED'&&current.gis)screen.append(button('Switch to hydraulic results and reports only','改为仅交付水力结果和报告',async()=>{await saveAll();current.gis=false;mark();await save();await showFinalReview();}));
 }
 renderFeasibility(screen,review.feasibility);
 if(showAcquisitionGaps(screen,current.acquisition))screen.append(button('Review source coverage and local files','查看来源覆盖和本地文件',async()=>{
  await save();finalReview=null;await open(current.id);
  const hub=document.querySelector('.source-hub');for(let p=hub;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;hub?.scrollIntoView({block:'start'});
 }));
 if(!review.ready&&current.intake?.fields.some(f=>f.missing&&f.parameter_candidates?.length)){
  screen.append(button('Choose source candidates for missing inputs','集中选择缺项的资料候选',async()=>{
   await save();finalReview=null;await open(current.id);
   const panel=document.querySelector('details[data-candidate-batch]');
   if(!panel)return;
   for(let p=panel;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;
   panel.querySelectorAll('details[data-has-missing]').forEach(d=>d.open=true);
   panel.scrollIntoView({block:'start'});
  }));
 }
 if(review.errors.length){const ul=el('ul');const remaining=review.errors.length>8?details(screen,'All remaining input checks','其余输入检查',false):null;const restList=el('ul');remaining?.append(restList);for(const [index,e] of review.errors.entries()){const f=review.fields.find(f=>f.key===e.field),li=el('li',typeof e==='string'?e:(f?tr(f.label.en,f.label.zh)+': ':'')+tr(e.en,e.zh));if(f)li.append(button('Go to field','定位此项',async()=>{const input=document.getElementById('input-'+f.key);let parent=input?.parentElement;while(parent){if(parent.tagName==='DETAILS')parent.open=true;parent=parent.parentElement;}input?.scrollIntoView({block:'center'});input?.focus();}));if(index<8)ul.append(li);else restList.append(li);}screen.append(ul);}
 if(review.refreshed_equivalent_fields?.length)screen.append(el('p',review.refreshed_equivalent_fields.length+tr(' unchanged derived values were rebound to the current geometry. Values, ranges and sources are listed below.',' 项数值及依据均相同的推导值已自动关联当前几何。请在下方核对数值、范围和来源。'),'status'));
 renderDependencyReview(screen,review);
 const context=details(screen,'Project, map settings and source files','项目、地图设置和来源文件',false);table(context,[tr('Setting','设置'),tr('Value','数值')],[[tr('Coordinates','坐标'),JSON.stringify(review.inputs.configuration?.location||current.native?.location||'see input source')],['GIS / Mapper',String(review.inputs.gis)],...Object.entries(review.inputs.metadata)]);table(context,[tr('Source','来源'), 'SHA-256'],review.inputs.sources.map(s=>[s.path,s.sha256]));
 if(review.native){const d=details(screen,'Complete native model inspection','完整原生模型输入',false);d.append(el('pre',JSON.stringify(review.inputs.native,null,2)),el('p',tr('For native-file edits, change the source in HEC-RAS and import that version again. This review binds the exact input files.','原生文件参数需在 HEC-RAS 中修改后重新读取；本次核对绑定确切的输入文件。')));}
 else{
  const assumptions=review.fields.filter(f=>!f.missing&&['assumed','inferred'].includes(f.evidence_class));screen.append(el('p',`${review.fields.length} `+tr('input fields · ','项输入 · ')+assumptions.length+tr(' marked estimates/assumptions.','项标为估计／假设。'),'status'));
  if(assumptions.length){const a=details(screen,'Estimates / assumptions ('+assumptions.length+')','估计／假设（'+assumptions.length+'）',false);parameterTable(a,assumptions);}
  if(review.key_inputs?.length){
   const box=details(screen,'Which inputs need a decision?','哪些关键输入需要判断？',true);
   const labels={MISSING:['Missing','缺失'],BASIS_MISSING:['Locate the input source','补查输入来源'],OTHER_CANDIDATES:['Compare alternatives','比较其他候选'],CHECK_APPLICABILITY:['Check applicability','核对适用性'],SOURCE_RECORDED:['Basis available','已有依据']};
   table(box,[tr('Input','输入'),tr('Current value','当前值'),tr('Review','复核'),tr('Evidence and alternatives','依据及候选')],review.key_inputs.map(r=>[tr(r.label.en,r.label.zh),format(r.value)+' '+(r.unit||''),tr(...labels[r.priority]),[r.basis,...r.sources.map(s=>s.path.split(/[\\/]/).pop()),Array.isArray(r.adopted_range)?r.adopted_range.join(' – '):'',r.alternatives.length?tr('Other candidates: ','其他候选：')+r.alternatives.map(v=>format(v)).join(', '):''].filter(Boolean).join(' · ')]));
  }
  renderPreparationAttention(screen,review.attention);
  renderParameterNavigator(screen,review.fields);
  const fields=details(screen,'Complete editable parameter list','完整可修改参数清单',false);
  parameterTable(fields,review.fields);
  const edit=details(fields,'Edit values (all fields)','修改数值（全部字段）');for(const f of review.fields)parameterInput(edit,{...f,parameter_candidates:[]});
 }
 const actions=el('div',undefined,'card confirm-card');screen.append(actions);actions.append(button('Save and refresh parameter list','保存并刷新参数清单',showFinalReview));
 const consent=check(actions,'I have checked these inputs, including estimates, bank positions and limitations, and want to run this conditional calculation.','我已核对这些输入、估计值、左右岸及限制，确认采用它们进行本次条件性计算。',false,v=>{const b=$('#confirm-run');if(b)b.disabled=!v||!finalReview?.ready||dirty;});consent.id='confirm-parameters';
 const run=button('Confirm and run HEC-RAS','确认并运行 HEC-RAS',async()=>{if(!consent.checked||dirty||!finalReview?.ready)throw Error(tr('Refresh and confirm the current parameters first.','请先刷新并确认当前参数。'));await api('start',{id:current.id,revision:current.revision,start:true,confirmed:true,review_token:finalReview.review_token});finalReview=null;await open(current.id);},'primary');run.id='confirm-run';run.disabled=true;actions.append(run);
}
function renderDependencyReview(parent,review){
 if(dependencyReviewState?.token!==review.review_token)dependencyReviewState={token:review.review_token,choices:new Map()};
 const keys=new Set(review.errors.filter(e=>e.code==='DERIVED_INPUT_CHANGED').map(e=>e.field));
 const fields=review.fields.filter(f=>keys.has(f.key));if(!fields.length)return;
 const box=el('section',undefined,'card');parent.append(box);
 box.append(el('h2',tr('Review changed dependencies together','集中处理已变化的关联参数')),
  el('p',tr('Compare saved values and current derivations below. Choose replacements, explicitly retain a conditional assumption, or edit the full field. No selection is made for you.','在这里比较原值和当前推导。可采用候选、明确保留原值为条件性假设，或修改完整字段。不会自动替你选择。')));
 const choices=dependencyReviewState.choices,feedback=el('p','', 'status');box.append(feedback);
 const count=()=>{feedback.textContent=choices.size+tr(' choices selected, not saved · ',' 项已选择，尚未保存 · ')+(fields.length-choices.size)+tr(' awaiting a decision',' 项尚待决定');};
 for(const f of fields){
  const row=el('section',undefined,'parameter');box.append(row);
  row.append(el('strong',tr(f.label.en,f.label.zh)+(f.unit?' · '+f.unit:'')),
   el('p',tr('Saved value: ','原值：')+format(f.value,f.kind)+' · '+originName(f.evidence_class)));
  const prior=f.answer?.candidate_record||{};
  row.append(el('p',tr(prior.condition?.en||f.basis,prior.condition?.zh||f.basis),'muted'));
  if(prior.range)row.append(el('p',tr('Previous reference range: ','原参考范围：')+prior.range.join(' – ')));
  const refs=details(row,'Current candidates and sources','当前候选与依据',true);
  for(const [i,c] of f.parameter_candidates.entries()){
   refs.append(el('strong',(i+1)+': '+format(c.value,f.kind)+' · '+originName(c.evidence_class)),
    el('p',tr(c.condition?.en||c.basis,c.condition?.zh||c.basis)));
   if(c.range)refs.append(el('p',tr('Reference range: ','参考范围：')+c.range.join(' – ')+tr(' · see applicability; not a confidence interval',' · 请核对适用性，不代表置信区间')));
   for(const source of [c.source,...(c.sources||[])].filter(Boolean))refs.append(el('small',source.path||String(source)));
  }
  if(!f.parameter_candidates.length)refs.append(el('p',tr('No current candidate is available. Inspect the source and edit the field, or explicitly retain a justified assumption.','暂无可用候选。请查看资料后修改字段，或明确保留有依据的假设。'),'warning'));
  const options=[['','Choose after reviewing','核对后选择'],...f.parameter_candidates.map((c,i)=>[String(i),(i+1)+': '+format(c.value,f.kind),(i+1)+': '+format(c.value,f.kind)])];
  if(!f.missing)options.push(['retain','Keep saved value as a conditional assumption','保留原值为条件性假设']);
  const priorChoice=choices.get(f.key),candidateIndex=priorChoice?.action==='candidate'?f.parameter_candidates.findIndex(c=>c.candidate===priorChoice.candidate):-1;
  const selected=priorChoice?.action==='retain'?'retain':candidateIndex>=0?String(candidateIndex):'';
  field(row,'dependency-'+f.key,'Decision','处理方式',selected,'select',options,v=>{
   if(v==='')choices.delete(f.key);
   else if(v==='retain')choices.set(f.key,{field:f.key,action:'retain'});
   else choices.set(f.key,{field:f.key,action:'candidate',candidate:f.parameter_candidates[Number(v)].candidate});
   count();
  });
  row.append(button('Edit value in complete list','在完整清单中修改数值',async()=>revealParameter(f.key)));
 }
 box.append(button('Save these decisions and refresh review','保存本组决定并刷新核对',async()=>{
  if(!choices.size)throw Error(tr('Choose at least one decision first.','请先选择至少一项处理方式。'));
  if(finalReview!==review||dirty)throw Error(tr('Parameters were edited. Save and refresh the parameter list first.','参数已编辑，请先保存并刷新参数清单。'));
  await saveAll();
  const result=await api('resolve-dependencies',{id:current.id,revision:review.revision,review_token:review.review_token,selections:[...choices.values()]});
  current=await api('project/'+current.id);finalReview=null;
  await showFinalReview();
  notify(result.saved_fields.length+tr(' decisions saved. Review the updated inputs before confirming the calculation.',' 项决定已保存。请核对更新后的输入，再确认计算。'));
 },'primary'));
 count();
}
function scopeFields(parent,scope,atHome=false){
 const box=details(parent,'Intended use and flow paths','用途和过流路径',false);
 const purpose=field(box,'project-purpose','Intended use','项目用途',scope.purpose||'screening','select',[
  ['screening','Site screening','场地初筛'],['comparison','Compare alternatives','方案比较'],['review','Prepare for engineering review','准备工程复核']]);
 const paths=field(box,'project-flow-paths','Known hydraulic setting','已知水力条件',scope.flow_paths||'unknown','select',[
  ['unknown','Check against the site materials','根据场地资料核查'],['single','One main flow path','单一主过流路径'],
  ['parallel','Separate branches or strong lateral exchange must be modeled','需模拟独立支汊或显著横向交换'],
  ['bridge','A bridge inside the reach must be modeled','需模拟河段内部桥梁'],['unsteady','Flood-wave timing or storage is essential','需模拟洪峰传播时间或蓄泄过程']]);
 const hint=el('p');box.append(hint);
 function update(){
  hint.textContent=['parallel','unsteady','bridge'].includes(paths.value)
   ?tr('This scope needs a different hydraulic model. You can retain the site and revise the limits.','该范围需采用其他水力模型，可以保留项目并调整河段范围。')
   :tr('Public data and the imported inputs will populate the feasibility review.','开工核查会沿用公开资料和已导入的输入。');
 }
 paths.addEventListener('change',update);update();
 const value=()=>({purpose:purpose.value,flow_paths:paths.value});
 if(!atHome)box.append(button('Save intended use and flow paths','保存用途与过流条件',async()=>{
  await saveAll();await api('save',{id:current.id,revision:current.revision,production_scope:value()});
  await open(current.id);notify(tr('Project scope saved. Feasibility updated.','范围已保存，开工核查已更新。'));
 }));
 return value;
}

function renderFeasibility(parent,data,editable=false){
 if(!data)return;
 const card=el('section',undefined,'card');parent.append(card);
 card.append(el('h2',tr('Before building this reach','开工前的项目判断')));
 const state={outside:tr('The requested flow paths exceed the single-reach steady model.','当前过流条件超出单河段恒定流范围。'),
  missing:tr('Inputs or datum checks remain. Use the available sources below.','还有待补输入或基准冲突，可按下表核对资料。'),
  review:tr('Continue to parameter review. Verify the listed assumptions for this use.','可以继续核对参数，请按项目用途复核下列假设。')};
 card.append(el('p',state[data.state],data.state==='outside'?'warning':'status'));
 if(data.use==='conditional_screening')card.append(el('p',tr('Suitable for a conditional screening run. Confirm the assumptions below before calculating.','当前可做条件性初筛。运算前请集中确认下列假设。')));
 const labels={scope:tr('Flow paths','过流路径'),flow:tr('Discharge','流量'),bed:tr('Submerged bed','水下河床'),
  datum:tr('Elevation datum','垂直基准'),boundary:tr('Boundary control','边界控制'),openings:tr('Culvert openings','涵洞开口'),
  inverts:tr('Length and inverts','涵长和涵底'),independent_event:tr('Independent event','独立事件')};
 const statuses={available:tr('Specified','已说明'),missing:tr('Needed','待补'),review:tr('Check evidence','核对依据'),
  conditional:tr('Conditional','条件性'),conflict:tr('Conflict','冲突'),outside:tr('Outside scope','超出范围')};
 const panel=details(card,'Inputs, sources and next actions','输入、依据与下一步',data.state!=='review');
 for(const row of data.rows){
  const f=row.facts;
  const item=details(panel,labels[row.key]+' · '+statuses[row.status],labels[row.key]+' · '+statuses[row.status],false);
  item.append(el('p',tr(row.en,row.zh)));
  const sources={scope:['The National Map','https://apps.nationalmap.gov/downloader/'],flow:['USGS StreamStats','https://streamstats.usgs.gov/ss/'],
   datum:['NOAA NCAT','https://www.ngs.noaa.gov/NCAT/'],bed:['USGS ScienceBase','https://www.sciencebase.gov/catalog/'],
   boundary:['USGS Water Data','https://waterdata.usgs.gov/'],independent_event:['USGS Water Data','https://waterdata.usgs.gov/']};
  if(sources[row.key]){const [label,url]=sources[row.key],link=el('a',label);link.href=url;link.target='_blank';link.rel='noopener noreferrer';item.append(link);}
  if(['inverts','openings'].includes(row.key))item.append(el('p',tr('Use the owner’s structure inventory, as-built sheet or survey. Import any original you obtain in Site materials.','优先查业主的结构台账、竣工图或实测断面，在本站资料中导入原件。')));
  if(row.key==='scope'&&f.mapped_junctions?.length)table(item,[tr('Mapped branch','地图支流'),tr('Direction','方向'),'WGS84'],
   f.mapped_junctions.map(p=>[p.name||tr('Unnamed','未命名'),p.direction==='entering'?tr('Entering reach','汇入'):tr('Leaving reach','流出'),p.lonlat.join(', ')]));
  if(row.key==='flow')table(item,[tr('Profile','工况'),'cfs',tr('Source','来源')],f.profiles.map(p=>[p.id,p.flow_cfs,p.source]));
  if(row.key==='datum')item.append(el('p',tr('Model / terrain: ','模型／地形：')+[f.model_datum||'—',f.terrain_datum||'—'].join(' / ')));
  if(f.basis)item.append(el('p',f.basis));
  if(f.values?.length)table(item,[tr('Group','涵孔组'),tr('Parameter','字段'),tr('Value','取值'),tr('Origin','类别'),tr('Source','依据')],
   f.values.map(v=>[v.group,v.field,v.value,v.origin,v.basis]));
  if(f.nearby_frequency_stations?.length)table(item,['USGS',tr('Distance to project point (m)','距项目定位点（m）')],
   f.nearby_frequency_stations.map(s=>[s.station,s.distance_to_project_m]));
  if(f.search_status)item.append(el('p',tr('USGS boundary search','USGS 边界资料查询')+' · '+f.search_status));
  if(f.stations?.length)table(item,['USGS',tr('Outlet distance (m)','距下游边界（m）'),tr('Station information','测站资料')],
   f.stations.map(s=>[s.station,s.boundary_m,[s.transfer_required?tr('Water-level transfer required','需水位传递依据'):'',
    s.datum,...(s.rating_dates||[]),...(s.gage_history||[]).map(h=>h.statement),
    ...(s.outside_rating||[]).map(p=>p+' '+tr('outside rating','超出评级曲线'))].filter(Boolean).join(' · ')]));
  if(f.search_failures?.length)item.append(el('p',f.search_failures.join('\n'),'warning'));
 }
 if(editable){
  scopeFields(card,data.scope);
  if(data.state!=='outside'&&current.intake)card.append(button('Open site materials and public search','打开本站资料与公开搜索',async()=>{
   const dest=document.querySelector('.source-hub');
   if(dest){for(let p=dest;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;dest.scrollIntoView({block:'start'});}
   else notify(tr('Use the source-material panel on this project.','请打开本项目的资料面板。'));
  }));
 }
}

function renderManual(screen){
 if(current.model_type==='river'){renderRiverManual(screen);return;}
 const intake=current.intake;if(!intake){screen.append(button('Prepare terrain and inputs','准备地形与输入',async()=>{await api('prepare',{id:current.id});await open(current.id);}));return;}
 screen.append(el('h2',tr('Build from site materials','从现场资料建立模型')),el('p',tr('Import site materials and check the crossing on the DEM, then prepare an automatic draft. Review the highlighted uncertainties and remaining inputs together before confirming the calculation.','导入现场资料并在 DEM 上核对设施位置，然后自动准备草稿。集中核对标出的不确定项与剩余输入，再确认运算。')));
 const sources=intake.section_count?details(screen,'Review or add source material','查看或补充资料'):screen;
 renderSources(sources);renderAutomation(screen);renderAutoGeometry(screen);renderParameterNavigator(screen,intake.fields);
 const guide=details(screen,'What materials are useful?','准备哪些资料？',false);
 table(guide,[tr('Input','输入'),tr('Preferred material / what automation can do','优先资料／可自动处理的部分')],[
 [tr('Flow and roughness','流量与糙率'),tr('Applicable StreamStats / hydrology report; channel/overbank photos. DEM does not determine design flow.','本站 StreamStats／水文报告；河槽与漫滩照片。DEM 不能确定设计流量。')],
 [tr('Culverts','涵洞'),tr('Count, shape, clear dimensions, length, inlet/outlet inverts and datum, floor/inlet construction, blockage. Use drawings or measured photos.','孔数、形状、净尺寸、涵长、进出口涵底及基准、底板和入口构造、淤堵情况。优先竣工图或有尺度照片。')],
 [tr('Terrain and road','地形与道路'),tr('USGS DEM is fetched automatically. Pick flow direction and road crest; inspect sections and banks. Road width still needs an explicit value.','自动获取 USGS DEM。点选流向和路面高点线，查看断面和岸站。路宽仍须明确填写。')],
 [tr('Boundary','边界'),tr('Remote reach slope or applicable boundary data. Positive sampled slopes can be proposed; verify reach extent.','远端代表河段坡降或适用边界资料。可提出正地形坡降候选，需核对范围。')]]);
 if(current.terrain?.raster)screen.append(el('p',tr('DEM downloaded. Coordinates, elevations and source hashes are retained.','DEM 已下载，坐标、高程及来源哈希已保留。'),'status'));
 const categories={flow:details(screen,'A · Flow and roughness','A · 流量与糙率',false),geometry:details(screen,'B · DEM, sections and banks','B · DEM、断面和左右岸',false),structure:details(screen,'C · Culvert and road','C · 涵洞与道路',false),boundary:details(screen,'D · Units and boundaries','D · 单位与边界'),sections:details(screen,'E · All section data (editable)','E · 全部断面数据（可修改）')};
 metadata(categories.geometry,false);renderMapEditor(categories.geometry);if(current.intake?.section_count)renderSectionRepair(categories.geometry);if(intake.geometry_review?.sections?.length)renderBanks(categories.geometry,intake.geometry_review);

 const losses=intake.fields.filter(f=>f.key.startsWith('g.cross_sections.')&&f.key.endsWith('.expansion_contraction')&&f.missing);
 if(losses.length){const box=details(categories.sections,'Conditional transition-loss batch','条件性批量设置渐变／突变损失',true);box.append(el('p',tr('For subcritical-transition assumptions: expansion/contraction 0.3/0.1 on gradual reaches, 0.5/0.3 at the upstream culvert face. Review mixed/supercritical applicability. Existing values are retained; every section remains editable.','按缓流过渡假设：渐变段扩散/收缩 0.3/0.1，涵洞上游外侧断面 0.5/0.3。混合流或急流需另判断适用性。不覆盖已有值，每个断面仍可修改。')));box.append(button('Use this loss scheme for missing sections','对缺失断面采用此损失方案',async()=>{await save();const face=current.intake.fields.find(f=>f.key==='g.structure.us_xs_rs')?.value;const selections=current.intake.fields.filter(f=>f.key.startsWith('g.cross_sections.')&&f.key.endsWith('.expansion_contraction')&&f.missing).map(f=>{const index=f.key.split('.')[2],rs=current.intake.fields.find(v=>v.key==='g.cross_sections.'+index+'.rs')?.value;return {field:f.key,candidate:f.parameter_candidates[rs===face?1:0].candidate};});await api('candidate',{id:current.id,revision:current.revision,selections,missing_only:true});await open(current.id);}));}
 const subgroups={};
 for(const f of intake.fields){
  if(f.key.endsWith('.source')||f.key.endsWith('.parameter_source')||f.key==='g.functional_section_basis'||f.key.endsWith('.reach_length_basis'))continue;
  const target=f.key.startsWith('c.scenarios.')?categories.flow:f.key.startsWith('g.cross_sections.')?categories.sections:f.key.startsWith('g.structure.')?categories.structure:categories.boundary;
  let dest=target;
  if(f.key.startsWith('g.structure.')){const suffix=f.key.split('.').at(-1),bucket=f.key.includes('.road.')?'road':f.key.includes('.groups.')?'group'+f.key.split('.')[3]:'position';const en=bucket==='road'?'Road crest / overtopping':bucket==='position'?'Structure position (derived after sections)':'Opening group '+(Number(f.key.split('.')[3])+1);const zh=bucket==='road'?'道路高点／越流':bucket==='position'?'结构位置（生成断面后推导）':'涵孔组 '+(Number(f.key.split('.')[3])+1);if(!subgroups[bucket])subgroups[bucket]=details(target,en,zh,false);dest=subgroups[bucket];if(!f.required){const opt=bucket+'optional';if(!subgroups[opt])subgroups[opt]=details(dest,'Optional / advanced parameters','可选／高级参数');dest=subgroups[opt];}}
  if(f.key.startsWith('g.cross_sections.')){const i=f.key.split('.')[2];if(!subgroups['xs'+i])subgroups['xs'+i]=details(target,'Cross section '+(Number(i)+1),'断面 '+(Number(i)+1));dest=subgroups['xs'+i];}
  parameterInput(dest,f);
 }
 categories.sections.append(button('Add section manually','手动增加断面',async()=>{await save();await api('geometry/add',{id:current.id,kind:'section'});await open(current.id);}));categories.structure.append(button('Add culvert group','增加涵孔组',async()=>{await save();await api('geometry/add',{id:current.id,kind:'group'});await open(current.id);}));
 const imp=details(screen,'Alternatively, use an existing HEC-RAS model','也可改用已有 HEC-RAS 工程');nativeSelector(imp);
}
function renderMapEditor(parent){
 anchors={upstream:[],downstream:[],inlet:[],outlet:[],road:[],...(current.map_picks||{})};anchorMode=null;
 const intro=el('p',tr('Pick each exterior reach upstream → downstream (at least two points each). Inlet/outlet picks are optional group centers. Pick the road crest left → right looking downstream. Map points are saved automatically.','上下游外部河段各按流向点选至少两点。进出口为可选的涵孔组中心；路面高点线面向下游从左到右。点位会自动保存。'));parent.append(intro);
 const actions=el('div',undefined,'actions'),canvas=el('div'),status=el('p','', 'status');parent.append(actions,status,canvas);let pointsTimer=null,pointsPromise=null;
 const params=el('div',undefined,'grid');parent.append(params);
 const width=field(params,'xs-width','Section width (ft)','断面宽度（ft）',current.sampling_parameters?.section_width_ft??200,'number');
 const spacing=field(params,'xs-spacing','Section spacing (ft)','断面间距（ft）',current.sampling_parameters?.section_spacing_ft??40,'number');
 const gap=field(params,'wall-gap','Wall / clear gap between barrels (ft, for equal spacing only)','涵孔间墙厚／净间距（ft，仅等距布置使用）',current.wall_gap_ft??'','number');
 let groupIndex=0;
 const groupPicks=structuredClone(current.group_map_picks||{});
 if(groupPicks['0'])Object.assign(anchors,groupPicks['0']);
 field(params,'map-opening-group','Opening group for inlet / outlet picks','进出口点选所属涵孔组',0,'select',(current.automation?.groups||[{index:0}]).map(g=>[g.index,'Group '+(g.index+1),'组 '+(g.index+1)]),v=>task(async()=>{await savePoints();groupIndex=Number(v);const saved=groupPicks[String(groupIndex)]||{};anchors.inlet=saved.inlet||[];anchors.outlet=saved.outlet||[];draw();notify(tr('Pick inlet/outlet centers for group ','请点选此组进出口中心：')+(groupIndex+1));}));
 parent.append(el('small',tr('200/40 ft are editable sampling proposals, not site dimensions. Blank wall spacing stays unknown.','200/40 ft 仅为可改的采样建议，不是本站尺寸；空白墙厚保持未知。')));
 const modes=[];
 async function savePoints(){clearTimeout(pointsTimer);if(pointsPromise)await pointsPromise;await save();const picks=JSON.parse(JSON.stringify(anchors));pointsPromise=api('geometry/picks',{id:current.id,revision:current.revision,group_index:groupIndex,picks,wall_gap_ft:gap.value===''?null:Number(gap.value),parameters:{section_width_ft:Number(width.value),section_spacing_ft:Number(spacing.value)}});try{current=await pointsPromise;groupPicks[String(groupIndex)]={inlet:picks.inlet,outlet:picks.outlet};pendingMapSave=null;mapDirty=false;status.textContent=tr('Map points saved. ','地图点位已保存。')+counts();refreshCandidateControls();}finally{pointsPromise=null;}}
 const counts=()=>Object.entries(anchors).map(([k,v])=>`${tr({upstream:'Upstream',downstream:'Downstream',inlet:'Inlet',outlet:'Outlet',road:'Road'}[k],{upstream:'上游',downstream:'下游',inlet:'进口',outlet:'出口',road:'路面'}[k])}: ${v.length}`).join(' · ');
 function queuePoints(){pendingMapSave=savePoints;mapDirty=true;status.textContent=tr('Saving map points… ','正在保存点位… ')+counts();clearTimeout(pointsTimer);pointsTimer=setTimeout(()=>{if(!busy)task(savePoints,tr('Save map points','保存地图点位'));else queuePoints();},700);}
 for(const input of [width,spacing,gap])input.onchange=queuePoints;
 for(const[k,en,zh]of [['upstream','Pick upstream reach','点选上游河段'],['downstream','Pick downstream reach','点选下游河段'],['inlet','Pick inlet center','点选进口组中心'],['outlet','Pick outlet center','点选出口组中心'],['road','Pick road crest','点选路面高点线']]){const b=button(en,zh,async()=>{anchorMode=anchorMode===k?null:k;draw();notify(anchorMode?tr('Click the map to add a point: ','点击地图添加：')+tr(en,zh):tr('Point selection cancelled.','已取消点选状态。'));});b.dataset.mode=k;modes.push(b);actions.append(b);}
 let controller=null;async function load(bounds){return controller.load(bounds);}
 actions.append(button('Load / refresh DEM','载入／刷新 DEM',()=>load()),button('Zoom in','放大',()=>zoom(1/1.2)),button('Zoom out','缩小',()=>zoom(1.2)),button('Undo last selected point','撤销当前模式最后一点',async()=>{if(!anchorMode)throw Error(tr('Choose a point type first.','请先选择点位类型。'));anchors[anchorMode].pop();await savePoints();draw();}));
 async function zoom(scale){controller.zoom(scale);}
 actions.append(button('Fit DEM','显示全部 DEM',()=>controller.fit('terrain')),button('Fit sections','显示全部断面',()=>controller.fit('sections')));
 parent.append(button('Generate / replace candidate sections','生成／替换候选断面',async()=>{await savePoints();await api('geometry/generate',{id:current.id,revision:current.revision,replace_existing:!!current.intake.section_count,parameters:{section_width_ft:Number(width.value),section_spacing_ft:Number(spacing.value)},external_reaches:['upstream','downstream'].map(id=>({id,anchors_xy:anchors[id]}))});mapData=null;await open(current.id);notify(tr('Sections generated. Inspect the profiles and choose the displayed layout candidates.','候选断面已生成，请查看断面并选择显示的布置候选。'));},'primary'));
 parent.append(button('Sample the selected road crest','采样已点选的路面高点线',async()=>{await savePoints();await api('geometry/estimate',{id:current.id,revision:current.revision});await open(current.id);notify(tr('Road profile candidates are ready in Culvert and road; they have not been adopted.','路面剖面候选已显示在“涵洞与道路”，尚未采用。'));}));
 function draw(){modes.forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mode===anchorMode)));status.textContent=counts();controller?.draw();}
 controller=terrainMap(canvas,{getAnchors:()=>anchors,getMode:()=>anchorMode,onPoint:point=>{if(['inlet','outlet'].includes(anchorMode))anchors[anchorMode]=[point];else anchors[anchorMode].push(point);draw();queuePoints();}});
 draw();
}

function renderRiverAutomation(card,data){
 card.append(el('h2',tr('Prepare the reach, confirm once','河段集中准备，运算前统一确认')),
 el('p',tr('Save the reach anchors, prepare the draft, then review boundaries, channel bed and uncertain banks. Estimates remain editable.','保存河段锚点并自动准备草稿，然后集中核对边界、水下河槽和不确定岸站；估计值均可修改。')));
 const checks=data.checks;card.append(el('p',checks.blocking_count+tr(' geometry / dependency checks remain',' 项几何／关联检查待处理'),checks.blocking_count?'warning':'status'));
 for(const q of checks.issues||[])card.append(el('p',tr(q.message,q.zh),'warning'));
 card.append(button('Prepare an automatic draft','自动准备草稿（含标注的估计值）',async()=>{await saveAll();await api('automatic-prepare',{id:current.id,revision:current.revision});await open(current.id);},'primary'));
 if(current.preparation_result){const p=current.preparation_result;card.append(el('p',tr('Draft saved. Required values remaining: ','草稿已保存，剩余必填项：')+(current.intake?.fields?.filter(f=>f.required&&f.missing).length??p.stages.at(-1).missing_required.length),'status'));if(!current.intake?.section_count)showEndpointSearch(card,p.geometry_proposal?.layouts?.[0]?.endpoint_search);if(p.geometry_proposal?.error)card.append(el('p',p.geometry_proposal.error,'warning'));if(!p.geometry_proposal?.layouts?.[0]?.endpoint_search||p.geometry_applied)renderPreparedBanks(card,p);renderPreparationAttention(card,current.intake?.current_attention??p.attention);}
 renderCandidateBatch(card);
 if(current.intake?.geometry_review?.sections?.length)renderBankBatch(card,current.intake.geometry_review);
}
function renderRiverManual(screen){
 const intake=current.intake;if(!intake){screen.append(button('Prepare terrain and inputs','准备地形与输入',async()=>{await api('prepare',{id:current.id});await open(current.id);}));return;}
 screen.append(el('h2',tr('River reach between bridges','桥间纯河道')),
 el('p',tr('Place the upstream end below the upstream bridge and the downstream end above the downstream bridge. Bridge backwater can still affect the boundary. Select a defensible flow and boundary condition before solving.','上端设在上游桥下游侧，下端设在下游桥上游侧。桥梁壅水仍可能影响边界；计算前需选定有依据的流量与边界条件。')));
 const sources=intake.section_count?details(screen,'Review or add source material','查看或补充资料'):screen;
 renderSources(sources);
 const map=details(screen,'Reach extent and DEM','河段范围与 DEM',!intake.section_count);metadata(map,false);renderTerrainExtent(map);renderRiverMap(map);
 renderAutomation(screen);renderAutoGeometry(screen);renderParameterNavigator(screen,intake.fields);
 if(intake.section_count){const sections=details(screen,'Section and bank adjustments','断面和岸站调整');renderSectionRepair(sections);if(intake.geometry_review?.sections?.length)renderBanks(sections,intake.geometry_review);}
 const fullEditor=details(screen,'Edit individual hydraulic inputs','逐项编辑水力参数');
 const cats={flow:details(fullEditor,'Flow and roughness','流量与糙率'),boundary:details(fullEditor,'Channel bed and boundaries','河槽与边界'),sections:details(fullEditor,'All section data','全部断面数据')},xs={};
 for(const f of intake.fields){if(f.key.endsWith('.source')||f.key.endsWith('.parameter_source')||f.key==='g.functional_section_basis'||f.key.endsWith('.reach_length_basis'))continue;
  let target=f.key.startsWith('c.scenarios.')?cats.flow:f.key.startsWith('g.cross_sections.')?cats.sections:cats.boundary;
  if(target===cats.sections){const i=f.key.split('.')[2];target=xs[i]||(xs[i]=details(target,'Cross section '+(Number(i)+1),'断面 '+(Number(i)+1)));}parameterInput(target,f);
 }
}
function renderTerrainExtent(parent){
 if(!current.terrain?.products?.length)return;
 const box=details(parent,'Expand DEM coverage','扩展 DEM 覆盖范围');
 box.append(el('p',tr('Set the acquisition radius around the project coordinate. Expansion reuses downloaded USGS originals, retains saved parameters and existing DEM cells, and checks full coverage. Hydraulic endpoints are selected separately on the map.','设置项目坐标周围的地形范围半径。扩展会复用已下载的 USGS 原始地形、保留已存参数和原有 DEM 像元，并检查完整覆盖；水力边界位置另行在地图上确认。')));
 const radius=field(box,'terrain-radius','Coverage radius (m)','范围半径（m）',current.terrain.buffer_m||300,'number');
 radius.min=50;radius.max=5000;radius.step=50;
 box.append(button('Expand from downloaded DEM','从已下载地形扩展',async()=>{
  const buffer=Number(radius.value);
  if(!Number.isFinite(buffer)||buffer<50||buffer>5000)throw new Error(tr('Use a radius of 50–5000 m.','半径须为 50–5000 米。'));
  await saveAll();
  notify(tr('Expanding DEM and checking coverage…','正在扩展 DEM 并检查覆盖范围…'));
  await api('geometry/expand-terrain',{id:current.id,revision:current.revision,buffer_m:buffer});
  await open(current.id);
  notify(tr('DEM coverage expanded. Use Fit DEM to inspect the full extent.','DEM 覆盖范围已扩展。点击“显示全部 DEM”检查完整范围。'));
 }));
}
function showEndpointSearch(parent,search){
 if(!search)return;
 const note=search.needs_bend_anchor
  ? tr('Add a bend anchor on the intended channel and prepare the draft again.','请在目标河道弯道上补一个锚点，再生成草稿。')
  : tr('Open Automatic DEM layout / QA repair, check the blue path against imagery or survey, then adopt the preview.','请展开「自动提出 DEM 布置／QA 修正」，对照航片或测量核对蓝线，然后采用预览。');
 parent.append(el('p',tr('Two-endpoint DEM search','双端点 DEM 搜索')+' · '+tr('path difference ','两次路径最大差异 ')+search.path_difference_ft.toFixed(1)+' ft · '+tr('two-sided terrain support ','两侧地形支持 ')+search.supported_flanks+'/'+search.flank_checks+'. '+note,search.needs_bend_anchor?'warning':'status'));
}
function riverBendIndex(points,point){
 let best=Infinity,index=1;
 for(let i=1;i<points.length;i++){
  const [x,y]=points[i-1],dx=points[i][0]-x,dy=points[i][1]-y,den=dx*dx+dy*dy;
  const at=den?Math.max(0,Math.min(1,((point[0]-x)*dx+(point[1]-y)*dy)/den)):0;
  const distance=Math.hypot(point[0]-x-at*dx,point[1]-y-at*dy);
  if(distance<best){best=distance;index=i;}
 }
 return index;
}
function renderRiverMap(parent){
 let points=structuredClone(current.map_picks?.river||[]),selecting=false,insertBend=false,timer=null,promise=null,coordinateText=null;
 const actions=el('div',undefined,'actions'),state=el('p','', 'status'),canvas=el('div');parent.append(el('p',tr('Start with two points, just below the upstream bridge and just above the downstream bridge. The DEM search follows bends between them. Add ordered bend points if the path is uncertain or follows the wrong channel.','先点上游桥下游侧，再点下游桥上游侧。程序会在两点间搜索弯曲河道。若提示不确定或走错支汊，请按流向补充弯道点。')),actions,state,canvas);
 async function commit(){clearTimeout(timer);if(promise)await promise;await save();promise=api('geometry/picks',{id:current.id,revision:current.revision,picks:{river:points},parameters:{}});try{current=await promise;pendingMapSave=null;mapDirty=false;if(coordinateText&&!pendingChanges.has('river-coordinates'))coordinateText.value=points.map(p=>p.join(', ')).join('\n');state.textContent=points.length+tr(' reach anchors saved',' 个河段锚点已保存');}finally{promise=null;}}
 function queued(){pendingMapSave=commit;mapDirty=true;state.textContent=tr('Saving reach anchors…','正在保存河段锚点…');clearTimeout(timer);timer=setTimeout(()=>{if(!busy)task(commit,tr('Save river anchors','保存河段锚点'));else queued();},700);}
 const pick=button('Pick river upstream → downstream','沿流向点选河段',async()=>{await saveAll();insertBend=false;bend.setAttribute('aria-pressed','false');selecting=!selecting;pick.setAttribute('aria-pressed',String(selecting));notify(selecting?tr('Click the DEM to add reach anchors. Dragging only pans.','点击 DEM 添加河段锚点，拖动只平移地图。'):tr('Point selection ended.','已退出点选。'));});actions.append(pick);
 const addedIndices=[];
 const bend=button('Insert a bend between saved anchors','在已存锚点间插入弯道点',async()=>{
  await saveAll();
  if(points.length<2)throw Error(tr('Save both endpoints first.','请先保存两端点。'));
  selecting=false;insertBend=!insertBend;pick.setAttribute('aria-pressed','false');bend.setAttribute('aria-pressed',String(insertBend));
  notify(insertBend?tr('Click a bend near the intended segment. Check the updated order on the map.','请点目标河段的弯道，再核对地图上的点位顺序。'):tr('Bend selection ended.','已退出弯道点选。'));
 });actions.append(bend);
 const map=terrainMap(canvas,{getAnchors:()=>({river:points}),getMode:()=>selecting||insertBend?'river':null,onPoint:p=>{if(pendingChanges.has('river-coordinates')){notify(tr('Save the coordinate edits first.','请先保存坐标输入。'),true);return;}const index=insertBend?riverBendIndex(points,p):points.length;points.splice(index,0,p);addedIndices.push(index);map.draw();queued();}});
 actions.append(button('Undo last anchor','撤销最后一个点',async()=>{await saveAll();if(points.length)points.splice(addedIndices.pop()??points.length-1,1);await commit();map.draw();}),button('Zoom in','放大',()=>map.zoom(1/1.2)),button('Zoom out','缩小',()=>map.zoom(1.2)),button('Fit DEM','显示全部 DEM',()=>map.fit('terrain')),button('Fit sections','显示全部断面',()=>map.fit('sections')));
 const numeric=details(parent,'Enter or paste reach coordinates','输入或粘贴河段坐标');
 numeric.append(el('p',tr('One easting, northing pair per line, ordered upstream to downstream. Use the DEM coordinate system and horizontal units shown on the map. Review the saved line on the map.','每行填写东坐标、北坐标，按上游到下游排列。采用地图显示的 DEM 坐标系及平面单位，保存后核对地图上的连线。')));
 async function saveCoordinates(){
  const lines=coordinateText.value.trim().split(/\r?\n/).filter(line=>line.trim());
  const parsed=lines.map(line=>line.trim().split(/[,\s]+/).map(Number));
  if(parsed.length<2||parsed.length>100||parsed.some(p=>p.length!==2||p.some(v=>!Number.isFinite(v))))throw new Error(tr('Enter 2–100 coordinate pairs, one pair per line.','请输入 2–100 对坐标，每行一对。'));
  const bounds=current.intake?.terrain_setup?.bounds;
  if(!bounds)throw new Error(tr('Load the DEM before entering coordinates.','请先载入 DEM 再输入坐标。'));
  if(parsed.some(p=>p[0]<bounds[0]||p[0]>bounds[2]||p[1]<bounds[1]||p[1]>bounds[3]))throw new Error(tr('A coordinate is outside the DEM. Check CRS, units and coverage.','有坐标位于 DEM 范围外，请核对坐标系、单位和覆盖范围。'));
  if(new Set(parsed.map(p=>p.join(','))).size!==parsed.length)throw new Error(tr('Remove repeated coordinates.','请修正重复坐标。'));
  clearTimeout(timer);if(promise)await promise;
  const previous=points;points=parsed;
  try{await commit();}catch(error){points=previous;throw error;}
  addedIndices.length=0;coordinateText.value=points.map(p=>p.join(', ')).join('\n');stageChange('river-coordinates','',0,null);map.draw();
  notify(points.length+tr(' reach anchors saved. Review their direction and position on the map.',' 个河段锚点已保存，请核对地图上的流向与位置。'));
 }
 coordinateText=field(numeric,'river-coordinate-pairs','Easting, northing','东坐标, 北坐标',points.map(p=>p.join(', ')).join('\n'),'textarea',null,()=>stageChange('river-coordinates',tr('Reach coordinates','河段坐标'),1,saveCoordinates));
 coordinateText.rows=8;
 numeric.append(button('Save coordinates and show on map','保存坐标并显示到地图',saveCoordinates));
 state.textContent=points.length+tr(' saved anchors',' 个已保存锚点');
}
home().catch(e=>notify(e.message,true));
