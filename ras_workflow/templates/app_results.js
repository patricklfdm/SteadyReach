'use strict';
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
 const old= comparison.diagnostics?.previous,now=comparison.diagnostics?.current;
 if(old?.status==='VERIFIED'&&now?.status==='VERIFIED'){
  table(box,[tr('Diagnostic coverage','诊断覆盖'),tr('Previous','上次'),tr('Current','本次')],[
   [tr('Native warning coverage','原生警告覆盖'),old.warning_coverage,now.warning_coverage],
   [tr('Native messages','原生信息条数'),old.native_messages??'—',now.native_messages??'—'],
   [tr('Combined diagnostic records','合并诊断记录'),old.issue_count,now.issue_count]]);
  const codes=[...new Set([...Object.keys(old.counts),...Object.keys(now.counts)])].sort();
  const counts=details(box,'Diagnostic changes by category','按类别查看诊断变化');
  table(counts,[tr('Category','类别'),tr('Previous','上次'),tr('Current','本次')],codes.map(code=>[code,old.counts[code]||0,now.counts[code]||0]));
 }else box.append(el('p',tr('Diagnostic comparison is incomplete. ','诊断对比尚不完整。')+[old?.error,now?.error].filter(Boolean).join(' '),'warning'));
 box.append(el('p',tr('Matched section IDs use hash-verified native water levels. Review any changed section positions. The workflow flags changes above ','匹配断面编号采用已核验哈希的原生水位。请核对断面位置改动。工作流将超过 ')+
  comparison.threshold_ft+tr(' ft for review. This threshold supports screening. Hydraulic convergence, source adequacy and engineering acceptance require separate assessment.',' ft 的变化标为待复核，此阈值用于筛查。水力收敛、资料充分性与工程验收仍需分别判断。')));
}

