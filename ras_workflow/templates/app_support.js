'use strict';
let supportIncident=null;

function supportPage(){
 if(finalReview)return 'confirm';
 if(!current?.results)return 'model';
 return lastResultPage.project===current.id?lastResultPage.key:'overview';
}

function renderSupportEntry(){
 const host=document.getElementById('support-area');
 host.replaceChildren();host.hidden=!current;
 if(current)host.append(button('Project diagnostics','项目诊断',()=>openSupport()));
}

async function openSupport(){
 const host=document.getElementById('support-area'),project=current.id;
 const prior=supportIncident;
 const context=prior?.id===project&&prior.revision===current.revision
  ?{page:prior.page,incident:prior.incident}:{page:supportPage()};
 const body={id:project,...context};
 const data=await api('support-preview',body);
 if(current?.id!==project)return;
 renderSupportEntry();
 const panel=el('section',undefined,'card');host.append(panel);
 const help={
  EDITION_MISMATCH:['Reopen the selected edition and match the returned material to its current fingerprint before applying.','重新打开选定版本，核对回传资料与当前指纹后再采用。'],
  EXPORT_TIMEOUT:['Open Reports and maps and retry the export from the saved hydraulic result.','打开“报告与地图”，从已有水力结果重试导出。'],
  EXPORT_FAILED:['Check the report converter, map renderer and file locks, then retry the failed export.','检查转换器、制图程序和文件占用，再重试失败的导出。'],
  LOW_SPACE:['Inspect project storage and free space on the working drive before retrying.','检查项目存储和工作盘可用空间，再重试。'],
  INPUT_EVIDENCE:['Open the input decision list and check the affected source or measurement.','打开待判断参数清单，核对受影响原件或测量。'],
  ENVIRONMENT:['Run the installation environment check and repair the listed component.','运行环境检查，修复所列组件。'],
  SOLVER:['Open task recovery and inspect the approved inputs and native run status.','打开任务恢复，核对已确认输入及原生运行状态。'],
  NO_FAILURE_RECORDED:['No failure is recorded for this edition. You can share the identifiers below with support.','本版当前无已记录故障。下方标识可交给支持人员。'],
  UNCLASSIFIED:['Include the step you expected to complete when sending this record to support.','联系支持时附上你原本想完成的操作。']
 };
 panel.append(el('h2',tr('Support preview','诊断预览')),el('p',tr(...help[data.record.incident])),
  el('pre',JSON.stringify(data.record,null,2)),button('Download reviewed JSON','下载已预览的 JSON',async()=>{
   const record=await api('support-export',{...body,token:data.token});
   const url=URL.createObjectURL(new Blob([JSON.stringify(record,null,2)],{type:'application/json'}));
   const link=el('a');link.href=url;link.download='SteadyReach-support-'+record.edition+'.json';
   link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
   notify(tr('Support file downloaded.','诊断文件已下载。'),false,'success');
  }));
 if(current.results&&['EXPORT_TIMEOUT','EXPORT_FAILED'].includes(data.record.incident)){
  panel.append(button('Open reports and maps','打开报告与地图',()=>{
   const tab=document.getElementById('result-tab-delivery');if(tab){tab.click();tab.focus();}
  }));
 }
 panel.tabIndex=-1;panel.focus();panel.scrollIntoView({block:'center'});
}
