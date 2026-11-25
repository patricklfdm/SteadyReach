'use strict';
const guidanceRequests=new Map();
function assessmentFact(row){
 const f=row.facts||{},decimal=(v,d)=>Number.isFinite(v)?v.toFixed(d):'—';
 if(row.code==='GEOMETRY_FLOW_PATH')return 'RS '+f.station+' · '+(f.side==='L'?tr('left','左侧'):tr('right','右侧'))+' '+decimal(f.baseline_share_pct,2)+'% → '+decimal(f.alternative_share_pct,2)+'% · '+tr('new end depth ','新过水端深 ')+decimal(f.end_excess_ft,3)+' ft';
 if(row.code==='BOUNDARY_INFLUENCE')return f.profile+' · '+sensitivityParameterLabel(f.parameter)+' · RS '+f.station+' · Δ '+decimal(f.delta_ft,3)+' ft · '+f.affected+'/'+f.compared+tr(' sections above ',' 条断面的绝对差超过 ')+f.threshold_ft+' ft';
 if(row.code==='FIELD_RESIDUAL' && f.missing_uncertainty!==undefined)return 'RS '+f.station+' · Δ '+decimal(f.peak_ft,3)+' ft · '+tr('Missing accuracy','缺测量精度')+' '+f.missing_uncertainty+' · '+tr('Outside accuracy','超出测量精度')+' '+f.outside_uncertainty;
 if(f.peak_ft!==undefined)return 'RS '+f.station+' · Δ '+decimal(f.peak_ft,3)+' ft';
 if(f.screened!==undefined)return tr('Screened observations','已初筛的测点')+' · '+f.screened;
 if(f.stations)return 'RS '+f.stations.join(', ');
 if(f.missing)return f.missing.join(', ');
 if(f.error)return f.error;
 if(f.errors)return f.errors.join(' · ');
 if(f.codes)return f.codes.join(' · ');
 if(f.records!==undefined)return f.records+tr(' diagnostic records',' 条诊断记录');
 if(f.status)return assessmentState(f.status);
 return '';
}
function assessmentState(value){
 const labels={VERIFIED_MAPPED:['Both mapped packages verified','两个制图包已核验'],VERIFIED_NATIVE_ONLY:['Native files only','仅有原生文件'],STALE:['Refresh required','需更新'],INCOMPLETE:['Incomplete','未完整生成'],UNVERIFIED:['Unverified','尚未核验'],EDITION_MISMATCH:['Edition mismatch','版本不符'],NO_CURRENT_SUBMISSION:['No bound QA submission','无绑定本次结果的 QA 提交'],REVIEW_IN_PROGRESS:['Review in progress','复核中'],DIFFERENT_ISSUE_INVENTORY:['Reviewed issue list differs','复核问题清单与当前不同'],CLOSED_WITH_RECORDED_CONDITIONS:['Closed with recorded conditions','已记录条件并闭合'],REVIEW_REQUIRED:['Review required','待复核'],NOT_TESTED:['No verified trial','尚无已核验的试算'],NOT_CONVERGED:['Unconverged','未收敛'],PENDING:['Pending','待复核'],NOT_PERFORMED:['Not performed','尚未执行']};
 return labels[value]?tr(...labels[value]):value||'—';
}
function showFieldSearch(box,a){
 const panel=details(box,'Find records and plan fieldwork','查资料与最小补测清单');
 panel.id='qa-tool-field-search';
 const result=el('div');let pending=false;
 async function load(refresh=false){
  if(pending)return;pending=true;result.setAttribute('aria-busy','true');
  result.replaceChildren(el('p',tr('Searching local records and official USGS sources…','正在核对本地资料并查询 USGS 官方来源…')));
  try{
   const packet=await api('qa-field-search',{id:current.id,summary_hash:a.summary.sha256,refresh});
   result.replaceChildren(el('p',tr('Evidence review prepared','本次资料复核生成时间')+' · '+packet.created_utc+' · '+tr(packet.limitations.en,packet.limitations.zh)));
   for(const r of packet.field_requests)result.append(el('p','RS '+r.rs+' · '+r.latitude+', '+r.longitude+' · '+tr(r.need.en,r.need.zh)+' '+tr(r.decision.en,r.decision.zh)));
   if(packet.boundary_evidence?.length){
    const b=details(result,'Can this rating supply the boundary?','这条评级曲线能否用作边界？');
    const reasons={FLOW_OUTSIDE_RATING:tr('Flow outside rating','流量超出评级范围'),AMBIGUOUS_STAGE:tr('Stage bracket unavailable','水位区间不明确'),CHECK_GAGE_ZERO:tr('Verify zero and datum','核实零点与基准'),CONFLICTING_DATUM_METADATA:tr('Station metadata disagree on datum','测站资料对高程基准的记载不同'),BOUNDARY_TRANSFER_REQUIRED:tr('Need gage-to-boundary transfer','需测站到边界的水位传递依据'),CONFIRM_RATING_AND_ZERO_DATE:tr('Check dates of rating, shifts and zero','核实评级、修正值和零点适用期'),NEED_BOUNDARY_UNCERTAINTY:tr('Need boundary uncertainty','需边界不确定度')};
    for(const r of packet.boundary_evidence){
     b.append(el('strong',r.station+' · '+r.profile+' · '+r.flow_cfs+' cfs'),el('p',r.range_cfs.join('–')+' cfs · '+r.distance_m+tr(' m to downstream boundary',' m 至下游边界')+' · '+(r.rating_start??'—')+' / '+(r.rating_end??tr('end unreported','未注明终止日'))));
     if(r.station_wse_bracket_ft)b.append(el('p',tr('At the gage only, tabulated bracket','仅测站处的查表区间')+' · '+r.station_wse_bracket_ft.join('–')+' ft '+r.station_datum));
     b.append(el('p',r.issues.map(i=>reasons[i]||i).join(' · ')));
     if(r.historical_dates_outside.length)b.append(el('p',tr('Peak dates outside this rating period','评级期以外的历史洪峰日期')+' · '+r.historical_dates_outside.join(', ')));
    }
   }
   if(packet.worksheet){const link=el('a',tr('Open observation candidate CSV','打开观测候选 CSV'));link.href='file/'+packet.worksheet.path.split('/').map(encodeURIComponent).join('/');link.download='Observation_candidates.csv';result.append(link,
    el('p',tr('Check gage zero, date, simultaneity and uncertainty, then import the reviewed rows under Field observations.','核实水尺零点、同期性、日期和误差后，在实测资料面板导入已核对的行。')),button('Open field observations','打开实测资料',()=>openGuidanceTool('observations')));}
   const groups={gage:['Streamgages','河道测站'],gage_history:['Gage datum and station history','水尺基准与站点历史'],rating:['Stage–discharge ratings','水位流量关系'],peak:['Annual peak records','历史洪峰'],catalog:['Public survey records','公开测量目录'],linear_context:['Road or levee context','附近道路或堤线'],local_document:['Project documents','项目文件'],screened_observation:['Screened field records','已初筛的观测']};
   for(const [kind,names] of Object.entries(groups)){
    const rows=packet.candidates.filter(r=>r.kind===kind);if(!rows.length)continue;
    const sub=details(result,names[0]+' ('+rows.length+')',names[1]+'（'+rows.length+'）');
    if(kind==='gage_history')sub.append(el('p',tr('Check that the gage zero and location apply on the observation date.','请核对观测当日适用的水尺零点和测站位置。')));
    for(const r of rows){
     const line=[r.name,r.station,r.date,r.parameter,r.value,r.unit,r.qualifier,r.rs?'RS '+r.rs:null,r.vertical_datum,
      r.distance_to_section_m!=null?tr('Section distance ','距断面 ')+r.distance_to_section_m+' m':null,
      r.distance_to_boundary_m!=null?tr('Boundary distance ','距边界 ')+r.distance_to_boundary_m+' m':null,
      r.datum_matches===false?tr('Check vertical datum','需核对高程基准'):null,r.position_accuracy,
      r.min_cfs!=null?r.min_cfs+'–'+r.max_cfs+' cfs':null,r.profile_in_range?Object.entries(r.profile_in_range).map(([p,v])=>p+' '+(v?tr('inside range','在曲线流量范围内'):tr('outside range','超出曲线流量范围'))).join(', '):null,...(r.validity||[]),...(r.issues||[])].filter(v=>v!=null&&v!=='');
     const p=el('p',line.join(' · '));sub.append(p);
     if(r.statement)p.append(' · ',r.statement);
     if(r.landing||r.url){const link=el('a',tr('Official record','官方记录'));link.href=r.landing||r.url;link.target='_blank';link.rel='noopener';p.append(' · ',link);}
    }
   }
   const attempts=details(result,'Search coverage and failures','查询覆盖与失败记录');
   table(attempts,[tr('Source','来源'),tr('Outcome','状态'),tr('Details','详情')],packet.searches.map(r=>[r.kind,r.status,r.error||[r.count,r.retrieval==='ARCHIVED'?tr('Verified local copy','已校验本机原件'):r.retrieval==='FETCHED'?tr('Downloaded','本次下载'):'',r.retrieved_utc].filter(v=>v!=null&&v!=='').join(' · ')]));
  }catch(e){result.replaceChildren(el('p',e.message,'warning'));}
  finally{pending=false;result.removeAttribute('aria-busy');}
 }
 panel.append(button('Refresh official sources','重新查询官方资料',()=>load(true)),result);
 panel.parentElement.addEventListener('toggle',()=>{if(panel.parentElement.open&&!result.hasChildNodes())void load();});
 if(panel.parentElement.open)void load();
}
async function openInvertRequest(panel){
 const id=current.id,revision=current.revision,summary_hash=current.summary.sha256;
 const v=await api('invert-request',{id,summary_hash});
 if(!panel.isConnected||current.id!==id)return;
 panel.replaceChildren(el('p',tr('Fill the measured inside-bottom elevations, datum and source. Keep the group and edition identifiers. Attach the survey record with the returned CSV.','填写实测内底高程、高程基准和来源，保留孔组与版本标识，导回时附上测量原件。')));
 table(panel,[tr('Group','孔组'),tr('End','位置'),tr('Prior (ft)','原值（ft）'),tr('Model datum','模型高程基准')],v.rows.map(r=>[r.opening_group,r.end==='inlet'?tr('Inlet','进口'):tr('Outlet','出口'),r.prior_ft??'—',r.datum||'—']));
 panel.append(button('Download invert survey worksheet','下载涵底补测表',()=>{
  const url=URL.createObjectURL(new Blob(['\ufeff'+v.csv],{type:'text/csv;charset=utf-8'})),a=el('a');a.href=url;a.download='invert_'+v.run+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  notify(tr('Worksheet exported. You can pause this review until records arrive.','补测表已导出，可暂停复核等待回传。'));
 }),button('Pause until survey returns','暂停并等待补测',async()=>{
  await api('iteration-choice',{id,revision,summary_hash,previous:current.iteration_choice?.token||null,choice:'wait'});
  await open(id);notify(tr('Waiting for survey records.','已保存等待补测状态。'));
 }),button('Import returned survey in a new revision','新建修订版并导回补测表',async()=>{
  const child=await api('revision',{id,revision,confirmed:true});await open(child.id);await openModelTool('site-file-import');
  notify(tr('Choose the returned worksheet and its survey source, then save and extract.','请选择回传表和测量原件，然后保存并解析。'));
 }));
}

