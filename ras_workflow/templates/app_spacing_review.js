'use strict';
function spacingReviewNumber(value,digits=6){return Number.isFinite(value)?value.toFixed(digits):'—';}
function spacingReviewRows(rows,profile,scope,search){return rows.filter(r=>(!profile||r.profile===profile)&&(scope==='all'||scope==='changes'&&r.exceeding_pairs.length||scope==='attention'&&r.flags.length)&&(!search||String(r.rs).includes(search)));}

function spacingProfilePlot(parent,rows,ids){
 const sorted=[...rows].sort((a,b)=>Number(b.rs)-Number(a.rs)),levels=sorted.flatMap(r=>r.cases.filter(Boolean).map(v=>v.wse_ft)).filter(Number.isFinite);
 if(!levels.length)return;
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 760 310');svg.classList.add('repair-profile');svg.setAttribute('aria-label',tr('Water-surface comparison across three spacing cases','三组加密工况水面线对比'));parent.append(svg);
 const lo=Math.min(...levels)-.1,hi=Math.max(...levels)+.1,px=i=>70+i*650/Math.max(1,sorted.length-1),py=v=>240-(v-lo)/Math.max(.2,hi-lo)*200,colors=['#4f6d30','#136fbc','#b33e67'];
 for(let i=0;i<=4;i++){const y=lo+(hi-lo)*i/4;svgEl(svg,'line',{x1:70,x2:720,y1:py(y),y2:py(y),stroke:'#ddd'});svgEl(svg,'text',{x:8,y:py(y)+4,'font-size':11}).textContent=y.toFixed(2);}
 for(let k=0;k<3;k++){let points=[];for(let i=0;i<sorted.length;i++){const value=sorted[i].cases[k]?.wse_ft;if(Number.isFinite(value))points.push([px(i),py(value)]);else if(sorted[i].cases[k]!==null){if(points.length)svgEl(svg,'polyline',{points:points.map(p=>p.join(',')).join(' '),fill:'none',stroke:colors[k],'stroke-width':2});points=[];}}
  if(points.length)svgEl(svg,'polyline',{points:points.map(p=>p.join(',')).join(' '),fill:'none',stroke:colors[k],'stroke-width':2});
  svgEl(svg,'text',{x:70+k*220,y:18,fill:colors[k],'font-size':12}).textContent=ids[k];
 }
 const ticks=Math.min(9,sorted.length);for(let tick=0;tick<ticks;tick++){const i=Math.round(tick*(sorted.length-1)/Math.max(1,ticks-1));svgEl(svg,'text',{x:px(i),y:260,'text-anchor':'middle','font-size':11}).textContent=String(Number(sorted[i].rs));}
 svgEl(svg,'text',{x:390,y:294,'text-anchor':'middle','font-size':12}).textContent=tr('Section order / RS (not a distance scale); WSE in ft','断面顺序／RS（非距离比例）；水位单位 ft');
}

function spacingSectionPlot(parent,row,ids){
 const native=row.section,x=native.station_ft,z=native.elevation_ft,levels=row.cases.filter(Boolean).map(v=>v.wse_ft).filter(Number.isFinite);
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 700 250');svg.classList.add('repair-profile');svg.setAttribute('aria-label',tr('Same-section water-level overlay','同断面三组水位叠加'));parent.append(svg);
 const lo=Math.min(...z,...levels),hi=Math.max(...z,...levels),px=v=>45+(v-x[0])/Math.max(1,x.at(-1)-x[0])*620,py=v=>195-(v-lo)/Math.max(1,hi-lo)*160;
 profileGrid(svg,x,lo,hi,[45,665,35,195]);
 svgEl(svg,'polyline',{points:x.map((v,i)=>px(v)+','+py(z[i])).join(' '),fill:'none',stroke:'#745b3b','stroke-width':2});
 const colors=['#4f6d30','#136fbc','#b33e67'];for(let i=0;i<3;i++){const v=row.cases[i]?.wse_ft;if(Number.isFinite(v))svgEl(svg,'line',{x1:45,x2:665,y1:py(v),y2:py(v),stroke:colors[i],'stroke-width':2,'stroke-dasharray':i===0?'7,3':i===1?'3,3':''});svgEl(svg,'text',{x:45+i*215,y:18,fill:colors[i],'font-size':12}).textContent=ids[i];}
 for(const bank of native.banks_ft.filter(Number.isFinite))svgEl(svg,'line',{x1:px(bank),x2:px(bank),y1:35,y2:195,stroke:'#65712a','stroke-dasharray':'4,4'});
 parent.append(el('p',tr('Brown: final-level native ground; vertical dashed lines: model banks. Compare only levels containing this same section. Missing levels are not zero.','棕色：末级原生地面；竖虚线：模型岸站。只对比包含同一断面的工况，未包含的工况不记为零。'),'muted'));
}

