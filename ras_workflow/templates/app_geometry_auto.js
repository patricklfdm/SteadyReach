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
 let referenceEnabled=null,referencePairs=null,referenceSource=null,referenceDatum=null;
 if(!isInitial&&current.model_type==='river'){
  const reference=details(box,'Check extent against reference water levels','按参考水位检查断面范围');
  box.insertBefore(reference.parentElement,note);
  reference.append(el('p',tr('Associate imported reference levels with current section IDs. Levels are interpolated along section-center distances, with the nearest control held beyond either end. This screens DEM coverage and requires review of source date, section correspondence and datum.','将已导入资料中的参考水位关联到当前断面编号。程序按断面中心之间的距离插值，控制点以外沿用最近控制值，用于筛查 DEM 覆盖；需核对资料年代、断面对应位置和高程基准。')));
  referenceEnabled=check(reference,'Use reference water levels for this preview','本次预览使用参考水位',false,clear);
  const sourceOptions=(current.attachments||[]).map(s=>[s.path,s.original_name||s.path,s.original_name||s.path]);
  referenceSource=field(reference,'reference-source','Imported reference source','已导入的参考资料',sourceOptions[0]?.[0]||'','select',sourceOptions,clear);
  referenceDatum=field(reference,'reference-datum','Reference vertical datum','参考水位高程基准',current.intake.fields.find(f=>f.key==='g.vertical_datum')?.value||current.metadata?.dem_vertical_datum||'','text',null,clear);
  referencePairs=field(reference,'reference-water-pairs','Current RS, reference water elevation (ft), one pair per line','当前断面 RS, 参考水位（ft），每行一组','','textarea',null,clear);
  referencePairs.rows=7;
 }
 box.insertBefore(button(isInitial?'Propose anchors and sections':'Suggest QA corrections',isInitial?'自动提出锚点与断面':'根据 QA 提出集中修正',async()=>{
  note.textContent=tr('Reading real DEM and checking candidate geometry…','正在读取真实 DEM 并检查候选几何…');out.replaceChildren();
  try{
   const body={mode:isInitial?'initial':'qa',reach_length_ft:Number(length.value),maximum_width_ft:Number(width.value)};
   if(referenceEnabled?.checked){
    const lines=referencePairs.value.trim().split(/\r?\n/).filter(v=>v.trim());
    const points=lines.map(line=>{const pair=line.trim().split(/[,，\s]+/).map(Number);if(pair.length!==2||!pair.every(Number.isFinite))throw Error(tr('Each line needs an RS and a water elevation in ft.','每行填写断面 RS 和参考水位（ft）两个数值。'));return {rs:pair[0],water_ft:pair[1]};});
    body.reference_screen={points,source_path:referenceSource.value,vertical_datum:referenceDatum.value.trim()};
   }
   proposal=await request('prepare',body);show();
  }
  catch(e){note.textContent=tr('Proposal not completed. Saved geometry is unchanged. ','提案未完成，已保存几何不变。')+e.message;throw e;}
 },'primary'),note);
 function show(){
  out.replaceChildren();note.textContent=proposal.layouts.length+tr(' candidate layouts ready; no model changes saved.',' 个候选方案已生成，尚未修改模型。');
  const choose=field(out,'auto-layout','Candidate layout','候选方案',proposal.layouts[0].id,'select',proposal.layouts.map((v,i)=>[v.id,'Candidate '+(i+1)+' · '+(v.can_apply?'preview ready':'needs attention'),'方案 '+(i+1)+' · '+(v.can_apply?'可预览采用':'仍需处理')]));
  const detail=el('div');out.append(detail);choose.onchange=()=>renderLayout(proposal.layouts.find(v=>v.id===choose.value),detail);renderLayout(proposal.layouts[0],detail);
 }
 function renderLayout(v,detail){
  layout=v;detail.replaceChildren();const changed=new Set(v.changed_sections),selected=new Set(v.changed_sections),rows=v.geometry.cross_sections;
  const symbols={VERIFY_BRIDGE_BOUNDARY_EFFECTS:'核对边界断面及桥梁壅水影响',VERIFY_SUBMERGED_CHANNEL_GEOMETRY:'核对水下河槽测量／地表 DEM 假设',DIRECTION_AND_CROSSING_UNCONFIRMED:'流向／设施位置仍需确认',BOUNDARY_REACH_EXTENT_NOT_HYDRAULICALLY_VERIFIED:'外部边界距离尚未经过水力验证',PRIOR_WSE_IS_A_SCREEN_NOT_NEW_HYDRAULICS:'前次水位仅作筛查，需新计算验证',REFERENCE_WSE_COVERAGE_SCREEN:'参考水位用于断面范围筛查；请核对断面对应位置、基准和漫滩过流路径。本站水位待真实计算。'};
  detail.append(el('p',tr('Basis: ','依据：')+(v.seed?.basis||'QA / DEM')));
  for(const w of v.warnings||[])detail.append(el('p',tr(w==='REFERENCE_WSE_COVERAGE_SCREEN'?'Reference water levels screen coverage. Review section correspondence, datum and floodplain flow paths; site water levels require computation.':w,symbols[w]||w),'warning'));
  detail.append(el('p',v.changed_sections.length+tr(' proposed section changes',' 条断面改动提案')+' · '+(v.unresolved?.length||0)+tr(' unresolved items',' 项仍需处理')));
  if(v.joint_search){
   const search=v.joint_search,rotations=(v.changes||[]).filter(change=>change.rotation_deg),limited=(search.components||[]).some(component=>component.search_limit_reached);
   detail.append(el('p',tr('Directions and widths were checked together across neighboring sections. ','已联合核查相邻断面的方向和宽度。')+rotations.length+tr(' sections were resampled from the DEM and need bank confirmation.',' 条断面已从 DEM 重新采样，需要确认岸站。'),'status'));
   if(limited)detail.append(el('p',tr('The search reached its computation limit. The displayed feasible combination requires map and profile review.','搜索已达到计算次数上限。请核对显示的可行组合、地图及剖面。'),'warning'));
   if((search.components||[]).some(component=>component.status==='NO_COMPATIBLE_CANDIDATE'))detail.append(el('p',tr('Some section groups have no compatible combination within the search bounds. Review the retained geometry and remaining issues.','部分断面组在搜索范围内未找到兼容组合，请检查保留的几何及剩余问题。'),'warning'));
   const searchDetails=details(detail,'Direction and extent search details','方向与范围搜索详情');
   table(searchDetails,['RS',tr('Rotation (degrees)','转角（度）'),tr('Added left / right (ft)','左／右延伸（ft）'),tr('Original samples','原采样点')],(v.changes||[]).map(change=>[change.rs,change.rotation_deg||0,(change.left_added_ft||0).toFixed(1)+' / '+(change.right_added_ft||0).toFixed(1),change.old_points_preserved?tr('Preserved','保留'):tr('Resampled from DEM','从 DEM 重新采样')]));
   searchDetails.append(el('small',tr('Rotations are bounded to ±30 degrees. The search prioritizes coverage, then small rotations and added width. Review flow direction and floodplain connections before adoption.','转角限制在 ±30 度内，依次优先满足覆盖、减小转角和增加宽度。采用前需核对流向及漫滩连通关系。')));
  }
  if(v.boundary_study_count)detail.append(el('p',tr('Extent screening includes ','范围筛查已纳入 ')+v.boundary_study_count+tr(' verified boundary studies from the same baseline. Review the proposed changes before recalculating.',' 组已核验、属于同一基准模型的边界敏感性结果。请核对改动提案后再重算。'),'status'));
  if(v.reference_screen){const ref=v.reference_screen;detail.append(el('p',tr('Reference source: ','参考资料：')+(ref.source.original_name||ref.source.path)+' · '+ref.vertical_datum));table(detail,['RS',tr('Reference elevation (ft)','参考水位（ft）')],ref.points.map(p=>[p.rs,p.water_ft]));}
  if(v.seed&&!v.seed.direction_known)detail.append(el('p',tr('The arrow is inferred from surface elevations around the pin. Verify the facility, road gap and flow direction. If wrong, use the manual map tools; buried openings are not inferred.','箭头仅由坐标周围地表高程推测。请核对设施、道路间隔及上下游；不正确时使用手动地图工具，不推测埋藏涵孔。'),'warning'));
  const canvas=el('div');detail.append(canvas);const anchorsPreview=Object.fromEntries((v.anchors||[]).map(r=>[r.id,r.anchors_xy]));
  const map=terrainMap(canvas,{getAnchors:()=>anchorsPreview,getMode:()=>null,onPoint:()=>{},detached:true,viewKey:project+'|auto-preview'});map.setPreview(rows);
  detail.append(button('Fit proposed sections','显示提案断面范围',()=>map.fit('preview')));
  const actionLabel=action=>({JOINT_ROTATION_AND_COVERAGE:tr('Rotate and check extent','转向并检查范围'),EXTEND_WET_ENDS:tr('Extend wet section ends','延伸过水端点'),EXTEND_REFERENCE_COVERAGE:tr('Extend to reference coverage','延伸参考水位覆盖范围')})[action]||action;
  table(detail,['RS',tr('Width ft','宽度 ft'),tr('Change / screen','改动／筛查'),tr('Bank uncertainty','岸站不确定性')],rows.map((r,i)=>[r.rs,(r.station_ft.at(-1)-r.station_ft[0]).toFixed(1),actionLabel(v.changes?.find(c=>c.rs===r.rs)?.action)||r.position_basis||tr('Retained','保留'),r.bank_stations_ft?tr('Existing plan positions retained','保留原岸站实际位置'):r.bank_candidates?.confidence]));
  const uncovered=rows.filter(r=>r.auto_layout&&!r.auto_layout.endpoints_above_screen);if(uncovered.length)detail.append(el('p',tr('Terrain relief screen still open at RS: ','下列断面端点仍未高于地形筛查高程：')+uncovered.map(r=>r.rs).join(', ')+tr('. Review wider terrain / floodplain coverage. This is not a calculated water level.','。请检查更宽地形及漫滩覆盖；该筛查高程不是计算水位。'),'warning'));
  const profiles=details(detail,'Inspect section profiles / edit bank candidates','查看剖面／修改岸站候选');const pairs=new Map();
  for(const i of changed){const r=rows[i],p=details(profiles,'RS '+r.rs,'RS '+r.rs);if(proposal.mode==='qa')check(p,'Include this geometry change','采用此断面几何改动',true,on=>{on?selected.add(i):selected.delete(i);});
   const candidate=r.bank_stations_ft||r.bank_candidates?.selected_indices?.map(j=>r.station_ft[j]);const grid=el('div',undefined,'grid');p.append(grid);
   const left=field(grid,'auto-bank-left-'+i,'Left bank station (ft)','左岸站距（ft）',candidate?.[0]??'','number'),right=field(grid,'auto-bank-right-'+i,'Right bank station (ft)','右岸站距（ft）',candidate?.[1]??'','number');pairs.set(i,[left,right]);
   const chart=document.createElementNS('http://www.w3.org/2000/svg','svg');chart.setAttribute('viewBox','0 0 700 230');chart.classList.add('chart');chart.setAttribute('aria-label','RS '+r.rs+' profile');p.append(chart);
   const info=el('p',(r.bank_candidates?.reasons||[]).join('; '),'muted');p.append(info);
   const draw=()=>{chart.replaceChildren();const x=r.station_ft,z=r.elevation_ft,before=v.before_sections?.[i],change=v.changes?.filter(c=>c.rs===r.rs).at(-1),water=change?.threshold_reference_wse_ft??change?.threshold_prior_wse_ft,levels=[...z,...(before?.elevation_ft||[]),...(Number.isFinite(water)?[water]:[])],lo=Math.min(...levels),hi=Math.max(...levels),pt=(a,b)=>[40+(a-x[0])/(x.at(-1)-x[0])*630,190-(b-lo)/Math.max(1,hi-lo)*160];
    profileGrid(chart,x,lo,hi,[40,670,30,190]);
    svgEl(chart,'polyline',{points:x.map((a,j)=>pt(a,z[j]).join(',')).join(' '),fill:'none',stroke:'#795438','stroke-width':2});
    if(before)svgEl(chart,'polyline',{points:before.station_ft.map((a,j)=>pt(a+(change?.station_label_shift_ft||0),before.elevation_ft[j]).join(',')).join(' '),fill:'none',stroke:'#6b7280','stroke-width':2,'stroke-dasharray':'5 4'});
    if(Number.isFinite(water)){const y=pt(x[0],water)[1];svgEl(chart,'line',{x1:40,x2:670,y1:y,y2:y,stroke:'#bd312b','stroke-dasharray':'6 4'});}
    for(const input of [left,right]){if(input.value==='')continue;const j=x.indexOf(Number(input.value));if(j>=0){const[cx,cy]=pt(x[j],z[j]);svgEl(chart,'circle',{cx,cy,r:5,fill:'#007641'});}}
   };
   if(proposal.mode==='qa')p.append(el('small',v.reference_screen?tr('Brown: proposed ground; grey dashed: original ground; red dashed: reference coverage level; green: banks.','棕色：提案地形；灰虚线：原地形；红虚线：参考范围筛查高程；绿色：岸站。'):tr('Brown: proposed ground; grey dashed: original ground; red dashed (when present): prior WSE, not a new result. Green: banks.','棕色：提案地形；灰虚线：原地形；红虚线（如有）：前次水位，并非新结果；绿色：岸站。')));
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
 request('status').then(r=>{if(box.isConnected&&r.pending){proposal=r.pending;length.value=proposal.bounds.reach_length_ft;width.value=proposal.bounds.maximum_width_ft;if(referenceEnabled&&proposal.reference_screen){const ref=proposal.reference_screen;referenceEnabled.checked=true;referenceSource.value=ref.source.path;referenceDatum.value=ref.vertical_datum;referencePairs.value=ref.points.map(p=>p.rs+', '+p.water_ft).join('\n');}show();}}).catch(e=>{note.textContent=e.message;note.className='warning';});
}

async function prepareQaRevision(){
 const next=await api('revision',{id:current.id,revision:current.revision,confirmed:true});
 await open(next.id);
 notify(tr('Original preserved. Preparing suggestions in the independent revision…','原项目保留，正在独立修订版中生成建议…'));
 const proposal=await api('geometry/auto-prepare',{id:next.id,revision:next.revision,mode:'qa'});
 await open(next.id);
 const changes=Math.max(0,...proposal.layouts.map(layout=>layout.changed_sections.length));
 notify(tr('QA preview saved. ','QA 预览已保存。')+changes+tr(' proposed section changes. Open DEM layout and QA suggestions to review and adopt.',' 条断面改动提案。请展开 DEM 自动布置与 QA 修正，查看并选择采用。'));
}
