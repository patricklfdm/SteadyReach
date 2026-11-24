'use strict';
let lang=localStorage.getItem('workflow-language')||'en',current=null,busy=false,poll=null,dirty=false,edited={},metaEdits={},mapData=null,anchorMode=null,anchors={upstream:[],downstream:[]};
const $=s=>document.querySelector(s),tr=(en,zh)=>lang==='zh'?zh:en,token=location.pathname.split('/')[1];
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
let saveTimer=null,savePromise=null,pendingMapSave=null,mapDirty=false,viewRequest=0;
// Tab-local drafts keep unadopted choices separate from model writes.
const uiDrafts=new Map(),draftFiles=new Map();
function draftKey(group,owner=current?.id||'home'){return 'steadyreach-ui/'+owner+'/'+group;}
function readDraft(key){
 if(uiDrafts.has(key))return uiDrafts.get(key);
 try{return JSON.parse(sessionStorage.getItem(key)||'null');}catch{return null;}
}
function writeDraft(key,value){
 if(value==null)uiDrafts.delete(key);else uiDrafts.set(key,value);
 try{if(value==null)sessionStorage.removeItem(key);else sessionStorage.setItem(key,JSON.stringify(value));}catch{/* Keep the draft in this tab when storage is full. */}
}
function rememberForm(key,inputs){
 const values={};
 for(const input of inputs){
  if(input.type==='file'){
   const k=key+'/'+input.id;
   if(input.files.length){draftFiles.set(k,input.files);values[input.id]=Array.from(input.files,f=>f.name);}
   else values[input.id]=input.dataset.reselect?JSON.parse(input.dataset.reselect):[];
  }else values[input.id]=input.type==='checkbox'?input.checked:input.value;
 }
 writeDraft(key,values);
}
function restoreForm(key,inputs){
 const values=readDraft(key)||{},missing=[];
 for(const input of inputs){
  if(!Object.hasOwn(values,input.id))continue;
  if(input.type==='file'){
   const files=draftFiles.get(key+'/'+input.id);
   if(files?.length)input.files=files;
   else if(values[input.id]?.length){input.dataset.reselect=JSON.stringify(values[input.id]);missing.push(...values[input.id]);}
  }else if(input.type==='checkbox')input.checked=values[input.id];
  else input.value=values[input.id];
 }
 return missing;
}
function observeForm(key,inputs,changed=()=>{}){
 for(const input of inputs)input.addEventListener(input.type==='file'||input.type==='checkbox'||input.tagName==='SELECT'?'change':'input',()=>{
  if(input.type==='file'){delete input.dataset.reselect;draftFiles.delete(key+'/'+input.id);}
  rememberForm(key,inputs);changed();
 });
}
function forgetForm(key,inputs){
 writeDraft(key,null);
 for(const input of inputs)if(input.type==='file')draftFiles.delete(key+'/'+input.id);
}
const pendingChanges=new Map();
function stageChange(key,label,count,commit){if(count)pendingChanges.set(key,{label,count,commit});else pendingChanges.delete(key);showPending();}
function showPending(){let node=document.getElementById('pending-changes');if(!node&&document.getElementById('screen')){node=el('div',undefined,'pending-changes');node.id='pending-changes';document.getElementById('screen').prepend(node);}if(node){node.hidden=!pendingChanges.size;node.textContent=tr('Selected changes not saved: ','已选择、尚未保存：')+[...pendingChanges.values()].map(p=>p.label+' '+p.count).join(' · ')+tr(' — Save all or review parameters to apply them.','；点击保存全部或核对参数时统一保存。');}}
async function saveAll(keys=null){
 validateBankInputs();
 await save();
 for(const [key,p]of [...pendingChanges].sort(([a],[b])=>(a==='associations'?-1:0)-(b==='associations'?-1:0))){
  if(keys&&!keys.includes(key))continue;
  notify(tr('Saving ','正在保存 ')+p.label+'…');await p.commit();pendingChanges.delete(key);showPending();
 }
 if(pendingMapSave)await pendingMapSave();
}

