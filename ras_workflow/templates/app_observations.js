'use strict';
function observationReason(code){
 const messages={
  NEED_COORDINATES_AND_CRS:['Supply coordinates and their horizontal CRS','补充坐标及水平坐标系'],
  INVALID_COORDINATES:['Check the coordinate order and range','检查坐标顺序和范围'],
  INVALID_COORDINATES_OR_CRS:['Check coordinates and CRS','检查坐标及坐标系'],
  OUTSIDE_SECTION_TOLERANCE:['Point outside the 5 m section match','测点超出断面 5 m 匹配范围'],
  MULTIPLE_NEARBY_SECTIONS:['Multiple nearby sections','有多个邻近断面'],
  VERTICAL_DATUM_MISMATCH:['Verify the vertical datum or supply a documented transformation','核实高程基准或提供有依据的转换'],
  NO_MATCHED_EVENT_RUN:['A calculation for this flood date and flow is needed','需要同场洪水、同流量的试算'],
  NEED_GAGE_ZERO:['Supply the gage zero in the stated datum and unit','补充同单位及基准的水尺零点'],
  NEED_EVENT_DISCHARGE:['Supply a positive measured event discharge','补充该次洪水的实测流量'],
  BOUNDARY_REQUIRES_DOWNSTREAM_OBSERVATION:['A boundary stage must match the downstream end','边界水位须匹配下游末端'],
  EVENT_DISCHARGE_MISMATCH:['Recorded and calculated discharges differ','记录流量与试算流量不符'],
  NEED_MEASUREMENT_KIND:['Choose a supported measurement kind','选择支持的测量类型'],
  NEED_OBSERVATION_ROLE:['Specify the intended use','指定观测用途'],
  NEED_SOURCE:['Provide the source or survey reference','补充观测出处'],
  NEED_ISO_DATE:['Enter YYYY-MM-DD','填写 YYYY-MM-DD 日期'],NEED_EVENT_ID:['Enter an event name','填写事件名'],
  NEED_ELEVATION_AND_UNIT:['Provide a measurement and supported unit','补充测量数值及有效单位'],
  INVALID_VERTICAL_UNCERTAINTY:['Check vertical uncertainty','核对高程不确定度'],
  INVALID_POSITION_UNCERTAINTY:['Check position uncertainty','核对位置不确定度'],
  POSITION_UNCERTAINTY_TOO_LARGE:['Coordinate uncertainty exceeds the matching tolerance','坐标不确定度超出匹配范围'],
  DOWNSTREAM_STAGE_USED_AS_BOUNDARY:['This stage location supplied the trial boundary','该点水位已用作本次边界条件'],
  NO_GEOMETRY:['No usable sections','缺少可用断面']
 };
 return messages[code]?tr(...messages[code]):code;
}
function renderRiverObservations(parent){
 const box=details(parent,'Field observations and event checks','实测资料与洪水事件校核');
 const link=el('a',tr('Download a blank CSV template','下载空白 CSV 模板'));link.href='observation-template.csv';link.download='observations.csv';box.append(link);
 box.append(el('p',tr('Use one row per observation. Keep a separate flood as holdout. A measured downstream stage used as a boundary is shown as an input.','一条观测一行。可保留另一次洪水作独立验证。用于下游边界的实测水位会列为输入。')));
 const file=field(box,'observations-file','Select a local CSV','选择本地 CSV','','file');file.accept='.csv,text/csv';
 const raw=field(box,'observations-text','Or paste the complete CSV, including its header','也可粘贴包含表头的完整 CSV','','textarea');
 file.addEventListener('change',async()=>{try{const selected=file.files[0];if(!selected)return;if(selected.size>2000000)throw Error(tr('Maximum 2 MB','最大 2 MB'));raw.value=await selected.text();notify(tr('CSV ready to check','CSV 已就绪，可检查'));}catch(error){notify(error.message,true);}});
 box.append(button('Check and save observations','核查并保存观测',async()=>{
   await api('river-observations',{id:current.id,revision:current.revision,summary_hash:current.summary.sha256,csv:raw.value});await open(current.id);
   document.getElementById('field-observations').closest('details').open=true;notify(tr('Observations saved. Review the matches and missing evidence.','观测已保存，请查看匹配情况与待补证据。'));
 }));box.id='field-observations';
 const packet=current.observation_review;if(!packet)return;
 const fmt=(v,n=2)=>Number.isFinite(v)?v.toFixed(n):'—';
 const showRows=(rows,target)=>table(target,[tr('Event / date','事件／日期'),tr('Use / type','用途／类型'),tr('Reading / datum','读数／基准'),tr('Located section','断面匹配'),tr('Flow (cfs)','流量（cfs）'),tr('Calculated (ft)','计算（ft）'),tr('Model − observed (ft)','计算减实测（ft）'),tr('Evidence / checks','出处／核查')],rows.map(r=>{
   let reading=(r.raw_elevation??'—')+' '+(r.raw_unit||'')+' · '+(r.observed_datum||'—');
   if(r.kind==='gage_height'&&Number.isFinite(r.observed_ft))reading+=' → '+fmt(r.observed_ft)+' ft';
   if(Number.isFinite(r.uncertainty_ft))reading+=' (±'+fmt(r.uncertainty_ft)+' ft)';
   return [r.event+' / '+r.date,r.role+' / '+r.kind,reading,r.location?'RS '+r.location.rs+' · '+fmt(r.location.distance_m,1)+' m':'—',fmt(r.flow_cfs),fmt(r.model_ft,3),r.role==='boundary'?tr('Boundary input','边界输入'):fmt(r.residual_ft,3),[r.source,...r.issues.map(observationReason)].filter(Boolean).join(' · ')];
 }));
 showRows(packet.rows,box);
 const action=el('div');box.append(action);
 function preview(plan,token){
   action.replaceChildren();const e=plan.event;
   action.append(el('p',e.event+' · '+e.date+' · '+fmt(e.flow_cfs)+' cfs · '+(Number.isFinite(e.downstream_ft)?tr('Measured downstream stage ','实测下游水位 ')+fmt(e.downstream_ft)+' ft':tr('Baseline boundary method','沿用原边界方法'))));
   const consent=check(action,'I reviewed this event and its boundary','我已核对此次洪水与边界',false,()=>{});
   action.append(button('Compute this observed event','计算该实测事件',async()=>{
     if(!consent.checked)throw Error(tr('Confirm the displayed event first','请先确认显示的事件'));
     await api('study-start',{id:current.id,revision:current.revision,confirmed:true,token});await open(current.id);
   }));
 }
 const used=new Set();
 for(const row of packet.rows.filter(r=>r.event_eligible)){
   const key=JSON.stringify([row.event,row.date]);if(used.has(key))continue;used.add(key);
   const name=row.event+' · '+row.date;
   box.insertBefore(button('Preview event '+name,'预览事件 '+name,async()=>{
    const p=await api('study-prepare',{id:current.id,revision:current.revision,kind:'observed_event',event:row.event,date:row.date});preview(p.plan,p.token);
   }),action);
 }
 if(current.pending_study_plan?.analysis_kind==='river_observed_event')preview(current.pending_study_plan,current.pending_study.sha256);
 for(const result of current.observed_events||[]){const group=details(box,'Computed event '+result.event.date,'已计算事件 '+result.event.date);showRows(result.rows,group);}
}
