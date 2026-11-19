'use strict';
const guidanceRequests=new Map();
function openGuidanceTool(key){
 const node=document.getElementById('qa-tool-'+key)||document.getElementById('qa-tool-qa');
 if(!node)throw Error(tr('Reopen this result to load the review tool.','请重新打开结果以加载复核工具。'));
 for(let p=node;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;
 node.scrollIntoView({block:'start',behavior:'smooth'});
 node.setAttribute('tabindex','-1');node.focus({preventScroll:true});
 notify(tr('Review tool opened. No input changed and no calculation started.','已展开相应复核工具；未修改输入、未启动计算。'));
}
function renderGuidance(parent){
 const box=details(parent,'Suggested next steps from this calculation','根据本次计算整理下一步',true);
 const content=el('div');box.append(content);
 const id=current.id,hash=current.summary.sha256;
 async function load(){
  content.replaceChildren(el('p',tr('Checking result evidence and completed studies…','正在核对结果证据与已完成试算…'),'status'));
  content.setAttribute('aria-busy','true');
  const key=id+'|'+hash+'|'+current.revision;
  try{
   let request=guidanceRequests.get(key);
   if(!request){request=api('qa-guidance',{id,summary_hash:hash});guidanceRequests.set(key,request);}
   const data=await request;
   if(!content.isConnected||current?.id!==id||current.summary?.sha256!==hash)return;
   content.replaceChildren();
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
  }catch(error){if(content.isConnected){content.replaceChildren(el('p',tr('Could not organize the next steps: ','暂时无法整理下一步：')+error.message,'warning'),button('Retry next-step guidance','重试整理下一步',load));}}
  finally{guidanceRequests.delete(key);content.removeAttribute('aria-busy');}
 }
 void load();
}