function notify(text='',error=false,tone='info'){$('#notice').setAttribute('role',error?'alert':'status');$('#notice').hidden=!text;$('#notice').textContent=text;$('#notice').className=error?'error':tone;}
async function api(route,body){const r=await fetch(route,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Workflow-Token':token,'X-SteadyReach-Client':'page'},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(data.error||r.status);return data;}
async function task(fn,label=tr('Working','正在处理'),source=null){
 if(busy)return;busy=true;const prior=new Map([...document.querySelectorAll('button,input,select,textarea')].map(b=>[b,b.disabled]));
 const working=label+'…',old=source?.textContent;notify(working,false,'working');document.body.setAttribute('aria-busy','true');prior.forEach((v,b)=>b.disabled=true);if(source){source.textContent=working;source.classList.add('working');}
 try{if(savePromise)await savePromise;if(pendingMapSave&&pendingMapSave!==fn)await pendingMapSave();await fn();if($('#notice').textContent===working)notify(label+(current?.status==='PROCESSING'?tr(' — started; follow progress below',' — 已启动，请查看下方进度'):''));}
 catch(e){notify(e.message,true);if(e.input)requestAnimationFrame(()=>{e.input.focus();e.input.scrollIntoView({block:'nearest'});});}
 finally{busy=false;document.body.removeAttribute('aria-busy');prior.forEach((v,b)=>{if(b.isConnected)b.disabled=v;});if(source?.isConnected){source.textContent=old;source.classList.remove('working');}}
}
function button(en,zh,fn,cls){const b=el('button',tr(en,zh),cls);b.type='button';b.onclick=()=>task(fn,tr(en,zh),b);return b;}
function field(parent,id,en,zh,value='',kind='text',options=null,onchange=null){const box=el('label',undefined,'field');box.append(el('span',tr(en,zh)));let input=el(kind==='select'?'select':kind==='textarea'?'textarea':'input');input.id=id;if(kind==='select'){for(const [v,en0,zh0]of options)input.append(new Option(tr(en0,zh0),v));}else if(kind!=='textarea'){input.type=kind;if(kind==='number'){input.step='any';input.addEventListener('wheel',()=>input.blur(),{passive:true});}}input.value=value??'';if(onchange)input.addEventListener(kind==='select'?'change':'input',()=>onchange(input.value));box.append(input);parent.append(box);return input;}
const expansionState=new Map();
function details(parent,en,zh,open=false,stateKey=en){const d=el('details');const key=(current?.id||'home')+'|'+(finalReview?'review':'edit')+'|'+(parent.closest('[data-key]')?.dataset.key||'')+'|'+stateKey;d.open=expansionState.get(key)??open;d.addEventListener('toggle',()=>expansionState.set(key,d.open));d.append(el('summary',tr(en,zh)));const b=el('div');d.append(b);parent.append(d);return b;}
function check(parent,en,zh,value,onchange){const l=el('label',undefined,'check'),i=el('input');i.type='checkbox';i.checked=value;l.append(i,el('span',tr(en,zh)));i.onchange=()=>onchange(i.checked);parent.append(l);return i;}
function table(parent,head,rows){const wrap=el('div',undefined,'scroll'),t=el('table'),hr=el('tr');head.forEach(h=>hr.append(el('th',h)));t.append(hr);for(const row of rows){const r=el('tr');for(const v of row)r.append(el('td',v??'—'));t.append(r);}wrap.append(t);parent.append(wrap);}
function shell(step){$('#steps').replaceChildren();[tr('1 · Project','1 · 建立项目'),tr('2 · Prepare model','2 · 准备模型'),tr('3 · Confirm inputs','3 · 开算确认'),tr('4 · Results','4 · 查看结果')].forEach((s,i)=>{const label=el('span',s,i===step?'active':'');if(i===step)label.setAttribute('aria-current','step');$('#steps').append(label);});document.documentElement.lang=lang==='zh'?'zh-CN':'en';$('#language').textContent=lang==='zh'?'English':'简体中文';$('#subtitle').textContent=tr('HEC-RAS · Local computation','HEC-RAS · 本机计算');$('#foot').textContent=tr('1D steady rivers and culverts. Actual HEC-RAS results; assumptions and unresolved checks remain visible. No engineering certification is implied.','1D 恒定流河道与涵洞分析。使用真实 HEC-RAS；保留估计项与未闭合检查，不自动认定设计合格。');$('#screen').replaceChildren();}
const stateLabel=s=>({NEW:tr('New','新建'),PROCESSING:tr('Processing','处理中'),INPUTS_READY:tr('Model draft','模型草稿'),RESULTS_READY:tr('Computed · review limitations','已计算 · 请查看限制'),RESULTS_READY_MAP_PENDING:tr('Computed · map export needs attention','已计算 · 地图导出待处理'),NEEDS_ATTENTION:tr('Needs attention · draft retained','需处理 · 草稿已保留'),ABANDONED:tr('Abandoned · files retained','已放弃 · 文件保留'),INTERRUPTED:tr('Interrupted · retry available','已中断 · 可重试')}[s]||s);
function rememberView(view){window.history?.replaceState({steadyReach:view},'');}
async function resumePage(){
 const view=window.history?.state?.steadyReach;
 if(!view?.project){await home();return;}
 try{
  await open(view.project);
  if(view.page==='confirm'&&current.status==='INPUTS_READY')await showFinalReview(false);
  else if(view.resultTab&&current.results)document.getElementById('result-panel-'+view.resultTab)?.dispatchEvent(new CustomEvent('steadyreach-show-panel'));
 }catch(error){await home();notify(tr('Could not reopen the saved view: ','无法恢复已保存的页面：')+error.message,true);}
}
function inputError(input,message){
 input.setAttribute('aria-invalid','true');
 let hint=document.getElementById(input.id+'-error');
 if(!hint){hint=el('small',message,'warning');hint.id=input.id+'-error';input.parentElement.append(hint);}
 hint.textContent=message;hint.hidden=false;input.setAttribute('aria-describedby',hint.id);
 function clear(){input.removeAttribute('aria-invalid');input.removeAttribute('aria-describedby');hint.hidden=true;input.removeEventListener('input',clear);input.removeEventListener('change',clear);}
 input.addEventListener('input',clear);input.addEventListener('change',clear);
 const error=new Error(message);error.input=input;throw error;
}
function surveyLimit(files){
 const large=Array.from(files).filter(f=>f.size>15000000);
 if(large.length)return tr('Over 15 MB: ','超过 15 MB：')+large.map(f=>f.name).join(', ');
 if(Array.from(files).reduce((sum,f)=>sum+f.size,0)>50000000)return tr('Selection exceeds 50 MB. Crop the terrain or reduce the package.','所选资料超过 50 MB。请裁剪地形或缩小资料包。');
 return '';
}
async function home(){
 const request=++viewRequest;
 pendingChanges.clear();clearTimeout(poll);current=null;finalReview=null;rememberView(null);
 dirty=false;mapData=null;shell(0);
 const screen=$('#screen');
 screen.append(el('h1',tr('Projects','项目')),el('p',tr('Start with a location, a surveyed river package, or a HEC-RAS model. Review inputs together before computing.','从坐标、实测河道资料包或已有 HEC-RAS 工程开始，集中核对参数后再计算。')));
 const saved=el('section');
 await renderSavedProjects(saved);
 if(viewRequest!==request)return;
 const hasProjects=!!saved.querySelector('[data-project-id]');
 if(!hasProjects)renderPractice(screen);
 const card=details(screen,'Start a new project','新建项目',!hasProjects,'new-project');
 screen.append(saved);
 if(hasProjects)renderPractice(screen);
 const form=el('div',undefined,'grid project-intake');card.append(form);
 const route=field(form,'route','Starting information','起始资料','coordinates','select',[
  ['coordinates','Coordinates / partial information','坐标／部分资料'],['native','Existing HEC-RAS model','已有 HEC-RAS 工程'],['survey','Georeferenced river survey package','已整理的实测河道资料包']]);
 const modelType=field(form,'model-type','What are you modeling?','你要模拟什么？','','select',[
  ['','Choose the site type','请选择地点类型'],['river','River reach (bridges excluded), e.g. between two bridges','纯河道（不建桥梁），例如两桥之间的河段'],['culvert','Flow through one or more culvert barrels','水流通过一孔或多孔涵洞']]);
 const title=field(form,'title','Project name','项目名称');
 const coords=el('div',undefined,'coordinate-pair');form.append(coords);
 const lat=field(coords,'latitude','Latitude (WGS84)','纬度（WGS84）','','number');
 const lon=field(coords,'longitude','Longitude (WGS84)','经度（WGS84）','','number');
 const q=field(form,'flow','Discharge (cfs), if known','流量（cfs，已知时填写）','','number');
 const more=details(card,'Optional roughness','可选：已知糙率');
 field(more,'channel_n','Channel Manning n','主槽糙率','','number');
 field(more,'overbank_n','Overbank Manning n','两侧漫滩糙率','','number');
 const native=el('div');card.append(native);nativeSelector(native,false);native.hidden=true;
 const intent=scopeFields(card,{},true);
 const key=draftKey('new-project','home');
 const surveyed=el('label',undefined,'field');surveyed.hidden=true;
 surveyed.append(el('span',tr('Select survey.json, the GeoTIFF and all sources listed in the manifest. Location, flow and roughness are read from the package.','选择 survey.json、GeoTIFF 和清单所列全部来源文件。坐标、流量及糙率取自资料包。')));
 const measured=el('input');measured.type='file';measured.multiple=true;measured.id='survey-files';const selection=el('small');selection.setAttribute('aria-live','polite');const selectionInfo=()=>{const files=Array.from(measured.files);const size=(files.reduce((sum,f)=>sum+f.size,0)/1e6).toFixed(1);selection.textContent=[files.length+tr(' files',' 个文件')+' · '+size+' MB',tr('15 MB per file / 50 MB total','单文件 15 MB／总计 50 MB'),surveyLimit(files)].filter(Boolean).join(' · ');};measured.onchange=selectionInfo;surveyed.append(measured,selection);card.append(surveyed);
 let locationScope='';modelType.onchange=()=>{if(route.value==='coordinates')locationScope=modelType.value;};
 route.onchange=()=>{const useSurvey=route.value==='survey';native.hidden=route.value!=='native';surveyed.hidden=!useSurvey;
 for(const input of [lat,lon,q,$('#channel_n'),$('#overbank_n'),modelType])input.disabled=useSurvey;
 for(const input of [lat,lon,q,modelType])input.parentElement.hidden=useSurvey;
 coords.hidden=useSurvey;more.parentElement.hidden=useSurvey;modelType.disabled=useSurvey||route.value==='native';
 if(useSurvey)modelType.value='river';else if(route.value==='native')modelType.value='culvert';else modelType.value=locationScope;};
 const gis=check(card,'Also prepare GIS / Mapper / exhibits','同时准备 GIS、Mapper 和展示图',true,()=>{});gis.id='new-gis';
 const inputs=Array.from(card.querySelectorAll('input,select,textarea'));
 restoreForm(key,inputs);if(route.value==='coordinates')locationScope=modelType.value;route.onchange();$('#project-flow-paths').dispatchEvent(new Event('change'));selectionInfo();
 const fileHint=el('p','', 'warning');card.append(fileHint);
 function updateForm(){
  title.required=true;modelType.required=route.value==='coordinates';lat.required=lon.required=route.value==='coordinates';
  measured.required=route.value==='survey';
  for(const input of [title,modelType,lat,lon,measured])input.setAttribute('aria-required',String(input.required));
  const file=route.value==='survey'?measured:route.value==='native'?$('#native-files'):null;
  fileHint.hidden=!file?.dataset.reselect;
  if(!fileHint.hidden)fileHint.textContent=tr('Reselect these files after reload: ','刷新后请重新选择这些文件：')+JSON.parse(file.dataset.reselect).join(', ');
 }
 updateForm();observeForm(key,inputs,updateForm);
 card.append(el('small',tr('Enter a project name. For a location start, also choose the site type and enter both coordinates.','请填写项目名称。按坐标建项时，还需选择地点类型、填写经纬度。')));
 card.append(button('Prepare project','准备项目',async()=>{
 if(!title.value.trim())inputError(title,tr('Enter a project name.','请填写项目名称。'));
 if(route.value!=='survey'){
   if(route.value==='coordinates'&&!modelType.value)inputError(modelType,tr('Choose a river reach or a culvert crossing.','请选择纯河道或涵洞设施。'));
  if(route.value==='coordinates'||lat.value||lon.value)for(const [input,minimum,maximum] of [[lat,-90,90],[lon,-180,180]]){
   if(!input.value||!Number.isFinite(input.valueAsNumber)||input.valueAsNumber<minimum||input.valueAsNumber>maximum)inputError(input,(input===lat?tr('Latitude','纬度'):tr('Longitude','经度'))+' · '+minimum+' … '+maximum);
  }
  if(route.value==='native'){const file=$('#native-files'),large=Array.from(file.files).filter(f=>f.size>15000000);if(large.length)inputError(file,tr('Over 15 MB: ','超过 15 MB：')+large.map(f=>f.name).join(', '));}
  if(route.value==='native'&&!$('#native-files').files.length&&!$('#native-path').value.trim())inputError($('#native-files'),tr('Select native inputs or enter a project path.','请选择原生输入文件或填写工程路径。'));
 }
 let body={production_scope:intent(),model_type:modelType.value,route:route.value,title:title.value,latitude:lat.value,longitude:lon.value,flow_cfs:q.value,channel_n:$('#channel_n').value,overbank_n:$('#overbank_n').value,gis:gis.checked};if(route.value==='native')Object.assign(body,await nativeBody());
 if(route.value==='survey'){if(!measured.files.length)inputError(measured,tr('Select the survey package files','请选择实测资料包中的文件'));const selected=Array.from(measured.files);const limit=surveyLimit(selected);if(limit)inputError(measured,limit);body.survey_files=await encodeFiles(measured.files);}
 const r=await api('create',body);forgetForm(key,inputs);await open(r.id);},'primary'));}

function savedProjectGroups(projects,deleted){
 const byId=new Map([...projects,...deleted].map(project=>[project.id,project]));
 const roots=new Map();
 function originalId(id){
  const path=new Set();
  while(!roots.has(id)){
   if(path.has(id)){
    // Keep a damaged parent loop in one stable, recoverable entry.
    const members=[...path];
    id=members.slice(members.indexOf(id)).sort()[0];
    break;
   }
   path.add(id);
   const parentId=byId.get(id)?.parent_revision?.project_id;
   if(!parentId)break;
   id=parentId;
  }
  const root=roots.get(id)??id;
  for(const member of path)roots.set(member,root);
  return root;
 }
 const groups=new Map();
 // The API supplies newest first. Keep that order, with the original first inside each entry.
 for(const project of projects){
  const id=originalId(project.id);
  if(!groups.has(id))groups.set(id,{id,original:byId.get(id),versions:[]});
  const versions=groups.get(id).versions;
  if(project.id===id)versions.unshift(project);
  else versions.push(project);
 }
 return groups.values();
}

function versionCaption(project,originalTitle,sequence){
 if(!project.parent_revision)return project.title;
 const name=project.title.replace(/(?:\s*·\s*(?:revision|QA draft))+$/gi,'').trim();
 let purpose=tr('Model inputs','模型输入');
 if(project.feedback_spec)purpose=tr('Field feedback','现场反馈');
 else if(/· QA draft/i.test(project.title))purpose=tr('Geometry and QA','几何与 QA');
 else if(name&&name!==originalTitle)purpose=name;
 const date=new Date(project.created_utc||project.parent_revision?.created_utc);
 const time=Number.isFinite(date.getTime())?' · '+date.toLocaleString(lang==='zh'?'zh-CN':'en-US'):'';
 return (sequence?tr('Revision ','修订 ')+sequence:tr('Revision','修订'))+' · '+purpose+time;
}
function indexEditions(projects,deleted){
 const numbers=new Map();
 for(const family of savedProjectGroups([...projects,...deleted],[])){
  const editions=family.versions.filter(p=>p.id!==family.id).sort((a,b)=>(a.created_utc||'').localeCompare(b.created_utc||'')||a.id.localeCompare(b.id));
  editions.forEach((p,i)=>{numbers.set(p.id,i+1);writeDraft(draftKey('edition',p.id),{rootTitle:family.original?.title||family.id,sequence:i+1});});
 }
 return numbers;
}
async function renderSavedProjects(parent){
 const data=await api('state');parent.replaceChildren();
 parent.append(el('h2',tr('Saved projects','已保存的项目')));
 if(!data.projects.length)parent.append(el('p',tr('No saved projects yet.','暂无已保存项目。'),'muted'));
 const deleted=data.deleted_projects||[];
 const sequenceById=indexEditions(data.projects,deleted);
 for(const group of savedProjectGroups(data.projects,deleted)){
  const title=group.original?.title??group.id;
  const count=group.versions.length;
  const entry=details(parent,title+' · '+count+(count===1?' version':' versions'),title+' · '+count+' 个版本',false,'project-group/'+group.id);
  if(!group.original)entry.append(el('p',tr('The original project is unavailable.','本机缺少原项目记录。'),'muted'));
  else if(group.versions[0].id!==group.id)entry.append(el('p',tr('The original project is in Deleted projects.','原项目已移至回收站。'),'muted'));
  for(const project of group.versions){
   const sequence=sequenceById.get(project.id);
   renderProjectCard(entry,project,false,parent,project.id===group.id,versionCaption(project,title,sequence));
  }
 }
 if(deleted.length){
  const trash=details(parent,'Deleted projects ('+deleted.length+')','回收站（'+deleted.length+'）',false,'deleted-projects');
  trash.append(el('p',tr('Deleted projects keep their files on this computer and can be restored. These files still use disk space and remain available to related revisions.','回收站保留本机项目文件，可随时恢复。文件仍占用磁盘空间，关联修订版可继续使用。'),'muted'));
  for(const project of deleted)renderProjectCard(trash,project,true,parent);
 }
}

function renderProjectCard(parent,project,deleted,list,original=false,caption=project.title){
 const card=el('div',undefined,'card');card.dataset.projectId=project.id;parent.append(card);
 if(original)card.append(el('span',tr('Original','原项目'),'tag'));
 card.append(el('h3',caption),el('p',deleted?tr('Deleted · can restore','已删除 · 可恢复'):stateLabel(project.status),'status'));
 if(project.parent_revision&&project.job?.action){const actions={run:tr('HEC-RAS run','HEC-RAS 计算'),'resume-run':tr('Resume approved run','恢复已确认计算'),delivery:tr('Package export','交付包导出'),'check-batch':tr('Follow-up checks','后续复核批次'),analyze:tr('Source analysis','资料解析')};if(actions[project.job.action])card.append(el('small',tr('Latest task: ','最近任务：')+actions[project.job.action]));}
 const actions=el('div',undefined,'actions');card.append(actions);
 if(deleted){
  actions.append(button('Restore project','恢复项目',async()=>{
   await api('restore-project',{id:project.id});await renderSavedProjects(list);
   notify(tr('Project restored: ','项目已恢复：')+project.title);
  }));
  return;
 }
 actions.append(button('Open / continue','打开／继续',async()=>{await open(project.id);notify();}));
 const manage=details(card,'Manage this version','管理此版本',false,'manage/'+project.id);manage.append(el('p',project.id,'muted'));const remove=el('button',tr('Delete project','删除项目'),'danger');remove.type='button';manage.append(remove);
 const confirmation=el('div');confirmation.hidden=true;manage.append(confirmation);
 confirmation.append(el('p',tr('Move “','将“')+project.title+tr('” to Deleted projects? You can restore it later. Project files stay available to related revisions.','”移至回收站？之后可恢复，关联修订版仍可使用其文件。'),'warning'));
 const choices=el('div',undefined,'actions');confirmation.append(choices);
 const confirm=button('Confirm deletion','确认删除',async()=>{
  await api('delete-project',{id:project.id,revision:project.revision,confirmed:true});
  await renderSavedProjects(list);notify(tr('Moved to Deleted projects: ','已移至回收站：')+project.title);
 },'danger');
 const cancel=el('button',tr('Cancel','取消'));cancel.type='button';choices.append(confirm,cancel);
 remove.onclick=()=>{confirmation.hidden=false;remove.hidden=true;cancel.focus();};
 cancel.onclick=()=>{confirmation.hidden=true;remove.hidden=false;remove.focus();};
 if(project.status==='PROCESSING'){
  remove.disabled=true;remove.title=tr('Wait for this project’s task to finish.','请等待此项目的当前任务结束。');
  card.append(el('small',tr('Deletion is available after the current task finishes.','当前任务结束后可删除项目。')));
 }
}

function nativeSelector(parent,existing=true){parent.append(el('p',tr('Choose the project, selected plan, geometry and steady-flow input files together. Previous results are not imported.','一次选择工程、目标计划、几何和恒定流输入文件，不导入旧结果。')));const input=field(parent,'native-files','Native input files (.prj, .pNN, .gNN, .fNN)','原生输入文件（.prj、.pNN、.gNN、.fNN）','','file');input.multiple=true;const advanced=details(parent,'Or use a local project path','或填写本机工程路径');field(advanced,'native-path','Full path to .prj','原生 .prj 完整路径');field(parent,'native-plan','Steady plan (blank uses saved plan)','恒定流计划（留空使用已保存计划）','','text');if(existing)parent.append(button('Read model inputs','读取模型输入',async()=>{const body=await nativeBody();await api('native',{id:current.id,...body});await open(current.id);}));}
async function encodeFiles(files){const out=[];for(const file of files){if(file.size>15000000)throw Error(tr('Each file must be at most 15 MB','每份文件不超过 15 MB'));const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});out.push({name:file.name,content});}return out;}
async function nativeBody(){const files=await encodeFiles($('#native-files').files);const native_path=$('#native-path').value.trim(),selected_plan=$('#native-plan').value.trim();if(!files.length&&!native_path)throw Error(tr('Select native inputs or enter a project path','请选择原生文件或填写工程路径'));return {files,native_path,selected_plan};}
async function pollProject(id){
 if(current?.id!==id)return;
 try{await open(id);}
 catch(error){
  if(current?.id!==id)return;
  notify(tr('Progress connection interrupted; retrying in 5 seconds. ','进度连接中断，5 秒后自动重试。')+error.message,true);
  poll=setTimeout(()=>pollProject(id),5000);
 }
}
async function open(id){const request=++viewRequest,changed=current?.id!==id,wasProcessing=!changed&&current?.status==='PROCESSING';clearTimeout(poll);const next=await api('project/'+id);if(viewRequest!==request)return;if(wasProcessing&&next.status==='PROCESSING'&&document.getElementById('task-progress')){
 const changed=[ 'phase','job','check_batch_progress','study_progress' ].some(key=>JSON.stringify(current[key])!==JSON.stringify(next[key]));
 current=next;if(changed)updateProcessing(next);poll=setTimeout(()=>pollProject(id),2500);return;
 }
 if(next.parent_revision&&!readDraft(draftKey('edition',id))){
  const list=await api('state');if(viewRequest!==request)return;indexEditions(list.projects,list.deleted_projects||[]);
 }
 current=next;pendingChanges.clear();edited={};metaEdits={};classEdits={};dirty=false;render();if(changed)window.scrollTo(0,0);if(current.status==='PROCESSING')poll=setTimeout(()=>pollProject(id),2500);else if(wasProcessing)notify(current.job?.status==='FAILED'?(current.errors||[]).join('\n'):current.job?.action==='automatic-prepare'?tr('Automatic draft saved. Review the highlighted interpretations, then confirm all calculation inputs.','自动草稿已保存。请核对集中列出的判断项，然后确认全部运算参数。'):current.results?tr('Calculation and export task finished. Review the results and delivery status.','任务已完成，请查看计算结果和交付状态。'):tr('Preparation finished. Review the model inputs.','资料准备完成，请核对模型输入。'),current.job?.status==='FAILED');}
