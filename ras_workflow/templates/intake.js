'use strict';
const $=s=>document.querySelector(s), token=location.pathname.split('/')[1];
let data, step=0, language='en', busy=false, dirty=false, sequence=0, timer, pending=Promise.resolve(), finished=false;
try{language=localStorage.getItem('hecras-intake-language')||'en';}catch{}
const tr=(en,zh)=>language==='zh'?zh:en;
const steps=()=>[tr('1 · Project & evidence','1 · 项目与资料'),tr('2 · Flows & roughness','2 · 流量与糙率'),tr('3 · Crossing & boundaries','3 · 结构与边界'),tr('4 · River cross sections','4 · 河道断面'),tr('5 · Review & continue','5 · 检查并继续')];
const el=(tag,text,cls)=>{let n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const label=f=>f.label[language==='zh'?'zh':'en'];
const val=f=>Object.hasOwn(data.draft.answers,f.key)?data.draft.answers[f.key].value:f.value;
const group=f=>f.key.startsWith('c.scenarios.')?1:f.key.startsWith('g.cross_sections.')?3:2;
function notice(text){$('#notice').hidden=!text;$('#notice').textContent=text||'';}
async function request(path,body){
 const options=body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Intake-Token':token},body:JSON.stringify(body)};
 const response=await fetch(path,options);const result=await response.json();if(!response.ok)throw Error(result.error||response.status);return result;
}
function payload(){return {revision:data.draft.revision,answers:data.draft.answers,reviewer:data.draft.reviewer,basis:data.draft.basis,consent:data.draft.consent,section_review_drafts:data.draft.section_review_drafts||{},geometry_setup_draft:data.draft.geometry_setup_draft||{},native_review:data.draft.native_review||{}};}
function savedText(){ $('#saved').textContent=dirty?tr('Unsaved changes','有尚未保存的修改'):tr('Draft saved on this computer','草稿已保存到本机'); }
function changed(){dirty=true;sequence++;savedText();clearTimeout(timer);timer=setTimeout(()=>save().catch(showError),900);}
function showError(e){const message=tr('Could not complete this action. Your current edits remain on this page. ','操作未完成，当前编辑仍保留在页面。')+e.message;notice(message);if($('#cancelDialog').open)$('#cancelError').textContent=message;savedText();}
async function save(){
 clearTimeout(timer);
 const action=async()=>{
  if(!dirty||finished)return;
  const seq=sequence,p=structuredClone(payload()),response=await request('save',p);
  const local=data.draft;
  data=response;
  if(seq!==sequence){local.revision=response.draft.revision;data.draft=local;}else dirty=false;
  savedText();if(seq===sequence)refreshFieldChecks();
 };
 pending=pending.catch(()=>{}).then(action);return pending;
}
function button(text,action,cls){const b=el('button',text,cls);b.type='button';b.onclick=()=>Promise.resolve().then(action).catch(showError);return b;}
function heading(title,description){const s=$('#screen');s.append(el('h2',title),el('p',description));return s;}
function applyResponse(r){data=r;dirty=false;render();savedText();}
async function operation(action){if(busy)return;busy=true;try{await save();await action();}finally{busy=false;}}
function parse(f,text){
 if(text.trim()==='')return null;
 if(f.kind==='number'||f.kind==='integer'){const n=Number(text);if(!Number.isFinite(n))throw Error(tr('Enter a finite number.','请输入有效数值。'));return n;}
 if(f.kind==='array'||f.kind==='matrix'){
  if(text.trim().startsWith('['))return JSON.parse(text);
  const nums=s=>s.trim().split(/[,，\s]+/).filter(Boolean).map(x=>{let n=Number(x);if(!Number.isFinite(n))throw Error(tr('Use numbers separated by commas.','请用逗号分隔数值。'));return n;});
  return f.kind==='array'?nums(text):text.trim().split(/\r?\n/).filter(x=>x.trim()).map(nums);
 }
 return text;
}
function display(value,kind){if(value===null||value===undefined)return '';if(kind==='matrix'&&Array.isArray(value))return value.map(x=>Array.isArray(x)?x.join(', '):String(x)).join('\n');if(kind==='array'&&Array.isArray(value))return value.join(', ');return typeof value==='object'?JSON.stringify(value):String(value);}
function evidenceOptions(select,value){select.append(new Option(tr('Choose evidence type','选择证据类别'),''));
 for(const [v,en,zh] of [['reported','Reported in a source','资料记载值'],['user_reported_measurement','Measurement supplied by user','用户提供的测量记录'],['as_built','As-built record','竣工资料'],['terrain_derived','Derived from exterior terrain','外部地形推导'],['inferred','Inferred with a stated basis','有依据的推断'],['assumed','Conditional assumption','条件性假设']])select.append(new Option(tr(en,zh),v));select.value=value||'';}
function answer(f){if(!data.draft.answers[f.key])data.draft.answers[f.key]={value:f.value,evidence_class:'',basis:'',confirmed:false};return data.draft.answers[f.key];}
function refreshFieldChecks(){
 for(const box of document.querySelectorAll('.field[data-key]')){
  box.querySelectorAll('.server-error').forEach(n=>n.remove());box.classList.remove('invalid');
  for(const e of data.check?.errors||[])if(e.field===box.dataset.key){box.classList.add('invalid');box.append(el('div',e[language==='zh'?'zh':'en'],'field-error server-error'));}
 }
}
function batchEvidence(screen,fields){
 const card=el('details',undefined,'card');card.append(el('summary',tr('Use one source for selected values','为所选数值共用一份来源')));
 const body=el('div',undefined,'body'),list=el('div'),selected=[];card.append(body);
 body.append(el('p',tr('Select only values supported by this source. Candidate evidence types cannot be upgraded. Applying a source clears final approval.','只选择该来源支持的数值。候选值证据类别不能升级；应用后会清除最终批准。')));
 for(const f of fields){const v=val(f);if(v===null||v===undefined||v===''||Array.isArray(v)&&!v.length)continue;
  const check=el('input');check.type='checkbox';const row=el('label',undefined,'check');row.append(check,el('span',label(f)+' = '+display(v,f.kind)));list.append(row);selected.push({f,check,shown:structuredClone(v)});}
 body.append(list);const type=el('select'),basis=el('input');type.id='batch-evidence';basis.id='batch-basis';const typeLabel=el('label',tr('Shared evidence type','共用证据类别')),basisLabel=el('label',tr('Shared source / page / applicability','共用来源 / 页码 / 适用依据'));typeLabel.htmlFor=type.id;basisLabel.htmlFor=basis.id;evidenceOptions(type,'');basis.placeholder=tr('Source, page and applicability','来源、页码及适用依据');body.append(typeLabel,type,basisLabel,basis);
 const confirm=el('input');confirm.type='checkbox';const labelNode=el('label',undefined,'check');labelNode.append(confirm,el('span',tr('I reviewed every selected value above for this site.','我已逐项审核上面所选数值对本站的适用性。')));body.append(labelNode);
 body.append(button(tr('Apply to selected values','应用到所选数值'),async()=>{
  const rows=selected.filter(x=>x.check.checked);if(!rows.length||!type.value||!basis.value.trim())throw Error(tr('Select values and supply an evidence type and source.','请选择数值并填写证据类别及来源。'));
  if(rows.some(({f,shown})=>JSON.stringify(val(f))!==JSON.stringify(shown)))throw Error(tr('A selected value changed. Save, reopen this step and review the refreshed list before applying.','所选数值已改变。请保存并重新打开此步骤，审核更新后的列表再应用。'));
  if(rows.some(({f})=>data.draft.answers[f.key]?.suggestion&&data.draft.answers[f.key].evidence_class!==type.value))throw Error(tr('Keep the original candidate evidence class, or supply a separately sourced value.','保留候选原有证据类别，或另行填写有独立来源的数值。'));
  for(const {f} of rows){const a=answer(f);a.evidence_class=type.value;a.basis=basis.value.trim();a.confirmed=confirm.checked;}
  data.draft.consent=false;changed();await save();render();
 }));screen.append(card);
}
function field(f){
 const box=el('div',undefined,'field');box.dataset.key=f.key;
 const id='field-'+f.key.replaceAll('.','-');let lab=el('label',label(f));lab.htmlFor=id;if(f.unit)lab.append(el('span',f.unit,'unit'));
 if(f.required)lab.append(el('span',tr('Required','必填'),'required'));box.append(lab);
 let input;
 if(f.kind==='choice'){input=el('select');input.append(new Option(tr('Not supplied','尚未提供'),''));for(const o of f.options)input.append(new Option(o==='box'?tr('Box','箱涵'):o==='circular'?tr('Circular','圆管'):o==='subcritical'?tr('Subcritical','缓流'):o==='mixed'?tr('Mixed flow','混合流'):o==='shared'?tr('Shared road profile','上下游共用路顶'):o==='distinct'?tr('Distinct road profiles','上下游分别定义路顶'):o,o));}
 else if(['array','matrix'].includes(f.kind)){input=el('textarea');input.rows=f.kind==='matrix'?3:2;}
 else {input=el('input');input.type=['number','integer'].includes(f.kind)?'number':'text';if(input.type==='number')input.step=f.kind==='integer'?'1':'any';}
 input.id=id;input.value=display(val(f),f.kind);input.autocomplete='off';box.append(input);
 if(f.help)box.append(el('small',f.help[language==='zh'?'zh':'en']));
 if(['array','matrix'].includes(f.kind))box.append(el('small',f.kind==='matrix'?tr('One pair per line, separated by a comma. A JSON array is also accepted.','每行一对数值，用逗号分隔；也接受 JSON 数组。'):tr('Comma-separated numbers; matching station/elevation lists must have the same length.','数值用逗号分隔；站距与高程列表长度必须一致。')));
 const localError=el('div','', 'field-error');box.append(localError);
 const meta=el('div',undefined,'meta');let a=data.draft.answers[f.key];meta.hidden=!a;
 const grid=el('div',undefined,'grid'),typeWrap=el('div'),basisWrap=el('div'),type=el('select'),basis=el('input');
 type.id=id+'-evidence';basis.id=id+'-basis';const typeLabel=el('label',tr('Evidence type','证据类别')),basisLabel=el('label',tr('Source / estimation basis','来源 / 估计依据'));typeLabel.htmlFor=type.id;basisLabel.htmlFor=basis.id;typeWrap.append(typeLabel,type);basisWrap.append(basisLabel,basis);grid.append(typeWrap,basisWrap);evidenceOptions(type,a?.evidence_class);basis.value=a?.basis||'';
 const confirm=el('input');confirm.type='checkbox';confirm.checked=a?.confirmed===true;const consent=el('label',undefined,'check');consent.append(confirm,el('span',tr('I reviewed this value and its applicability to this site.','我已审核此值及其对本站的适用性。')));meta.append(grid,consent);box.append(meta);
 input.oninput=()=>{const a=answer(f);a.confirmed=false;confirm.checked=false;a.suggestion=null;meta.hidden=false;data.draft.consent=false;try{a.value=parse(f,input.value);localError.textContent='';}catch(e){a.value=input.value;localError.textContent=e.message;box.classList.add('invalid');}changed();};
 type.onchange=()=>{answer(f).evidence_class=type.value;answer(f).confirmed=false;confirm.checked=false;data.draft.consent=false;changed();};basis.oninput=()=>{answer(f).basis=basis.value;answer(f).confirmed=false;confirm.checked=false;data.draft.consent=false;changed();};confirm.onchange=()=>{answer(f).confirmed=confirm.checked;data.draft.consent=false;changed();};
 if(['g.flow_regime','g.structure.road.profile_mode'].includes(f.key))input.onchange=async()=>{await save();render();};
 for(const suggestion of f.suggestions||[]){
  const card=el('div',undefined,'suggestion');const condition=suggestion.condition?.[language==='zh'?'zh':'en']||suggestion.basis;
  card.append(el('strong',tr('Reference candidate · ','参考候选 · ')+condition));
  card.append(el('p',(suggestion.range?tr('Reference range: ','参考范围：')+suggestion.range.join(' – ')+'; ':'')+tr('candidate value: ','候选值：')+display(suggestion.value,f.kind)));
  if(suggestion.limitation)card.append(el('p',suggestion.limitation[language==='zh'?'zh':'en']));
  if(suggestion.url&&/^https:\/\//.test(suggestion.url)){const link=el('a',tr('Source and applicable conditions','来源及适用条件'));link.href=suggestion.url;link.target='_blank';link.rel='noopener noreferrer';card.append(link);}
  if(suggestion.value!==null&&suggestion.value!==undefined)card.append(button(tr('Use as a candidate','采用为待审候选'),async()=>{
   const a=answer(f);a.value=suggestion.value;a.basis=suggestion.basis;a.evidence_class=suggestion.evidence_class;a.confirmed=false;a.suggestion=await hashObject(suggestion);data.draft.consent=false;data.check.errors=data.check.errors.filter(e=>e.field!==f.key);changed();render();
  }));box.append(card);
 }
 for(const e of data.check?.errors||[])if(e.field===f.key){box.classList.add('invalid');box.append(el('div',e[language==='zh'?'zh':'en'],'field-error server-error'));}
 return box;
}
// Server supplies stable suggestion identity; JSON canonicalization stays server-side.
async function hashObject(s){return s.id;}
function fileCard(){
 const box=el('div',undefined,'card');box.append(el('h3',tr('Bring existing evidence into this review','导入已有资料')),
 el('p',tr('Import complete geometry or a section draft from this workflow. All values remain subject to your review. PDFs/photos can be attached as evidence; they are not automatically converted into geometry.','可导入本工作流格式的完整几何或断面草稿，再逐项审核。PDF/照片可作为证据附件，不会自动转换成几何。')));
 const kind=el('select');kind.id='uploadKind';for(const [v,en,zh] of [['geometry','Complete geometry JSON','完整几何 JSON'],['sections','Cross-section draft JSON','断面草稿 JSON'],['evidence','Supporting document / photograph','说明文件 / 照片证据']])kind.append(new Option(tr(en,zh),v));
 const file=el('input');file.type='file';file.id='uploadFile';const basis=el('input');basis.id='uploadBasis';basis.placeholder=tr('Source, page and why it applies to this site','来源、页码及适用于本站的依据');const cls=el('select');cls.id='uploadClass';evidenceOptions(cls,'');
 box.append(el('label',tr('File type','文件类型')),kind,file,el('label',tr('Evidence type','证据类别')),cls,el('label',tr('Source description','来源说明')),basis);
 box.append(button(tr('Import for review','导入待审'),()=>operation(async()=>{
  if(!file.files[0])throw Error(tr('Select a file first.','请先选择文件。'));if(!cls.value||!basis.value.trim())throw Error(tr('Provide evidence type and source.','请填写证据类别和来源。'));
  const selected=file.files[0];if(selected.size>15000000)throw Error(tr('Maximum 15 MB per attachment.','单个附件最多 15 MB。'));
  const content=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=()=>reject(Error('File read failed'));r.readAsDataURL(selected);});
  applyResponse(await request('upload',{revision:data.draft.revision,name:selected.name,content,kind:kind.value,basis:basis.value,evidence_class:cls.value}));
 })));
 for(const u of data.draft.uploads)box.append(el('p',u.original_name+' · '+u.basis,'muted'));return box;
}
function overview(){
 const screen=heading(tr('Complete the inputs, at your pace','按你的进度补齐资料'),tr('The workflow is waiting for your decision. Saving a draft does not approve a model or start HEC-RAS.','工作流正在等待你的决定。保存草稿不会批准模型或启动 HEC-RAS。'));
 const missing=data.fields.filter(f=>f.required&&(val(f)===null||val(f)===''||Array.isArray(val(f))&&!val(f).length)).length;
 if(data.location)screen.append(el('p',tr('Site coordinates (WGS84): ','本站坐标（WGS84）：')+data.location.latitude+', '+data.location.longitude+' · '+(data.location.source||''),'muted'));
 const card=el('div',undefined,'card');
 if(data.native_import){card.append(el('h3',tr('Native inputs are ready for your review','原生输入已读取，等待审核')),el('p',tr('Complete the native-model review below, then choose Confirm native inputs and continue. It includes the source sections, roughness, crossing and boundaries. You do not need to enter these again in the manual-entry steps.','请完成下方原生模型审核，再点“确认原生输入并继续”。其中已包含来源断面、糙率、结构和边界，无需在手工填报步骤重复填写。')));}
 else{card.append(el('div',String(missing),'metric'),el('p',tr('required values still to supply','项必填值仍需补充')),el('p',tr('You may enter values, review available candidates, import existing records, or save and return later. No unsupported site defaults are filled in.','可以填写数值、审核已有候选、导入资料，或保存后稍后继续。没有依据的本站参数保持空白。')));const pendingReviews=Object.values(data.draft.answers).filter(a=>a.confirmed!==true).length;card.append(el('p',tr('Entered values awaiting confirmation: ','已填但尚待确认：')+pendingReviews+tr(' · External sections: ',' · 外部断面数：')+data.section_count),button(tr('Show remaining checks','查看待处理检查项'),()=>{step=4;render();}));}
 screen.append(card);
 nativeInputCard(screen);screen.append(fileCard());const warning=el('div',undefined,'card warning');warning.append(el('h3',tr('What terrain can provide','地形能提供什么')),el('p',tr('DEM supports exterior ground and section sampling. Culvert lengths, buried inverts, entrance construction and flood flows need their own evidence. Geometry uses international feet; DEM units are reviewed separately.','DEM 可支持外部地形和断面采样。涵长、埋藏涵底、入口构造和洪水流量需要各自的依据。几何使用国际英尺，DEM 单位单独审核。')));screen.append(warning);
 if(data.suggestion_error)screen.append(el('p',tr('Suggestion file needs attention: ','建议文件需要处理：')+data.suggestion_error,'field-error'));
 if(data.geometry_checkpoint){const c=data.geometry_checkpoint;screen.append(el('p',tr('Terrain sections: ','地形断面：')+c.status+' · '+(c.error||c.reason||tr('Open step 4 to review profiles and banks.','打开第 4 步复核剖面与岸站。')),'card'));}
 const actions=el('div',undefined,'actions');actions.append(button(tr('Save and return later','保存并稍后继续'),pause),button(tr('Export this draft record','下载本次填报记录'),download),button(tr('Abandon this workflow','放弃此工作流'),openCancel,'danger'));screen.append(actions);
}
function fieldScreen(){
 const descriptions=[null,tr('Provide the applicable flow and roughness evidence. A literature range is a reference for review, not an approved site value.','填写适用的流量与糙率依据。文献范围供审核参考，不是已批准的本站值。'),tr('Check units, datum, road crest, boundaries and each culvert group. All displayed engineering inputs are editable.','检查单位、基准、路顶、边界及各涵洞组。显示的工程输入均可编辑。'),tr('Import a section draft on step 1, or add sections below. Review all banks, reach lengths and sampling. At least four functional exterior sections are required.','可在第 1 步导入断面草稿，或在此添加。需审核岸位、流程长度和采样，至少四个功能完整的外部断面。')];
 const screen=heading(steps()[step],descriptions[step]);if(step===3){geometrySetup(screen);terrainReview(screen);}let parent=screen,last='',details;
 const visible=data.fields.filter(f=>group(f)===step);batchEvidence(screen,visible);
 for(const f of visible){
  const match=f.key.match(/^g\.(cross_sections|structure\.groups)\.(\d+)\./);const section=match?match[1]+match[2]:'';
  if(section!==last){parent=screen;last=section;if(section){details=el('details');details.open=Number(match[2])===0;details.append(el('summary',(match[1]==='cross_sections'?tr('Cross section ','断面 '):tr('Culvert group ','涵洞组 '))+(Number(match[2])+1)));parent=el('div',undefined,'body');details.append(parent);screen.append(details);}}
  parent.append(field(f));
 }
 if(step===2||step===3)screen.append(button(step===3?tr('Add a blank section','添加空白断面'):tr('Add a separate culvert group','添加独立涵洞组'),()=>operation(async()=>applyResponse(await request('add',{revision:data.draft.revision,kind:step===3?'section':'group'})))));
}
function review(){
 const screen=heading(tr('Review and decide','检查并决定'),tr('Your original project stays unchanged. Approval creates an independent conditional configuration and allows the workflow to continue.','原项目输入保持不变。确认后创建独立的条件性配置，允许工作流继续。'));
 const count=Object.keys(data.draft.answers).length;screen.append(el('p',tr('Edited fields: ','已编辑字段：')+count+tr(' · Sections: ',' · 断面数：')+data.section_count+tr(' · Culvert groups: ',' · 涵洞组：')+data.group_count));
 const edits=el('details');edits.append(el('summary',tr('Review entered values and their sources','查看已填数值与来源')));for(const [key,a]of Object.entries(data.draft.answers)){const f=data.fields.find(f=>f.key===key);const card=el('div',undefined,'card');card.append(el('strong',f?label(f):key),el('pre',JSON.stringify(a.value)),el('p',a.evidence_class+' · '+a.basis));edits.append(card);}screen.append(edits);
 for(const [name,en,zh] of [['reviewer','Decision maker','决定人'],['basis','Site applicability and authorization basis','本站适用性及授权依据']]){const id='decision-'+name;const lab=el('label',tr(en,zh));lab.htmlFor=id;const input=el(name==='basis'?'textarea':'input');input.id=id;input.value=data.draft[name]||'';input.oninput=()=>{data.draft[name]=input.value;changed();};screen.append(lab,input);}
 const checkbox=el('input');checkbox.id='decision-consent';checkbox.type='checkbox';checkbox.checked=data.draft.consent===true;checkbox.onchange=()=>{data.draft.consent=checkbox.checked;changed();};const lab=el('label',undefined,'check');lab.append(checkbox,el('span',tr('I reviewed the site, units, datum, geometry, sources and assumptions, and authorize these inputs for conditional calculation. This does not establish engineering acceptance.','我已审核本站、单位、基准、几何、来源及假设，授权按这些输入进行条件性计算。这不构成工程接受。')));screen.append(lab);
 const actions=el('div',undefined,'actions');actions.append(button(tr('Check completeness','检查完整性'),validateForm),button(tr('Confirm inputs and continue','确认输入并继续'),approve,'primary'),button(tr('Save for later','保存待续'),pause));screen.append(actions);
 if(data.check){const box=el('div',undefined,data.check.ready?'card':'card warning');box.append(el('h3',data.check.ready?tr('Inputs passed the current checks','输入通过当前检查'):tr('Still needs your attention','仍需你处理')));
 const list=el('ul',undefined,'error-list');for(const e of data.check.errors){const f=data.fields.find(f=>f.key===e.field);const li=el('li');li.append(button((f?label(f)+': ':'')+e[language==='zh'?'zh':'en'],()=>{if(f){step=group(f);render();const box=[...document.querySelectorAll('.field')].find(x=>x.dataset.key===f.key);if(box){const d=box.closest('details');if(d)d.open=true;box.scrollIntoView({behavior:'smooth',block:'center'});box.querySelector('input,select,textarea')?.focus();}}}));list.append(li);}box.append(list);screen.append(box);}
}
async function validateForm(){await operation(async()=>{applyResponse(await request('validate',payload()));notice('');});}
async function approve(){await operation(async()=>{const r=await request('validate',payload());applyResponse(r);if(!data.check.ready)return;const result=await request('apply',{revision:data.draft.revision});if(result.status==='APPLIED')done(result.status,result.project);else{data.check=result;render();}});}
async function pause(){await operation(async()=>{await request('pause',payload());done('WAITING_FOR_INPUT');});}
function download(){const blob=new Blob([JSON.stringify(data.draft,null,2)],{type:'application/json;charset=utf-8'});const a=el('a');a.href=URL.createObjectURL(blob);a.download=data.project_id+'_intake_record.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
function openCancel(){const d=$('#cancelDialog');$('#cancelTitle').textContent=tr('Abandon this workflow?','放弃此工作流？');$('#cancelExplain').textContent=tr('This stops further calculation for this project. Sources, drafts and previous results are retained. Restarting requires an explicit new review.','这会停止此项目的后续计算。资料、草稿及历史结果保留，重新开始需明确发起新审核。');$('#cancelNameLabel').textContent=tr('Your name','姓名');$('#cancelReasonLabel').textContent=tr('Reason','原因');$('#cancelConsent').textContent=tr('I choose to abandon this project workflow.','我明确选择放弃此项目工作流。');$('#keepWorking').textContent=tr('Keep working','继续填写');$('#confirmCancel').textContent=tr('Confirm abandonment','确认放弃');$('#cancelName').value=data.draft.reviewer||'';$('#cancelConfirm').checked=false;$('#cancelError').textContent='';d.showModal();}
$('#keepWorking').onclick=()=>$('#cancelDialog').close();
$('#confirmCancel').onclick=()=>operation(async()=>{if(!$('#cancelName').value.trim()||!$('#cancelReason').value.trim()||!$('#cancelConfirm').checked)throw Error(tr('Enter your name and reason, and confirm abandonment.','请填写姓名和原因，并勾选明确放弃。'));const result=await request('cancel',{revision:data.draft.revision,reviewer:$('#cancelName').value,reason:$('#cancelReason').value,confirmed:$('#cancelConfirm').checked});$('#cancelDialog').close();done(result.status);}).catch(showError);
function done(status,project){notice('');$('#subtitle').textContent=tr('Your decision is saved locally. See the next step below.','决定已保存在本机，请查看下方下一步。');finished=true;clearTimeout(timer);dirty=false;$('#badge').textContent=status;$('#saved').textContent=tr('Decision saved','决定已保存');$('#screen').replaceChildren();const box=el('div',undefined,'card');box.id='complete';const title=status==='APPLIED'?tr('Inputs confirmed','输入已确认'):status==='CANCELLED'?tr('Workflow abandoned','工作流已放弃'):tr('Saved for later','已保存，等待继续');box.append(el('h2',title),el('p',status==='APPLIED'?tr('Return to PowerShell to follow calculation and report progress. Only a completed solver run can produce hydraulic results.','请返回 PowerShell 查看计算和报告进度，只有真实求解完成后才会产生水力结果。'):status==='CANCELLED'?tr('No further calculation will start for this project until you explicitly restart its review.','明确重新开始审核前，此项目不会继续计算。'):tr('You can close this page and PowerShell. Reopen the wizard with the command below.','可以关闭页面和 PowerShell。用下列命令可恢复填报。')));if(!data.launcher_url)box.append(el('pre','.\\.venv\\Scripts\\python.exe workflow.py '+(status==='APPLIED'?'run':'intake')+' --project "'+data.session.project+'" --scenario '+data.scenario+(status==='CANCELLED'?' --refresh':'')));if(data.launcher_url){const a=el('a',tr('Return to workflow home →','返回工作流首页 →'));a.href=data.launcher_url;box.append(a);box.querySelector('p').textContent=status==='APPLIED'?tr('Calculation will continue automatically. Follow progress and open reports from the home page.','计算会自动继续。回到首页查看进度及报告。'):tr('Your decision is saved. Return to the home page; no terminal command is needed.','决定已保存，回到首页即可，无需输入终端命令。');}if(project)box.append(el('p',tr('Approved project: ','已批准配置：')+project,'muted'));$('#screen').append(box);document.querySelector('footer').hidden=true;$('#steps').replaceChildren();}
function render(){
 if(finished)return;document.documentElement.lang=language==='zh'?'zh-CN':'en';$('#title').textContent=tr('Complete project inputs','补齐项目资料');$('#subtitle').textContent=tr('Your progress is saved locally. Calculation waits for your decision.','进度保存在本机，计算等待你的决定。');$('#language').textContent=language==='zh'?'English':'简体中文';$('#project').replaceChildren(el('strong',data.title),el('div',data.project_id+' · '+data.scenario,'muted'));$('#badge').textContent=data.session.status;
 $('#steps').replaceChildren();steps().forEach((title,i)=>{$('#steps').append(button(title,()=>{step=i;render();window.scrollTo(0,0);},step===i?'active':''));});$('#screen').replaceChildren();if(step===0)overview();else if(step===4)review();else fieldScreen();
 $('#back').textContent=tr('Back','上一步');$('#back').disabled=step===0;$('#next').textContent=step===4?tr('Check completeness','检查完整性'):tr('Next','下一步');$('#save').textContent=tr('Save draft','保存草稿');savedText();
}
$('#language').onclick=()=>{language=language==='en'?'zh':'en';try{localStorage.setItem('hecras-intake-language',language);}catch{}render();};
$('#back').onclick=()=>{if(step>0){step--;render();}};$('#next').onclick=()=>{if(step<4){step++;render();window.scrollTo(0,0);}else validateForm().catch(showError);};$('#save').onclick=()=>save().catch(showError);
window.addEventListener('beforeunload',e=>{if(dirty&&!finished){e.preventDefault();e.returnValue='';}});
request('state').then(r=>{data=r;if(r.session.status!=='WAITING_FOR_INPUT'){done(r.session.status,r.session.approved_project);return;}render();}).catch(showError);
