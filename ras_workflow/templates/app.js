'use strict';
let lang=localStorage.getItem('workflow-language')||'en',current=null,busy=false,poll=null,dirty=false,edited={},metaEdits={},mapData=null,anchorMode=null,anchors={upstream:[],downstream:[]};
const $=s=>document.querySelector(s),tr=(en,zh)=>lang==='zh'?zh:en,token=location.pathname.split('/')[1];
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
let saveTimer=null,savePromise=null,pendingMapSave=null,mapDirty=false;
const pendingChanges=new Map();
function stageChange(key,label,count,commit){if(count)pendingChanges.set(key,{label,count,commit});else pendingChanges.delete(key);showPending();}
function showPending(){let node=document.getElementById('pending-changes');if(!node&&document.getElementById('screen')){node=el('div',undefined,'pending-changes');node.id='pending-changes';document.getElementById('screen').prepend(node);}if(node){node.hidden=!pendingChanges.size;node.textContent=tr('Selected changes not saved: ','已选择、尚未保存：')+[...pendingChanges.values()].map(p=>p.label+' '+p.count).join(' · ')+tr(' — Save all or review parameters to apply them.','；点击保存全部或核对参数时统一保存。');}}
async function saveAll(){
 validateBankInputs();
 await save();
 for(const [key,p]of [...pendingChanges].sort(([a],[b])=>(a==='associations'?-1:0)-(b==='associations'?-1:0))){
  notify(tr('Saving ','正在保存 ')+p.label+'…');await p.commit();pendingChanges.delete(key);showPending();
 }
 if(pendingMapSave)await pendingMapSave();
}

