'use strict';
const guidanceRequests=new Map();
function assessmentFact(row){
 const f=row.facts||{},decimal=(v,d)=>Number.isFinite(v)?v.toFixed(d):'—';
 if(row.code==='GEOMETRY_FLOW_PATH')return 'RS '+f.station+' · '+(f.side==='L'?tr('left','左侧'):tr('right','右侧'))+' '+decimal(f.baseline_share_pct,2)+'% → '+decimal(f.alternative_share_pct,2)+'% · '+tr('new end depth ','新过水端深 ')+decimal(f.end_excess_ft,3)+' ft';
 if(row.code==='BOUNDARY_INFLUENCE')return f.profile+' · '+sensitivityParameterLabel(f.parameter)+' · RS '+f.station+' · Δ '+decimal(f.delta_ft,3)+' ft · '+f.affected+'/'+f.compared+tr(' sections above ',' 条断面的绝对差超过 ')+f.threshold_ft+' ft';
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
function showResultAssessment(box,a){
 const label=s=>tr(s.en,s.zh),primary=a.findings[0];
 box.append(el('h2',tr('Delivery assessment','结果交付评估')+' · L'+a.level+' · '+label(a.title)));
 const use=[
  tr('Restore calculation evidence before interpreting water levels.','先恢复本次计算证据，再解读水位。'),
  tr('Use this edition for internal troubleshooting. Resolve the listed evidence or package gaps before handoff.','本版可用于内部排查，交出前先补齐所列证据或交付包。'),
  tr('Share the model and maps with an engineer for conditional review. Include the limitations below.','可以将本版模型和地图连同下列限制交给工程师复核。'),
  tr('The technical package can enter sign-off review. The responsible engineer decides suitability and approval.','技术资料可送签审，由负责工程师判断用途与签发。')];
 box.append(el('p',use[a.level]));
 function action(parent,row){
  const f=row.facts||{};
  parent.append(el('p',label(row.reason)),el('p',assessmentFact(row),'muted'));
  parent.append(button('Open related tool','打开对应工具',()=>{
   openGuidanceTool(row.target);
   if(row.target==='floodplain'&&f.station)document.getElementById('qa-tool-floodplain')?.dispatchEvent(new CustomEvent('steadyreach-inspect-floodplain',{detail:{rs:f.station,geometry:f.case}}));
  }));
 }
 if(primary){const first=el('div');box.append(first);first.append(el('strong',tr('First action','优先处理')));action(first,primary);}
 if(a.delivery){
  const d=a.diagnostics,counts=a.delivery.files;
  box.append(el('p',tr('Delivery files','交付文件')+' · '+assessmentState(a.delivery.status)+(counts?' · Minimal '+counts.minimal+' / Complete '+counts.complete:''),
   'status'),el('p',tr('Native messages','原生信息')+' '+(d.native_messages??'—')+' · '+tr('Combined diagnostic records','综合诊断记录')+' '+(d.records??'—')+' · QA '+assessmentState(a.qa.status)));
 }
 if(a.findings.length>1){const more=details(box,'All remaining findings ('+(a.findings.length-1)+')','其余限制及处理入口（'+(a.findings.length-1)+'）');for(const r of a.findings.slice(1))action(more,r);}
 if(a.candidate_findings?.length){
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
  actions.append(button('Prepare QA revision suggestions','根据 QA 创建修订建议',prepareQaRevision),button('Open editable revision tool','打开独立修订入口',()=>openGuidanceTool('revision')));}
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
 for(let p=node;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;
 node.scrollIntoView({block:'start',behavior:'smooth'});
 node.setAttribute('tabindex','-1');node.focus({preventScroll:true});
 notify(tr('Review tool opened. No input changed and no calculation started.','已展开相应复核工具；未修改输入、未启动计算。'));
}
function renderGuidance(parent){
 const assessment=el('section',undefined,'result-assessment');parent.append(assessment);
 const box=details(parent,'Suggested next steps from this calculation','根据本次计算整理下一步');
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
   if(data.assessment)showResultAssessment(assessment,data.assessment);
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