function purposeAction(parent,row){
 const a=row.action;if(!a)return;
 const tool=a.tool==='revision'&&current.native_review?'native':a.tool;
 if(tool==='invert-request'&&!current.native_review){
  const out=el('div');out.setAttribute('aria-live','polite');
  parent.append(button('Request inlet and outlet elevations','索取各组进出口涵底高程',()=>openInvertRequest(out)),out);return;
 }
 const labels={atlas:['Inspect computed section','查看计算断面'],revision:['Revise inputs and conditions','修订输入和用途条件'],native:['Check this run’s native output','核对此次原生输出'],observations:['Check observed event','检查实测事件'],comparison:['Compare editions','比较两版'], 'field-feedback':['Request surveyed channel geometry','索取河槽测量资料']};
 Object.assign(labels,{qa:['Review hydraulic checks','查看水力检查'],coverage:['Review section coverage','复核断面覆盖'],delivery:['Inspect delivery evidence','检查交付证据'],sensitivity:['Review sensitivity','复核敏感性']});
 let target=tool==='invert-request'?'native':tool;
 if(target==='comparison'&&!current.comparison)target=current.native_review?'native':'revision';
 if(target==='field-feedback'&&current.native_review)target='native';
 const stations=a.stations||[];
 const station=stations.length?field(parent,'qa-wet-'+a.profile,'Wet cross section','过水端点断面',String(stations[0]),'select',stations.map(s=>[String(s),'RS '+s,'RS '+s])):null;
 parent.append(button(...(labels[target]||labels.revision),()=>{
  openGuidanceTool(target);
  if(station)document.getElementById('qa-tool-atlas').dispatchEvent(new CustomEvent('steadyreach-inspect-section',{detail:{profile:a.profile,rs:station.value}}));
 }));
}

