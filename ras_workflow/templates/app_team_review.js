function renderTeamReview(parent){
 const panel=details(parent,'Formal team review and client issue','正式团队复核与客户交付');
 const project=current.id,region=el('div'),feedback=el('p');
 feedback.setAttribute('role','status');panel.append(region,feedback);
 const labels={DRAFT:['Draft','草稿'],SUBMITTED:['Submitted for review','已提交复核'],RETURNED:['Returned','已退回'],
  SUPERSEDED:['Superseded','已被新版替代'],REVIEWED:['Reviewed for the stated purpose','已按所述用途复核'],WITHDRAWN:['Withdrawn','已撤回'],DELIVERED:['Issued','已交付']};
 function download(name,content,type){
  const a=el('a'),url=URL.createObjectURL(new Blob([content],{type}));a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }
 async function load(){
  const s=await api('team-inspect',{id:project});if(current.id!==project||!region.isConnected)return;
  region.replaceChildren();region.append(el('p',tr(...labels[s.state])+' · '+s.edition.run,'status'));
  if(s.history.length){const history=details(region,'Submission and decision history','提交与处理历史');
   table(history,[tr('Run','运行'),tr('Action','操作'),tr('Operator','经办人'),'RS',tr('Decision','意见')],
    s.history.map(r=>[r.edition.run,tr(...labels[r.state]),r.actor,r.station||'—',r.note]));
   const latest=s.history.filter(r=>r.edition.project===project).at(-1);
   if(latest?.handoff?.client&&latest.state==='DELIVERED'){region.append(el('p',tr('Send this Client folder','将此 Client 目录转交客户')+' · '+latest.handoff.client),
    button('Open client issue folder','打开客户交付目录',()=>api('open-folder',{id:project,path:latest.handoff.client})));}}
  if(s.decisions.length){const decisions=details(region,'Earlier decisions affected by this edition','本版对既有复核意见的影响');
   table(decisions,['RS',tr('Review note','意见'),tr('Affected inputs','受影响输入')],s.decisions.map(r=>[r.station||'—',r.note,r.changed.join(', ')||tr('Referenced inputs unchanged','所引用输入保持一致')]));}
  const names={submit:['Submit this edition','提交本版'],return:['Return for revision','退回修订'],review:['Record review','记录复核结论'],
   withdraw:['Withdraw formal issue','撤回正式提交'],deliver:['Issue client folders','生成正式客户交付']};
  const actions={DRAFT:['submit'],SUBMITTED:['return','review','withdraw'],RETURNED:['submit','withdraw'],REVIEWED:['deliver','withdraw'],DELIVERED:['withdraw'],WITHDRAWN:['submit'],SUPERSEDED:[]}[s.state];
  if(!actions.length)return;
  const form=el('div');region.append(form);
  const actor=field(form,'team-operator','Operator at this formal step','本次正式操作经办人',sessionStorage.getItem('steadyreach-team-operator')||'');
  actor.autocomplete='off';actor.addEventListener('input',()=>sessionStorage.setItem('steadyreach-team-operator',actor.value));
  const note=field(form,'team-note','Review comment or reason for issue','复核意见或提交说明','','textarea');
  const draftId=['team-review',project,s.edition.summary_sha256,s.head||'new'].join('/');
  let saved={};try{saved=JSON.parse(sessionStorage.getItem(draftId)||'{}');}catch{}
  note.value=saved.note||'';
  let station,dependencies;
  if(s.state==='SUBMITTED'){
   station=field(form,'team-station','Station for this comment','意见对应断面','','select',[['','Entire edition','整版'],...s.stations.map(v=>[v,'RS '+v,'RS '+v])]);
   dependencies=field(form,'team-deps','Related inputs (select as needed)','关联输入（可多选）','','select',s.dependencies.filter(k=>!k.startsWith('RS/')).map(k=>[k,k,k]));
   dependencies.multiple=true;dependencies.size=3;station.value=saved.station||'';
   for(const opt of dependencies.options)opt.selected=(saved.dependencies||[]).includes(opt.value);
   form.append(el('p',tr('Select a station or related input. A revision will compare the corresponding snapshots.','选择断面或关联输入，修订版会比较对应的输入快照。')));
  }
  const saveDraft=()=>sessionStorage.setItem(draftId,JSON.stringify({note:note.value,station:station?.value,
    dependencies:dependencies?Array.from(dependencies.selectedOptions,o=>o.value):[]}));
  note.addEventListener('input',saveDraft);station?.addEventListener('change',saveDraft);dependencies?.addEventListener('change',saveDraft);
  let scopeToken;
  if(actions.includes('deliver')){
   const preview=el('div');form.append(button('Preview client and internal files','预览客户与内部文件',async()=>{
    const r=await api('team-scope',{id:project});preview.replaceChildren();scopeToken=r.scope_token;
    for(const [kind,titleEn,titleZh] of [['client','Client files','客户文件'],['internal','Internal inventory','内部清单']]){
     const d=details(preview,titleEn,titleZh);
     for(const [pack,rows] of Object.entries(r[kind])){d.append(el('h4',pack+' · '+rows.length));rows.forEach(f=>d.append(el('p',f.path+(f.distribution==='internal'?' · '+tr('Internal only','仅内部'):''))));}}
    const records=Object.entries(r.internal).flatMap(([pack,rows])=>rows.map(row=>({pack,row})));
    const pick=field(preview,'team-preview-member','Inspect file contents','核对文件内容','0','select',records.map(({pack,row},i)=>[String(i),pack+' / '+row.path,pack+' / '+row.path]));
    const contents=el('div');preview.append(button('Preview selected file','查看所选文件内容',async()=>{
     const {pack,row}=records[Number(pick.value)];const member=await api('team-file',{id:project,scope_token:scopeToken,package:pack,member:row.path});
     contents.replaceChildren(el('p',row.path+' · '+row.size_bytes+' bytes · SHA-256 '+row.sha256));
     if(member.format==='image'){const img=el('img');img.src=member.image;img.alt=row.path;contents.append(img);}
     else if(member.format==='text')contents.append(el('pre',member.text||tr('No extractable text.','没有可提取文字。')));
     else contents.append(el('p',tr('Use the original application to inspect this file.','请用原软件核对该类型文件。')));
    }),contents);
    feedback.textContent=tr('Preview ready. Confirm the audience before issuing.','预览已就绪，请核对收件范围后交付。');
   }),preview);
  }
  function payload(action){return {schema:s.schema,edition:s.edition,head:s.head,action,actor:actor.value,note:note.value,
    station:station?.value||null,dependencies:dependencies?Array.from(dependencies.selectedOptions,o=>o.value):[],scope_token:scopeToken};}
  async function send(body){await api('team-decide',{...body,id:project});sessionStorage.removeItem(draftId);feedback.textContent=tr('Decision recorded for this run.','已记录到本次运行。');await load();}
  for(const action of actions)form.append(button(...names[action],async()=>{
   if(action==='deliver'&&!scopeToken)throw Error(tr('Preview the client and internal inventories first.','请先预览客户和内部清单。'));
   await send(payload(action));
  }));
  if(s.state==='SUBMITTED'){
   const offline=details(region,'Exchange a comment offline','离线交换复核意见');
   offline.append(button('Download offline review form','下载离线复核表',async()=>{
    const form=await api('team-form',{id:project,head:s.head});download('Review_'+s.edition.run+'.html',form.html,'text/html;charset=utf-8');
    feedback.textContent=tr('Send the HTML form to the reviewer. Import the returned JSON here.','将 HTML 表单交给复核人，在这里导入回传 JSON。');
   }));
   const file=field(offline,'team-return-file','Returned comment JSON','回传意见 JSON','','file');file.accept='.json';
   const detail=el('div');offline.append(detail);
   file.onchange=async()=>{detail.replaceChildren();try{
    const f=file.files[0];if(!f)return;if(f.size>100000)throw Error(tr('File too large.','文件过大。'));
    const reply=JSON.parse(await f.text());if(!['return','review'].includes(reply.action)||reply.schema!==s.schema||reply.head!==s.head||
       reply.edition?.project!==project||reply.edition?.summary_sha256!==s.edition.summary_sha256)throw Error(tr('Different edition or review round.','版本或复核轮次不符。'));
    detail.append(el('p',[reply.actor,reply.station?'RS '+reply.station:'',reply.note].filter(Boolean).join(' · ')),button('Record this offline comment','登记这份离线意见',()=>send(reply)));
   }catch(e){detail.textContent=e.message;}};
  }
 }
 panel.append(button('Open formal review','打开正式复核',load));
}
