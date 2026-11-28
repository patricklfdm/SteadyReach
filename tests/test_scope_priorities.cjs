'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const context=vm.createContext({});
for(const name of ['app_sources.js','app_guidance.js']){
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../ras_workflow/templates',name),'utf8'),context);
}
test('a culvert invert and reach boundary precede ordinary edits without reading outside the scoped queue',()=>{
 const invert={key:'g.structure.groups.0.us_invert_ft'},boundary={key:'g.boundaries.downstream.type'};
 const ordinary={key:'c.label',missing:true,required:true},clash={key:'g.value',source_conflict:true};
 assert.deepEqual(Array.from(context.controllingInputs({rows:[ordinary,invert,clash]},'culvert'),f=>f.key),[clash.key,invert.key,ordinary.key]);
 assert.equal(context.controllingInputs({rows:[ordinary,boundary]},'river')[0],boundary);
});
test('confirmed result ownership issues precede a site priority; the same boundary evidence appears once',()=>{
 const step={code:'BOUNDARY_DOWNSTREAM_Q100',en:'RS 1400.',zh:'RS 1400。',action:{tool:'sensitivity'}};
 const outcome={code:'VERIFY_OUTLET_INFLUENCE',en:step.en+' Check stage.',zh:step.zh,action:step.action};
 const rows=context.priorityRows({edition_brief:{next_decision:outcome},review_steps:[step],findings:[
  {code:'OUTPUT_CONSISTENCY',reason:{en:'Ownership',zh:'归属'},target:'qa'}]},null);
 assert.deepEqual(Array.from(rows,r=>r.en),['Ownership',outcome.en]);
});