function renderResultTools(parent){
 if(!current.native_review)parent.append(button('Prepare QA revision suggestions','根据 QA 创建修订建议',prepareQaRevision));
 renderStudy(parent);
 renderSpacing(parent);
 renderCoverage(parent);
 if(current.delivery?.mapped&&!current.exports_need_refresh)parent.append(button('Open QGIS review copy','打开 QGIS 复核副本',async()=>{const r=await api('qgis-preview',{id:current.id});notify(tr('Opened a separate preview copy: ','已打开独立复核副本：')+r.path);}));
 const box=details(parent,'Complete native outputs / refresh deliverables','补齐原生输出／更新交付包',!!current.exports_need_refresh||['UNAVAILABLE','COMPLETE_WITH_DIFFERENCES'].includes(current.automatic_native_outputs?.status));
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
 const qa=current.qa_locations;if(!qa?.rows.length)return;
 const area=details(parent,'Locate wet edges and separated water areas','定位湿端点与分隔水面',true);
 area.append(el('p',tr('These plots use this run’s original section and water-surface arrays. Red means a low section end. A separated wet interval does not prove a connected real-world flow path. To change geometry, create an editable revision first.','下图使用本次原始断面及计算水位数组。红色表示低端点；分隔的湿区不证明实际纵向过流连通。修改几何前请先创建可编辑修订版。')));
 for(const r of qa.rows){const row=details(area,r.profile+' · RS '+r.rs,r.profile+' · RS '+r.rs);row.append(el('p',tr('WSE / left excess / right excess (ft): ','水位／超左端点／超右端点（ft）：')+[r.wse_ft,r.left_excess_ft,r.right_excess_ft].map(v=>v.toFixed(3)).join(' / ')));
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 700 230');svg.classList.add('repair-profile');svg.setAttribute('role','img');svg.setAttribute('aria-label',r.profile+' RS '+r.rs);row.append(svg);
  const x=r.station_ft,z=r.elevation_ft,lo=Math.min(...z,r.wse_ft),hi=Math.max(...z,r.wse_ft),pt=(a,b)=>[55+(a-x[0])/(x.at(-1)-x[0])*615,185-(b-lo)/Math.max(1,hi-lo)*155];
  svgEl(svg,'polyline',{points:x.map((v,i)=>pt(v,z[i]).join(',')).join(' '),fill:'none',stroke:'#795438','stroke-width':2});
  for(const [a,b]of r.wet_intervals_ft){const [x1,y1]=pt(a,r.wse_ft),[x2,y2]=pt(b,r.wse_ft);svgEl(svg,'line',{x1,y1,x2,y2,stroke:'#1679be','stroke-width':3});}
  for(const i of [0,x.length-1]){const [cx,cy]=pt(x[i],z[i]);svgEl(svg,'circle',{cx,cy,r:5,fill:z[i]<r.wse_ft?'#c33122':'#286954'});}
  svgEl(svg,'text',{x:5,y:20}).textContent=hi.toFixed(2)+' ft';svgEl(svg,'text',{x:5,y:186}).textContent=lo.toFixed(2)+' ft';svgEl(svg,'text',{x:55,y:215}).textContent=tr('Station (ft): ','横距（ft）：')+x[0].toFixed(1)+' → '+x.at(-1).toFixed(1);
  if(r.cutline_xy)row.append(el('small',tr('Projected cutline: ','投影断面线：')+r.cutline_xy.map(p=>p.map(v=>v.toFixed(2)).join(', ')).join(' → ')));
 }
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
 const box=details(parent,'Automatic wet-end repair batch','湿端自动修订批次',pending||!!current.coverage_result);
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
 const box=details(parent,'Section-spacing trial','断面加密试算',!!current.spacing_result);
 box.append(el('p',tr('Prepare two nested DEM refinements around spacing-related warnings or throughout the reach. Review the added sections and inferred banks once, then run the baseline and both refinements sequentially.','按加密相关警告定位区间，或选择全河段，准备两级嵌套 DEM 加密。集中核对新增断面和推定岸站后，依次计算基准及两级加密。')));
 const scope=field(box,'spacing-scope','Refinement extent','加密范围',current.pending_study_plan?.scope||'warnings','select',[
  ['warnings','Intervals beside spacing-related warnings','加密相关警告相邻区间'],['all','Entire continuous reach','完整连续河段']]);
 const preview=el('div');let proposal=null;
 box.append(button('Prepare nested spacing preview','生成两级加密预览',async()=>{
  proposal=await api('study-prepare',{id:current.id,revision:current.revision,kind:'spacing',scope:scope.value});
  current.pending_study=proposal.entry;current.pending_study_plan=proposal.plan;
  showProposal();notify(tr('Spacing preview saved. Review the proposed sections before confirming calculation.','加密预览已保存，请核对新增断面后确认计算。'));
 }),preview);
 scope.addEventListener('input',()=>{proposal=null;preview.replaceChildren();});
 function showProposal(){
  preview.replaceChildren();const plan=proposal.plan;
  if(plan.excluded_intervals?.length)preview.append(el('p',tr('Intervals excluded because new cutlines could not fit — ','新增断面无法适配而排除的区间 — ')+plan.excluded_intervals.map(v=>v.upstream_rs+' → '+v.downstream_rs).join(', ')+tr('. These locations remain for geometry review.','。这些位置仍需几何复核。'),'warning'));
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
  const confirmed=check(preview,'I confirm the displayed sections, inferred banks and trial assumptions','我确认显示的断面、推定岸站和试算假设',false,()=>{});
  preview.append(button('Confirm and run three spacing cases','确认并计算三个加密工况',async()=>{
   if(!proposal||!confirmed.checked)throw Error(tr('Review and confirm this spacing preview first.','请先核对并勾选确认本次加密预览。'));
   await api('study-start',{id:current.id,revision:current.revision,token:proposal.token,confirmed:true});await open(current.id);
  },'primary'));
 }
 if(current.pending_study_plan?.analysis_kind==='section_spacing'){
  proposal={plan:current.pending_study_plan,token:current.pending_study.sha256};showProposal();
 }
 if(current.spacing_result){
  const r=current.spacing_result,c=r.convergence;
  if(r.excluded_intervals?.length)box.append(el('p',tr('Full-reach spacing coverage is incomplete. Excluded intervals — ','全河段加密覆盖尚不完整，排除区间 — ')+r.excluded_intervals.map(v=>v.upstream_rs+' → '+v.downstream_rs).join(', '),'warning'));
  box.append(el('p',r.status==='STABLE_AT_REVIEW_THRESHOLD'?tr('Both nested refinements meet the internal water-level threshold.','两次嵌套加密均达到内部水位变化阈值。'):tr('Spacing convergence remains open.','断面加密收敛仍待处理。'),r.status==='STABLE_AT_REVIEW_THRESHOLD'?'status':'warning'));
  if(c)table(box,[tr('Profile','工况'),tr('First refinement max |ΔWSE| ft','第一级最大 |Δ水位| ft'),tr('Second refinement max |ΔWSE| ft','第二级最大 |Δ水位| ft')],c.rows.map(v=>[v.profile,...v.last_two_max_xs_deltas_ft.map(x=>x.toFixed(6))]));
  table(box,[tr('Case','工况'),tr('Sections','断面数'),tr('Native messages','原生信息'),tr('Wet-end sections','湿端断面数')],r.cases.map(v=>[v.id,v.section_count,v.diagnostics?.native_messages??'—',v.wet_sections?.length??'—']));
  const completed=r.cases.filter(row=>row.status==='COMPUTED'&&row.id!=='baseline');
  if(completed.length){
   const selected=field(box,'spacing-continue-case','Continue from computed case','选择继续使用的已计算工况',completed.at(-1).id,'select',completed.map(row=>[row.id,row.id,row.id]));
   box.append(button('Prepare editable QA revision from selected case','从所选工况自动准备可编辑修订版',()=>continueStudyCase('spacing',selected.value,current.latest_spacing.sha256)));
  }
  box.append(el('p',tr('The 0.10 ft threshold is a workflow screen. Results cover the selected intervals and compare every retained section. Hydraulic warnings, submerged-bed accuracy and engineering acceptance remain open. The baseline deliverables can be refreshed to include this comparison.','0.10 ft 为工作流筛查阈值。结论限于所选区间，并对比全部保留断面。水力警告、水下河床准确性与工程验收仍需判断。可更新基准报告及交付包以纳入本次对比。')),
   button('Open spacing trial files','打开加密试算文件',()=>api('open-folder',{id:current.id,path:current.latest_spacing.path.replace(/\/[^/]+$/,'')})));
  if(r.failed_cases?.length)box.append(el('p',tr('Incomplete cases — ','未完成工况 — ')+r.failed_cases.join(', '),'warning'));
 }
}

function renderStudy(parent){
 if(current.native_review)return;
 const box=details(parent,'Optional sensitivity batch','可选：敏感性批量计算');
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
