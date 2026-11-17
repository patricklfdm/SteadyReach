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