function renderFieldReturn(parent){
 if(current.native_review||!current.summary)return;
 const box=details(parent,'Import a field return and compare changes','导回补测并核对变化');
 box.id='qa-tool-return';
 const mode=field(box,'return-mode','Returned evidence','回传内容','geometry','select',[
  ['geometry','Elevations and surveyed profiles','涵底、道路、河床剖面或下游边界水位'],
  ...(current.model_type==='river'?[['observation','Independent event stage','独立事件实测水位']]:[])]);
 box.append(el('p',tr('Keep unused rows blank. For a surveyed profile, enter elevations at the listed stations. Reported values require the original record.','无新资料的行留空。实测剖面按表内站距顺序填写高程。填报实测值时请附原始记录。')));
 const identity={id:current.id,summary_hash:current.summary.sha256};
 box.append(button('Download field-return worksheet','下载本版补测表',async()=>{
  let csv;
  if(mode.value==='observation')csv='event,date,role,kind,x,y,horizontal_crs,elevation,unit,vertical_datum,gage_zero,flow,flow_unit,vertical_uncertainty,horizontal_uncertainty_m,source,profile\r\n';
  else csv=(await api('return-request',identity)).csv;
  const a=el('a'),url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'}));
  a.href=url;a.download='Field_return_'+mode.value+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }));
 function picker(id,en,zh,accept){
  const label=el('label',tr(en,zh)),input=el('input');input.id=id;input.type='file';input.accept=accept;label.append(input);box.append(label);return input;
 }
 const csv=picker('return-csv','Returned CSV','回传 CSV','.csv'),doc=picker('return-record','Field original','测量原件','.pdf,.txt,.csv,.json,.jpg,.jpeg,.png');
 const output=el('section');output.setAttribute('aria-live','polite');let preview=null;
 const invalidate=()=>{preview=null;output.replaceChildren();};
 for(const f of [mode,csv,doc])f.addEventListener('change',invalidate);
 box.append(button('Preview returned values','预览回传数值',async()=>{
  invalidate();
  if(!csv.files[0]||csv.files[0].size>2000000)throw Error(tr('Choose a CSV up to 2 MB.','请选择 2 MB 以内的 CSV。'));
  const f=doc.files.length?(await encodeFiles(doc.files))[0]:null;
  const body={...identity,mode:mode.value,csv:await csv.files[0].text(),document:f?{name:f.name,data:f.content}:null};
  const view=await api('return-preview',body);preview={body,token:view.token};
  output.append(el('p',tr('Source run','来源运行')+' · '+view.run));
  table(output,[tr('Location or event','位置或事件'),tr('Previous','原值'),tr('Returned','回传值'),tr('Unit and datum','单位和基准'),tr('Basis','依据')],
    view.rows.map(r=>[r.location,JSON.stringify(r.before)??'—',JSON.stringify(r.after),r.unit+' '+r.datum,r.classification+' · '+r.source]));
  for(const r of view.rows.filter(r=>'uncertainty_ft' in r)){
   const unknown=tr('unreported','未说明');
   output.append(el('p',r.location+' · '+tr('Measurement uncertainty (ft)','测量不确定度（ft）')+' · '+(r.prior_uncertainty_ft??unknown)+' → '+(r.uncertainty_ft??unknown)));
  }
  if(view.other_fields.length)output.append(el('p',tr('Other values retained','沿用原值的其他位置')+' · '+view.other_fields.join(', ')));
  output.append(button('Confirm return and open revision','确认回传并打开修订版',async()=>{
   if(!preview)throw Error(tr('Preview current selections again.','请重新预览当前文件。'));
   const child=await api('return-apply',{...preview.body,token:preview.token,confirmed:true});await open(child.id);
   notify(tr('Return saved. Review the complete inputs before starting HEC-RAS.','回传已保存。核对本版完整输入后可启动 HEC-RAS。'));
  },'primary'));
 }),output);
}
function priorityRows(assessment,comparison){
 const rows=assessment.purpose_decision?.rows||[],review=comparison?.review,items=[];
 const seen=new Set();
 function add(key,en,zh,target,action){
  if(seen.has(key))return;
  seen.add(key);items.push({en,zh,action:action||{tool:target,stations:[]}});
 }
 const errors=(assessment.findings||[]).filter(f=>['OUTPUT_CONSISTENCY','EVIDENCE_GAPS','WARNING_COVERAGE'].includes(f.code));
 for(const f of errors)add(f.code,f.reason.en,f.reason.zh,f.target);
 if(review?.flags?.includes('CHECK_WATER_LEVEL_CHANGE')&&review.maximum_at_verified_center){
  const v=review.maximum_at_verified_center,delta=Number(v.change).toFixed(3);
  let en=v.profile+' · RS '+v.station+' · signed stage change '+delta+' ft.',zh=v.profile+' · RS '+v.station+' · 水位变化 '+delta+' ft。';
  const split=(review.investigation||[]).find(r=>r.kind==='overbank_share'||r.en.includes('overbank share'));
  if(split){en+=' '+split.en;zh+=' '+split.zh;}
  add('revision-change',en,zh,'comparison');
 }
 for(const state of ['exceeded','missing']){
  for(const row of rows.filter(r=>r.state===state&&r.action)){
   const key=row.action.tool;
   add(key,row.en,row.zh,key,row.action);
  }
 }
 for(const f of assessment.next_actions||[])if(f.target&&f.reason)add(f.target,f.reason.en,f.reason.zh,f.target);
 return items;
}
function showResultAssessment(overview,a,box=overview){
 const label=s=>tr(s.en,s.zh),ordered=a.next_actions||a.findings,primary=ordered[0];
 overview.append(el('h2',tr('Delivery assessment','结果交付评估')+' · L'+a.level+' · '+label(a.title)));
 if(a.purpose_decision){
  const d=a.purpose_decision, panel=el('section',undefined,'card');overview.append(panel);
  panel.append(el('h3',label(d)),el('p',tr(d.note_en,d.note_zh)));
  const priorities=priorityRows(a,current.comparison).slice(0,3);
  if(priorities.length){
   const first=el('section');first.id='result-priorities';panel.append(first);
   first.append(el('h3',tr('What should I review first?','现在先处理什么？')));
   for(const row of priorities){const card=el('div');first.append(card);card.append(el('p',label(row)));purposeAction(card,row);}
  }
  const all=details(panel,'All project acceptance conditions','查看全部用途条件');
  for(const row of d.rows){all.append(el('p',label(row),row.state==='met'?'muted':'warning'));if(!priorities.some(p=>p.action===row.action))purposeAction(all,row);}
  if(current.model_type!=='river')for(const p of current.results?.metrics||[]){
   if(!Number.isFinite(p.metrics?.roadway_flow_software_cfs))panel.append(el('p',p.profile_id+' · '+tr('Native roadway discharge is unknown.','原生路面越流量未知。'),'warning'),
    button('Inspect native roadway discharge','核对原生路面流量',()=>openGuidanceTool('native')));
  }
 }
 if(!current.native_review&&a.run_id)overview.append(button('Compare and import returned field records','补测回来了，核对并导入',()=>openGuidanceTool('return')));
 if(a.use_guide){
  const panel=el('section',undefined,'card');overview.append(panel);
  panel.append(el('h3',tr('What can I use this run for?','这次计算可以用到什么程度？')),
   el('strong',tr('Use now','当前可用')),el('p',label(a.use_guide.allowed)),
   el('strong',tr('Hold for review','暂缓用途')),el('p',label(a.use_guide.deferred)));
  const limits=(a.findings||[]).filter(row=>row.ceiling===a.level);
  if(limits.length){
   const reason=details(panel,'Why this level? ('+limits.length+')','为什么是这个等级？（'+limits.length+' 项）');
   for(const row of limits)reason.append(el('p',label(row.reason)));
  }
 }
 function action(parent,row){
  const f=row.facts||{};
  parent.append(el('p',(row.scope==='CANDIDATE'?tr('Unadopted alternative · ','未采用方案 · '):'')+label(row.reason)),el('p',assessmentFact(row),'muted'));
  if(row.code==='FLOW_SPLIT_COVERAGE'){
   parent.append(el('p',tr('For the same profile, compare total discharge with the culvert, road and bypass entries in HEC-RAS. A blank road entry leaves overtopping unresolved.','对同一工况，逐项对照 HEC-RAS 的总流量、涵孔流量、路面与绕流流量。路面栏空白时，是否漫顶仍待核实。')),
    button('Inspect native structure output','查看原生结构输出',()=>openGuidanceTool('native')));
  }
  if(row.code==='FIELD_RESIDUAL'&&f.observations?.length){
   const detailsBox=details(parent,'Independent observations needing field records','需补现场记录的独立事件测点');
   table(detailsBox,[tr('Event / date','事件／日期'),'RS',tr('Residual (ft)','偏差（ft）'),tr('Survey uncertainty (ft)','实测不确定度（ft）'),tr('Source','来源')],f.observations.map(o=>[o.event+' / '+o.date,o.location?.rs??'—',o.residual_ft.toFixed(3),o.uncertainty_ft>0?o.uncertainty_ft:tr('Request survey record','待补联测或精度记录'),o.source||'—']));
  }
  if(row.code==='FIELD_RESIDUAL'||row.code==='BOUNDARY_INFLUENCE')parent.append(button('Add field feedback or export a request','补录现场反馈或导出索资清单',()=>openGuidanceTool('field-feedback')));
  const toolLabels={'field-search':['Find field records','查找实测资料'],observations:['Compare observed levels','对比实测水位'],qa:['Inspect warnings','查看警告'],floodplain:['Inspect overbank flow','检查漫滩流量'],delivery:['Check delivery files','检查交付文件']};
  parent.append(button(...(toolLabels[row.target]||['Open related tool','打开对应工具']),()=>{
   openGuidanceTool(row.target);
   if(row.target==='floodplain'&&f.station)document.getElementById('qa-tool-floodplain')?.dispatchEvent(new CustomEvent('steadyreach-inspect-floodplain',{detail:{rs:f.station,geometry:f.case}}));
  }));
 }
 renderIterationChoices(overview,a,primary);
 if(primary&&!a.purpose_decision){const first=el('div');overview.append(first);action(first,primary);}
 if(a.event_tailwaters?.length){
  const panel=details(box,'Measured tailwater by observed event','按实测事件核对尾水');
  table(panel,[tr('Event / date','事件／日期'),'RS','cfs',tr('Datum','基准'),tr('Observed interval (ft)','观测区间（ft）')],a.event_tailwaters.map(r=>[r.event+' / '+r.date,r.rs,r.flow_cfs,r.datum,r.interval_ft?.map(v=>v.toFixed(3)).join('–')??tr('Need verified event record and uncertainty','待补匹配事件资料与测量精度')]));
  panel.append(el('p',tr('Intervals use the imported measurement uncertainty for the named event. Review the source before using an interval for sensitivity testing.','区间按该场事件导入的观测不确定度计算，作为敏感性试算依据前请核对原件。')));
 }
 if(a.delivery){
  const d=a.diagnostics,counts=a.delivery.files;
  overview.append(el('p',tr('Delivery files','交付文件')+' · '+assessmentState(a.delivery.status)+(counts?' · Minimal '+counts.minimal+' / Complete '+counts.complete:''),
   'status'),el('p',tr('Native messages','原生信息')+' '+(d.native_messages??'—')+' · '+tr('Combined diagnostic records','综合诊断记录')+' '+(d.records??'—')+' · QA '+assessmentState(a.qa.status)));
 }
 if(ordered.length>1){const more=details(box,'Next actions in priority order ('+(ordered.length-1)+')','其余事项（按优先顺序，共 '+(ordered.length-1)+' 项）');for(const r of ordered.slice(1))action(more,r);}
 if(a.candidate_findings?.length&&!ordered.some(row=>row.scope==='CANDIDATE')){
  const candidates=details(box,tr('Unadopted geometry alternatives','未采用的几何候选'), '未采用的几何候选');
  for(const row of a.candidate_findings)action(candidates,row);
 }
 if(a.area&&current.model_type==='river'){
  const panel=details(box,'Engineering area of interest','工程关注河段');
  panel.append(el('p',tr('Whole adopted edition','采用版全河段')+' · L'+a.level+' | '+tr('Area of interest','关注河段')+' · RS '+a.area.selected[0]+'–'+a.area.selected.at(-1)+' · L'+a.area.level),
   el('p',tr('The area grade restricts boundary influence to these stations and retains the other whole-model checks.','关注河段按选定断面评估边界影响，其他检查沿用全模型的结果。')));
  const options=a.area.stations.map(rs=>[rs,'RS '+rs,'RS '+rs]);
  const up=field(panel,'assessment-area-us','Upstream end','关注河段上端',a.area.selected[0],'select',options);
  const down=field(panel,'assessment-area-ds','Downstream end','关注河段下端',a.area.selected.at(-1),'select',options);
  panel.append(button('Apply review limits','采用关注范围',async()=>{
   await api('qa-assessment-area',{id:current.id,summary_hash:a.summary.sha256,upstream:up.value,downstream:down.value});
   await open(current.id);
  }));
  const decimal=v=>Number.isFinite(v)?v.toFixed(3):'—';
  if(a.boundary_cases.length)table(panel,[tr('Case','工况'),tr('Boundary RS / Δ ft','边界 RS／水位差 ft'),tr('Area peak RS / Δ ft','关注河段峰值 RS／水位差 ft'),tr('Affected / compared in area','关注河段超阈／比对数')],
   a.boundary_cases.map(c=>[c.profile+' / '+c.case,c.boundary_rs+' / '+decimal(c.boundary_delta_ft),(c.area.station??'—')+' / '+decimal(c.area.delta_ft),c.area.affected+' / '+c.area.compared]));
 }
 if(a.run_id&&!current.native_review){const actions=el('div',undefined,'actions');box.append(actions);
  if(current.model_type==='river')actions.append(button('Review checks in one batch','集中核对本版试算',()=>{
   openGuidanceTool('check-batch');
   document.getElementById('qa-tool-check-batch')?.dispatchEvent(new CustomEvent('steadyreach-recommend-checks',{detail:a.recommended_checks}));
  }));
  actions.append(button('Prepare QA revision suggestions','根据 QA 创建修订建议',prepareQaRevision),button('Open editable revision tool','打开独立修订入口',()=>openGuidanceTool('revision')));}
 if(a.run_id&&current.model_type==='river')showFieldSearch(box,a);
 const scope=details(box,'Grading scope and evidence','分级范围与核验依据');
 for(let i=0;i<a.levels.length;i++)scope.append(el('p','L'+i+' · '+label(a.levels[i])));
 scope.append(el('p',tr('Grades describe the permitted handoff. Engineering approval and visual map inspection remain separate. Section counts exclude manifest files.','等级描述本版可交付的用途。工程签发和地图目视验收单列判断。文件数不含清单自身。')));
 if(a.run_id){
  const output=el('p');
  box.append(button('Save assessment summary (.txt)','保存评估摘要（.txt）',async()=>{
   const result=await api('qa-assessment-save',{id:current.id,summary_hash:a.summary.sha256,assessment_hash:a.evidence_hash,language:lang});
   const link=el('a',tr('Open saved summary','打开已保存摘要'));
   link.href='file/'+result.file.path.split('/').map(encodeURIComponent).join('/');
   link.target='_blank';link.rel='noopener';output.replaceChildren(link,el('span',' · '+result.file.path));
  }),output);
  scope.append(el('p','Run '+a.run_id+' · '+a.profiles.join(', ')+' · '+a.input_adequacy),
  el('p',tr('Map visual review recorded in the delivery receipt','交付回执记录的地图目视验收')+' · '+assessmentState(a.delivery.visual_review)));
  if(a.boundary_cases.length)table(scope,[tr('Parameter / case','参数／工况'),'RS','Δ WSE (ft)',tr('Affected / compared','受影响／已比对')],a.boundary_cases.map(c=>[sensitivityParameterLabel(c.parameter)+' / '+c.profile+' / '+c.case,c.station,c.delta_ft.toFixed(3),c.affected+' / '+c.compared]));
  const refs=details(scope,'Source files ('+a.sources.length+')','来源文件（'+a.sources.length+'）');
  for(const ref of a.sources)refs.append(el('p',ref.path+' · '+ref.sha256,'muted'));}
}
function openGuidanceTool(key){
 const node=document.getElementById(key==='observations'?'field-observations':'qa-tool-'+key)||document.getElementById('qa-tool-qa');
 if(!node)throw Error(tr('Reopen this result to load the review tool.','请重新打开结果以加载复核工具。'));
 const panel=node.closest('[role="tabpanel"]');if(panel?.hidden)panel.dispatchEvent(new CustomEvent('steadyreach-show-panel'));
 for(let p=node;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;
 node.scrollIntoView({block:'start',behavior:'smooth'});
 node.setAttribute('tabindex','-1');node.focus({preventScroll:true});
 notify(tr('Review tool opened. No input changed and no calculation started.','已展开相应复核工具；未修改输入、未启动计算。'));
}
function renderGuidance(parent,reviewPage=parent){
 const assessment=el('section',undefined,'result-assessment');parent.append(assessment);
 const box=details(reviewPage,'Diagnostic priorities by location','按位置查看诊断优先项');
 const secondary=el('section');reviewPage.append(secondary);
 const content=el('div');box.append(content);
 const id=current.id,hash=current.summary.sha256,edition=current.revision;
 async function load(){
  assessment.setAttribute('aria-live','polite');
  assessment.replaceChildren(el('p',tr('Assessing native results, warning coverage and both delivery packages…','正在评估原生结果、警告覆盖及两个交付包…'),'status'));
  content.replaceChildren(el('p',tr('Checking result evidence and completed studies…','正在核对结果证据与已完成试算…'),'status'));
  content.setAttribute('aria-busy','true');
  const key=id+'|'+hash+'|'+current.revision;
  try{
   let request=guidanceRequests.get(key);
   if(!request){request=api('qa-guidance',{id,summary_hash:hash,include_assessment:true});guidanceRequests.set(key,request);}
   const data=await request;
   if(!content.isConnected||current?.id!==id||current.summary?.sha256!==hash||current.revision!==edition)return;
   assessment.replaceChildren();
   secondary.replaceChildren();if(data.assessment)showResultAssessment(assessment,data.assessment,secondary);
   content.replaceChildren();
   if(data.assessment?.level===0){content.append(el('p',tr('Reopen this result and restore the displayed evidence.','请重新打开本次结果，按上方提示恢复证据。')));return;}
   content.append(el('p',tr('Suggested work order, not a risk score. Opening a tool does not accept a change or start the solver.','以下为建议处理顺序，不是风险评分。打开工具不代表接受修改，也不会启动求解器。')),
    el('p',(data.issue_count??'—')+tr(' diagnostic records · ',' 条诊断记录 · ')+data.verified_study_count+tr(' authenticated studies for this calculation.',' 项已核验且属于本次计算的试算。'),'status'));
   if(data.operator_actions){
    const log=data.operator_actions,counts=log.counts;
    const panel=details(content,'Recorded operations for this project edition','本项目版本的实际操作记录');
    panel.append(el('p',log.recorded_requests+tr(' successful workflow requests. Background tasks, reads and polling are excluded.',' 次成功操作请求。后台任务、读取和轮询均不计入。')));
    if(data.operator_lineage?.editions.length>1){
     const history=data.operator_lineage;
     panel.append(el('p',tr('This branch, including ancestor activity before each revision: ','本分支及各祖先版本在派生前的记录合计：')+history.recorded_requests+tr(' successful requests. ',' 次成功请求。')+(history.complete?'':tr('Earlier history is partial.','早期操作历史不完整。'))));
    }
    if(log.coverage!=='FROM_CREATION')panel.append(el('p',tr('This count covers recorded requests only. Earlier actions or previous editions may have their own history.','此处仅汇总已记录的请求。更早操作或其他版本有各自的历史。'),'warning'));
    table(panel,[tr('Action','操作'),tr('Count','次数')],[[tr('Submitted hydraulic or geometry fields','手动提交水力或几何数值字段'),counts.manual_hydraulic_fields||0],[tr('Named reach selections','河段范围选择'),counts.reach_selections||0],[tr('Decision requests','决定请求'),counts.decision_requests||0],[tr('Compute confirmations (included above)','其中运算确认'),counts.compute_consents||0],[tr('Bank pairs submitted','提交岸站对'),counts.bank_pairs_submitted||0],[tr('Manual geometry preview entries','手动几何预览条目'),counts.section_adjustments_submitted||0],[tr('Map point saves','地图选点保存'),counts.map_save_requests||0]]);
   }
   if(data.local_problems?.length){
    const panel=details(content,'Issues grouped by section and profile','按河段和工况集中复核',true);
    for(const issue of data.local_problems){
     const title=tr(issue.title.en,issue.title.zh)+' · '+(issue.profile||'—')+' · '+(issue.stations.length?'RS '+issue.stations[0]+(issue.stations.length>1?' – '+issue.stations.at(-1):''):tr('Unlocated','位置未绑定'));
     const card=details(panel,title,title);
     for(const rs of issue.stations){
      card.append(button('Profile and neighbors · RS '+rs,'剖面和邻近断面 · RS '+rs,()=>{
       openGuidanceTool('atlas');
       document.getElementById('qa-tool-atlas').dispatchEvent(new CustomEvent('steadyreach-inspect-section',{detail:{rs,profile:issue.profile}}));
      }));
     }
     card.append(el('p',tr(issue.explanation.en,issue.explanation.zh)),el('p',issue.records+tr(' records',' 条记录')+' · '+issue.codes.join(', ')),button('Review this issue','查看这组问题',()=>openGuidanceTool(issue.target)));
    }
   }
   if(data.parameter_response?.length){
    const stopped=details(content,'When to stop this check','这轮检查何时结束',true);
    for(const r of data.parameter_response){
     const affected=r.affected.map(v=>'RS '+v.rs).join(', ');
     stopped.append(el('p',r.profile+' · '+r.case+' · '+r.paths.map(sensitivityParameterLabel).join(', ')+' · ΔWSE '+r.minimum_ft.toFixed(3)+' … '+r.maximum_ft.toFixed(3)+' ft. '+
      (affected?tr('Above the screening limit at ','超过筛查值的断面为 ')+affected+tr('. Check field support for this range before choosing another condition.','。先查清该范围的现场依据，随后决定是否另设条件。'):
       tr('All compared sections are within the screening limit. End this comparison for the tested range.','本次可比断面均在筛查值内，这组范围的比较可结束。'))));
    }
    stopped.append(el('p',tr('Each result covers only the named profile, compared stations and tested range. Missing controls require evidence before another batch.','各结论只覆盖所列工况、可比断面和已试范围。缺少控制依据时应先补资料，再启动下一批。')));

    const panel=details(content,'Where did the tested inputs change water levels?','已测试参数影响了哪些断面的水位？',true);
    table(panel,[tr('Case and profile','工况'),tr('Tested parameter','测试参数'),tr('Peak signed change (ft)','最大有符号变化（ft）'),tr('Stations above screening threshold','超过筛查值的断面')],data.parameter_response.map(r=>[r.case+' · '+r.profile,r.paths.map(sensitivityParameterLabel).join(' + '),'RS '+r.peak_rs+' · '+r.signed_peak_ft.toFixed(3),r.affected.length+' / '+r.compared+' ('+r.threshold_ft+' ft) · '+r.affected.map(a=>a.rs).join(', ')]));
   }
   for(const [index,row]of data.actions.entries()){
    const title=(index+1)+'. '+tr(row.title.en,row.title.zh);
    const item=details(content,title,title,index===0);
    item.append(el('p',tr(row.explanation.en,row.explanation.zh)));
    if(row.errors?.length)item.append(el('p',row.errors.join('\n'),'warning'));
    if(row.records)item.append(el('p',row.records+tr(' records; locations — ',' 条记录；位置 — ')+row.locations.map(v=>v.filter(Boolean).join(' · RS ')).join(', ')));
    if(row.outcome){const labels={NOT_TESTED_FOR_THIS_BASELINE:tr('Not tested for this baseline','本基准尚未检验'),NOT_CONVERGED:tr('Convergence remains open','收敛仍待处理'),STABLE_AT_REVIEW_THRESHOLD:tr('Meets the internal comparison threshold; review scope','达到内部比较阈值，仍须核对范围')};item.append(el('p',labels[row.outcome]||row.outcome,'status'));}
    if(row.excluded_intervals?.length)item.append(el('p',tr('Excluded intervals remain unresolved: ','排除区间仍未闭合：')+row.excluded_intervals.map(v=>v.upstream_rs+' → '+v.downstream_rs).join(', '),'warning'));
    if(row.tested?.length)table(item,[tr('Parameter','参数'),tr('Case','工况'),tr('Max matched-section |ΔWSE| ft','对应断面最大 |Δ水位| ft')],row.tested.map(v=>[sensitivityParameterLabel(v.parameter),v.case,v.max_delta_ft.toFixed(4)]));
    item.append(button('Open relevant review tool','打开对应复核工具',()=>openGuidanceTool(row.target)));
   }
   content.append(el('p',tr('No warning is closed by this list. Input adequacy, hydraulic QA and engineering acceptance remain separate.','此清单不会关闭任何警告；输入充分性、水力 QA 和工程接受仍分别判断。'),'warning'));
  }catch(error){if(content.isConnected){assessment.replaceChildren(el('p',tr('Assessment unavailable. ','评估暂不可用。')+error.message,'warning'),button('Retry assessment','重新评估',load));content.replaceChildren(el('p',tr('Could not organize the next steps: ','暂时无法整理下一步：')+error.message,'warning'),button('Retry next-step guidance','重试整理下一步',load));}}
  finally{guidanceRequests.delete(key);content.removeAttribute('aria-busy');}
 }
 void load();
}
