'use strict';
// Proposals are editable and require an explicit local choice. No reviewer form.
function revealParameter(key){const input=document.getElementById('input-'+key);let p=input;while(p){if(p.tagName==='DETAILS')p.open=true;p=p.parentElement;}input?.scrollIntoView({block:'center'});input?.focus();}
function renderAutomation(parent){
 const data=current.automation;if(!data)return;
 const card=el('section',undefined,'card automation');parent.append(card);
 if(current.model_type==='river'){renderRiverAutomation(card,data);return;}
 card.append(el('h2',tr('Prepare together, confirm once','集中准备，运算前统一确认')),el('p',tr('Associate opening points → inspect early geometry checks → review derived values and bank profiles. Saved values stay selected. No HEC-RAS run starts here.','关联洞口测点 → 提前检查几何 → 集中核对推导值和岸站。默认保留已保存的数值，此处不启动 HEC-RAS。')));
 const checks=data.checks,issues=checks.issues||[];
 const status=el('p',tr('Early checks: ','提前检查：')+checks.blocking_count+tr(' blocking · ',' 项待解决 · ')+(issues.length-checks.blocking_count)+tr(' notices',' 项提醒'),issues.length?'warning':'status');card.append(status);
 if(issues.length){const d=details(card,'Geometry / dependency checks ('+issues.length+')','几何／关联参数检查（'+issues.length+'）',true);for(const q of issues){const p=el('p',tr(q.message,q.zh));p.append(el('small',q.code+(q.tentative?tr(' · tentative point pairing',' · 测点配对尚未确认'):'')));if(q.field)p.append(button('Edit input','修改参数',async()=>revealParameter(q.field)));else if(q.sections?.length)p.append(button('Inspect section','查看断面',async()=>sectionRepairController?.select(q.sections[0])));d.append(p);}}
 const automatic=el('div',undefined,'actions');card.append(automatic);
 automatic.append(button('Prepare an automatic draft','自动准备草稿（含标注的估计值）',async()=>{await saveAll();await api('automatic-prepare',{id:current.id,revision:current.revision});await open(current.id);},'primary'));
 card.append(el('p',tr('Extract materials, repair DEM geometry and fill dependent values together. All estimates stay editable in the final confirmation. Check crossing direction, construction assumptions and conflicting sources.','集中提取资料、修正 DEM 几何并填入关联参数；估计值可在最终确认前修改。重点核对流向、结构假设及资料冲突。'),'muted'));
 const prepared=current.preparation_result;if(prepared){const last=prepared.stages.at(-1);card.append(el('p',tr('Automatic draft saved · ','自动草稿已保存 · ')+prepared.stages.reduce((n,s)=>n+s.changed_fields.length,0)+tr(' field updates · ',' 次参数更新 · ')+last.missing_required.length+tr(' required items remaining · ',' 个必填项待补 · ')+last.conflicts.length+tr(' source differences',' 处来源差异'),'status'));renderPreparationAttention(card,prepared.attention);}
 if(current.model_type!=='river')renderOpeningAssociations(card,data);
 renderCandidateBatch(card);
 if(current.intake?.geometry_review?.sections?.length)renderBankBatch(card,current.intake.geometry_review);
 card.append(el('p',tr('Remaining judgment: same-barrel correspondence, interior versus exterior crown, net clear dimensions, floor/inlet condition and local blockage, hydraulic flow paths, boundaries and uncertain banks. Unknowns stay blank; estimates are labelled.','仍需判断：是否同一涵孔、内顶还是外顶、有效净尺寸、底板／入口及局部淤堵、过流路径、边界和不确定岸站。未知值留空，估计值明确标注。'),'muted'));
}

