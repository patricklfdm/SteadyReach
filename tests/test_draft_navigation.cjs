const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = name => fs.readFileSync(path.join(__dirname, '../ras_workflow/templates', name), 'utf8');
function element() {
  return {dataset:{}, isConnected:true, disabled:false, value:'', listeners:{}, files:[],
    append(){}, replaceChildren(){}, setAttribute(){}, removeAttribute(){},
    addEventListener(type, fn){this.listeners[type]=fn;}};
}
function screen() {
  const nodes = new Map(), storage = new Map();
  function select(key) {
    if(!nodes.has(key)) nodes.set(key, element());
    return nodes.get(key);
  }
  const context=vm.createContext({document:{createElement:element,querySelector:select,querySelectorAll:()=>[],body:element()},
    window:{addEventListener(){}},location:{pathname:'/test/'},localStorage:{getItem(){},setItem(){}},
    sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)}});
  vm.runInContext(source('app.js'),context);
  return {context, select};
}

test('changing language never invokes a pending adoption callback; explicit adoption still works',async()=>{
  const {context,select}=screen();
  vm.runInContext(`let finalReview=null,commits=0;current={id:'A'};
    save=async()=>{};render=()=>{};showPending=()=>{};function validateBankInputs(){}
    function stage(){stageChange('candidates','choices',1,async()=>{commits++;});}
    writeDraft(draftKey('candidates'),[['field',{value:0}]]);stage();`,context);
  await select('#language').onclick();
  assert.equal(vm.runInContext('commits',context),0);
  assert.equal(vm.runInContext("readDraft(draftKey('candidates'))[0][1].value",context),0);
  assert.equal(vm.runInContext("readDraft(draftKey('candidates','another'))",context),null);
  await vm.runInContext('stage();saveAll()',context);
  assert.equal(vm.runInContext('commits',context),1);
});


test('batch recovery lists the baseline and the individual retries using the saved journal',()=>{
  const {context}=screen(),shown=[];
  Object.assign(context,{renderCheckBatchProgress(){}});
  vm.runInContext(source('app_results.js'),context);
  const m={scenario:'q100',status:'NEEDS_ATTENTION',results:{run_id:'existing'},job:{action:'check-batch',status:'FAILED'},
    delivery:{complete:{},minimal:{},status:'READY_FOR_REVIEW'},study_progress:[{id:'baseline',status:'COMPUTED'},
      {id:'refinement_1',status:'FAILED'},{id:'refinement_2',status:'FAILED'}]};
  assert.match(context.batchHeadline(m),/Q100 results available.*incomplete/i);
  context.renderBatchStatus({append:(...items)=>shown.push(...items.map(n=>n.textContent))},m);
  assert.ok(shown.includes('Saved calculations: baseline'));
  assert.ok(shown.includes('Cases to check on retry: refinement_1, refinement_2'));
  assert.ok(shown.includes('Delivery: Complete and Minimal available'));
  assert.equal(context.batchHeadline({...m,job:{action:'delivery',status:'FAILED'}}),'');
});

test('refreshing the confirm screen reads the model without adopting a staged choice',async()=>{
  const {context}=screen(),args=[];
  context.window.history={state:{steadyReach:{page:'confirm',project:'A'}}};
  context.capture=v=>args.push(v);
  vm.runInContext("current={id:'A',status:'INPUTS_READY'};open=async()=>{};let showFinalReview=async(adopt)=>capture(adopt);",context);
  await context.resumePage();
  assert.deepEqual(args,[false]);
});

test('field feedback belongs to a project, run and event, including an attachment until reload',async()=>{
  const {context}=screen();
  const inputs=new Map(),box=element(),routes=[];
  box.parentElement={open:true,addEventListener(){}};
  const rows=['A','B'].map(event=>({event,date:'day',rs:'100',point_id:event,stage_ft:1}));
  Object.assign(context,{el:element,button:element,details:()=>box,table(){},
    field:(parent,id,en,zh,value='',type='text')=>{const item={...element(),value,id,type};inputs.set(id,item);return item;},
    api:async route=>{routes.push(route);return route==='field/request'?{rows}:{};}});
  vm.runInContext(source('app_field_feedback.js'),context);
  vm.runInContext("current={id:'test',revision:3,summary:{sha256:'run'}};feedbackLink=()=>{};renderFieldFeedback({});",context);
  await new Promise(resolve=>setImmediate(resolve));
  const select=inputs.get('field-event'),ref=inputs.get('feedback-reference'),file=inputs.get('field-source');
  ref.value='Observed at XS 100';ref.listeners.input();
  file.files=[{name:'survey.txt'}];file.listeners.change();
  async function change(event){select.value=JSON.stringify([event,'day']);await select.onchange();}
  await change('B');
  assert.equal(inputs.get('feedback-reference').value,'');
  await change('A');
  assert.equal(inputs.get('feedback-reference').value,ref.value);
  assert.equal(inputs.get('field-source').files[0].name,'survey.txt');
  vm.runInContext('draftFiles.clear();uiDrafts.clear()',context);
  await change('B');await change('A');
  assert.equal(inputs.get('field-source').dataset.reselect,'["survey.txt"]');
  assert.equal(inputs.get('feedback-reference').value,ref.value);
  assert.ok(routes.every(r=>['field/request','field/latest'].includes(r)));
});

test('native-import submission freezes editable controls and restores their prior state after failure',async()=>{
  const controls=[element(),element(),element()],message=element();
  controls[1].disabled=true;controls[0].dataset.field='title';controls[0].value='typed';
  let rejectRequest;
  const context=vm.createContext({window:{addEventListener(){}},location:{pathname:'/test/'},
    document:{querySelector:s=>s==='#consent'?controls[2]:message,querySelectorAll:s=>s==='[data-field]'?[controls[0]]:controls},
    fetch:()=>new Promise((_,reject)=>{rejectRequest=reject;})});
  vm.runInContext(source('native_import.js').split("request('state').then")[0],context);
  const running=vm.runInContext("data={draft:{revision:1}};act('save')",context);
  assert.ok(controls.every(c=>c.disabled));rejectRequest(Error('local connection interrupted'));await running;
  assert.deepEqual(controls.map(c=>c.disabled),[false,true,false]);
  assert.equal(controls[0].value,'typed');assert.match(message.textContent,/interrupted/);
});
