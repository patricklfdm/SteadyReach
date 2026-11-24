'use strict';
function feedbackLink(panel,entry,label){
 const a=el('a',label);a.href='file/'+entry.path.split('/').map(encodeURIComponent).join('/');a.download=entry.path.split('/').pop();panel.append(a,el('br'));
}
function renderFieldResponse(parent,f){
 const panel=el('section');parent.append(panel);panel.append(el('h2',tr('Field review result','现场反馈情景结果')),el('p',f.run_id));
 if(f.assumed)panel.append(el('p',tr('Assumed feedback for workflow testing. Field verification remains open.','假设反馈用于流程验证，现场核实仍待完成。'),'warning'));
 if(f.mode==='event'){
  panel.append(el('p',f.event+' · '+f.date+' · '+f.flow_cfs.toFixed(2)+' cfs'));
  table(panel,[tr('Profile','工况'),tr('Downstream WSE (ft)','下游水位 (ft)')],f.stages.map(p=>[p.profile,p.stage_ft.toFixed(3)]));
  table(panel,[tr('Profile','工况'),tr('Peak RS','峰值断面'),'Δ ft',tr('Over threshold / compared','超阈／比对')],f.responses.map(r=>[r.profile,r.peak_rs,r.delta_ft.toFixed(3),r.affected.length+' / '+f.area.length]));
  const more=details(panel,'Sections affected inside the review area','关注河段受影响的断面');
  for(const r of f.responses)more.append(el('p',r.profile+' · '+r.threshold_ft+' ft · RS '+(r.affected.join(', ')||'—')));
 }else panel.append(el('p','RS '+f.comparison.station+' · '+f.decision+' · '+riverVariantName(f.selected)),el('p',f.condition),el('p',tr('Maximum repeat WSE difference','重算水位最大差值')+' · '+f.repeat_max_delta_ft.toFixed(4)+' ft'));
}
function feedbackCsv(rows){
 const keys=['point_id','event','date','rs','role','stage_ft','datum','flow_cfs','original_source','point_type','basis','uncertainty_ft','reference'];
 const quote=v=>'"'+String(v??'').replaceAll('"','""')+'"';
 return [keys.join(','),...rows.map(r=>keys.map(k=>quote(r[k])).join(','))].join('\r\n');
}
function feedbackPreview(panel,packet,request){
 const s=packet.review;panel.replaceChildren();
 panel.append(el('h3',tr('Saved scenario preview','已保存的情景预览')),el('p',s.assumed?tr('ASSUMED FEEDBACK · conditional trial','假设反馈 · 条件性试算'):tr('Source-based review','依据来源复核'),s.assumed?'warning':'status'));
 if(s.mode==='event'){
  panel.append(el('p',s.event+' · '+s.date+' · '+s.flow_cfs+' cfs'));
  table(panel,[tr('Profile','工况'),tr('Downstream WSE (ft)','下游水位 (ft)')],s.stages.map(v=>[v.profile,v.stage_ft.toFixed(3)]));
  table(panel,['RS',tr('Point type / basis','点类型／依据'),tr('Uncertainty ft','不确定度 ft'),tr('Record','依据')],s.rows.map(r=>[r.rs,r.point_type+' / '+r.basis,r.uncertainty_ft||'—',r.reference||'—']));
  if(s.supporting_record)feedbackLink(panel,s.supporting_record,tr('Open the attached field record','打开已保存的现场记录'));
  panel.append(el('p',tr('Documented / assumed / unresolved records','有记录／假设／待补的点记录数')+' · '+[s.uses.documented.length,s.uses.assumed.length,s.uses.unresolved.length].join(' / ')));
 }else panel.append(el('p','RS '+s.comparison.station+' · '+s.decision+' · '+s.selected+' · '+s.condition));
 if(s.blockers.length){
  const labels={BOUNDARY_LOCATION:tr('Locate the observed boundary at the downstream section.','请将观测边界定位到最下游断面。'),UPSTREAM_EVENT_CONTROL:tr('This batch requires an active downstream control and a supported upstream condition.','此尾水批次需要有效的下游控制和适用的上游条件。'),BOUNDARY_ACCURACY:tr('Confirm downstream point identity, basis and uncertainty.','补充下游点身份、依据和不确定度。'),EVENT_FLOW:tr('Resolve the event discharge.','核实事件流量。'),MIXED_EVENT_ROLES:tr('Separate calibration and holdout events.','区分率定和独立事件。'),BOUNDARY_OBSERVATION:tr('Supply a located downstream stage.','补充下游水位及位置。'),CONFLICTING_CONTROLS:tr('Resolve competing downstream observations.','核对冲突的下游观测。')};
  panel.append(el('p',s.blockers.map(v=>labels[v]||v).join(' '),'warning'));return;
 }
 panel.append(el('p',tr('Confirming starts a separate HEC-RAS project, reports and both packages.','确认后将建立独立 HEC-RAS 子项目，执行计算并生成报告和两种交付包。')),
  button('Confirm and compute this scenario','确认并计算此情景',async()=>{
   const r=await api('field/confirm',{...request,mode:s.mode,event:s.event,date:s.date,token:packet.token,confirmed:true});await open(r.id);
  },'primary'));
}
function renderFieldFeedback(parent){
 const box=details(parent,'Field feedback and tailwater trial','补录现场反馈并试算尾水');box.id='qa-tool-field-feedback';
 const request={id:current.id,revision:current.revision,summary_hash:current.summary.sha256};
 const panel=el('div');box.append(panel);let started=false;
 async function load(){
  panel.replaceChildren(el('p',tr('Reading event and source records…','正在核对事件和原始记录…')));
  try{
   const [data,saved]=await Promise.all([api('field/request',request),api('field/latest',request)]);
   if(!panel.isConnected)return;
   panel.replaceChildren();feedbackLink(panel,data.request,tr('Download the site-specific field request','下载本站现场索资清单'));
   if(!data.rows.length){
    panel.append(el('p',tr('Import located event stages and concurrent flow first. For an offsite gage, document the transfer to the downstream section.','先导入有位置的事件水位及同期流量。异地测站需有到下游边界的水位传递依据。')),
     button('Open field observations','打开实测资料',()=>openGuidanceTool('observations')));return;
   }
   feedbackLink(panel,data.template,tr('Download the prefilled point table (CSV)','下载已预填的测点表（CSV）'));
   const events=[...new Set(data.rows.map(r=>JSON.stringify([r.event,r.date])))];
   const savedEvent=saved.event?.review;
   const eventKey=draftKey('feedback-event/'+request.summary_hash,request.id);
   const preferred=readDraft(eventKey),lastEvent=savedEvent?JSON.stringify([savedEvent.event,savedEvent.date]):null;
   const selected=field(panel,'field-event','Observed event','观测事件',events.includes(preferred)?preferred:events.includes(lastEvent)?lastEvent:events[0],'select',events.map(v=>[v,JSON.parse(v).join(' / '),JSON.parse(v).join(' / ')]));
   const wrap=el('div');panel.append(wrap);
   function edit(){
    wrap.replaceChildren();
    const [event,date]=JSON.parse(selected.value),rows=data.rows.filter(r=>r.event===event&&r.date===date);
    const last=saved.event?.review;const snapshot=last?.event===event&&last.date===date?last:null;
    const values=rows.map(r=>({...r,...snapshot?.rows.find(old=>old.point_id===r.point_id)}));
    table(wrap,['RS',tr('Role','用途'),'WSE ft',tr('Datum','基准')],values.map(r=>[r.rs,r.role,r.stage_ft.toFixed(3),r.datum]));
    const group=field(wrap,'feedback-origin','Feedback basis','反馈性质','unknown','select',[['unknown','Choose…','请选择'],['documented','Documented field record','有现场记录'],['assumed','Assumed for scenario testing','模拟工程反馈／假设']]);
    const point=field(wrap,'feedback-type','Point identity','点身份','unknown','select',[['unknown','Unknown','未知'],['measured','Measured point','实测点'],['interpolated','Interpolated point','插值点']]);
    const scope=field(wrap,'feedback-scope','Apply shared values to','共用值适用范围','all','select',[['all','All points in this event','该事件全部测点'],['boundary','Boundary only','仅边界点'],['other','Non-boundary points','仅非边界点']]);
    const u=field(wrap,'feedback-u','Vertical uncertainty (± ft)','垂直不确定度 (± ft)','','number');
    const ref=field(wrap,'feedback-reference','Field record or assumption','现场记录出处或假设说明');
    const file=field(wrap,'field-source','Supporting record for documented feedback','实测反馈的证明文件','','file');file.accept='.txt,.pdf,.csv,.png,.jpg,.jpeg';
    const csv=field(wrap,'field-return','Or import the edited point table','或导入逐点编辑的反馈表','','file');csv.accept='.csv';
    const key=draftKey('field-feedback/'+request.summary_hash+'/'+selected.value,request.id);
    const inputs=[group,point,scope,u,ref,file,csv];
    const preview=el('div');
    const missingFiles=restoreForm(key,inputs);
    if(missingFiles.length){
     const reminder=el('div');wrap.append(reminder);
     reminder.append(el('p',tr('Reselect draft attachments: ','请重新选择草稿附件：')+missingFiles.join(', '),'warning'),
      button('Continue without the missing attachments','清除待重选的附件',async()=>{
       for(const input of [file,csv])delete input.dataset.reselect;
       rememberForm(key,inputs);reminder.hidden=true;
      }));
    }
    wrap.append(button('Save and preview field feedback','保存并预览现场反馈',async()=>{
     for(const input of [file,csv])if(input.dataset.reselect&&!input.files.length)throw Error(tr('Reselect your attachment or clear the file selection: ','请重新选择附件或清除所选文件：')+JSON.parse(input.dataset.reselect).join(', '));
     const updates=values.map(r=>group.value==='unknown'||(scope.value==='boundary'&&r.role!=='boundary')||(scope.value==='other'&&r.role==='boundary')?r:{...r,basis:group.value,point_type:point.value,uncertainty_ft:u.value,reference:ref.value});
     const payload={...request,mode:'event',event,date,csv:csv.files[0]?await csv.files[0].text():feedbackCsv(updates)};
     if(saved.event?.review?.event===event&&saved.event.review.date===date&&saved.event.review.supporting_record)payload.reuse_document=saved.event.token;
     if(file.files[0]){const f=file.files[0];if(f.size>12000000)throw Error(tr('Maximum 12 MB','最大 12 MB'));
      payload.attachment={name:f.name,data:await new Promise((ok,fail)=>{const reader=new FileReader();reader.onerror=()=>fail(Error('File read failed'));reader.onload=()=>ok(reader.result.split(',')[1]);reader.readAsDataURL(f);})};}
     const p=await api('field/preview',payload);saved.event=p;forgetForm(key,inputs);
     for(const entry of p.review.rows)Object.assign(values.find(v=>v.point_id===entry.point_id),entry);
     feedbackPreview(preview,p,request);notify(tr('Feedback saved. Review the values below.','已保存反馈，请核对下方数值。'));
    }),preview);
    if(snapshot)feedbackPreview(preview,saved.event,request);
    const dirty=()=>preview.replaceChildren(el('p',tr('Save edits to review the updated scenario before computing.','请保存修改并核对新预览后再计算。'),'status'));
    if(readDraft(key))dirty();
    observeForm(key,inputs,dirty);
   }
   async function switchEvent(){
    const selection=selected.value,[event,date]=JSON.parse(selection);writeDraft(eventKey,selection);
    wrap.replaceChildren(el('p',tr('Reading saved feedback…','正在读取已存反馈…')));
    try{
     const state=await api('field/latest',{...request,event,date});
     if(selected.value===selection){saved.event=state.event;edit();}
    }catch(e){if(selected.value===selection)wrap.replaceChildren(el('p',e.message,'warning'),button('Retry','重试',switchEvent));}
   }
   selected.onchange=switchEvent;
   if(events.includes(preferred)&&lastEvent!==preferred)await switchEvent();else edit();
  }catch(e){panel.replaceChildren(el('p',e.message,'warning'),button('Retry field records','重试读取现场资料',load));}
 }
 box.parentElement.addEventListener('toggle',()=>{if(box.parentElement.open&&!started){started=true;void load();}});
 if(box.parentElement.open){started=true;void load();}
}
function fieldGeometryComparison(panel,r,geometry,profile,request){
 const body={...request,station:r.rs,geometry:geometry==='baseline'?'rotated':geometry,profile};
 const output=el('div');
 panel.append(button('Compare overbank paths and record a decision','并排查看漫滩通路并记录决定',async()=>{
  const d=await api('field/compare',body);if(!output.isConnected)return;
  output.replaceChildren();const names=['baseline',d.alternative];
  const maps=el('div',undefined,'section-context-grid');output.append(maps);
  const xy=Object.values(d.variants).flatMap(v=>v.sections.flatMap(s=>s.cut)),xs=xy.map(p=>p[0]),ys=xy.map(p=>p[1]);
  const left=Math.min(...xs),top=Math.max(...ys),k=Math.min(510/Math.max(1,Math.max(...xs)-left),215/Math.max(1,top-Math.min(...ys)));
  const x=v=>10+(v-left)*k,y=v=>12+(top-v)*k;
  for(const name of names){
   const v=d.variants[name],card=el('div');maps.append(card);card.append(el('strong',riverVariantName(name)));
   const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 540 245');svg.setAttribute('aria-label',riverVariantName(name)+' RS '+r.rs);card.append(svg);
   if(d.imagery.status==='READY'){const a=d.imagery.bounds;svgEl(svg,'image',{href:d.imagery.uri,x:x(a[0]),y:y(a[3]),width:(a[2]-a[0])*k,height:(a[3]-a[1])*k,preserveAspectRatio:'none'});}
   const pts=line=>line.map(p=>x(p[0])+','+y(p[1])).join(' ');
   for(const strip of v.strips.filter(s=>s.corners_xy))svgEl(svg,'polygon',{points:pts(strip.corners_xy),fill:strip.at_interpolated_stage?'#39ac88':'#ffa64d','fill-opacity':.35});
   for(const layer of d.layers)for(const road of layer.lines)svgEl(svg,'polyline',{points:pts(road.xy),stroke:'#fff2ad',fill:'none','stroke-width':2});
   for(const cut of v.sections)svgEl(svg,'polyline',{points:pts(cut.cut),stroke:cut.rs===r.rs?'#ff428e':'#58dce6',fill:'none','stroke-width':2.3});
  }
  const variants=d.variants;const ref=variants.baseline.sections;
  table(output,[tr('Geometry','几何'),'RS','WSE ft','Δ ft',tr('L / R flow (%)','左／右分流 (%)')],names.flatMap(n=>variants[n].sections.map(s=>[riverVariantName(n),s.rs,s.wse_ft.toFixed(3),(s.wse_ft-ref.find(b=>b.rs===s.rs).wse_ft).toFixed(3),s.share.map(v=>Number.isFinite(v)?v.toFixed(2):'—').join(' / ')])));
  table(output,[tr('Geometry','几何'),'RS',tr('Side','岸侧'),tr('Terrain route','地形通路'),tr('Road or levee','道路或堤线')],names.flatMap(n=>variants[n].strips.map(s=>[riverVariantName(n),r.rs+' → '+s.neighbor,s.side,s.status,s.crossings.map(v=>v.name||v.layer).join(', ')||'—'])));
  const choice=field(output,'path-decision','Engineering disposition','几何与现场决定','retain_baseline','select',[['retain_baseline','Retain baseline','保留基准'],['use_candidate','Use the displayed candidate in a new edition','在新版本采用所示候选'],['request_survey','Keep baseline pending a crossing survey','暂保留基准，需开口测量'],['review_2d','Keep baseline pending a 2D review','暂保留基准，需二维复核']]);
  const note=field(output,'path-condition','Conditions to include in the report','写入报告的适用条件','','textarea');
  const assumed=check(output,'Simulated engineer feedback for testing','用于测试的模拟工程反馈',false,()=>{});
  const preview=el('div');output.append(button('Save geometry decision and preview','保存几何决定并预览',async()=>{
   const p=await api('field/preview',{...body,mode:'geometry',decision:choice.value,condition:note.value,assumed:assumed.checked});feedbackPreview(preview,p,body);
  }),preview);
  for(const input of [choice,note,assumed])input.addEventListener('input',()=>preview.replaceChildren());
  const prior=(await api('field/latest',request)).geometry;
  if(prior&&prior.review.comparison.station===r.rs&&prior.review.comparison.alternative===d.alternative&&prior.review.comparison.profile===profile){choice.value=prior.review.decision;note.value=prior.review.condition;assumed.checked=prior.review.assumed;feedbackPreview(preview,prior,body);}
 }),output);
}