function renderPreparationAttention(parent,notices){
 if(!notices?.length)return;
 const box=details(parent,'Check these interpretations before confirming','确认前集中核对这些判断',true);
 for(const notice of notices){
  const row=el('p',tr(notice.en,notice.zh),'warning');box.append(row);
  if(notice.fields?.length){
   const links=el('div',undefined,'actions');row.append(links);
   for(const key of notice.fields){const f=(finalReview?.fields||current.intake?.fields||[]).find(v=>v.key===key);if(f)links.append(button(f.label.en,f.label.zh,async()=>revealParameter(key)));}
  }
 }
}

function renderOpeningAssociations(parent,data){
 const box=details(parent,'Opening groups and survey-point associations','多组涵孔与测点关联',!data.mapping.length&&!!data.suggested.length);
 box.append(el('p',tr('Pairing is suggested from point codes and the selected flow direction. Confirm each inlet/outlet pair against the map or sketch. “Location only” supplies no invert. Crown minus height requires an explicit interior-crown interpretation.','按测点代码和已选流向提出配对。请对照地图或草图核对进出口。“仅位置”不推导涵底；采用“内顶减净高”需明确确认测点为内顶。')));
 if(!data.surveys.length){box.append(el('p',tr('Import a survey and resolve its CRS/units to enable point pairing. You can still edit group parameters and use the DEM/map tools below.','导入测量资料并确定坐标／单位后，可启用测点配对；仍可在下方编辑涵孔参数及使用地图。'),'muted'));return;}
 const draftKey='opening-association-'+current.id;let rows=structuredClone(data.mapping.length?data.mapping:[]);
 let restored=false;try{const cached=JSON.parse(sessionStorage.getItem(draftKey)||'null');if(cached?.revision===current.revision){rows=cached.rows;restored=true;}}catch{}
 const content=el('div'),feedback=el('p','', 'status');box.append(feedback);
 const remember=()=>{stageChange('associations',tr('Opening associations','洞口关联'),1,commitAssociations);sessionStorage.setItem(draftKey,JSON.stringify({revision:current.revision,rows}));feedback.textContent=tr('Association edits retained in this browser; click Save associations to prepare candidates.','关联编辑已暂存；点击“保存关联”后生成候选。');};
 box.append(button('Suggest all opening pairs','自动建议全部洞口配对',async()=>{rows=structuredClone(data.suggested);remember();draw();notify(rows.length?tr('Pairing proposal ready. Check group order and point meaning before saving.','配对提案已就绪，请核对组顺序及测点含义后保存。'):tr('No unambiguous pairing found. Add a row and identify points from the map or source.','未找到明确配对；可增加一行并从地图或资料指认测点。'));}));
 box.append(content);
 function draw(){content.replaceChildren();for(const [i,r] of rows.entries()){
  const row=details(content,tr('Group ','组 ')+(r.group+1)+tr(' / barrel ','／孔 ')+(r.barrel+1),tr('Group ','组 ')+(r.group+1)+tr(' / barrel ','／孔 ')+(r.barrel+1),true);
  const grid=el('div',undefined,'grid');row.append(grid);const prefix='assoc-'+i+'-';
  field(grid,prefix+'group','Group (1-based)','组号（从 1 开始）',r.group+1,'number',null,v=>{r.group=Number(v)-1;remember();});
  field(grid,prefix+'barrel','Barrel in group (1-based)','组内孔号（从 1 开始）',r.barrel+1,'number',null,v=>{r.barrel=Number(v)-1;remember();});
  field(grid,prefix+'shape','Shape for a new group','新组形状',r.shape||data.groups[r.group]?.shape||'box','select',[['box','Box / rectangular','箱形／矩形'],['circular','Circular','圆形']],v=>{r.shape=v;remember();});
  field(grid,prefix+'source','Survey source','测量来源',r.source,'select',data.surveys.map(s=>[s.source.sha256,s.source.original_name||s.source.path,s.source.original_name||s.source.path]),v=>{r.source=v;r.context_hash=data.surveys.find(s=>s.source.sha256===v).context_hash;remember();});
  for(const side of ['us','ds'])field(grid,prefix+side,side==='us'?'Inlet point IDs (comma separated)':'Outlet point IDs (comma separated)',side==='us'?'进口测点编号（逗号分隔）':'出口测点编号（逗号分隔）',(r[side]||[]).join(', '),'text',null,v=>{r[side]=v.split(/[,，\s]+/).filter(Boolean);remember();});
  field(row,prefix+'meaning','What do these elevations represent?','这些高程代表什么？',r.interpretation||'location','select',[
   ['location','Location only; do not derive an invert','仅位置，不推导涵底'],['invert','Identified interior invert points','已辨认的内涵底测点'],['interior_crown','Assume interior crown / low chord; subtract clear height','假定内顶／低梁底，减去净高']],v=>{r.interpretation=v;remember();});
  row.append(el('small',tr('Several IDs at one mouth use their mean XY/elevation. Do not combine different barrels or unrelated surfaces. Same-group members must share hydraulic parameters; split them otherwise.','同一洞口多个点使用 XY／高程均值。不可混合不同涵孔或不同表面；同组孔的水力参数必须一致，否则分组。')),button('Remove association','移除关联',async()=>{rows.splice(i,1);remember();draw();}));
 }}
 box.append(button('Add opening association','增加洞口关联',async()=>{const s=data.surveys[0];rows.push({group:Math.min(rows.length,9),barrel:0,shape:'circular',source:s.source.sha256,context_hash:s.context_hash,us:[],ds:[],interpretation:'location'});remember();draw();}));
 const create=check(box,'Allow creating the displayed new groups (dimensions remain unknown)','允许创建显示的新组（未知尺寸仍留空）',false,()=>{});
 async function commitAssociations(){await save();current=await api('opening-associations',{id:current.id,revision:current.revision,mapping:rows,create_groups:create.checked});sessionStorage.removeItem(draftKey);pendingChanges.delete('associations');}
 box.append(button('Save associations / prepare candidates','保存关联／生成候选',async()=>{await commitAssociations();await open(current.id);notify(tr('Associations saved; dependent candidates refreshed.','关联已保存，关联候选已刷新。'));},'primary'));
 draw();if(restored)remember();
}

