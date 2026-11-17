'use strict';
function renderResultTools(parent){
 if(!current.native_review)parent.append(button('Prepare QA revision suggestions','根据 QA 创建修订建议',prepareQaRevision));
 renderStudy(parent);
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

function renderStudy(parent){
 if(current.native_review)return;
 const box=details(parent,'Optional sensitivity batch','可选：敏感性批量计算');
 box.append(el('p',tr('Choose explicit low/high values for one parameter. The baseline and changed cases will run sequentially after one confirmation, with automatic water-level comparison. Bounds are assumptions, not measured uncertainty.','选择一个参数并填写明确的低／高值，统一确认后自动依次计算基准与变化工况并对比水位。范围属于假设，不是实测误差。')));
 const options=[['scenario.channel_n','Channel Manning n','主槽糙率'],['scenario.overbank_n','Overbank Manning n','漫滩糙率'],['boundary_slopes.upstream','Upstream normal-depth slope','上游正常水深坡降'],['boundary_slopes.downstream','Downstream normal-depth slope','下游正常水深坡降']];
 if(current.model_type==='river'){
  const r=current.results||{},b=r.boundaries||{};
  for(let i=options.length-1;i>=0;i--){const key=options[i][0];if(key.startsWith('boundary_slopes.')){const side=key.split('.')[1];if(b[side]?.type!=='normal_depth'||side==='upstream'&&r.flow_regime==='subcritical')options.splice(i,1);}}
  if(b.downstream?.type==='known_stage')for(const [i,p]of (r.metrics||[]).entries())options.push(['boundaries.downstream.stages_ft.'+i,p.profile_id+' downstream WSE (ft)',p.profile_id+' 下游绝对水位（ft）']);
 }
 for(const g of current.results?.metrics?.[0]?.culvert_groups||[])options.push(['groups.'+g.group_id+'.depth_blocked_ft','Group '+(g.group_id+1)+' uniform bottom fill (ft)','第 '+(g.group_id+1)+' 组全涵长底部填塞（ft）']);
 const path=field(box,'study-field','Parameter','参数',options[0][0],'select',options),low=field(box,'study-low','Low value','低值','','number'),high=field(box,'study-high','High value','高值','','number');
 if(current.model_type==='river')box.append(el('small',tr('Known-stage sensitivity uses absolute water-surface elevations in the model datum. Select ranges supported by the boundary evidence; bridge backwater is not removed by ending the reach before the bridge.','已知水位敏感性采用模型高程基准下的绝对水位。范围需有边界依据；把模型截在桥前不会消除桥梁壅水。')));
 else box.append(el('small',tr('For blockage, HEC-RAS applies the fill depth throughout the barrel. Do not use a local inlet-photo depth without deciding whether that assumption is appropriate. No generic percentage range is filled automatically.','填塞深度会作用于整根涵管。入口照片中的局部淤堵不能未经判断直接等同于全涵长填塞；不会自动填入通用百分比范围。')));
 const preview=el('div');box.append(preview);let proposal=null;
 for(const input of [path,low,high])input.addEventListener('input',()=>{proposal=null;preview.replaceChildren();});
 box.append(button('Prepare and review batch','准备并核对批量工况',async()=>{if(!low.value.trim()||!high.value.trim())throw Error(tr('Enter both bounds.','请填写两个范围端值。'));proposal=await api('study-prepare',{id:current.id,revision:current.revision,parameters:[{path:path.value,low:Number(low.value),high:Number(high.value)}]});preview.replaceChildren();table(preview,['Case','Changes'],proposal.plan.cases.map(c=>[c.id,c.changes.map(v=>v.path+': '+JSON.stringify(v.before)+' → '+JSON.stringify(v.after)).join('; ')]));preview.append(el('p',tr('Only these cases will be calculated. Reports are generated for each case; GIS packages are kept with the original baseline to avoid repeated map exports.','只计算显示的这些工况；每个工况生成报告，GIS 交付包保留原基准，避免重复出图。')),button('Confirm displayed cases and calculate','确认显示工况并计算',async()=>{if(!proposal)throw Error('Prepare the current range again');await api('study-start',{id:current.id,revision:current.revision,token:proposal.token,confirmed:true});await open(current.id);},'primary'));}));
 if(current.study_result){const r=current.study_result;box.append(el('p',r.status,'status'));table(box,[tr('Parameter','参数'),tr('Tested response','测试响应'),current.model_type==='river'?'Max Δ upstream WSE ft':'Max ΔHW ft','Max ΔXS WSE ft'],r.measurement_priorities.map(p=>[p.id,p.priority,p.max_abs_hw_change_ft,p.max_abs_matched_xs_change_ft]));if(r.failed_cases.length)box.append(el('p',tr('Failed/incomplete cases: ','失败／未完成工况：')+r.failed_cases.join(', '),'warning'));box.append(button('Open study results','打开敏感性结果',()=>api('open-folder',{id:current.id,path:current.latest_study.path.replace(/\/[^/]+$/,'')})));}
}
