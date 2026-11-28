async function createTransferFolder(output){
 const id=current.id,revision=current.revision;
 output.textContent=tr('Copying and verifying both packages…','正在复制并校验两种交付包…');
 try{
  const selected=JSON.parse(sessionStorage.getItem('selected-baseline/'+current.summary.sha256)||'null');
  const info=await api('handoff-export',{id,revision,summary_hash:current.summary.sha256,selected_from:selected});
  output.replaceChildren(el('p',tr('English and Chinese opening guides saved','已保存中英文打开说明')+' · L'+info.level+' · '+info.run_id,'status'),
   el('p',tr('Transfer this entire folder. Open Start_EN.html or Start_zh-CN.html. Both verified packages are inside.','整体转交此目录。双击 Start_zh-CN.html 或 Start_EN.html，两种已校验的交付包均在目录内。')),el('code',info.folder),
   button('Open transfer folder','打开可转交目录',()=>api('open-folder',{id,path:info.folder})));
 }catch(error){
  output.textContent=error.message;
  if(sessionStorage.getItem('selected-baseline/'+current.summary.sha256))output.append(button('Review this edition directly','直接复核当前版本',async()=>{
   sessionStorage.removeItem('selected-baseline/'+current.summary.sha256);await open(current.id);
  }));
  throw error;
 }
}
function renderRecipientHandoff(parent){
 const output=el('div');output.id='transfer-status';output.setAttribute('aria-live','polite');
 const action=button('Verify packages and create recipient guide','校验双包并生成收件人说明',()=>createTransferFolder(output));
 const state=el('p');state.id='recipient-action';
 function reflect(){
  const choice=current.iteration_choice?.choice;
  const blocked=['parent','wait','unavailable'].includes(choice);
  action.hidden=blocked;state.hidden=!blocked;output.replaceChildren();
  state.textContent=choice==='parent'?tr('The previous edition was selected. Open it under Summary to hand off its files.','已选用上一版。请从结果总览打开该基准版，再交接其文件。'):tr('Waiting for field records. Resume review under Summary before handoff.','正在等现场资料。资料就绪后可从结果总览继续复核并交接。');
  if(choice==='unavailable')state.textContent=tr('Check the saved choice under Summary before handoff.','交接前请在结果总览重新核对使用版本。');
 }
 state.addEventListener('iteration-updated',reflect);reflect();
 parent.append(state,action,output);renderTeamReview(parent);
}
function renderArchivedEdition(parent,edition,caption,refresh){
 const card=el('div',undefined,'card');card.dataset.projectId=edition.id;parent.append(card);
 const states={ARCHIVED:tr('Archived','已归档'),RETIRING:tr('Cleanup interrupted','清理中断'),RESTORING:tr('Restore interrupted','恢复中断')};
 card.append(el('h3',caption),el('p',states[edition.phase]+' · '+edition.id),el('p',edition.archive,'muted'));
 async function change(action){await api('storage-'+action,{id:edition.id,archive_hash:edition.sha256,confirmed:true});await refresh();}
 card.append(button('Restore this edition','恢复此版本',()=>change('restore')));
 if(edition.phase==='RETIRING')card.append(button('Resume verified cleanup','继续已核验的清理',()=>change('retire')));
}
function renderEditionStorage(parent,edition,refresh){
 const box=details(parent,'Storage and recovery by edition','版本存储与恢复');
 const area=el('div');const size=n=>(n/1048576).toLocaleString(undefined,{maximumFractionDigits:2})+' MiB';
 async function inspect(){
  const p=await api('storage-preview',{id:edition.id});area.replaceChildren();
  area.append(el('p',p.title+' · '+p.id));
  table(area,[tr('Logical','逻辑占用'),tr('Exclusive','独占'),tr('Shared','共享'),tr('Releasable','可释放')],[[p.logical_bytes,p.exclusive_bytes,p.shared_bytes,p.reclaimable_bytes].map(size)]);
  table(area,[tr('Archive upper estimate','归档空间上限估计'),tr('Restore allowance','版本恢复预留'),tr('Workspace free','工作盘当前可用')],[[p.archive_upper_bytes,p.restore_reserve_bytes,p.workspace_free_bytes].map(size)]);
  const categories={inputs:tr('Inputs and project records','原件与项目记录'),delivery:tr('Published packages','已发布交付包'),dependency:tr('Linked data','引用数据'),calculation:tr('Calculation','计算'),export:tr('Temporary exports','临时导出'),study:tr('Studies','复核试算'),preview:tr('Previews','预览'),review:tr('Reviews','复核'),cache:tr('Cache','缓存')};
  categories.reports=tr('Published reports','已发布报告');categories.terrain=tr('Terrain rasters','地形栅格');
  table(area,[tr('Contents','内容'),tr('Files','文件数'),tr('Size','大小'),tr('Shared','共享'),tr('Eligible before protection','保护策略生效前的候选量')],Object.entries(p.groups).map(([k,v])=>[categories[k]||k,v.files,size(v.bytes),size(v.shared_bytes||0),size(v.candidate_bytes||0)]));
  if(p.dependents.length)area.append(el('p',tr('Required by these editions: ','以下版本仍引用本版：')+p.dependents.join(', '),'warning'));
  if(p.unverified_sources?.length)area.append(el('p',tr('Locate originals with these registered fingerprints before cleanup: ','请在清理前找回指纹相符的原件：')+p.unverified_sources.join(', '),'warning'));
  if(p.pinned)area.append(el('p',tr('This edition is pinned.','本版本已固定。')));
  area.append(button(p.pinned?'Unpin edition':'Pin edition',p.pinned?'取消固定':'固定版本',async()=>{await api('storage-pin',{id:edition.id,confirmed:true,pinned:!p.pinned});await inspect();}));
  const candidates=details(area,'Preview cleanup candidates ('+p.candidate_files+')','查看清理候选（'+p.candidate_files+'）');
  if(p.candidate_files)candidates.append(el('pre',p.candidates.join('\n')));
  area.append(el('p',tr('Choose an existing local folder outside the checkout. The archive uses space on that drive. Published packages, original inputs and shared terrain stay online during cleanup.','选择工作目录外已有的本机目录。归档会占用所选磁盘空间。清理时已发布双包、原始输入和共享地形继续可用。')));
  const dir=field(area,'archive-dir-'+edition.id,'Archive folder','归档目录',p.default_directory);
  const batch=details(area,'Estimate space for similar runs','预估同类批次所需空间');
  batch.append(el('p',tr('Budget one retained copy and one archive per edition, one temporary working copy for serial processing, and room to restore one edition. Larger terrain and concurrent jobs need a separate estimate.','按每版一份工作文件和一份归档、串行处理一份临时副本及恢复一个版本估算。更大地形或并发任务需另行估算。')));
  const count=field(batch,'capacity-count-'+edition.id,'Number of similar editions','同类版本数',1,'number');
  count.min=1;count.max=10000;count.step=1;
  const output=el('div');output.id='capacity-estimate-'+edition.id;output.setAttribute('aria-live','polite');
  batch.append(button('Estimate peak space','预估空间峰值',async()=>{
    output.replaceChildren();
    const path=dir.value,editions=Number(count.value);
    const r=await api('storage-capacity',{id:edition.id,token:p.token,directory:path,editions});
    if(path!==dir.value||editions!==Number(count.value))return;
    output.dataset.state=r.status;
    output.append(el('p',r.status==='READY'?tr('Estimated space is available.','当前空间满足估算。'):tr('More space is required.','当前可用空间不足。')));
    table(output,[tr('Workspace peak','工作盘峰值'),tr('Archive allowance','归档用量'),tr('Restore reserve','恢复预留'),tr('Workspace shortage','工作盘缺口'),tr('Archive drive shortage','归档盘缺口')],[[r.workspace_needed_bytes,r.archive_bytes,r.restore_reserve_bytes,r.workspace_short_bytes,r.archive_short_bytes].map(size)]);
  }),output);
  const clear=()=>{output.replaceChildren();delete output.dataset.state;};
  count.oninput=clear;dir.oninput=clear;
  area.append(button('Create verified archive','创建并校验归档',async()=>{await api('storage-archive',{id:edition.id,confirmed:true,token:p.token,directory:dir.value});await inspect();}));
  if(p.archive)area.append(el('p',tr('Archive','归档')+' · '+size(p.archive_bytes)+' · '+p.archive));
  if(p.matches_archive&&p.reclaimable_bytes>0){
   if(p.same_volume)area.append(el('p',tr('Estimated net space gained on this drive including the ZIP: ','计入同盘归档后，预计磁盘净释放：')+size(p.reclaimable_bytes-p.archive_bytes),'muted'));
   const confirm=details(area,'Release archived working files','释放已归档的工作文件');
   confirm.append(el('p',tr('Restoring this edition will require the verified ZIP at its registered location.','恢复该版本需要已登记位置的归档 ZIP。')+' '+size(p.reclaimable_bytes)));
   confirm.append(button('Confirm cleanup of this edition','确认清理此版本',async()=>{const r=await api('storage-retire',{id:edition.id,confirmed:true,token:p.token,archive_hash:p.archive_hash});await refresh();notify(tr('Edition archived. Volume free-space change: ','版本已归档，磁盘可用空间变化：')+size(r.actual_volume_gain));}));
  }
 }
 box.append(button('Inspect edition storage','查看版本占用',inspect),area);
}
function renderHandoff(parent) {
 renderEditionStorage(parent,current,home);
 const box=details(parent,'Handoff, local files and optional pilot timing','交付预览、本地文件与可选试点计时');
 const area=el('div');box.append(area);
 async function inspect(){
  const key={id:current.id,revision:current.revision};
  const view=await api('handoff-inspect',key),p=view.package;
  area.replaceChildren();
  const bytes=n=>(n/1048576).toFixed(2)+' MiB';
  const originals=view.storage.originals;
  area.append(el('p',tr('Keep these project originals and their backups.','以下为项目原件，请保留并备份。')));
  if(originals.length)table(area,[tr('Original attachment','原始附件'),tr('Size','大小')],originals.map(a=>[a.name,bytes(a.bytes)]));
  else area.append(el('p',tr('No registered attachments.','暂无已登记附件。')));
  const cached=view.storage.reinstallable;
  area.append(el('p',tr('Verified setup downloads that can be downloaded again','可重新下载的已核验安装缓存')+' · '+bytes(cached.reduce((sum,r)=>sum+r.bytes,0))));
  if(cached.length)table(area,[tr('Installer cache','安装缓存'),tr('Size','大小')],cached.map(r=>[r.name,bytes(r.bytes)]));
  if(!p){area.append(el('p',tr('A saved delivery will show the files shared in each package here.','生成交付后，此处列出各包将提供的材料。')));return;}
  area.append(el('p',p.run+' · '+(p.stale?tr('Previous edition. Refresh the delivery before sharing.','此为旧版，请更新交付后再发送。'):tr('Current delivery','本次交付')),p.stale?'warning':'status'));
  if(p.latitude!=null&&p.longitude!=null)area.append(el('p',tr('Project location (latitude, longitude)','项目位置（纬度，经度）')+' · '+p.latitude+', '+p.longitude));
  if(p.attachments.length)table(area,[tr('Registered attachment / photo','已登记附件／照片'),'Complete','Minimal'],p.attachments.map(a=>[a.name,a.complete?'✓':'—',a.minimal?'✓':'—']));
  for(const [kind,paths] of Object.entries(p.coordinate_files)){
   const list=details(area,kind+' · coordinate-bearing files',kind+' · 含地理位置的文件');paths.forEach(path=>list.append(el('p',path)));
  }
  const sources=details(area,'Additional original source files in Complete','完整包内的其他来源文件');
  p.additional_sources.forEach(path=>sources.append(el('p',path)));
  for(const f of p.pdfs){
   area.append(el('p',f.package+' / '+f.path+' · '+(f.ok?tr('Verified','已核验'):tr('Missing or changed','缺失或有变化')),f.ok?'':'warning'));
   if(!f.ok&&!p.stale)area.append(button('Restore this PDF','仅恢复此 PDF',async()=>{
    await api('handoff-repair',{...key,edition:p.edition,package:f.package,path:f.path});await inspect();
    notify(tr('PDF restored to the registered fingerprint.','PDF 已恢复并与登记指纹一致。'));
   }));
  }
 }
 box.append(button('Inspect handoff and storage','查看交付与存储清单',inspect));
 box.append(button('Open optional pilot clock','打开可选试点计时',async()=>{
  const timer=document.getElementById('project-pilot-clock');
  if(timer){await timer.showClock();timer.scrollIntoView({block:'center'});}
 }));
}
function renderPilotClock(parent){
 const timer=el('div');timer.id='project-pilot-clock';timer.hidden=true;
 const toggle=button('Pilot log','试点记录',async()=>{
  if(timer.hidden)await timer.showClock();else timer.hidden=true;
  toggle.setAttribute('aria-expanded',String(!timer.hidden));notify();
 });toggle.setAttribute('aria-controls',timer.id);toggle.setAttribute('aria-expanded','false');parent.append(toggle,timer);
 timer.showClock=async()=>{await showClock();timer.hidden=false;toggle.setAttribute('aria-expanded','true');};
 async function showClock(action='read',revision=null){
  const info=await api('pilot-clock',{id:current.id,action,timer_revision:revision});
  timer.replaceChildren();
  timer.append(button('Show measured workload','查看已记录的工作量',async()=>{
   const r=await api('work-metrics',{id:current.id});
   const old=timer.querySelector('.work-metrics');if(old)old.remove();
   const box=el('div',undefined,'work-metrics');timer.append(box);
   const log=r.interaction_receipts,unknown=tr('Unmeasured','未测量');
   table(box,[tr('Recorded on this edition','本版本已有记录'),tr('Value','数值')],[
    [tr('Recorded requests','已记录请求数'),log.recorded_requests],
    [tr('Repeated confirmation of the same run or study token','同一运算或试算确认凭据的重复请求'),log.repeated_confirmations??unknown],
    [tr('Repeat field submissions','重复提交字段数'),log.repeat_field_submissions??unknown],
    [tr('Timed engineering work (s)','已计工程操作（秒）'),r.active_engineer_seconds??unknown],
    [tr('Waiting for records (s)','等资料（秒）'),r.external_wait_seconds??unknown],
    [tr('Native solver wall time (s)','原生求解器用时（秒）'),r.native_solver_wall_seconds??unknown],
    [tr('Compute call within solver time (s)','其中实际计算调用（秒）'),r.compute_call_wall_seconds??unknown]]);
   box.append(el('small',tr('Request counts include retries. Timing uses completed records; an unmeasured interval stays unknown.','请求数包含重试。耗时取自已完成记录；未计时保留为未知。')));
   table(box,[tr('Machine task','机器任务'),tr('Attempts','次数'),tr('Timed seconds','有计时的秒数'),tr('Untimed','缺少计时')],Object.entries(r.machine_by_action).map(([k,v])=>[k,v.attempts,v.attempts===v.untimed?unknown:v.completed_seconds,v.untimed]));
  }));
  const labels={engineer:tr('Engineering work','工程师操作'),external_wait:tr('Waiting for data','等外部资料')};
  timer.append(el('p',(info.open?labels[info.open.kind]+' · '+new Date(info.open.started_utc).toLocaleString():tr('Paused','已暂停'))+
   ' · '+tr('Recorded intervals','已记录时段')+' '+info.intervals.length+' · '+tr('Recorded developer interventions','已记录的开发者介入')+' '+info.developer_interventions.length));
  timer.append(el('p',tr('Pause when leaving. Discard the open interval if it includes unattended time.','离开前请暂停；当前时段若误计了离开时间，可舍弃。')));
  const actions=[['engineer','Time engineering work','计工程师操作时间'],['external_wait','Time external wait','计等资料时间'],['pause','Pause and save','暂停并保存'],['discard','Discard open interval','舍弃当前时段']];
  for(const [mode,en,zh] of actions){
   if((!info.open&&['pause','discard'].includes(mode))||info.open?.kind===mode)continue;
   timer.append(button(en,zh,()=>showClock(mode,info.revision)));
  }
  const topic=field(timer,'pilot-topic','Where did you get stuck?','遇到困难的环节','unspecified','select',[
   ['unspecified','Current step','当前步骤'],['data','Site data','现场资料'],['geometry','Geometry','几何'],
   ['parameters','Inputs','参数'],['hydraulics','Interpreting results','解读结果'],['delivery','Delivery','交付'],['recovery','Recovery','恢复']]);
  for(const [kind,en,zh] of [['blocker','Record a sticking point','记下卡点'],['intervention','Record developer assistance','记录一次开发者介入']]){
   timer.append(button(en,zh,async()=>{
    const page=current.results?(lastResultPage.project===current.id?lastResultPage.key:'overview'):'model';
    await api('pilot-clock',{id:current.id,action:kind,timer_revision:info.revision,topic:topic.value,page});
    await showClock();notify(tr('Saved with the current project step.','已连同当前项目步骤保存。'));
   }));
  }
  if(info.checkpoints?.length)table(timer,[tr('Time','时间'),tr('Project step','项目步骤'),tr('Topic','环节'),tr('Developer assisted','开发者介入')],
   info.checkpoints.slice(-5).map(row=>[new Date(row.at).toLocaleString(),[row.page,row.phase||row.status].filter(Boolean).join(' · '),row.topic,row.kind==='intervention'?'✓':'—']));
 }
}