function sameCandidate(a,b){
 return ['value','evidence_class','basis','automation_context','source','sources'].every(k=>JSON.stringify(a?.[k])===JSON.stringify(b?.[k]));
}
function renderCandidateBatch(parent,retained=new Map()){
 const all=current.intake.fields.filter(f=>(f.parameter_candidates?.length||retained.has(f.key))&&!f.key.endsWith('.bank_stations_ft'));
 const pending=all.filter(f=>f.missing),box=details(parent,'Review parameter candidates together ('+pending.length+' missing fields)','集中核对参数候选（'+pending.length+' 个缺项）');
 box.closest('details').dataset.candidateBatch='true';
 box.append(el('p',tr('Existing values are kept unless you explicitly select a replacement. A selected assumption is still conditional. You can edit any parameter in the full form below.','已有值默认保留，仅在明确选择替代值后修改。选中的假设仍是条件性输入，全部参数可在下方完整表单中修改。')));
 const selections=new Map(retained),selects=new Map(),feedback=el('p',tr('No candidates selected.','尚未选择候选。'),'status');box.append(feedback);
 box.closest('details').candidateSelections=selections;
 function count(){feedback.textContent=selections.size+tr(' candidates selected; not saved yet.',' 项候选已选，尚未保存。');stageChange('candidates',tr('Parameter candidates','参数候选'),selections.size,commitCandidates);}
 const controls=el('div',undefined,'actions');box.append(controls);
 controls.append(button('Select changed derived values','选中已变化的推导值',async()=>{for(const f of all.filter(v=>v.derived_update_available)){const choices=f.parameter_candidates.filter(c=>c.automation_context);if(choices.length===1){const n=f.parameter_candidates.indexOf(choices[0]);selects.get(f.key).value=String(n);selects.get(f.key).dispatchEvent(new Event('change'));}}count();notify(tr('Changed derived values selected for review; manual overrides are retained.','已选择有变化的推导值供核对，手动输入保持不变。'));}));
 controls.append(button('Select unique missing candidates','选中缺项的唯一候选',async()=>{for(const f of pending){const choices=f.parameter_candidates;const unique=choices.length&&choices.every(c=>JSON.stringify(c.value)===JSON.stringify(choices[0].value)&&c.evidence_class===choices[0].evidence_class);if(unique){selections.set(f.key,choices[0]);selects.get(f.key).value='0';selects.get(f.key).dispatchEvent(new Event('change'));}}count();notify(tr('Selections prepared. Inspect their conditions before applying.','选择已准备，请检查适用条件后集中采用。'));}),button('Clear selections','清空选择',async()=>{selections.clear();selects.forEach(s=>{s.value='';s.dispatchEvent(new Event('change'));});count();}));
 const buckets=new Map();for(const f of all){const name=f.key.includes('.groups.')?tr('Opening group ','涵孔组 ')+(Number(f.key.split('.')[3])+1):f.key.startsWith('g.cross_sections.')?tr('Section lengths and coefficients','断面流程长度及系数'):f.key.includes('.road.')?tr('Road crest','路顶'):tr('Flow, boundaries and model settings','流量、边界与模型设置');if(!buckets.has(name))buckets.set(name,details(box,name,name,false));const dest=buckets.get(name),row=el('section',undefined,'parameter');dest.append(row);
  row.append(el('strong',tr(f.label.en,f.label.zh)),el('p',tr('Saved: ','已保存：')+(format(f.value,f.kind)||'—')+' · '+originName(f.evidence_class)));
  const options=[['',f.missing?'Leave unresolved':'Keep saved value',f.missing?'暂不采用':'保留已保存值'],...f.parameter_candidates.map((c,i)=>[String(i),format(c.value,f.kind)+' · '+originName(c.evidence_class),format(c.value,f.kind)+' · '+originName(c.evidence_class)])];
  const prior=retained.get(f.key),matched=prior?f.parameter_candidates.findIndex(c=>sameCandidate(c,prior)):-1;
  if(prior&&matched<0)options.push(['stale',tr('Previous choice needs review','先前选择需重新核对')+' · '+format(prior.value,f.kind),tr('Previous choice needs review','先前选择需重新核对')+' · '+format(prior.value,f.kind)]);
  const info=el('p',prior&&matched<0?tr('Inputs changed. Your previous choice is retained for comparison. Choose a current candidate or clear it before saving.','输入依据已变化，先前选择保留供比较。请选当前候选或清除此项后保存。'):tr('Select a candidate to see its formula / condition.','选择候选后显示公式／条件。'),prior&&matched<0?'warning':'muted');
  const selectedValue=prior?(matched>=0?String(matched):'stale'):'';
  const select=field(row,'batch-'+f.key,'Candidate','候选',selectedValue, 'select',options,v=>{const c=v==='stale'?prior:v===''?null:f.parameter_candidates[Number(v)];if(c)selections.set(f.key,c);else selections.delete(f.key);info.textContent=c?tr(c.condition?.en||c.basis,c.condition?.zh||c.basis):tr('Saved input retained.','保留现有输入。');count();});selects.set(f.key,select);row.append(info);
  const refs=details(row,'All candidate formulas / sources','全部候选的公式／来源');for(const c of f.parameter_candidates)refs.append(el('p',format(c.value,f.kind)+' · '+tr(c.condition?.en||c.basis,c.condition?.zh||c.basis)));
  row.append(button('Edit value directly','直接修改数值',async()=>revealParameter(f.key)));
 }
 async function commitCandidates(){await save();const chosen=[];for(const [key,c] of selections){const f=current.intake.fields.find(f=>f.key===key),fresh=f?.parameter_candidates.find(v=>sameCandidate(v,c));if(!fresh)throw Error(key+tr(': candidate changed; choose its current proposal or clear the previous choice.', '：候选依据变化，请选择当前提案或清除先前选择。'));chosen.push({field:key,candidate:fresh.candidate});}if(!chosen.length)return;current=await api('candidate',{id:current.id,revision:current.revision,selections:chosen});selections.clear();count();}
 box.append(button('Save all selected changes','保存全部所选更改',async()=>{await saveAll();await open(current.id);notify(tr('All selected changes saved.','全部所选更改已保存。'));},'primary'));
 count();
}

