// Offline draft recovery. Storage availability is checked; JSON export remains portable.
const draftKey='hecras.review.v1:'+packet.project_id+':'+spec.packet.path;
let exportedSnapshot=null,draftTimer=null,recoverableDraft=null,storageError=false;
Object.assign(words.en,{restoreDraft:'Restore local draft',discardDraft:'Discard local draft',draftAvailable:'A saved draft is available for this exact review packet.',draftStale:'A draft belongs to an older packet. It cannot be restored here; keep its exported JSON with the original review.',draftSaved:'Draft saved in this browser. Export JSON for a portable copy.',draftUnavailable:'Browser draft storage is unavailable. Export JSON before leaving.',draftEmpty:'No local draft. Export JSON to save a portable copy.',draftRestored:'Local draft restored. Model inputs are unchanged.'});
Object.assign(words.cn,{restoreDraft:'恢复本地草稿',discardDraft:'删除本地草稿',draftAvailable:'发现属于当前审核包的草稿，可点击恢复。',draftStale:'草稿属于旧审核包，不能在此恢复；请保留其导出 JSON 并使用原审核页面。',draftSaved:'草稿已保存在本浏览器。请导出 JSON 保存可迁移副本。',draftUnavailable:'浏览器草稿存储不可用，请在离开前导出 JSON。',draftEmpty:'暂无本地草稿，请导出 JSON 保存可迁移副本。',draftRestored:'已恢复本地草稿，模型输入未改变。'});
function samePacket(a,b){return a&&b&&['path','sha256','size_bytes'].every(k=>a[k]===b[k]);}
function reviewError(en,cn){return new Error(lang==='en'?en:cn);}
function validateSaved(value){
  if(!value||typeof value!=='object'||Array.isArray(value)||value.schema_version!==spec.schema_version)throw reviewError('Unsupported decisions format. Choose an exported decisions JSON.','决定格式不支持，请选择本页导出的决定 JSON。');
  if(!samePacket(value.packet,spec.packet))throw reviewError('Different review snapshot. Open the page for the original packet.','审核包不匹配，请打开该文件原先所属的审核页面。');
  for(const key of ['reviewer','review_basis'])if(value[key]!=null&&typeof value[key]!=='string')throw reviewError('Reviewer and review basis must be text.','审核人和审核依据必须为文本。');
  if(!Array.isArray(value.decisions)||value.decisions.length!==spec.decisions.length)throw reviewError('Decision count does not match this packet.','决定数量与审核包不符。');
  value.decisions.forEach((d,i)=>{
    const f=all[i];
    if(!d||d.id!==f.id||!['PENDING','RETAIN_CANDIDATE','REJECT','DEFER'].includes(d.decision))throw reviewError('Invalid decision item: '+i,'决定条目无效：'+i);
    if(d.note!=null&&typeof d.note!=='string')throw reviewError('Decision notes must be text.','决定理由必须为文本。');
    if(d.candidate_index!=null&&(!Number.isInteger(d.candidate_index)||!f.candidates||d.candidate_index<0||d.candidate_index>=f.candidates.length))throw reviewError('Source candidate index is invalid: '+d.id,'来源候选序号无效：'+d.id);
    if(d.bank_indices!=null){
      const n=f.data?.station_ft?.length;
      if(f.kind!=='section'||!Array.isArray(d.bank_indices)||d.bank_indices.length!==2||d.bank_indices.some(x=>x!==null&&(!Number.isInteger(x)||x<=0||x>=n-1)))throw reviewError('Bank samples must be interior section points: '+d.id,'岸线必须选择断面内部采样点：'+d.id);
      // Partial or reversed bank selections may be saved as unfinished drafts;
      // the model-import gate still requires two ordered complete bank points.
    }
    if(d.decision!=='RETAIN_CANDIDATE'&&(d.bank_indices!=null||d.candidate_index!=null))throw reviewError('Unselected items contain candidate choices: '+d.id,'未保留条目中包含候选选择：'+d.id);
  });
  return value;
}
function captureDecisions(){saveCurrent();spec.reviewer=el('reviewer').value||null;spec.review_basis=el('basis').value||null;return JSON.parse(JSON.stringify(spec));}
function loadDecisions(value){validateSaved(value);spec.decisions=JSON.parse(JSON.stringify(value.decisions));spec.reviewer=value.reviewer??null;spec.review_basis=value.review_basis??null;el('reviewer').value=spec.reviewer||'';el('basis').value=spec.review_basis||'';bankMode=null;render();}
function draftNotice(key){el('draftStatus').dataset.message=key;el('draftStatus').textContent=words[lang][key];}
function inspectDraft(){
  try{
    const raw=localStorage.getItem(draftKey);
    recoverableDraft=raw?JSON.parse(raw):null;
    if(recoverableDraft){validateSaved(recoverableDraft.decisions);draftNotice('draftAvailable');}
    else draftNotice('draftEmpty');
  }catch(e){
    if(recoverableDraft){draftNotice('draftStale');recoverableDraft=null;}
    else{storageError=true;draftNotice('draftUnavailable');}
  }
  el('restoreDraft').disabled=!recoverableDraft;
}
function saveDraft(){
  try{const value=captureDecisions();localStorage.setItem(draftKey,JSON.stringify({saved_at:new Date().toISOString(),decisions:value}));storageError=false;recoverableDraft={decisions:value};el('restoreDraft').disabled=false;draftNotice('draftSaved');}
  catch(e){storageError=true;draftNotice('draftUnavailable');}
}
function changed(){clearTimeout(draftTimer);draftTimer=setTimeout(saveDraft,350);}
function hasUnexportedChanges(){return JSON.stringify(captureDecisions())!==exportedSnapshot;}
function refreshDraftLanguage(){const key=el('draftStatus').dataset.message;if(key)draftNotice(key);}
el('restoreDraft').onclick=()=>{if(!recoverableDraft)return;try{loadDecisions(recoverableDraft.decisions);draftNotice('draftRestored');}catch(e){el('status').textContent=e.message;}};
el('discardDraft').onclick=()=>{try{localStorage.removeItem(draftKey);recoverableDraft=null;el('restoreDraft').disabled=true;draftNotice('draftEmpty');}catch(e){draftNotice('draftUnavailable');}};
document.addEventListener('input',event=>{if(['note','reviewer','basis'].includes(event.target.id))changed();});
document.addEventListener('change',event=>{if(['decision','candidate'].includes(event.target.id))changed();});
globalThis.addEventListener?.('beforeunload',event=>{if(hasUnexportedChanges()){saveDraft();event.preventDefault();event.returnValue='';}});
globalThis.addEventListener?.('pagehide',()=>{if(hasUnexportedChanges())saveDraft();});
el('file').onchange=async()=>{
  const file=el('file').files?.[0];if(!file)return;
  try{
    if(file.size>5*1024*1024)throw reviewError('Decisions file exceeds 5 MB. Select the small exported decisions JSON.','决定文件超过 5 MB，请选择导出的小型决定 JSON。');
    let value;try{value=JSON.parse((await file.text()).replace(/^\uFEFF/,''));}catch(e){throw reviewError('Invalid JSON text. Choose the exported .json file; current decisions were kept.','JSON 文本格式错误，请选择导出的 .json；当前决定已保留。');}
    loadDecisions(value);exportedSnapshot=JSON.stringify(captureDecisions());saveDraft();el('status').textContent=lang==='en'?'Decisions loaded; model inputs are unchanged.':'已载入决定，模型输入未改变。';
  }catch(e){el('status').textContent=e.message;}
  finally{el('file').value='';}
};
const exportDownload=el('export').onclick;
el('export').onclick=()=>{exportDownload();exportedSnapshot=JSON.stringify(captureDecisions());saveDraft();};
const switchLanguage=el('language').onclick;
el('language').onclick=()=>{switchLanguage();refreshDraftLanguage();};
exportedSnapshot=JSON.stringify(captureDecisions());
inspectDraft();