function projectHeading(m){
 if(!m.parent_revision)return m.title;
 const info=readDraft(draftKey('edition',m.id))||{},root=info.rootTitle||m.title.replace(/(?:\s*·\s*(?:revision|QA draft))+$/gi,'').trim();
 return root+' · '+versionCaption(m,root,info.sequence);
}
function updateProcessing(m){
 const region=document.getElementById('task-progress');
 region.replaceChildren();region.append(el('p',m.phase?.startsWith('CHECK_BATCH_')?checkStepName(m.phase.slice(12).toLowerCase()):({RUN:tr('Starting HEC-RAS','正在启动 HEC-RAS'),HEC_RAS_REPORTS_DELIVERY:tr('Calculating and preparing reports and maps','正在计算并制作报告与地图'),PREPARE:tr('Preparing model inputs','正在准备模型输入')})[m.phase]||m.phase));if(m.check_batch_progress)renderCheckBatchProgress(region,m.check_batch_progress);if(m.study_progress)renderStudyProgress(region,m.study_progress);
 document.getElementById('task-record').textContent=JSON.stringify(m.job,null,2);
}
function render(){const m=current;rememberView({project:m.id,page:'model'});shell(m.results?3:m.status==='PROCESSING'&&m.job?.action==='run'?2:1);const screen=$('#screen');screen.append(button('← Projects','← 项目列表',async()=>{await save();await home();notify();}),el('h1',projectHeading(m)),el('p',batchHeadline(m)||stateLabel(m.status),batchHeadline(m)?'warning':'status'));if(!m.results||m.status==='PROCESSING')renderPilotClock(screen);if(m.status==='ABANDONED'){screen.append(el('p',tr('Inputs and results are retained. Create a new project to restart.','输入和结果已保留，需要重新开始时请建立新项目。')));return;}if(m.status==='PROCESSING'){
 const region=el('section');region.id='task-progress';region.setAttribute('aria-label',tr('Task progress','任务进度'));
 screen.append(el('div',undefined,'progress'),el('p',tr('Working locally. You may close this browser tab; keep the launcher running.','正在本机处理。可关闭浏览器标签页，请保留启动程序。')),region);
 const record=el('pre');record.id='task-record';details(screen,'Technical details','技术详情').append(record);updateProcessing(m);return;
 }
 if(m.results&&m.status!=='ABANDONED'){renderResults(screen);return;}
 renderTaskRecovery(screen,m);if(m.calculation_recovery&&m.calculation_recovery.mode!=='REVIEW_INPUTS'&&!m.results?.run_id)return;if(m.feedback_spec&&(m.job?.status==='FAILED'||!m.results)){screen.append(button('Resume confirmed field check','继续已确认的现场情景',async()=>{await api('field/resume',{id:m.id,confirmed:true});await open(m.id);}));if(!m.results)return;}if(m.summary){screen.append(el('p',tr('L0 · The saved calculation evidence is unavailable. Restore the matching summary before reviewing results.','L0 · 保存的计算证据不可用。请恢复对应的汇总文件后再复核结果。'),'warning'));}if(m.feasibility?.state==='outside'){renderFeasibility(screen,m.feasibility,true);return;}
 const preparation=preparationActions(m);
 const ready=m.missing.length===0&&(m.native||m.intake?.section_count)&&!preparation.length;
 const reviewInputs=()=>button('Review calculation inputs →','核对运算输入 →',()=>showFinalReview(), 'primary');
 if(ready){
  const summary=el('section',undefined,'card');screen.append(summary);
  summary.append(el('h2',tr('Ready for input review','可以核对运算输入')),el('p',m.native?tr('The selected native plan is available for review.','所选原生计划已就绪。'):m.intake.section_count+tr(' cross sections prepared. Check the flow, boundaries and assumptions before running.',' 条断面已就绪。开算前请核对流量、边界和假设。')),reviewInputs());
 }
 renderPreparationActions(screen,preparation);
 const requests=siteEvidenceRequests(m.intake?.fields||[]);
 if(requests.length&&!m.native){
  const panel=details(screen,'Request site records or measurements','集中索取现场资料与补测');
  panel.append(el('p',tr('One worksheet per source includes gaps and values that need verification. Enter new measurements in value. Current values are provided for reference.','按资料来源生成索取表，合并缺项和待核对的已采用值。新测量填入 value 列，current_value 列供参考。')));
  renderRequestBundles(panel,requests);
 }
 const scope=ready?details(screen,'Model scope and data limitations','模型适用范围与资料限制'):screen;
 renderFeasibility(scope,m.feasibility,true);
 const editor=ready?details(screen,'Inspect or edit the prepared model','检查或修改已准备的模型'):screen;
 if(m.native){renderNative(editor);renderSources(editor);}else renderManual(editor);
 const pending=details(screen,'Missing values / checks','缺失项／检查结果',false);if(m.missing.length){pending.append(el('p',tr('Supply the listed model inputs or read a complete native model. ','补齐列出的模型输入，或读取完整原生模型。')+m.missing.length+tr(' checks remain.',' 项待处理。')));const list=el('ul');for(const text of m.missing.slice(0,8))list.append(el('li',text));pending.append(list);if(m.missing.length>8){const rest=details(pending,'Show every missing field','展开全部缺失字段');const all=el('ul');for(const text of m.missing.slice(8))all.append(el('li',text));rest.append(all);}}else pending.append(el('p',tr('Required technical checks are satisfied for a conditional computation.','条件性计算所需的技术输入检查已通过。')));const actions=el('div',undefined,'actions');editor.append(actions);actions.append(button('Save all changes','保存全部更改',async()=>{await saveAll();await open(m.id);notify(tr('Saved locally','已保存到本机'));}));if(!ready)actions.append(reviewInputs());
 const utilities=details(screen,'Project options','项目管理');renderHandoff(utilities);const leave=details(utilities,'Stop this project','停止此项目');leave.append(el('p',tr('Abandoning stops further actions and retains saved files.','放弃将停止后续操作，已保存文件仍保留。')),button('Abandon workflow','放弃工作流',async()=>{const b=button('Confirm abandonment — keep saved files','确认放弃，保留已存文件',async()=>{await api('abandon',{id:m.id});await open(m.id);});leave.append(el('p',tr('Click the confirmation below to stop. You may continue editing if you change your mind.','点击下方确认按钮才会放弃，也可继续编辑取消此操作。'),'warning'),b);b.scrollIntoView({block:'nearest'});}));}