function renderBankBatch(parent,review){
 review=structuredClone(review);
 const box=details(parent,'Bank-profile gallery / batch selection','岸站剖面总览／集中选择');
 box.append(el('p',tr('Saved banks are retained by default. Check uncertain profiles together; select only the changes you want to save. Clicking a dot changes the chosen left/right bank. This is a terrain interpretation, not engineering acceptance.','默认保留已存岸站。集中查看不确定剖面，只勾选需要保存的更改；选左／右岸后点击采样点。此处是地形解释，不是工程验收。')));
 const picks=new Map(),selected=new Set(),feedback=el('p','', 'status');box.append(feedback);
 const count=()=>{const incomplete=[...selected].filter(i=>!bankPairReady(review.sections[i],picks.get(i))).map(i=>'RS '+review.sections[i].rs);feedback.textContent=selected.size+tr(' sections selected; existing banks on other sections will be retained.',' 条断面待保存，其余断面的已存岸站会保留。')+(incomplete.length?tr(' Check both bank positions before saving: ',' 保存前请补齐或修正左右岸：')+incomplete.join(', '):'');feedback.className=incomplete.length?'warning':'status';stageChange('banks',tr('Bank positions','岸站'),selected.size,commitBanks);};
 for(const [i,row] of review.sections.entries()){
  const saved=row.bank_stations_ft?.length===2,x=row.station_ft,z=row.elevation_ft,bank=saved?row.bank_stations_ft.map(v=>x.indexOf(v)):(row.bank_candidates?.selected_indices?.slice()||[null,null]);
  picks.set(i,bank);
  const confidence=row.bank_candidates?.confidence||'UNRESOLVED';
  const d=details(box,'RS '+row.rs+' · '+(saved?'saved':'missing')+' · '+confidence,'RS '+row.rs+' · '+(saved?'已保存':'缺失')+' · '+confidence,false);
  if(!saved&&!bankPairReady(row,bank))d.append(el('p',tr('No reliable automatic bank pair is available. Both stations remain blank. Inspect the profile and select both banks using the dots or numeric inputs before saving.','未找到可靠的自动岸站组合，左右岸保持空白。请查看剖面，通过点选或数字输入补齐两岸后保存。'),'warning'));
  const use=check(d,'Save this section in the batch','集中保存此断面',false,v=>{if(v)selected.add(i);else selected.delete(i);count();});
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 700 220');svg.classList.add('repair-profile');d.append(svg);let side=null;
  const actions=el('div',undefined,'actions');d.append(actions);const left=button('Pick left bank','选择左岸',async()=>{side=side===0?null:0;draw();}),right=button('Pick right bank','选择右岸',async()=>{side=side===1?null:1;draw();});actions.append(left,right);
  const numbers=bankNumberInputs(d,'batch-bank-'+i,row,()=>bank,pair=>{bank.splice(0,2,...pair);selected.add(i);use.checked=true;count();draw();});
  const note=el('p');d.append(note,el('small',(row.bank_candidates?.reasons||[]).join('; ')));
  function draw(){svg.replaceChildren();const finite=z.filter(Number.isFinite);if(!finite.length)return;const lo=Math.min(...finite),hi=Math.max(...finite),xy=j=>[45+(x[j]-x[0])/Math.max(1,x.at(-1)-x[0])*620,175-(z[j]-lo)/Math.max(1,hi-lo)*145];profileGrid(svg,x,lo,hi,[45,665,30,175]);numbers.sync();svgEl(svg,'polyline',{points:z.map((v,j)=>Number.isFinite(v)?xy(j).join(','):'').join(' '),fill:'none',stroke:'#6e5334','stroke-width':2});z.forEach((v,j)=>{if(!Number.isFinite(v))return;const [cx,cy]=xy(j),c=svgEl(svg,'circle',{cx,cy,r:bank.includes(j)?5:2.5,fill:bank.includes(j)?'#b55c16':'#286954'});c.onclick=()=>{if(side===null)return;bank[side]=j;selected.add(i);use.checked=true;count();draw();};});left.setAttribute('aria-pressed',String(side===0));right.setAttribute('aria-pressed',String(side===1));note.textContent=tr('Left / right: ','左／右：')+bank.map(j=>x[j]?.toFixed(3)??'—').join(' / ')+' ft'+(side===null?'':tr(' · click the profile',' · 请点击剖面'));
  }draw();
 }
 async function commitBanks(){
  for(const i of selected)bankSelection(review,i,picks.get(i));
  await save();
  const sections=[...selected].map(i=>bankSelection(review,i,picks.get(i)));
  if(!sections.length)return;
  current=await api('geometry/banks',{id:current.id,revision:current.revision,sections});
  for(const {index} of sections){review.sections[index]=structuredClone(current.intake.geometry_review.sections[index]);}
  selected.clear();count();
 }
 box.append(button('Save all selected changes','保存全部所选更改',async()=>{await saveAll();await open(current.id);notify(tr('All selected changes saved.','全部所选更改已保存。'));},'primary'));count();
}

