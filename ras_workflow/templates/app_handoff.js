function renderHandoff(parent) {
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
 const timer=el('div');box.append(timer);
 async function showClock(action='read',revision=null){
  const info=await api('pilot-clock',{id:current.id,action,timer_revision:revision});
  timer.replaceChildren();
  const labels={engineer:tr('Engineering work','工程师操作'),external_wait:tr('Waiting for data','等外部资料')};
  timer.append(el('p',(info.open?labels[info.open.kind]+' · '+new Date(info.open.started_utc).toLocaleString():tr('Paused','已暂停'))+
   ' · '+tr('Recorded intervals','已记录时段')+' '+info.intervals.length+' · '+tr('Developer interventions','开发者介入')+' '+info.developer_interventions.length));
  timer.append(el('p',tr('Pause when leaving. Discard the open interval if it includes unattended time.','离开前请暂停；当前时段若误计了离开时间，可舍弃。')));
  const actions=[['engineer','Time engineering work','计工程师操作时间'],['external_wait','Time external wait','计等资料时间'],['pause','Pause and save','暂停并保存'],['discard','Discard open interval','舍弃当前时段'],['intervention','Record developer assistance','记录一次开发者介入']];
  for(const [mode,en,zh] of actions){
   if((!info.open&&['pause','discard'].includes(mode))||info.open?.kind===mode)continue;
   timer.append(button(en,zh,()=>showClock(mode,info.revision)));
  }
 }
 box.append(button('Open optional pilot clock','打开可选试点计时',()=>showClock()));
}