function mark(){dirty=true;clearTimeout(saveTimer);notify(tr('Unsaved changes','更改尚未保存'),false,'caution');saveTimer=setTimeout(async()=>{if(busy){mark();return;}try{await save();notify(tr('Saved locally','已自动保存到本机'),false,'success');}catch(e){notify(e.message,true);}},1100);}
async function save(){
 if(!current)return;
 const invalid=document.querySelector('input:invalid,textarea:invalid');if(invalid){invalid.reportValidity();throw Error(tr('Correct the highlighted value before continuing','请先修正标出的无效值'));}
 clearTimeout(saveTimer);if(savePromise){await savePromise;if(dirty)return save();return;}if(!current||!dirty)return;
 const id=current.id,metadata={...metaEdits},values={...edited},classes={...classEdits},gis=current.gis;metaEdits={};edited={};classEdits={};dirty=false;
 savePromise=(async()=>{try{const result=await api('save',{id,revision:current.revision,metadata,values:Object.keys(values).length?values:undefined,classes,gis});if(current?.id===id){const pendingGis=current.gis;current=result;if(dirty)current.gis=pendingGis;}}catch(e){metaEdits={...metadata,...metaEdits};edited={...values,...edited};classEdits={...classes,...classEdits};dirty=true;throw e;}finally{savePromise=null;}})();
 await savePromise;if(dirty)await save();
}
window.addEventListener('beforeunload',e=>{if(dirty||savePromise||mapDirty||pendingChanges.size){e.preventDefault();e.returnValue='';}});
function metadata(parent,native){const grid=el('div',undefined,'grid');parent.append(grid);const m=current.metadata;const add=(key,en,zh,kind='text',options=null)=>field(grid,'meta-'+key,en,zh,m[key]||'',kind,options,v=>{metaEdits[key]=v;mark();});if(native){add('native_length_unit','Model foot convention','模型英尺定义','select',[['','Select','请选择'],['US survey foot','US survey foot','美制测量英尺'],['international ft','International foot','国际英尺']]);add('vertical_datum','Model elevation datum','模型高程基准');}if(current.gis||!native){if(native)add('horizontal_crs','Native model projected CRS (EPSG)','原生模型投影坐标系（EPSG）');add('dem_vertical_unit','DEM elevation unit','DEM 高程单位','select',[['','Select','请选择'],['m','Metres','米'],['US survey foot','US survey feet','美制测量英尺'],['international foot','International feet','国际英尺']]);add('dem_vertical_datum','DEM elevation datum','DEM 高程基准');}if(current.terrain_metadata){const d=details(parent,'Automatic metadata / remaining uncertainty','自动获取的元数据／剩余不确定性');d.append(el('pre',JSON.stringify(current.terrain_metadata,null,2)));}}
function renderNative(screen){const n=current.native,box=el('section',undefined,'card');screen.append(box);box.append(el('h2',tr('Model inputs read','模型输入已读取')),el('p',`${n.plan} · ${n.title} · ${n.regime}`),el('p',tr('Saved source plan: ','来源原保存计划：')+n.saved_plan));table(box,[tr('Profile','工况'),tr('Flow (cfs)','流量（cfs）')],n.profiles.map(p=>[p.id,p.flow_cfs]));table(box,[tr('Group','涵孔组'),tr('Shape','形状'),tr('Count','孔数'),'Width / height (ft)','Length (ft)','US / DS invert (ft)'],n.structure.groups.map(g=>[g.name,g.shape,g.count,`${g.span_ft} / ${g.rise_ft}`,g.length_ft,`${g.us_invert_ft} / ${g.ds_invert_ft}`]));const detailsBox=details(box,'Sections, roughness and boundaries','断面、糙率与边界');table(detailsBox,['RS','Banks (ft)','Manning n subdivisions'],n.sections.map(x=>[x.rs,x.banks.join(' / '),JSON.stringify(x.manning)]));detailsBox.append(el('pre',JSON.stringify(n.boundaries,null,2)));if(n.prior_flow_matches.length)box.append(el('p',tr('Previously entered discharge matches the native profile and is retained.','先前填写的流量与原生工况匹配，原输入已保留。')));if(n.conflicts.length){box.append(el('p',n.conflicts.join('\n'),'warning'),button('Use native values instead of earlier entries','改用原生模型参数（保留先前记录）',async()=>{await save();await api('use-native-values',{id:current.id,revision:current.revision,use_native:true});await open(current.id);}));}const meta=el('section',undefined,'card');screen.append(meta);meta.append(el('h2',tr('Units and map context','单位与地图信息')));check(meta,'Include GIS / Mapper / exhibits','包含 GIS、Mapper 和展示图',current.gis,async v=>{current.gis=v;mark();await task(async()=>{await save();render();});});metadata(meta,true);const replace=details(screen,'Use a different native model','改用其他原生模型');nativeSelector(replace);}
function parseInput(f,value){
 if(value.trim()==='')return null;
 if(['number','integer'].includes(f.kind)){const n=Number(value);if(!Number.isFinite(n)||f.kind==='integer'&&!Number.isInteger(n))throw Error(tr('Enter a valid '+f.kind,'请输入有效数值'+(f.kind==='integer'?'（整数）':'')));return n;}
 if(['array','matrix'].includes(f.kind)){const row=s=>s.trim().split(/[,，\s]+/).filter(Boolean).map(Number);const v=value.trim().startsWith('[')?JSON.parse(value):(f.kind==='matrix'?value.trim().split(/\r?\n/).map(row):row(value));if(!Array.isArray(v)||!(f.kind==='matrix'?v.every(r=>Array.isArray(r)&&r.length&&r.every(Number.isFinite)):v.every(Number.isFinite)))throw Error(tr('Use finite numbers separated by commas; matrix rows go on separate lines.','请输入逗号分隔的有限数值，矩阵每行一组。'));return v;}
 return value;
}
function format(v,kind){if(v==null)return '';if(kind==='matrix'&&Array.isArray(v))return v.map(p=>p.join(', ')).join('\n');if(Array.isArray(v))return v.join(', ');return String(v);}
function svgEl(svg,tag,attrs){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);svg.append(e);return e;}
function renderBanks(parent,review){
 review=structuredClone(review);
 const box=el('div',undefined,'card');parent.append(box);
 box.append(el('h3',tr('Bank positions','左右岸位置')));
 const choose=field(box,'bank-section','Cross section','断面','0','select',review.sections.map((row,i)=>[String(i),'RS '+row.rs,'RS '+row.rs]));
 const chart=document.createElementNS('http://www.w3.org/2000/svg','svg');
 chart.setAttribute('viewBox','0 0 700 240');chart.classList.add('chart');box.append(chart);
 const selections=readBankChoices('single-banks',review,box);
 let side=null,picks=null,numbers=null,sectionIndex=0;
 const buttons=el('div',undefined,'actions');box.append(buttons);
 const left=button('Pick left bank','选择左岸',async()=>{side=side===0?null:0;draw(false);});
 const right=button('Pick right bank','选择右岸',async()=>{side=side===1?null:1;draw(false);});
 buttons.append(left,right);
 const info=el('p');box.append(info);

 async function commitBanks(){
  validateBankInputs(box);await save();
  const sections=[...selections].map(([index,bank_indices])=>bankSelection(review,index,bank_indices));
  current=await api('geometry/banks',{id:current.id,revision:current.revision,sections});
  for(const {index} of sections){review.sections[index]=structuredClone(current.intake.geometry_review.sections[index]);}
  selections.clear();storeBankChoices('single-banks',review,selections);pendingChanges.delete('single-banks');showPending();
 }
 function selectBanks(pair){
  picks=pair.slice();selections.set(sectionIndex,picks.slice());storeBankChoices('single-banks',review,selections);
  stageChange('single-banks',tr('Bank positions','左右岸位置'),selections.size,commitBanks);
  draw(false);
 }
 buttons.append(button('Use these bank positions','采用当前岸站',async()=>{
  validateBankInputs(box);
  if(!selections.size)selectBanks(picks);
  await saveAll(['single-banks']);await open(current.id);
  notify(tr('Bank positions saved.','岸站已保存。'));
 }));
 function draw(reset=true){
  const row=review.sections[sectionIndex],x=row.station_ft,z=row.elevation_ft;
  if(reset)picks=selections.get(sectionIndex)?.slice()||row.bank_stations_ft?.map(value=>x.indexOf(value))||row.bank_candidates?.selected_indices?.slice()||[null,null];
  chart.replaceChildren();
  const low=Math.min(...z.filter(Number.isFinite)),high=Math.max(...z.filter(Number.isFinite));
  const point=i=>[45+(x[i]-x[0])/(x.at(-1)-x[0])*620,200-(z[i]-low)/Math.max(high-low,1)*170];
  profileGrid(chart,x,low,high,[45,665,30,200]);numbers?.sync();
  svgEl(chart,'polyline',{points:z.map((value,i)=>Number.isFinite(value)?point(i).join(','):'').join(' '),fill:'none',stroke:'#6e5334','stroke-width':2});
  z.forEach((value,i)=>{
   if(!Number.isFinite(value))return;
   const [cx,cy]=point(i);
   const marker=svgEl(chart,'circle',{cx,cy,r:picks.includes(i)?6:3,fill:picks.includes(i)?'#b55c16':'#286954'});
   marker.onclick=()=>{if(side===null)return;const pair=picks.slice();pair[side]=i;selectBanks(pair);};
  });
  left.setAttribute('aria-pressed',String(side===0));right.setAttribute('aria-pressed',String(side===1));
  info.textContent=tr('Uncertainty: ','不确定性：')+(review.bank_review?.sections[sectionIndex]?.reasons||row.bank_candidates?.reasons||[]).map(bankReviewReason).join(' · ');
 }
 function numericEditor(){
  box.querySelector('[data-bank-numbers]')?.remove();
  const host=el('div');host.dataset.bankNumbers='true';box.append(host);
  numbers=bankNumberInputs(host,'single-bank',review.sections[sectionIndex],()=>picks,selectBanks);
  numbers.sync();
 }
 choose.onchange=()=>{
  try{validateBankInputs(box);}catch(error){choose.value=String(sectionIndex);notify(error.message,true);return;}
  sectionIndex=Number(choose.value);numbers=null;draw();numericEditor();
 };
 draw();numericEditor();
 if(selections.size)stageChange('single-banks',tr('Bank positions','左右岸位置'),selections.size,commitBanks);
}
function renderResults(screen){
 const r=current.results,pages=resultPages(screen);
 const overview=pages.overview;
 const recovery=details(pages.review,'Task details and recovery','批次详情与恢复',false,'result-task-recovery');
 recovery.id='qa-tool-recovery';
 renderTaskRecovery(recovery,current);
 if(current.feedback_spec&&current.job?.status==='FAILED')recovery.append(button('Resume confirmed field check','继续已确认的现场情景',async()=>{await api('field/resume',{id:current.id,confirmed:true});await open(current.id);}));
 if(!recovery.childElementCount)recovery.parentElement.hidden=true;
 const summary=el('section',undefined,'result-summary');overview.append(summary);
 const profiles=r.metrics||[];
 const values=profiles.map(p=>p.flow_cfs).filter(Number.isFinite);
 const flows=values.length===profiles.length&&values.length
  ?(Math.min(...values)===Math.max(...values)?String(values[0]):Math.min(...values)+'–'+Math.max(...values))+' cfs':'';
 const available=(current.report_files||[]).some(file=>file.name.endsWith('.pdf'));
 const report=available?tr('PDF reports available','PDF 报告可查看'):tr('Check report export','请检查报告导出');
 const profileCount=profiles.length===1?profiles[0].profile_id:profiles.length+tr(' profiles',' 个工况');
 summary.append(el('p',[profileCount,flows,report].filter(Boolean).join(' · '),'status'));
 renderGuidance(summary,pages.review);
 if(batchHeadline(current))summary.prepend(button('Review unfinished checks','查看未完成的复核',()=>openGuidanceTool('recovery')));
 else if(recovery.childElementCount)summary.prepend(button('Review task and recovery options','查看任务详情与恢复操作',()=>openGuidanceTool('recovery')));

 overview.append(el('h2',tr('Hydraulic results','水力计算结果')));
 const fmt=v=>v==null?'—':Number(v).toFixed(3);
 const river=current.model_type==='river';
 const columns=river?[tr('Upstream WSE (ft)','上端水位 (ft)'),tr('Downstream WSE (ft)','下端水位 (ft)'),tr('Max channel velocity (ft/s)','最大主槽流速 (ft/s)')]:[tr('Headwater (ft)','进口水位 (ft)'),tr('Tailwater (ft)','出口水位 (ft)'),tr('Inlet velocity (ft/s)','进口流速 (ft/s)'),tr('Road flow (cfs)','路面流量 (cfs)')];
 const keys=river?['upstream_wse_ft','downstream_wse_ft','max_channel_velocity_fts']:['headwater_wse_ft','tailwater_wse_ft','inlet_velocity_fts','roadway_flow_software_cfs'];
 table(overview,[tr('Profile','工况'),'Q (cfs)',...columns],(r.metrics||[]).map(p=>[p.profile_id,Number.isFinite(p.flow_cfs)?Number(p.flow_cfs.toFixed(3)):'—',...keys.map(k=>fmt(p.metrics[k]))]));
 if(current.field_response)renderFieldResponse(overview,current.field_response);
 const d=current.delivery;
 if(!d||!['READY_FOR_REVIEW'].includes(d.status)||current.exports_need_refresh)overview.append(el('p',tr('Review the export status under Reports and maps before sharing.','发送前请打开“报告与地图”核对导出状态。'),'warning'));

 if(!current.native_review){const revise=guidanceTarget(details(pages.review,'Revise inputs / compare a new run','修改参数／对比重算'),'revision');revise.append(el('p',tr('Create a separate editable revision. This completed project and its results remain saved. No calculation starts until you confirm the revised parameters.','创建独立可编辑修订版，保留当前完整项目和结果。核对并确认修订参数后才会重新计算。')),button('Create editable revision','创建可编辑修订版',async()=>{const next=await api('revision',{id:current.id,revision:current.revision,confirmed:true});await open(next.id);notify(tr('Revision ready. Edit parameters, then confirm to calculate.','修订版已就绪；修改参数后统一确认计算。'));}));}
 if(current.comparison)renderRevisionComparison(pages.review,current.comparison);

 if(river&&!current.native_review)renderExtentReview(pages.review);
 const issues=r.diagnostics?.issues||[],groups={};for(const i of issues)(groups[i.code]??=[]).push(i);const qa=guidanceTarget(details(pages.review,'Automatic checks and warnings ('+issues.length+')','自动检查与警告（'+issues.length+'）',false),'qa');for(const[code,rows]of Object.entries(groups)){const b=details(qa,code+' · '+rows.length,code+' · '+rows.length);table(b,['Profile','RS','Severity','Action'],rows.map(i=>[i.profile,i.station,i.severity,i.recommended_action]));}qa.append(el('p',tr('Full native warning-table coverage: ','完整原生警告表覆盖状态：')+warningCoverageLabel(r.diagnostics?.warning_coverage)));
 renderResultTools(pages.review,pages.delivery);
 const delivery=pages.delivery;
 const files=el('section');delivery.prepend(files);
 files.append(el('h2',tr('Reports','报告')));
 const reports=current.report_files||[];
 const pdf=el('div',undefined,'actions');files.append(pdf);
 const other=reports.some(f=>!f.name.toLowerCase().endsWith('.pdf'))?details(files,'Editable report files','可编辑版报告'):null;
 for(const f of reports){
  const captions={'Report_EN.pdf':['English report (PDF)','英文报告（PDF）'],'Report_CN.pdf':['Chinese report (PDF)','中文报告（PDF）'],'Summary_EN.pdf':['English summary (PDF)','英文摘要（PDF）']};
  const a=el('a',captions[f.name]?tr(...captions[f.name]):f.name,'link');
  a.href='file/'+f.path;a.target='_blank';a.rel='noopener';
  (f.name.toLowerCase().endsWith('.pdf')?pdf:other).append(a);
 }
 if(!reports.length)files.append(el('p',tr('Report files are pending.','报告文件待生成。'),'warning'));
 files.append(guidanceTarget(el('h2',tr('Delivery packages','交付包')),'recipient'));
 if(d){
  files.append(el('p',tr('Delivery status: ','交付状态：')+deliveryState(d.status),d.status==='INCOMPLETE'?'warning':'status'));
  for(const key of ['minimal','complete'])if(d[key]){
   files.append(button(key==='minimal'?'Open Minimal':'Open Complete',key==='minimal'?'打开最小交付包':'打开完整交付包',()=>api('open-folder',{id:current.id,path:d[key].path})));
  }
  if(d.minimal&&d.complete&&!current.exports_need_refresh)renderRecipientHandoff(files);
  renderDeliveryRecovery(files,d);
 }else files.append(el('p',tr('Delivery packages are pending.','交付包待生成。'),'warning'));
 const actions=details(pages.delivery,'Export again without solving','重新导出（不重新求解）');actions.append(button('Regenerate reports','重新生成报告',async()=>{await api('report',{id:current.id});await open(current.id);}),button('Regenerate delivery','重新生成交付包',async()=>{await api('delivery',{id:current.id});await open(current.id);}));
 renderPilotClock(delivery);renderHandoff(delivery);
 const technical=details(pages.review,'Technical details / provenance','技术详情／来源记录');
 technical.append(el('pre',JSON.stringify({summary:current.summary,job:current.job,results:r},null,2)));
}
$('#language').onclick=()=>task(async()=>{await save();pendingChanges.clear();lang=lang==='en'?'zh':'en';localStorage.setItem('workflow-language',lang);if(finalReview&&finalReview.revision!==current?.revision)await showFinalReview(false);else if(finalReview)renderFinalReview();else if(current)render();else await home();notify(tr('Language set to English.','已切换为简体中文。'));});