function profileGrid(svg, x, lo, hi, bounds) {
 const [left, right, top, bottom] = bounds;
 const high = lo + Math.max(1, hi-lo);
 for (let i=0; i<=5; i++) {
  const px=left+(right-left)*i/5, py=bottom-(bottom-top)*i/5;
  svgEl(svg,'line',{x1:px,x2:px,y1:top,y2:bottom,stroke:'#d1d9df','stroke-width':.7});
  svgEl(svg,'line',{x1:left,x2:right,y1:py,y2:py,stroke:'#d1d9df','stroke-width':.7});
  svgEl(svg,'text',{x:px,y:bottom+15,'text-anchor':'middle','font-size':10}).textContent=(x[0]+(x.at(-1)-x[0])*i/5).toFixed(1);
  svgEl(svg,'text',{x:left-5,y:py+3,'text-anchor':'end','font-size':10}).textContent=(lo+(high-lo)*i/5).toFixed(1);
 }
 svgEl(svg,'text',{x:left,y:top-8,'font-size':10}).textContent=tr('Elevation (ft)','高程（ft）');
 svgEl(svg,'text',{x:left,y:bottom+30,'font-size':10}).textContent=tr('Station (ft)','横距（ft）');
}

function bankPairReady(row,indices){
 return Array.isArray(indices)&&indices.length===2&&indices.every(i=>Number.isInteger(i)&&i>0&&i<row.station_ft.length-1&&Number.isFinite(row.station_ft[i])&&Number.isFinite(row.elevation_ft[i]))&&indices[0]<indices[1];
}

