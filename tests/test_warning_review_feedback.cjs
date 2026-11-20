const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../ras_workflow/templates/app_warning_study.js'),'utf8');
const calls=[],buttons=new Map(),fields=new Map();
const element=()=>({append(){},replaceChildren(){},addEventListener(){}});
const metrics={warnings:13,notes:0,errors:0,wet_ends:0,low_ends:0,critical:0,numerical:0,section_count:22,min_margin_ft:.41,max_wse_delta_ft:.5};
const plan={analysis_kind:'native_warning_review',policy:{metrics,maximum_rounds:8,maximum_width_ft:2000}};
const current={revision:2,id:'site',latest_warning_study:{sha256:'result'},warning_study:{
  recommended:'trial_01',lowest_count:'baseline',residual:[],stop:'BUDGET_REACHED',
  cases:['baseline','trial_01'].map(id=>({id,metrics,audit:{path:'projects/site/audit.json'},project:{path:'projects/site/Model.prj'}}))
}};
const ctx=vm.createContext({current,tr:en=>en,el:element,details:element,table(){},notify(){},open:async()=>{},
 field(p,id,en,zh,value){const e={...element(),value};fields.set(id,e);return e;},
 button(en,zh,fn){buttons.set(en,fn);return element();},
 api:async(route,body)=>{calls.push({route,body});return {plan,entry:{sha256:'seal'},token:'seal'};},
 continueStudyCase:async(...args)=>calls.push({continue:args})});
vm.runInContext(source,ctx);
(async()=>{
 ctx.renderWarningStudy(element());
 await buttons.get('Preview scope and original warnings')();
 assert.equal(calls[0].body.kind,'warning_review');assert.equal(calls[0].body.maximum_rounds,8);
 assert.equal(calls.length,1);
 await buttons.get('Confirm limits and start automatic review')();
 assert.equal(calls[1].route,'study-start');assert.equal(calls[1].body.token,'seal');assert.equal(calls[1].body.confirmed,true);
 await buttons.get('Create editable revision from this trial')();
 assert.deepEqual(calls[2].continue,['warning_review','trial_01','result']);
 console.log('Native warning preview, confirmation and independent revision PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