function renderSpacingDiagnostics(parent){
 const box=details(parent,'Locate spacing differences and compare sections','定位加密差异并对比断面'),output=el('div');box.append(output);
 const id=current.id,hash=current.summary.sha256,token=current.latest_spacing.sha256;let loading=false,loaded=false;
 async function load(){
  if(loading||loaded)return;loading=true;output.setAttribute('aria-busy','true');output.replaceChildren(el('p',tr('Authenticating three native cases and locating water-level differences…','正在核验三组原生结果并定位水位差异…'),'status'));
  try{const data=await api('spacing-diagnostics',{id,summary_hash:hash,study_token:token});if(!output.isConnected||current?.id!==id||current.summary?.sha256!==hash||current.latest_spacing?.sha256!==token)return;loaded=true;draw(data);}
  catch(error){if(output.isConnected&&current?.id===id){output.replaceChildren(el('p',tr('Spacing comparison unavailable: ','加密对比暂不可用：')+error.message,'warning'),button('Retry spacing comparison','重试读取加密对比',load));}}
  finally{loading=false;output.removeAttribute('aria-busy');}
 }
 function draw(data){
  output.replaceChildren();const ids=data.cases.map(c=>c.id),lookup=new Map(data.rows.map(r=>[r.section.section_id,r.section]));
  output.append(el('p',data.section_profiles+tr(' section/profile records · ',' 条断面／工况记录 · ')+data.above_threshold+tr(' above the internal threshold · ',' 条超过内部阈值 · ')+data.wet_section_profiles+tr(' wet in at least one case.',' 条至少在一组工况中端点浸水。'),'status'));
  output.append(el('p',tr('Differences are observations, not proof of a cause or a preferred model. A channel Froude crossing of 1 does not by itself prove a hydraulic jump. No bank, boundary, flow path or warning is changed here.','差异是观察结果，不能据此确定原因或选择“更正确”的模型。主槽弗劳德数跨过 1 本身不能证明存在水跃。此处不修改岸站、边界、过流路径或警告。'),'warning'));
  table(output,[tr('Profile','工况'),tr('Comparison','对比'),tr('Compared / matched','已对比／对应断面'),tr('Above threshold','超阈值数'),tr('Max |ΔWSE| ft','最大 |Δ水位| ft'),tr('RS at maximum','最大差异 RS')],data.pairs.map(p=>[p.profile,p.from_case+' → '+p.to_case,p.compared_sections+' / '+p.matched_sections,p.above_threshold,spacingReviewNumber(p.max_abs_delta_ft),p.worst_stations.join(', ')]));
  if(data.missing_results)output.append(el('p',data.missing_results+tr(' comparisons have unavailable values; they are not passed.',' 条对比缺少有效值，不能判为通过。'),'warning'));
  if(data.unlocated_issues.length){const other=details(output,'Messages without unique locations','无法唯一定位的信息');table(other,['Case','Profile','RS','Message'],data.unlocated_issues.map(v=>[v.case,v.issue.profile??'—',v.issue.station??'—',v.issue.evidence?.native_message||v.issue.code]));}
  const profiles=[...new Set(data.rows.map(r=>r.profile))],controls=el('div'),chart=el('div'),count=el('p','','status'),list=el('div');output.append(controls,chart,count,list);
  const profile=field(controls,'spacing-review-profile','Profile','工况',profiles[0],'select',profiles.map(v=>[v,v,v]));
  const scope=field(controls,'spacing-review-scope','Show','显示',data.above_threshold?'changes':'attention','select',[['changes','Above threshold','超过阈值'],['attention','All observations / warnings','全部观察／警告'],['all','All sections','全部断面']]);
  const search=field(controls,'spacing-review-search','Find RS','查找 RS','');
  function refresh(){chart.replaceChildren();spacingProfilePlot(chart,data.rows.filter(r=>r.profile===profile.value),ids);list.replaceChildren();const rows=spacingReviewRows(data.rows,profile.value,scope.value,search.value.trim());count.textContent=rows.length+tr(' matching records, largest changes first. Expand a section for values, native warnings and map correspondence.',' 条匹配记录，按差异从大到小排列。展开断面可看数值、原生警告及地图对应。');
   rows.forEach((row,index)=>{const panel=details(list,'RS '+row.rs+' · max |ΔWSE| '+spacingReviewNumber(row.maximum_abs_delta_ft)+' ft','RS '+row.rs+' · 最大 |Δ水位| '+spacingReviewNumber(row.maximum_abs_delta_ft)+' ft',index===0);let drawn=false;
    function detail(){if(drawn||!panel.parentElement.open)return;drawn=true;const origins={BASELINE:tr('Original baseline section','原始基准断面'),FIRST_REFINEMENT:tr('Added at level 1','第一级新增断面'),SECOND_REFINEMENT:tr('Added at level 2; no consecutive-level comparison at this station','第二级新增断面；该位置没有连续两级对比')};panel.append(el('p',origins[row.origin]));
     table(panel,[tr('Metric','指标'),...ids],[['WSE ft',...row.cases.map(v=>spacingReviewNumber(v?.wse_ft))],['EGL ft',...row.cases.map(v=>spacingReviewNumber(v?.egl_ft))],['Critical WSE ft',...row.cases.map(v=>spacingReviewNumber(v?.critical_wse_ft))],['Channel V ft/s',...row.cases.map(v=>spacingReviewNumber(v?.velocity_fts,3))],['Channel Fr',...row.cases.map(v=>spacingReviewNumber(v?.froude,4))],['Min Error ft',...row.cases.map(v=>spacingReviewNumber(v?.min_error_ft))]]);
     panel.append(el('p',tr('Signed WSE change, level 0→1 / 1→2: ','带正负号的水位差，第 0→1／1→2 级：')+row.delta_wse_ft.map(v=>spacingReviewNumber(v)).join(' / ')+' ft'));
     if(row.wet_cases.length)panel.append(el('p',tr('Wet section ends in: ','端点浸水工况：')+row.wet_cases.join(', '),'warning'));
     if(row.channel_froude_crossings.length)panel.append(el('p',tr('Channel Fr crosses 1 between compared levels: ','对比前后主槽 Fr 跨过 1：')+row.channel_froude_crossings.join(', '),'warning'));
     spacingSectionPlot(panel,row,ids);atlasMap(panel,row.section,lookup,data.horizontal_crs);
     const messages=row.cases.flatMap(v=>v?v.issues.map(i=>[v.case,i.code,i.evidence?.native_message||i.recommended_action||'—']):[]);if(messages.length)table(panel,[tr('Case','工况'),tr('Code','代码'),tr('Native / diagnostic message','原生／诊断信息')],messages);
    }panel.parentElement.addEventListener('toggle',detail);detail();
   });
  }
  profile.onchange=refresh;scope.onchange=refresh;search.oninput=refresh;refresh();
  output.append(el('p',tr('All final-round case inputs and outputs remain saved. Use the computed-case continuation below if an independent geometry revision is needed, then confirm its parameters before calculating.','末轮所有工况输入输出均保留。需要独立修改几何时，可使用下方“从所选工况准备修订版”，确认参数后再计算。'),'muted'));
 }
 box.parentElement.addEventListener('toggle',()=>{if(box.parentElement.open)void load();});if(box.parentElement.open)void load();
}