function notify(text='',error=false){$('#notice').hidden=!text;$('#notice').textContent=text;$('#notice').className=error?'error':'';}
async function api(route,body){const r=await fetch(route,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Workflow-Token':token},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(data.error||r.status);return data;}
async function task(fn,label=tr('Working','正在处理'),source=null){
 if(busy)return;busy=true;const prior=new Map([...document.querySelectorAll('button,input,select,textarea')].map(b=>[b,b.disabled]));
 const working=label+'…',old=source?.textContent;notify(working);document.body.setAttribute('aria-busy','true');prior.forEach((v,b)=>b.disabled=true);if(source){source.textContent=working;source.classList.add('working');}
 try{if(savePromise)await savePromise;if(pendingMapSave&&pendingMapSave!==fn)await pendingMapSave();await fn();if($('#notice').textContent===working)notify(label+(current?.status==='PROCESSING'?tr(' — started; follow progress below',' — 已启动，请查看下方进度'):tr(' — done',' — 已完成')));}
 catch(e){notify(e.message+tr(' · Saved data retained; correct the input or retry.',' · 已保存数据保留，可修正输入或重试。'),true);}
 finally{busy=false;document.body.removeAttribute('aria-busy');prior.forEach((v,b)=>{if(b.isConnected)b.disabled=v;});if(source?.isConnected){source.textContent=old;source.classList.remove('working');}}
}
function button(en,zh,fn,cls){const b=el('button',tr(en,zh),cls);b.type='button';b.onclick=()=>task(fn,tr(en,zh),b);return b;}
function field(parent,id,en,zh,value='',kind='text',options=null,onchange=null){const box=el('label',undefined,'field');box.append(el('span',tr(en,zh)));let input=el(kind==='select'?'select':kind==='textarea'?'textarea':'input');input.id=id;if(kind==='select'){for(const [v,en0,zh0]of options)input.append(new Option(tr(en0,zh0),v));}else if(kind!=='textarea'){input.type=kind;if(kind==='number'){input.step='any';input.addEventListener('wheel',()=>input.blur(),{passive:true});}}input.value=value??'';if(onchange)input.addEventListener(kind==='select'?'change':'input',()=>onchange(input.value));box.append(input);parent.append(box);return input;}
const expansionState=new Map();
function details(parent,en,zh,open=false){const d=el('details');const key=(current?.id||'home')+'|'+(finalReview?'review':'edit')+'|'+(parent.closest('[data-key]')?.dataset.key||'')+'|'+en;d.open=expansionState.get(key)??open;d.addEventListener('toggle',()=>expansionState.set(key,d.open));d.append(el('summary',tr(en,zh)));const b=el('div');d.append(b);parent.append(d);return b;}
function check(parent,en,zh,value,onchange){const l=el('label',undefined,'check'),i=el('input');i.type='checkbox';i.checked=value;l.append(i,el('span',tr(en,zh)));i.onchange=()=>onchange(i.checked);parent.append(l);return i;}
function table(parent,head,rows){const wrap=el('div',undefined,'scroll'),t=el('table'),hr=el('tr');head.forEach(h=>hr.append(el('th',h)));t.append(hr);for(const row of rows){const r=el('tr');for(const v of row)r.append(el('td',v??'—'));t.append(r);}wrap.append(t);parent.append(wrap);}
function shell(step){$('#steps').replaceChildren();[tr('1 · Project','1 · 建立项目'),tr('2 · Model','2 · 确认模型'),tr('3 · Results','3 · 查看结果')].forEach((s,i)=>$('#steps').append(el('span',s,i===step?'active':'')));$('#language').textContent=lang==='zh'?'English':'简体中文';$('#subtitle').textContent=tr('HEC-RAS · Local computation','HEC-RAS · 本机计算');$('#foot').textContent=tr('1D steady rivers and culverts. Actual HEC-RAS results; assumptions and unresolved checks remain visible. No engineering certification is implied.','1D 恒定流河道与涵洞分析。使用真实 HEC-RAS；保留估计项与未闭合检查，不自动认定设计合格。');$('#screen').replaceChildren();}
const stateLabel=s=>({NEW:tr('New','新建'),PROCESSING:tr('Processing','处理中'),INPUTS_READY:tr('Complete the model','补齐模型'),RESULTS_READY:tr('Computed · review limitations','已计算 · 请查看限制'),RESULTS_READY_MAP_PENDING:tr('Computed · map export needs attention','已计算 · 地图导出待处理'),NEEDS_ATTENTION:tr('Needs attention · draft retained','需处理 · 草稿已保留'),ABANDONED:tr('Abandoned · files retained','已放弃 · 文件保留'),INTERRUPTED:tr('Interrupted · retry available','已中断 · 可重试')}[s]||s);
async function home(){clearTimeout(poll);current=null;dirty=false;mapData=null;shell(0);const screen=$('#screen');screen.append(el('h1',tr('A steady-flow model, with fewer steps','更少步骤，完成恒定流计算')),el('p',tr('Start from a location or a native HEC-RAS model. Supply missing engineering values on one model page.','从坐标或已有 HEC-RAS 工程开始，在一个模型页面补齐必要参数。')));const card=el('section',undefined,'card');screen.append(card);const form=el('div',undefined,'grid');card.append(form);const route=field(form,'route','Starting information','起始资料','coordinates','select',[['coordinates','Coordinates / partial information','坐标／部分资料'],['native','Existing HEC-RAS model','已有 HEC-RAS 工程']]);const modelType=field(form,'model-type','Analysis scope','分析范围','culvert','select',[['culvert','Culvert crossing','涵洞设施'],['river','River reach (bridges excluded)','纯河道（不建桥梁）']]);const title=field(form,'title','Project name','项目名称');const lat=field(form,'latitude','Latitude (WGS84)','纬度（WGS84）','','number'),lon=field(form,'longitude','Longitude (WGS84)','经度（WGS84）','','number');const q=field(form,'flow','Discharge (cfs), if known','流量（cfs，已知时填写）','','number');const more=details(card,'Optional roughness','可选：已知糙率');field(more,'channel_n','Channel Manning n','主槽糙率','','number');field(more,'overbank_n','Overbank Manning n','两侧漫滩糙率','','number');const native=el('div');card.append(native);nativeSelector(native,false);native.hidden=true;route.onchange=()=>{native.hidden=route.value!=='native';};let gis=true;check(card,'Also prepare GIS / Mapper / exhibits','同时准备 GIS、Mapper 和展示图',true,v=>gis=v);card.append(button('Prepare project','准备项目',async()=>{let body={model_type:modelType.value,route:route.value,title:title.value,latitude:lat.value,longitude:lon.value,flow_cfs:q.value,channel_n:$('#channel_n').value,overbank_n:$('#overbank_n').value,gis};if(route.value==='native')Object.assign(body,await nativeBody());const r=await api('create',body);await open(r.id);},'primary'));const saved=el('section');screen.append(saved);await renderSavedProjects(saved);}

async function renderSavedProjects(parent){
 const data=await api('state');parent.replaceChildren();
 parent.append(el('h2',tr('Saved projects','已保存的项目')));
 if(!data.projects.length)parent.append(el('p',tr('No saved projects yet.','暂无已保存项目。'),'muted'));
 for(const project of data.projects)renderProjectCard(parent,project,false,parent);
 const deleted=data.deleted_projects||[];
 if(deleted.length){
  const trash=details(parent,'Deleted projects ('+deleted.length+')','回收站（'+deleted.length+'）');
  trash.append(el('p',tr('Deleted projects keep their files on this computer and can be restored. These files still use disk space and remain available to related revisions.','回收站保留本机项目文件，可随时恢复。文件仍占用磁盘空间，关联修订版可继续使用。'),'muted'));
  for(const project of deleted)renderProjectCard(trash,project,true,parent);
 }
}

function renderProjectCard(parent,project,deleted,list){
 const card=el('div',undefined,'card');card.dataset.projectId=project.id;parent.append(card);
 card.append(el('h3',project.title),el('p',deleted?tr('Deleted · can restore','已删除 · 可恢复'):stateLabel(project.status),'status'),el('small',project.id));
 const actions=el('div',undefined,'actions');card.append(actions);
 if(deleted){
  actions.append(button('Restore project','恢复项目',async()=>{
   await api('restore-project',{id:project.id});await renderSavedProjects(list);
   notify(tr('Project restored: ','项目已恢复：')+project.title);
  }));
  return;
 }
 actions.append(button('Open / continue','打开／继续',()=>open(project.id)));
 const remove=el('button',tr('Delete project','删除项目'),'danger');remove.type='button';actions.append(remove);
 const confirmation=el('div');confirmation.hidden=true;card.append(confirmation);
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
async function open(id){if(pendingChanges.size)await saveAll();const changed=current?.id!==id,wasProcessing=!changed&&current?.status==='PROCESSING';clearTimeout(poll);current=await api('project/'+id);edited={};metaEdits={};classEdits={};dirty=false;render();if(changed)window.scrollTo(0,0);if(current.status==='PROCESSING')poll=setTimeout(()=>pollProject(id),2500);else if(wasProcessing)notify(current.job?.status==='FAILED'?(current.errors||[]).join('\n'):current.job?.action==='automatic-prepare'?tr('Automatic draft saved. Review the highlighted interpretations, then confirm all calculation inputs.','自动草稿已保存。请核对集中列出的判断项，然后确认全部运算参数。'):tr('Background task finished. Review the result and export status below.','后台任务已结束，请查看下方结果和导出状态。'),current.job?.status==='FAILED');}
function render(){const m=current;shell(m.results?2:1);const screen=$('#screen');screen.append(button('← Projects','← 项目列表',async()=>{await saveAll();await home();}),el('h1',m.title),el('p',stateLabel(m.status),'status'));if(m.status==='ABANDONED'){screen.append(el('p',tr('Inputs and results are retained. Create a new project to restart.','输入和结果已保留，需要重新开始时请建立新项目。')));return;}if(m.status==='PROCESSING'){screen.append(el('div',undefined,'progress'),el('p',tr('Working locally. You may close this browser tab; keep the launcher running.','正在本机处理。可关闭浏览器标签页，请保留启动程序。')),el('p',m.phase));const d=details(screen,'Technical details','技术详情');d.append(el('pre',JSON.stringify(m.job,null,2)));return;}if(m.errors?.length){screen.append(el('p',m.errors.join('\n'),'warning'));if(!m.results)screen.append(button('Retry preparation','重试准备',async()=>{await api('prepare',{id:m.id});await open(m.id);}));}if(m.results){renderResults(screen);return;}if(m.native)renderNative(screen);else renderManual(screen);if(m.native)renderSources(screen);const pending=details(screen,'Missing values / checks','缺失项／检查结果',false);if(m.missing.length){pending.append(el('p',tr('Supply the listed model inputs or read a complete native model. ','补齐列出的模型输入，或读取完整原生模型。')+m.missing.length+tr(' checks remain.',' 项待处理。')));const list=el('ul');for(const text of m.missing.slice(0,8))list.append(el('li',text));pending.append(list);if(m.missing.length>8){const rest=details(pending,'Show every missing field','展开全部缺失字段');const all=el('ul');for(const text of m.missing.slice(8))all.append(el('li',text));rest.append(all);}}else pending.append(el('p',tr('Required technical checks are satisfied for a conditional computation.','条件性计算所需的技术输入检查已通过。')));screen.append(el('p',tr('Start uses the displayed inputs for a conditional calculation. User-entered and estimated values remain identified in the saved record. This does not sign off engineering QA.','开始计算将采用页面所示输入进行条件性计算。用户填入值与估计项会保留标记，此操作不签署工程 QA。'),'muted'));const actions=el('div',undefined,'actions');actions.append(button('Save all changes','保存全部更改',async()=>{await saveAll();await open(m.id);notify(tr('Saved locally','已保存到本机'));}),button('Review all parameters →','核对全部参数 →',async()=>{await saveAll();await showFinalReview();},'primary'));screen.append(actions);const leave=details(screen,'Stop this project','停止此项目');leave.append(el('p',tr('Abandoning stops further actions and retains saved files.','放弃将停止后续操作，已保存文件仍保留。')),button('Abandon workflow','放弃工作流',async()=>{const b=button('Confirm abandonment — keep saved files','确认放弃，保留已存文件',async()=>{await api('abandon',{id:m.id});await open(m.id);});leave.append(el('p',tr('Click the confirmation below to stop. You may continue editing if you change your mind.','点击下方确认按钮才会放弃，也可继续编辑取消此操作。'),'warning'),b);b.scrollIntoView({block:'nearest'});}));}
function mark(){dirty=true;clearTimeout(saveTimer);notify(tr('Unsaved changes','更改尚未保存'));saveTimer=setTimeout(async()=>{if(busy){mark();return;}try{await save();notify(tr('Saved locally','已自动保存到本机'));}catch(e){notify(e.message,true);}},1100);}
async function save(){
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
 const selections=new Map();
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
  selections.clear();pendingChanges.delete('single-banks');showPending();
 }
 function selectBanks(pair){
  picks=pair.slice();selections.set(sectionIndex,picks.slice());
  stageChange('single-banks',tr('Bank positions','左右岸位置'),selections.size,commitBanks);
  draw(false);
 }
 buttons.append(button('Use these bank positions','采用当前岸站',async()=>{
  validateBankInputs(box);
  if(!selections.size)selectBanks(picks);
  await saveAll();await open(current.id);
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
  info.textContent=tr('Uncertainty: ','不确定性：')+(row.bank_candidates?.reasons||[]).join('; ');
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
}
function renderResults(screen){const r=current.results;
if(!current.native_review){const revise=details(screen,'Revise inputs / compare a new run','修改参数／对比重算');revise.append(el('p',tr('Create a separate editable revision. This completed project and its results remain saved. No calculation starts until you confirm the revised parameters.','创建独立可编辑修订版，保留当前完整项目和结果。核对并确认修订参数后才会重新计算。')),button('Create editable revision','创建可编辑修订版',async()=>{const next=await api('revision',{id:current.id,revision:current.revision,confirmed:true});await open(next.id);notify(tr('Revision ready. Edit parameters, then confirm to calculate.','修订版已就绪；修改参数后统一确认计算。'));}));}
if(current.comparison)renderRevisionComparison(screen,current.comparison);
screen.append(el('p',tr('Fresh solver run: ','本次求解运行：')+r.run_id),el('p',tr('Calculation completed; hydraulic warnings and engineering acceptance remain separate.','求解完成；水力警告和工程接受仍需分别判断。'),'warning'));const fmt=v=>v==null?'—':Number(v).toFixed(3);if(current.model_type==='river'){table(screen,[tr('Profile','工况'),'Q (cfs)',tr('Upstream WSE ft','上端水位 ft'),tr('Downstream WSE ft','下端水位 ft'),tr('Max channel velocity ft/s','最大主槽流速 ft/s')],(r.metrics||[]).map(p=>[p.profile_id,p.flow_cfs,fmt(p.metrics.upstream_wse_ft),fmt(p.metrics.downstream_wse_ft),fmt(p.metrics.max_channel_velocity_fts)]));}else{table(screen,[tr('Profile','工况'),'Q (cfs)','HW (ft)','TW (ft)',tr('Inlet velocity (ft/s)','进口流速（ft/s）'),tr('Road flow (cfs)','路面流量（cfs）')],(r.metrics||[]).map(p=>[p.profile_id,p.flow_cfs,fmt(p.metrics.headwater_wse_ft),fmt(p.metrics.tailwater_wse_ft),fmt(p.metrics.inlet_velocity_fts),fmt(p.metrics.roadway_flow_software_cfs)]));}const links=el('div',undefined,'actions');screen.append(links);for(const f of current.report_files||[]){const a=el('a',f.name,'link');a.href='file/'+f.path;a.target='_blank';links.append(a);}const d=current.delivery;if(d){screen.append(el('p',tr('Delivery status: ','交付状态：')+d.status));for(const key of ['minimal','complete'])if(d[key]){const path=d[key].path;screen.append(button(key==='minimal'?'Open Minimal':'Open Complete',key==='minimal'?'打开最小交付包':'打开完整交付包',()=>api('open-folder',{id:current.id,path})));}if(d.error)screen.append(el('p',d.error,'warning'));}renderResultTools(screen);const issues=r.diagnostics?.issues||[],groups={};for(const i of issues)(groups[i.code]??=[]).push(i);const qa=details(screen,'Automatic checks and warnings ('+issues.length+')','自动检查与警告（'+issues.length+'）',true);for(const[code,rows]of Object.entries(groups)){const b=details(qa,code+' · '+rows.length,code+' · '+rows.length);table(b,['Profile','RS','Severity','Action'],rows.map(i=>[i.profile,i.station,i.severity,i.recommended_action]));}qa.append(el('p',tr('Full native warning-table coverage: ','完整原生警告表覆盖状态：')+JSON.stringify(r.diagnostics?.warning_coverage||'NOT_EXPORTED')));const actions=details(screen,'Export again without solving','重新导出（不重新求解）');actions.append(button('Regenerate reports','重新生成报告',async()=>{await api('report',{id:current.id});await open(current.id);}),button('Regenerate delivery','重新生成交付包',async()=>{await api('delivery',{id:current.id});await open(current.id);}));const technical=details(screen,'Technical details / provenance','技术详情／来源记录');technical.append(el('pre',JSON.stringify({summary:current.summary,job:current.job,results:r},null,2)));}
$('#language').onclick=()=>task(async()=>{await saveAll();lang=lang==='en'?'zh':'en';localStorage.setItem('workflow-language',lang);if(finalReview)renderFinalReview();else if(current)render();else await home();notify(tr('Language set to English.','已切换为简体中文。'));});