function bankSelection(review,index,bank_indices){
 const row=review.sections[index];
 if(!row||!bankPairReady(row,bank_indices))throw Error('RS '+(row?.rs??index)+tr(': select both banks at valid interior samples, with left before right, or deselect this section. No bank changes were saved.','：请补齐有效内部样点上的左右岸，并确保左岸在右岸之前；也可取消勾选此断面。本批岸站更改尚未保存。'));
 const latest=current.intake.geometry_review;
 const keys=['rs','station_ft','elevation_ft','cutline_xy','center_xy','bank_stations_ft'];
 if(keys.some(key=>JSON.stringify(review.sections[index]?.[key])!==JSON.stringify(latest.sections[index]?.[key]))){
  throw Error(tr('Section shape/banks changed; review this selection again.','断面形状或岸站已改变，请重新核对该选择。'));
 }
 return {index,bank_indices,fingerprint:latest.fingerprints[index]};
}

function validateBankInputs(parent=document){
 const invalid=parent.querySelector('[data-bank-input][aria-invalid="true"]');
 if(invalid)throw Error(tr('Correct the bank station before saving. ','保存前请修正岸站输入。')+invalid.getAttribute('data-bank-error'));
}

function bankNumberInputs(parent, id, row, getBanks, changed) {
 const grid=el('div',undefined,'grid');parent.append(grid);
 const note=el('p','', 'status');note.hidden=true;parent.append(note);
 const inputs=['left','right'].map((side,i)=>field(grid,id+'-'+side,i?'Right bank (ft)':'Left bank (ft)',i?'右岸站距（ft）':'左岸站距（ft）','','number'));
 inputs.forEach(input=>input.setAttribute('data-bank-input','true'));
 function sync(){
  const banks=getBanks();
  inputs.forEach((input,i)=>{
   input.value=Number.isInteger(banks?.[i])?Number(row.station_ft[banks[i]].toFixed(3)):'';
   input.setCustomValidity('');input.removeAttribute('aria-invalid');input.removeAttribute('data-bank-error');
  });
  note.hidden=true;note.textContent='';
 }
 function reject(input,message){
  input.setCustomValidity(message);input.setAttribute('aria-invalid','true');input.setAttribute('data-bank-error',message);
  note.textContent=message;note.className='warning error';note.hidden=false;
  input.reportValidity();
 }
 inputs.forEach((input,side)=>input.addEventListener('change',()=>{
  const x=row.station_ft,value=input.value===''?NaN:Number(input.value),pair=getBanks().slice();
  if(!Number.isFinite(value)||value<=x[0]||value>=x.at(-1)){reject(input,tr('Choose an interior station.','请输入断面范围内的站距。'));return;}
  const index=x.reduce((best,v,i)=>Math.abs(v-value)<Math.abs(x[best]-value)?i:best,0);pair[side]=index;
  if(index===0||index===x.length-1){reject(input,tr('The nearest DEM sample is a section endpoint. Choose an interior sample.','最近的 DEM 样点位于断面端点，请选择内部样点。'));return;}
  if(pair[0]!==null&&pair[1]!==null&&pair[0]>=pair[1]){reject(input,tr('Left bank must precede right bank.','左岸站距必须小于右岸。'));return;}
  input.setCustomValidity('');changed(pair);sync();
  note.className='status';note.hidden=false;
  note.textContent=tr('Selected DEM sample ','已选 DEM 样点 ')+x[index].toFixed(3)+tr(' ft · pending save',' ft · 待保存');
 }));
 return {sync};
}

function refreshCandidateControls() {
 if(finalReview||!current?.intake)return;
 const batch=document.querySelector('[data-candidate-batch]');
 if(batch){
  const host=el('div');renderCandidateBatch(host,batch.candidateSelections||new Map());
  const replacement=host.querySelector('[data-candidate-batch]');replacement.open=batch.open;
  batch.replaceWith(...host.childNodes);
 }
 for(const box of document.querySelectorAll('.parameter[data-key]')){
  const key=box.dataset.key;
  if(Object.hasOwn(edited,key)||Object.hasOwn(classEdits,key)||box.contains(document.activeElement))continue;
  const field=current.intake.fields.find(f=>f.key===key);
  if(field){const host=el('div');parameterInput(host,field);box.replaceWith(...host.childNodes);}
 }
 if(pendingChanges.has('candidates'))notify(tr('Candidates refreshed. Pending choices are retained; changed dependencies are marked for review.','候选已刷新，待保存选择已保留；依据变化的选择已标记待核对。'));
}
