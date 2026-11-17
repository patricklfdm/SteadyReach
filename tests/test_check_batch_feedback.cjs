const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const buttons=new Map(),fields=new Map(),checks=[],calls=[],notes=[];
const element=()=>({append(){},replaceChildren(){},addEventListener(){}});
const plan={status:'REVIEW_REQUIRED',maximum_calculations:8,deferred_parameters:[],steps:[{id:'sensitivity',status:'READY',maximum_calculations:5,parameters:[{path:'boundary_slopes.downstream',low:.001,high:.01}]}]};
const proposal={token:'saved',plan,studies:{sensitivity:{measurement_topics:[]}}};
const context=vm.createContext({current:{id:'isolated',revision:1,model_type:'river',check_batch_preview:proposal},
 tr:(en,zh)=>en,el:(tag,text)=>{if(text)notes.push(text);return element()},details:element,
 field:(p,id,en,zh,value)=>{const input={...element(),value};fields.set(id,input);return input},table(){},notify(){},open:async()=>{},
 check(p,en,zh,value){const box={...element(),checked:value};checks.push(box);return box},
 button(en,zh,fn){buttons.set(en,fn);return element()},api:async(route,body)=>{calls.push({route,body});return proposal}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../ras_workflow/templates/app_check_batch.js'),'utf8'),context);
(async()=>{
 context.renderCheckBatch(element());
 await assert.rejects(buttons.get('Confirm and run checks → deliverables')(),/confirm/);
 checks.at(-1).checked=true;await buttons.get('Confirm and run checks → deliverables')();
 assert.equal(calls.at(-1).route,'checks-start');assert.equal(calls.at(-1).body.token,'saved');
 await buttons.get('Prepare checks and delivery preview')();
 assert.equal(calls.at(-1).route,'checks-prepare');assert.equal(calls.at(-1).body.maximum_rounds,2);
 assert.equal(context.current.check_batch_preview.token,'saved');
 assert.ok(notes.some(v=>v.includes('Total limit: 8')));
 context.current.active_check_batch={plan:{sha256:'original'}};
 context.current.check_batch_progress={status:'INCOMPLETE',steps:{delivery:{status:'INCOMPLETE',error:'export test'}}};
 context.renderCheckBatch(element());await buttons.get('Resume checks and delivery')();
 assert.equal(calls.at(-1).body.retry,true);assert.equal(calls.at(-1).body.token,'original');
 context.current.check_batch_progress={status:'QUEUED',steps:{}};buttons.clear();context.renderCheckBatch(element());
 assert.ok(buttons.has('Resume checks and delivery'));
 context.current.check_batch_preview.plan.options={sensitivity:false,spacing:true,maximum_intervals:7,maximum_rounds:0,maximum_width_ft:1500};
 context.renderCheckBatch(element());
 assert.equal(fields.get('checks-intervals').value,7);assert.equal(fields.get('checks-rounds').value,0);
 assert.equal(fields.get('checks-width').value,1500);assert.equal(checks.at(-3).checked,false);
 console.log('Batch scope, consent gate, preview retention and same-confirmation retry PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
