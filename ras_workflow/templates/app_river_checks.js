'use strict';
function riverVariantName(name){
 return {baseline:tr('Original','基准'),fixed:tr('Fixed direction','固定方向'),rotated:tr('Rotation allowed','允许旋转')}[name]||name;
}
function renderRiverComparison(parent){
 const box=details(parent,'Compare two geometry revisions','并排比选两种几何修订');
 box.id='qa-tool-geometry-comparison';
 box.append(el('p',tr('Both candidates start from this Q100 result with the same flow, roughness and boundary conditions.','两个候选均从本次 Q100 出发，保持相同流量、糙率及边界条件。')));
 const width=field(box,'compare-width','Maximum total width (ft)','断面总宽上限（ft）',1200,'number');
 const preview=el('div');box.append(button('Preview both geometries','预览两种几何',async()=>{
  const p=await api('study-prepare',{id:current.id,revision:current.revision,kind:'river_geometry',maximum_width_ft:Number(width.value)});
  current.pending_study_plan=p.plan;current.pending_study=p.entry;show(p.plan,p.token);
  notify(tr('Both candidate geometries are ready to inspect.','两种候选几何已准备好，可检查后统一确认。'));
 }),preview);
 function show(plan,token){
  width.value=plan.maximum_width_ft;preview.replaceChildren();for(const c of plan.cases){
   const part=details(preview,riverVariantName(c.id)+' ('+c.changes.length+')',riverVariantName(c.id)+' ('+c.changes.length+')');
   table(part,['RS',tr('Rotation °','旋转 °'),tr('Added L / R (ft)','左右增加宽度（ft）')],c.changes.map(r=>[r.rs,r.rotation_deg||0,[r.left_added_ft||0,r.right_added_ft||0].map(n=>n.toFixed(1)).join(' / ')]));
   if(c.unresolved.length)part.append(el('p',c.unresolved.length+tr(' outstanding geometry checks.',' 项几何检查待复核。'),'warning'));
   if(c.banks.length)table(part,['RS',tr('Proposed banks (ft)','候选岸站（ft）'),tr('Confidence','置信度')],c.banks.map(r=>[r.rs,r.banks_ft.map(n=>n.toFixed(1)).join(' / '),r.confidence]));
  }
  const consent=check(preview,'I reviewed both geometries and their bank assumptions','我已核对这两种几何及其岸站假设',false,()=>{});
  preview.append(button('Run both revisions','统一运行两个修订工况',async()=>{
   if(!consent.checked)throw Error(tr('Confirm the displayed candidates first.','请先核对并确认显示的两种候选。'));
   const retry=current.geometry_comparison?.status==='INCOMPLETE'&&current.active_study?.study?.sha256===token;
   await api('study-start',{id:current.id,revision:current.revision,confirmed:true,token,retry});await open(current.id);
  },'primary'));
 }
 width.addEventListener('input',()=>preview.replaceChildren());
 if(current.pending_study_plan?.analysis_kind==='river_geometry_comparison')show(current.pending_study_plan,current.pending_study.sha256);
 const data=current.geometry_comparison;if(!data)return;
 if(data.status==='INCOMPLETE'){box.append(el('p',tr('Some cases are incomplete. Check the last task before retrying.','部分工况未完成，请查看作业详情。'),'warning'));return;}
 const names=['baseline','fixed','rotated'];
 const rows=data.rows;
 table(box,[tr('Case','工况'),tr('Wet sections','湿端断面'),tr('New / cleared ends','新增／消除湿端'),tr('Critical fallbacks','临界水深回退')],names.map(k=>{
  const v=data.totals[k];return [riverVariantName(k),v.wet_sections,v.new_wet_ends+' / '+v.cleared_wet_ends,v.critical_fallbacks+(v.missing_fallbacks?' ('+v.missing_fallbacks+tr(' unknown',' 项未知')+')':'')];}));
 const first=rows.find(r=>names.some(k=>r.variants[k].new_wet.some(Boolean)))||rows.find(r=>names.some(k=>r.variants[k].wet.some(Boolean)))||rows[0];
 const select=field(box,'comparison-station','Inspect a common station','查看同一位置的断面',first.rs,'select',rows.map(r=>[r.rs,'RS '+r.rs,'RS '+r.rs]));
 const panel=el('div');box.append(panel);
 function paint(){
  const selected=rows.find(r=>r.rs===select.value)||first;
  panel.replaceChildren();
  const maps=el('div',undefined,'river-comparison-maps');panel.append(maps);
  const points=rows.flatMap(r=>names.flatMap(k=>r.variants[k].cut));
  const xx=points.map(p=>p[0]),yy=points.map(p=>p[1]),x0=Math.min(...xx),y1=Math.max(...yy);
  const scale=Math.min(296/Math.max(1,Math.max(...xx)-x0),244/Math.max(1,y1-Math.min(...yy)));
  const xy=p=>[12+(p[0]-x0)*scale,14+(y1-p[1])*scale];
  for(const name of names){
   const item=el('div');item.append(el('strong',riverVariantName(name)));maps.append(item);
   const canvas=el('canvas');canvas.width=320;canvas.height=275;canvas.setAttribute('aria-label',riverVariantName(name)+' RS '+selected.rs);item.append(canvas);
   const ctx=canvas.getContext('2d');if(!ctx)continue;
   function line(coords,color,width){ctx.beginPath();for(const [i,p] of coords.entries()){const [x,y]=xy(p);if(i)ctx.lineTo(x,y);else ctx.moveTo(x,y);}ctx.strokeStyle=color;ctx.lineWidth=width;ctx.stroke();}
   line(rows.map(r=>r.variants[name].center),'#167c99',2);
   for(const row of [...rows.filter(r=>r!==selected),selected]){
    const v=row.variants[name];line(v.cut,row===selected?'#3c2583':'#89969d',row===selected?3:1);
    for(const [j,id] of [0,v.cut.length-1].entries())if(v.wet[j]||v.cleared_wet[j]){
     const [x,y]=xy(v.cut[id]);ctx.beginPath();ctx.arc(x,y,row===selected?5:3,0,2*Math.PI);ctx.fillStyle=v.new_wet[j]?'#b4182b':v.cleared_wet[j]?'#00865c':'#b15d00';ctx.fill();}
   }
  }
  panel.append(el('small',tr('North up. Purple = selected section. Red = newly wet end, amber = wet, green = cleared.','北向上。紫色为所选断面，红点为新增湿端，橙点为过水，绿点为已消除湿端。')));
  const fmt=v=>Number.isFinite(v)?v.toFixed(3):'—', pair=v=>v.map(fmt).join(' / ');
  table(panel,[tr('Case','工况'),tr('WSE / Δ (ft)','水位／变化（ft）'),tr('Left / right end (ft)','左右端高程（ft）'),tr('Wet sides','过水侧'),tr('Left / right discharge (%)','左右漫滩占比（%）'),tr('Critical fallback','临界回退')],names.map(name=>{
   const v=selected.variants[name];return [riverVariantName(name),pair([v.stage_ft,v.delta_wse_ft]),pair(v.ends_ft),[v.wet[0]?tr('Left','左'):null,v.wet[1]?tr('Right','右'):null].filter(Boolean).join(' + ')||tr('Dry','均干'),pair(v.ob_percent),v.critical_fallback===null?'—':v.critical_fallback?tr('Yes','是'):tr('No','否')];}));
 }
 select.addEventListener('change',paint);paint();
 if(names.some(k=>data.totals[k].new_wet_ends&&data.totals[k].cleared_wet_ends))box.append(el('p',tr('A revision clears some wet ends while introducing others. Inspect the individual locations before selecting a geometry.','有修订同时消除了原湿端并新增其他湿端，选用前请逐个核对位置。'),'warning'));
 if(data.table){const a=el('a',tr('Download all station comparisons (CSV)','下载逐断面比选表（CSV）'));a.href='file/'+data.table.path;a.download='section_comparison.csv';box.append(a);}
}
