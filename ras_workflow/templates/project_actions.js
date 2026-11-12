'use strict';
let actionTimer=null,trialDrafts={},deliveryDraft=null,deliveryExpanded=false;
function renderProjectActions(){
 const h=data.home;if(!h)return;let out=document.getElementById('project-actions');if(!out){out=node('div');out.id='project-actions';$('home').append(out);}out.replaceChildren();const tr=(en,zh)=>lang==='zh'?zh:en;
 out.append(node('h3',tr('Progress and next action','当前进度与下一步')));
 const steps=node('ol');for(const p of h.progress||[])steps.append(node('li',p.stage+' · '+p.status));out.append(steps);
 const scenario=node('select');scenario.id='action-scenario';for(const id of h.scenarios||[]){const op=node('option',id);op.value=id;scenario.append(op);}out.append(node('label',tr('Scenario','工况')),scenario);
 const reviewer=node('input');reviewer.id='action-reviewer';reviewer.placeholder=tr('Operator name for computation','执行计算的操作人');out.append(reviewer);
 const freshLabel=node('label',undefined,'check'),fresh=node('input');fresh.type='checkbox';fresh.id='action-fresh';freshLabel.append(fresh,node('span',tr('Force a new solver run (preserve the previous run for comparison)','强制重新求解（保留前次运行以供对比）')));out.append(freshLabel);
 const consent=node('label',undefined,'check'),check=node('input');check.type='checkbox';check.id='action-consent';consent.append(check,node('span',tr('Run the selected project using its recorded input approvals, or explicitly reopen cancelled input review. Missing inputs will pause for review.','按已有输入审核记录执行所选项目，或明确恢复已放弃的输入复核。缺资料仍暂停等待审核。')));out.append(consent);
 renderReportOptions(out,h,tr);
 renderDeliveryOptions(out,h,tr);
 const buttons=[];for(const [action,en,zh]of [['INPUT','Open input / geometry review','打开输入 / 几何复核'],['QA','Open latest hydraulic review','打开最新水力复核'],['REPORT','Regenerate latest report','重新生成最新报告'],['RUN','Run / retry selected scenario','运行 / 重试所选工况']]){const b=button(tr(en,zh),()=>task(async()=>{await save();const r=await api('project-action',{action,scenario:scenario.value,project_sha256:h.project_sha256,reviewer:reviewer.value,confirmed:check.checked,recompute:fresh.checked,report_context:action==='REPORT'?reportContext(h):null,previous_run_id:action==='QA'?reportDraft.previous_run_id:null});if(action==='QA'){await refresh();message(tr('Latest review loaded.','已加载最新复核。'));return;}if(r.url){const a=node('a',tr('Open local input wizard','进入本机填报向导'));a.href=r.url;a.target='_blank';a.rel='noreferrer';out.append(a);message(tr('Wizard ready. Use the link below.','向导已就绪，请点击下方链接。'));}else{data.action=r;renderProjectActions();pollProjectAction();message(tr('Action started; progress remains on disk.','操作已开始，进度保存在本机。'));}}));b.id='project-action-'+action;buttons.push(b);out.append(b);}
 const job=data.action;if(job){out.append(node('p',job.action+' · '+job.status,'boundary'),node('p',job.log||''));if(job.status==='RUNNING')buttons.forEach(b=>b.disabled=true);if(job.error)out.append(node('p',job.error));}
 for(const r of h.recovery||[]){const details=node('details');details.append(node('summary',tr('Recovery command: ','恢复命令：')+r.kind),node('pre',r.command));for(const e of r.errors||[])details.append(node('p',e));out.append(details);}
 const history=node('details');history.append(node('summary',tr('Report edition history','报告版本历史')));for(const e of h.report_history||[])history.append(node('p',(e.registered_utc||tr('Original run','原运行'))+' · '+(e.verified?'VERIFIED':'EVIDENCE_CHANGED')),node('p',e.manifest.path));out.append(history);
 out.append(button(tr('Refresh project status','刷新项目状态'),()=>task(async()=>{await save();await refresh();message('');})));
 if(job?.status==='RUNNING')pollProjectAction();
}
function renderDeliveryOptions(out,h,tr){
 const box=node('details');box.id='delivery-options';box.open=deliveryExpanded;box.addEventListener('toggle',()=>{if(box.isConnected)deliveryExpanded=box.open;});box.append(node('summary',tr('Complete and minimal delivery packages','完整与最小交付包')));
 box.append(node('p',tr('Both folders contain the same computed model. Complete adds editable GIS, bilingual reports, inputs and QA evidence. Exporting does not rerun the solver.','两份文件夹使用同一计算模型；完整包另含可编辑 GIS、双语报告、输入和 QA 证据。导出不会重新求解。')));
 if(h.delivery){
  box.append(node('p',h.delivery.status));if(h.delivery.error)box.append(node('p',h.delivery.error));
  for(const key of ['complete','minimal'])if(h.delivery[key]){
   box.append(node('p',(key==='complete'?tr('Complete folder: ','完整包：'):tr('Minimal folder: ','最小包：'))+h.delivery[key].path));
   const links=node('p');for(const a of (h.artifacts||[]).filter(a=>a.path.startsWith(h.delivery[key].path+'/'))){
    const name=a.path.split('/').pop(),label=name==='READ_ME.txt'?tr('Opening instructions','打开说明'):name==='PACKAGE_MANIFEST.json'?tr('File manifest','文件清单'):tr('English exhibit PDF','英文展示 PDF');
    if(links.childNodes.length)links.append(node('span',' · '));links.append(link(a,label));
   }box.append(links);
  }
 }
 if(h.delivery_mapped===false){box.append(node('p',tr('This model has no reviewed geographic terrain. These packages contain native model/results and reports only; no GIS exhibit is claimed.','此模型没有已审核的地理地形资料。交付包仅含原生模型/结果及报告，不声明含 GIS 展示。')));const b=button(tr('Export native-only complete and minimal folders','导出仅含原生资料的完整包与最小包'),()=>task(async()=>{await save();data.action=await api('project-action',{action:'DELIVERY',project_sha256:h.project_sha256});renderProjectActions();pollProjectAction();}));b.id='project-action-DELIVERY';b.disabled=!h.run_id||data.action?.status==='RUNNING';box.append(b);out.append(box);return;}
 deliveryDraft??=structuredClone(h.delivery_settings||{});const draft=deliveryDraft;draft.imagery??={};
 function field(label,value,change){const l=node('label',label),i=node('input');i.value=value||'';i.addEventListener('input',()=>change(i.value));l.append(i);box.append(l);return i;}
 field(tr('Reviewed geometry CRS (e.g. EPSG code)','已复核模型坐标系（例如 EPSG 编码）'),draft.horizontal_crs,v=>draft.horizontal_crs=v);
 field(tr('Contour interval, native vertical feet','等高距，采用模型高程英尺单位'),draft.contour_interval||2,v=>draft.contour_interval=v);
 const imageMode=node('select');imageMode.id='delivery-imagery-mode';
 for(const [value,en,zh] of [['usgs_naip','Download USGS NAIP automatically','自动下载 USGS NAIP 航片'],['local','Use my local RGB GeoTIFF','使用本地 RGB GeoTIFF'],['not_available','Record imagery unavailable','记录航片不可用']]){const option=node('option',tr(en,zh));option.value=value;imageMode.append(option);}
 imageMode.value=draft.imagery.mode||(draft.imagery.raster?'local':draft.imagery.reason?'not_available':'usgs_naip');
 box.append(node('label',tr('Aerial imagery','航片来源')),imageMode);
 const imagePath=field(tr('Offline RGB GeoTIFF, relative to project.json','离线 RGB GeoTIFF，相对于 project.json 的路径'),draft.imagery.raster,v=>draft.imagery.raster=v);
 const imageSource=field(tr('Imagery source and year','航片来源与年份'),draft.imagery.source,v=>draft.imagery.source=v);
 const imageReason=field(tr('Reason imagery is unavailable','航片不可用的原因'),draft.imagery.reason,v=>draft.imagery.reason=v);
 function imageFields(){draft.imagery.mode=imageMode.value;imagePath.parentElement.hidden=imageSource.parentElement.hidden=imageMode.value!=='local';imageReason.parentElement.hidden=imageMode.value!=='not_available';}
 imageMode.addEventListener('change',imageFields);imageFields();
 box.append(node('p',tr('USGS download saves a small offline natural-color image with source dates and coverage checks. Download failure pauses delivery for a local image or an explicit unavailable decision.','USGS 下载会保存带来源日期和覆盖检查的小范围离线自然色航片；下载失败时暂停交付，可改用本地航片或明确记录不可用。')));
 const reviewer=field(tr('Delivery reviewer','交付资料审核人'),draft.reviewer,v=>draft.reviewer=v);
 box.append(node('p',tr('The CRS must describe the native model. Terrain is cropped and reprojected automatically within the same horizontal datum. Datum changes still require separate review. This form does not approve hydraulic inputs.','坐标系须正确描述原生模型。地形会在同一水平基准下自动裁剪、重投影；基准变换仍需另行审核。此表不批准水力参数。')));
 const b=button(tr('Review settings and export both folders','审核上述资料并导出两份文件夹'),()=>task(async()=>{await save();const imagery=imageMode.value==='usgs_naip'?{mode:'usgs_naip'}:imageMode.value==='local'?{raster:draft.imagery.raster,source:draft.imagery.source}:{mode:'not_available',reason:draft.imagery.reason};const settings={horizontal_crs:draft.horizontal_crs,contour_interval:Number(draft.contour_interval||2),imagery};const r=await api('project-action',{action:'DELIVERY',project_sha256:h.project_sha256,reviewer:reviewer.value,delivery_settings:settings});data.action=r;renderProjectActions();pollProjectAction();}));
 b.id='project-action-DELIVERY';b.disabled=!h.run_id||data.action?.status==='RUNNING';box.append(b);out.append(box);
}
function pollProjectAction(){
 if(actionTimer)return;actionTimer=setTimeout(async()=>{actionTimer=null;try{data.action=await api('action-status');if(data.action?.status==='RUNNING'){renderProjectActions();}else {await refresh();message((lang==='zh'?'操作状态：':'Action status: ')+(data.action?.status||''),data.action?.status==='FAILED');}}catch(e){message(e.message,true);}},3000);
}
function renderInvestigation(out,row){
 const g=data.qa.investigation_guides?.[row.key];if(!g)return;const tr=(en,zh)=>lang==='zh'?zh:en;
 const panel=node('details');panel.id='investigation-guide';panel.append(node('summary',tr('Investigation guide and parameter trial','调查步骤与参数对照试验')),node('p',lang==='zh'?g.action_zh:g.action_en),node('p',tr('Evidence needed: ','所需证据：')+(lang==='zh'?g.closure_zh:g.closure_en)));out.append(panel);
 panel.append(node('p',tr('Geometry/domain findings need the geometry wizard and a comparable rerun. Parameter trials below require supported bounds and separate study approval; they do not close this issue.','几何及范围问题应使用几何向导并进行可比重算。下方参数试验需要有依据的范围及独立研究批准，不会关闭本问题。')));
 if(!data.home)return;trialDrafts[row.key]??={};const draft=trialDrafts[row.key],fields={};function field(key,label,type='text'){const l=node('label',label),v=node(type==='textarea'?'textarea':'input');v.id='investigation-'+key;if(type!=='textarea')v.type=type;if(type==='number')v.step='any';v.value=draft[key]||'';v.addEventListener('input',()=>{draft[key]=v.value;mark();});l.append(v);panel.append(l);fields[key]=v;return v;}
 const select=node('select');select.id='investigation-parameter';for(const p of g.parameters){const o=node('option',p);o.value=p;select.append(o);}select.value=draft.parameter||g.parameters[0];select.addEventListener('change',()=>{draft.parameter=select.value;mark();});panel.append(node('label',tr('Parameter path','参数路径')),select);
 field('low',tr('Supported lower bound','有依据的下限'),'number');field('high',tr('Supported upper bound','有依据的上限'),'number');field('basis',tr('Range basis and source locator','范围依据与来源位置'),'textarea');field('hypothesis',tr('Question this trial should answer','本次试验要回答的问题'),'textarea');field('measurement',tr('Measurement or inspection needed','需要的补测或检查'),'textarea');
 const evidence=node('select');evidence.id='investigation-evidence';evidence.append(new Option(tr('Select uploaded range evidence','选择已上传的范围证据'),''));for(const e of data.qa.uploads){const a=data.qa.artifacts.find(v=>v.path===e.path);if(a)evidence.append(new Option(data.qa.upload_names?.[e.path]||e.path,a.id));}evidence.value=draft.evidence||'';evidence.addEventListener('change',()=>{draft.evidence=evidence.value;mark();});panel.append(evidence);
 panel.append(button(tr('Prepare reviewable trial cases','准备待审核试验方案'),()=>task(async()=>{await save();if(!fields.low.value.trim()||!fields.high.value.trim())throw Error(tr('Both bounds are required.','必须填写上下限。'));const r=await api('investigation',{revision:data.qa.revision,issue_keys:[row.key],reviewer:$('reviewer').value,scenario:data.qa.scenario_id,hypothesis:fields.hypothesis.value,evidence_ids:[evidence.value],ranges:[{path:select.value,low:Number(fields.low.value),high:Number(fields.high.value),basis:fields.basis.value,measurement_action:fields.measurement.value}]});await refresh();message(tr('Draft prepared. Review the study files before running: ','方案已准备。执行前请审核研究文件：')+r.study.path);})));
 for(const e of data.qa.investigations||[]){panel.append(node('p',tr('Saved investigation: ','已保存调查：')+e.path));const prefix=e.path.replace(/investigation\.json$/,'');for(const a of data.qa.artifacts.filter(a=>a.path.startsWith(prefix)&&/study\.json$|review\.template\.json$/.test(a.path)))panel.append(link(a));}
}
