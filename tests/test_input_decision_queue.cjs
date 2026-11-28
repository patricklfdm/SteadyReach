'use strict';
const assert=require('node:assert/strict');
const {test}=require('node:test');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../ras_workflow/templates/app_sources.js'),'utf8');
const ctx=vm.createContext({});
vm.runInContext(source,ctx);
test('each input has one decision, with conflicts and missing measurements visible',()=>{
 const make=(key,options)=>({key,required:true,missing:true,...options});
 const rows=[make('g.structure.groups.0.us_invert_ft',{}),
  make('g.structure.groups.0.ds_invert_ft',{source_conflict:true,parameter_candidates:[{}]}),
  make('g.structure.groups.0.length_ft',{parameter_candidates:[{}]}),
  make('g.setting',{}),make('g.roughness',{missing:false,evidence_class:'assumed'})];
 const groups=ctx.decisionQueue(rows);
 for(const [i,id] of ['measure','conflict','candidate','decision','assumption'].entries()){
  assert.equal(groups[id].length,1);assert.equal(groups[id][0].key,rows[i].key);
 }
});
test('field returns list only changed inputs and unverified parents reopen the full list',()=>{
 const fields=[{key:'a'},{key:'b'}];
 for(const [mode,expected] of [['CHANGES_ONLY',['b']],['FULL_REVIEW',['a','b']]]){
  const list=ctx.decisionFields({fields,return_scope:{mode,affected:[{key:'b'}]}});
  assert.deepEqual(Array.from(list,f=>f.key),expected);
 }
});
test('opening evidence from preparation preserves a pending candidate choice',()=>{
 assert.match(ctx.renderDecisionQueue.toString(),/await showFinalReview\(false\)/);
});
