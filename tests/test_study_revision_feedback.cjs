const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../ras_workflow/templates/app_geometry_auto.js'),'utf8');
const calls=[];
const context=vm.createContext({current:{id:'parent',revision:4},tr:en=>en,
 api:async(route,body)=>{calls.push({route,body});return{id:'independent',status:'PROCESSING'};},
 open:async id=>calls.push({open:id}),notify:message=>calls.push({message})});
vm.runInContext(source.slice(source.indexOf('async function continueStudyCase(')),context);
(async()=>{
 await context.continueStudyCase('coverage','repair_2','sealed-analysis');
 assert.equal(calls[0].route,'revision');
 assert.equal(calls[0].body.case_id,'repair_2');
 assert.equal(calls[0].body.study_token,'sealed-analysis');
 assert.equal(calls[0].body.prepare,true);
 assert.equal(calls[1].open,'independent');
 assert.match(calls[2].message,/consolidated draft/);
 assert.equal(calls.filter(c=>c.route==='start'||c.route==='study-start').length,0);
 context.api=async()=>({id:'saved-draft',status:'INPUTS_READY'});
 await context.continueStudyCase('spacing','refinement_1','sealed-spacing');
 assert.match(calls.at(-1).message,/draft saved.*could not start/);
 const results=fs.readFileSync(path.join(__dirname,'../ras_workflow/templates/app_results.js'),'utf8');
 const buttons=new Map(),selections=new Map(),continued=[];
 const element=()=>({append(){},replaceChildren(){},addEventListener(){}});
 const view=vm.createContext({current:{model_type:'river',latest_coverage:{path:'coverage/analysis.json',sha256:'coverage-seal'},
  coverage_result:{status:'GEOMETRY_REVIEW_REQUIRED',cases:[{id:'saved_baseline',status:'REUSED_BASELINE'},
   {id:'repair_1',status:'COMPUTED'},{id:'repair_2',status:'FAILED'}]},
  latest_spacing:{path:'spacing/analysis.json',sha256:'spacing-seal'},
  spacing_result:{status:'NOT_CONVERGED',cases:[{id:'baseline',status:'COMPUTED'},
   {id:'refinement_1',status:'COMPUTED'},{id:'refinement_2',status:'FAILED'}]}},
  tr:en=>en,el:element,details:element,table(){},check(){return {...element(),checked:false};},
  field(parent,id,en,zh,value,type,options){const input={...element(),value};selections.set(id,{input,options});return input;},
  button(en,zh,action){buttons.set(en,action);return element();},
  continueStudyCase:async(...args)=>continued.push(args)});
 vm.runInContext(results.slice(results.indexOf('function renderCoverage('),results.indexOf('function renderStudy(parent)')),view);
 view.renderCoverage(element());
 view.renderSpacing(element());
 await buttons.get('Continue from final repair with automatic QA preparation')();
 assert.deepEqual(continued[0],['coverage','repair_1','coverage-seal']);
 const select=selections.get('spacing-continue-case');
 assert.equal(select.input.value,'refinement_1');
 assert.deepEqual(JSON.parse(JSON.stringify(select.options)),[['refinement_1','refinement_1','refinement_1']]);
 await buttons.get('Prepare editable QA revision from selected case')();
 assert.deepEqual(continued[1],['spacing','refinement_1','spacing-seal']);
 console.log('Computed-case continuation opens the independent draft with preparation feedback PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
