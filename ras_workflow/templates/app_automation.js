'use strict';
// Proposals are editable and require an explicit local choice. No reviewer form.
function revealParameter(key){const input=document.getElementById('input-'+key);let p=input;while(p){if(p.tagName==='DETAILS')p.open=true;p=p.parentElement;}input?.scrollIntoView({block:'center'});input?.focus();}
function renderAutomation(parent){
 const data=current.automation;if(!data)return;
 const card=el('section',undefined,'card automation');parent.append(card);
 card.append(el('h2',tr('Prepare together, confirm once','集中准备，运算前统一确认')),el('p',tr('Associate opening points → inspect early geometry checks → review derived values and bank profiles. Saved values stay selected. No HEC-RAS run starts here.','关联洞口测点 → 提前检查几何 → 集中核对推导值和岸站。默认保留已保存的数值，此处不启动 HEC-RAS。')));
 const checks=data.checks,issues=checks.issues||[];
 const status=el('p',tr('Early checks: ','提前检查：')+checks.blocking_count+tr(' blocking · ',' 项待解决 · ')+(issues.length-checks.blocking_count)+tr(' notices',' 项提醒'),issues.length?'warning':'status');card.append(status);
 if(issues.length){const d=details(card,'Geometry / dependency checks ('+issues.length+')','几何／关联参数检查（'+issues.length+'）',true);for(const q of issues){const p=el('p',tr(q.message,q.zh));p.append(el('small',q.code+(q.tentative?tr(' · tentative point pairing',' · 测点配对尚未确认'):'')));if(q.field)p.append(button('Edit input','修改参数',async()=>revealParameter(q.field)));else if(q.sections?.length)p.append(button('Inspect section','查看断面',async()=>sectionRepairController?.select(q.sections[0])));d.append(p);}}
 renderOpeningAssociations(card,data);
 renderCandidateBatch(card);
 if(current.intake?.geometry_review?.sections?.length)renderBankBatch(card,current.intake.geometry_review);
 card.append(el('p',tr('Remaining judgment: same-barrel correspondence, interior versus exterior crown, net clear dimensions, floor/inlet condition and local blockage, hydraulic flow paths, boundaries and uncertain banks. Unknowns stay blank; estimates are labelled.','仍需判断：是否同一涵孔、内顶还是外顶、有效净尺寸、底板／入口及局部淤堵、过流路径、边界和不确定岸站。未知值留空，估计值明确标注。'),'muted'));
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

function renderCandidateBatch(parent){
 const all=current.intake.fields.filter(f=>f.parameter_candidates?.length&&!f.key.endsWith('.bank_stations_ft'));
 const pending=all.filter(f=>f.missing),box=details(parent,'Review parameter candidates together ('+pending.length+' missing fields)','集中核对参数候选（'+pending.length+' 个缺项）');
 box.append(el('p',tr('Existing values are kept unless you explicitly select a replacement. A selected assumption is still conditional. You can edit any parameter in the full form below.','已有值默认保留，仅在明确选择替代值后修改。选中的假设仍是条件性输入，全部参数可在下方完整表单中修改。')));
 const selections=new Map(),selects=new Map(),feedback=el('p',tr('No candidates selected.','尚未选择候选。'),'status');box.append(feedback);
 function count(){feedback.textContent=selections.size+tr(' candidates selected; not saved yet.',' 项候选已选，尚未保存。');stageChange('candidates',tr('Parameter candidates','参数候选'),selections.size,commitCandidates);}
 const controls=el('div',undefined,'actions');box.append(controls);
 controls.append(button('Select changed derived values','选中已变化的推导值',async()=>{for(const f of all.filter(v=>v.derived_update_available)){const choices=f.parameter_candidates.filter(c=>c.automation_context);if(choices.length===1){const n=f.parameter_candidates.indexOf(choices[0]);selects.get(f.key).value=String(n);selects.get(f.key).dispatchEvent(new Event('change'));}}count();notify(tr('Changed derived values selected for review; manual overrides are retained.','已选择有变化的推导值供核对，手动输入保持不变。'));}));
 controls.append(button('Select unique missing candidates','选中缺项的唯一候选',async()=>{for(const f of pending){const choices=f.parameter_candidates;const unique=choices.length&&choices.every(c=>JSON.stringify(c.value)===JSON.stringify(choices[0].value)&&c.evidence_class===choices[0].evidence_class);if(unique){selections.set(f.key,choices[0]);selects.get(f.key).value='0';selects.get(f.key).dispatchEvent(new Event('change'));}}count();notify(tr('Selections prepared. Inspect their conditions before applying.','选择已准备，请检查适用条件后集中采用。'));}),button('Clear selections','清空选择',async()=>{selections.clear();selects.forEach(s=>{s.value='';s.dispatchEvent(new Event('change'));});count();}));
 const buckets=new Map();for(const f of all){const name=f.key.includes('.groups.')?tr('Opening group ','涵孔组 ')+(Number(f.key.split('.')[3])+1):f.key.startsWith('g.cross_sections.')?tr('Section lengths and coefficients','断面流程长度及系数'):f.key.includes('.road.')?tr('Road crest','路顶'):tr('Flow, boundaries and model settings','流量、边界与模型设置');if(!buckets.has(name))buckets.set(name,details(box,name,name,false));const dest=buckets.get(name),row=el('section',undefined,'parameter');dest.append(row);
  row.append(el('strong',tr(f.label.en,f.label.zh)),el('p',tr('Saved: ','已保存：')+(format(f.value,f.kind)||'—')+' · '+originName(f.evidence_class)));
  const options=[['',f.missing?'Leave unresolved':'Keep saved value',f.missing?'暂不采用':'保留已保存值'],...f.parameter_candidates.map((c,i)=>[String(i),format(c.value,f.kind)+' · '+originName(c.evidence_class),format(c.value,f.kind)+' · '+originName(c.evidence_class)])];
  const info=el('p',tr('Select a candidate to see its formula / condition.','选择候选后显示公式／条件。'),'muted');
  const select=field(row,'batch-'+f.key,'Candidate','候选','', 'select',options,v=>{const c=v===''?null:f.parameter_candidates[Number(v)];if(c)selections.set(f.key,c);else selections.delete(f.key);info.textContent=c?tr(c.condition?.en||c.basis,c.condition?.zh||c.basis):tr('Saved input retained.','保留现有输入。');count();});selects.set(f.key,select);row.append(info);
  const refs=details(row,'All candidate formulas / sources','全部候选的公式／来源');for(const c of f.parameter_candidates)refs.append(el('p',format(c.value,f.kind)+' · '+tr(c.condition?.en||c.basis,c.condition?.zh||c.basis)));
  row.append(button('Edit value directly','直接修改数值',async()=>revealParameter(f.key)));
 }
 async function commitCandidates(){await save();const chosen=[];for(const [key,c] of selections){const f=current.intake.fields.find(f=>f.key===key),fresh=f?.parameter_candidates.find(v=>JSON.stringify(v.value)===JSON.stringify(c.value)&&v.basis===c.basis&&v.automation_context===c.automation_context);if(!fresh)throw Error(key+tr(': candidate changed; clear its selection and reopen the model to review updated proposals.', '：候选依据变化，请清空该选择并重新打开模型核对更新提案。'));chosen.push({field:key,candidate:fresh.candidate});}if(!chosen.length)return;current=await api('candidate',{id:current.id,revision:current.revision,selections:chosen});selections.clear();count();}
 box.append(button('Save all selected changes','保存全部所选更改',async()=>{await saveAll();await open(current.id);notify(tr('All selected changes saved.','全部所选更改已保存。'));},'primary'));
}

function renderBankBatch(parent,review){
 const box=details(parent,'Bank-profile gallery / batch selection','岸站剖面总览／集中选择');
 box.append(el('p',tr('Saved banks are retained by default. Check uncertain profiles together; select only the changes you want to save. Clicking a dot changes the chosen left/right bank. This is a terrain interpretation, not engineering acceptance.','默认保留已存岸站。集中查看不确定剖面，只勾选需要保存的更改；选左／右岸后点击采样点。此处是地形解释，不是工程验收。')));
 const picks=new Map(),selected=new Set(),feedback=el('p','', 'status');box.append(feedback);
 const count=()=>{feedback.textContent=selected.size+tr(' sections selected; existing banks on other sections will be retained.',' 条断面待保存，其余断面的已存岸站会保留。');stageChange('banks',tr('Bank positions','岸站'),selected.size,commitBanks);};
 for(const [i,row] of review.sections.entries()){
  const saved=row.bank_stations_ft?.length===2,x=row.station_ft,z=row.elevation_ft,bank=saved?row.bank_stations_ft.map(v=>x.indexOf(v)):row.bank_candidates?.selected_indices?.slice();
  if(!bank)continue;picks.set(i,bank);
  const d=details(box,'RS '+row.rs+' · '+(saved?'saved':'missing')+' · '+row.bank_candidates?.confidence,'RS '+row.rs+' · '+(saved?'已保存':'缺失')+' · '+row.bank_candidates?.confidence,false);
  const use=check(d,'Save this section in the batch','集中保存此断面',false,v=>{if(v)selected.add(i);else selected.delete(i);count();});
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 700 220');svg.classList.add('repair-profile');d.append(svg);let side=null;
  const actions=el('div',undefined,'actions');d.append(actions);const left=button('Pick left bank','选择左岸',async()=>{side=side===0?null:0;draw();}),right=button('Pick right bank','选择右岸',async()=>{side=side===1?null:1;draw();});actions.append(left,right);
  const note=el('p');d.append(note,el('small',(row.bank_candidates?.reasons||[]).join('; ')));
  function draw(){svg.replaceChildren();const finite=z.filter(Number.isFinite);if(!finite.length)return;const lo=Math.min(...finite),hi=Math.max(...finite),xy=j=>[45+(x[j]-x[0])/Math.max(1,x.at(-1)-x[0])*620,175-(z[j]-lo)/Math.max(1,hi-lo)*145];svgEl(svg,'polyline',{points:z.map((v,j)=>Number.isFinite(v)?xy(j).join(','):'').join(' '),fill:'none',stroke:'#6e5334','stroke-width':2});z.forEach((v,j)=>{if(!Number.isFinite(v))return;const [cx,cy]=xy(j),c=svgEl(svg,'circle',{cx,cy,r:bank.includes(j)?5:2.5,fill:bank.includes(j)?'#b55c16':'#286954'});c.onclick=()=>{if(side===null)return;bank[side]=j;selected.add(i);use.checked=true;count();draw();};});left.setAttribute('aria-pressed',String(side===0));right.setAttribute('aria-pressed',String(side===1));note.textContent=tr('Left / right: ','左／右：')+bank.map(j=>x[j]?.toFixed(3)??'—').join(' / ')+' ft'+(side===null?'':tr(' · click the profile',' · 请点击剖面'));
   svgEl(svg,'text',{x:45,y:208}).textContent=tr('Station (ft) ','横距（ft）')+x[0].toFixed(1)+' → '+x.at(-1).toFixed(1);
  }draw();
 }
 async function commitBanks(){await save();const sections=[...selected].map(i=>{const latest=current.intake.geometry_review;const keys=['station_ft','elevation_ft','cutline_xy','center_xy','bank_stations_ft'];if(keys.some(k=>JSON.stringify(review.sections[i][k])!==JSON.stringify(latest.sections[i][k])))throw Error(tr('Section shape/banks changed; review this selection again.','断面形状或岸站已改变，请重新核对该选择。'));return {index:i,bank_indices:picks.get(i),fingerprint:latest.fingerprints[i]};});if(!sections.length)return;current=await api('geometry/banks',{id:current.id,revision:current.revision,sections});selected.clear();count();}
 box.append(button('Save all selected changes','保存全部所选更改',async()=>{await saveAll();await open(current.id);notify(tr('All selected changes saved.','全部所选更改已保存。'));},'primary'));count();
}
