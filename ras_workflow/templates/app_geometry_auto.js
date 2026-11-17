'use strict';
function renderAutoGeometry(parent){
 const isInitial=!current.intake?.section_count,project=current.id;
 const box=details(parent,'Automatic DEM layout / QA repair','自动提出 DEM 布置／QA 修正',isInitial||!!current.parent_revision);
 box.append(el('p',tr('The program proposes reach anchors, section locations and widths. Review the map, uncertain banks and remaining issues together. This step never runs the solver or changes the original completed project.','程序提出外部锚点、断面位置与范围。在同一处核对地图、不确定岸站及剩余问题；此步骤不启动求解器，也不修改原已完成项目。')));
 const settings=details(box,'Optional search bounds (editable)','可选：搜索范围（可修改）');
 const length=field(settings,'auto-reach-length','Exterior search length per side (ft)','每侧外部河段搜索长度（ft）',400,'number');
 if(current.model_type==='river')length.parentElement.hidden=true;
 const width=field(settings,'auto-width-limit','Maximum section search width (ft)','断面搜索宽度上限（ft）',isInitial?800:1200,'number');
 settings.append(el('small',tr('Search limits are algorithm controls, not accepted model limits or flood extents. Initial widths use terrain relief, not a calculated water level.','搜索上限是算法控制值，不是已确认的模型边界或洪水范围。初始宽度采用地形起伏筛查，不是计算水位。')));
 const note=el('p','', 'status'),out=el('div');box.append(note,out);let proposal=null,layout=null;
 async function request(action,body={}){if(current.id!==project)throw Error('Project changed');if(action!=='status')await saveAll();return api('geometry/auto-'+action,{id:project,revision:current.revision,...body});}
 const clear=()=>{proposal=null;out.replaceChildren();note.textContent=tr('Search bounds changed; generate a fresh proposal.','搜索范围已修改，请重新生成提案。');};length.oninput=clear;width.oninput=clear;
 box.insertBefore(button(isInitial?'Propose anchors and sections':'Suggest QA corrections',isInitial?'自动提出锚点与断面':'根据 QA 提出集中修正',async()=>{
  note.textContent=tr('Reading real DEM and checking candidate geometry…','正在读取真实 DEM 并检查候选几何…');out.replaceChildren();
  try{proposal=await request('prepare',{mode:isInitial?'initial':'qa',reach_length_ft:Number(length.value),maximum_width_ft:Number(width.value)});show();}
  catch(e){note.textContent=tr('Proposal not completed. Saved geometry is unchanged. ','提案未完成，已保存几何不变。')+e.message;throw e;}
 },'primary'),note);
 function show(){
  out.replaceChildren();note.textContent=proposal.layouts.length+tr(' candidate layouts ready; no model changes saved.',' 个候选方案已生成，尚未修改模型。');
  const choose=field(out,'auto-layout','Candidate layout','候选方案',proposal.layouts[0].id,'select',proposal.layouts.map((v,i)=>[v.id,'Candidate '+(i+1)+' · '+(v.can_apply?'preview ready':'needs attention'),'方案 '+(i+1)+' · '+(v.can_apply?'可预览采用':'仍需处理')]));
  const detail=el('div');out.append(detail);choose.onchange=()=>renderLayout(proposal.layouts.find(v=>v.id===choose.value),detail);renderLayout(proposal.layouts[0],detail);
 }
 function renderLayout(v,detail){
  layout=v;detail.replaceChildren();const changed=new Set(v.changed_sections),selected=new Set(v.changed_sections),rows=v.geometry.cross_sections;
  const symbols={VERIFY_BRIDGE_BOUNDARY_EFFECTS:'核对边界断面及桥梁壅水影响',VERIFY_SUBMERGED_CHANNEL_GEOMETRY:'核对水下河槽测量／地表 DEM 假设',DIRECTION_AND_CROSSING_UNCONFIRMED:'流向／设施位置仍需确认',BOUNDARY_REACH_EXTENT_NOT_HYDRAULICALLY_VERIFIED:'外部边界距离尚未经过水力验证',PRIOR_WSE_IS_A_SCREEN_NOT_NEW_HYDRAULICS:'前次水位仅作筛查，需新计算验证'};
  detail.append(el('p',tr('Basis: ','依据：')+(v.seed?.basis||'QA / DEM')));
  for(const w of v.warnings||[])detail.append(el('p',tr(w,symbols[w]||w),'warning'));
  if(v.seed&&!v.seed.direction_known)detail.append(el('p',tr('The arrow is inferred from surface elevations around the pin. Verify the facility, road gap and flow direction. If wrong, use the manual map tools; buried openings are not inferred.','箭头仅由坐标周围地表高程推测。请核对设施、道路间隔及上下游；不正确时使用手动地图工具，不推测埋藏涵孔。'),'warning'));
  const canvas=el('div');detail.append(canvas);const anchorsPreview=Object.fromEntries((v.anchors||[]).map(r=>[r.id,r.anchors_xy]));
  const map=terrainMap(canvas,{getAnchors:()=>anchorsPreview,getMode:()=>null,onPoint:()=>{},detached:true,viewKey:project+'|auto-preview'});map.setPreview(rows);
  detail.append(button('Fit proposed sections','显示提案断面范围',()=>map.fit('preview')));
  table(detail,['RS',tr('Width ft','宽度 ft'),tr('Change / screen','改动／筛查'),tr('Bank uncertainty','岸站不确定性')],rows.map((r,i)=>[r.rs,(r.station_ft.at(-1)-r.station_ft[0]).toFixed(1),v.changes?.find(c=>c.rs===r.rs)?.action||r.position_basis||tr('Retained','保留'),r.bank_stations_ft?tr('Existing plan positions retained','保留原岸站实际位置'):r.bank_candidates?.confidence]));
  const uncovered=rows.filter(r=>r.auto_layout&&!r.auto_layout.endpoints_above_screen);if(uncovered.length)detail.append(el('p',tr('Terrain relief screen still open at RS: ','下列断面端点仍未高于地形筛查高程：')+uncovered.map(r=>r.rs).join(', ')+tr('. Review wider terrain / floodplain coverage. This is not a calculated water level.','。请检查更宽地形及漫滩覆盖；该筛查高程不是计算水位。'),'warning'));
  const profiles=details(detail,'Inspect section profiles / edit bank candidates','查看剖面／修改岸站候选');const pairs=new Map();
  for(const i of changed){const r=rows[i],p=details(profiles,'RS '+r.rs,'RS '+r.rs);if(proposal.mode==='qa')check(p,'Include this geometry change','采用此断面几何改动',true,on=>{on?selected.add(i):selected.delete(i);});
   const candidate=r.bank_stations_ft||r.bank_candidates?.selected_indices?.map(j=>r.station_ft[j]);const grid=el('div',undefined,'grid');p.append(grid);
   const left=field(grid,'auto-bank-left-'+i,'Left bank station (ft)','左岸站距（ft）',candidate?.[0]??'','number'),right=field(grid,'auto-bank-right-'+i,'Right bank station (ft)','右岸站距（ft）',candidate?.[1]??'','number');pairs.set(i,[left,right]);
   const chart=document.createElementNS('http://www.w3.org/2000/svg','svg');chart.setAttribute('viewBox','0 0 700 230');chart.classList.add('chart');chart.setAttribute('aria-label','RS '+r.rs+' profile');p.append(chart);
   const info=el('p',(r.bank_candidates?.reasons||[]).join('; '),'muted');p.append(info);
   const draw=()=>{chart.replaceChildren();const x=r.station_ft,z=r.elevation_ft,before=v.before_sections?.[i],change=v.changes?.find(c=>c.rs===r.rs),water=change?.threshold_prior_wse_ft,levels=[...z,...(before?.elevation_ft||[]),...(Number.isFinite(water)?[water]:[])],lo=Math.min(...levels),hi=Math.max(...levels),pt=(a,b)=>[40+(a-x[0])/(x.at(-1)-x[0])*630,190-(b-lo)/Math.max(1,hi-lo)*160];
    profileGrid(chart,x,lo,hi,[40,670,30,190]);
    svgEl(chart,'polyline',{points:x.map((a,j)=>pt(a,z[j]).join(',')).join(' '),fill:'none',stroke:'#795438','stroke-width':2});
    if(before)svgEl(chart,'polyline',{points:before.station_ft.map((a,j)=>pt(a+(change?.station_label_shift_ft||0),before.elevation_ft[j]).join(',')).join(' '),fill:'none',stroke:'#6b7280','stroke-width':2,'stroke-dasharray':'5 4'});
    if(Number.isFinite(water)){const y=pt(x[0],water)[1];svgEl(chart,'line',{x1:40,x2:670,y1:y,y2:y,stroke:'#bd312b','stroke-dasharray':'6 4'});}
    for(const input of [left,right]){if(input.value==='')continue;const j=x.indexOf(Number(input.value));if(j>=0){const[cx,cy]=pt(x[j],z[j]);svgEl(chart,'circle',{cx,cy,r:5,fill:'#007641'});}}
   };
   if(proposal.mode==='qa')p.append(el('small',tr('Brown: proposed ground; grey dashed: original ground; red dashed (when present): prior WSE, not a new result. Green: banks.','棕色：提案地形；灰虚线：原地形；红虚线（如有）：前次水位，并非新结果；绿色：岸站。')));
   for(const input of [left,right])input.onchange=()=>{if(input.value!==''){const value=Number(input.value);if(!Number.isFinite(value))return;input.value=r.station_ft.reduce((a,b)=>Math.abs(a-value)<Math.abs(b-value)?a:b);notify(tr('Bank snapped to displayed DEM sample; verify before confirming.','岸站已对齐显示的采样点，请在确认前核对。'));}draw();};draw();
  }
  if(v.issues?.length){const checks=details(detail,'Remaining geometry checks','剩余几何检查',true);table(checks,['Code','Sections'],v.issues.map(q=>[q.code,(q.sections||[]).map(i=>rows[i]?.rs).join(', ')]));}
  if(v.unresolved?.length){const remaining=details(detail,'Other unresolved QA / decisions','其他未解决 QA／判断',false);table(remaining,['RS','Issue',tr('Action','处理')],v.unresolved.map(q=>[q.rs,q.code||q.status,q.action||tr('Inspect terrain/domain or supply more evidence.','检查地形／模型范围或补充依据。')]));}
  detail.append(el('p',tr('Adoption preserves the prior run. Only the displayed proposal is adopted; unresolved QA stays open. The complete parameter review follows, and computation requires its separate run confirmation.','采用后保留原运行，仅保存本次显示的提案，未解决 QA 继续保留。随后进入完整参数核对，确认运行后才求解。'),'muted'));
  const confirm=check(detail,'I checked direction, extent, changes and the displayed bank candidates (including uncertainty).','我已核对方向、范围、改动及显示的岸站候选（包括不确定性）。',false,on=>apply.disabled=!on||!v.can_apply);
  const apply=button('Adopt and review calculation inputs','采用并核对运算参数',async()=>{
   if(!confirm.checked||!proposal)throw Error(tr('Confirm the current preview first.','请先确认当前预览。'));
   const banks={};for(const[i,[l,r]]of pairs){if(selected.has(i)&&l.value!==''&&r.value!=='')banks[i]=[Number(l.value),Number(r.value)];}
   await request('apply',{proposal_id:proposal.id,token:proposal.token,layout_id:v.id,confirmed:true,confirm_banks:true,banks,section_indices:[...selected]});
   await open(project);notify(tr('Geometry saved in this draft. Check the full inputs before computing.','几何已保存到此草稿，请在计算前核对完整参数。'));await showFinalReview();
  },'primary');apply.disabled=true;detail.append(apply);
 }
 request('status').then(r=>{if(box.isConnected&&r.pending){proposal=r.pending;length.value=proposal.bounds.reach_length_ft;width.value=proposal.bounds.maximum_width_ft;show();}}).catch(e=>{note.textContent=e.message;note.className='warning';});
}

async function prepareQaRevision(){
 const next=await api('revision',{id:current.id,revision:current.revision,confirmed:true});
 await open(next.id);
 notify(tr('Original preserved. Preparing suggestions in the independent revision…','原项目保留，正在独立修订版中生成建议…'));
 await api('geometry/auto-prepare',{id:next.id,revision:next.revision,mode:'qa'});await open(next.id);
}
