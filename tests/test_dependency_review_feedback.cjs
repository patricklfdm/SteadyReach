const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../ras_workflow/templates/app_editor.js'),'utf8');
const buttons=new Map(),inputs=new Map(),messages=[],calls=[];
const texts=[];
const el=(tag,text)=>{if(text)texts.push(text);return {append(){}};};
const key='g.boundary_slopes.downstream';
const review={revision:3,review_token:'sealed',errors:[{code:'DERIVED_INPUT_CHANGED',field:key}],fields:[{
 key,kind:'number',label:{en:'Downstream slope',zh:'下游坡降'},unit:'ft/ft',value:.011647,
 evidence_class:'assumed',basis:'Original proxy',answer:{candidate_record:{range:[.001,.02]}},
 parameter_candidates:[{candidate:'current',value:.006,evidence_class:'assumed',basis:'New proxy',range:[.004,.008]}]}]};
const context=vm.createContext({current:{id:'isolated',revision:3},finalReview:review,dependencyReviewState:null,dirty:false,
 tr:en=>en,el,details:el,format:String,originName:v=>v,saveAll:async()=>{},
 field(parent,id,en,zh,value,type,options,change){const input={value,change,options};inputs.set(id,input);return input;},
 button(en,zh,action){buttons.set(en,action);return el();},
 notify:message=>messages.push(message),showFinalReview:async()=>calls.push('review'),
 revealParameter:async key=>calls.push({reveal:key}),
 api:async(route,body)=>{calls.push({route,body});return route==='resolve-dependencies'?{saved_fields:[key]}:{id:'isolated',revision:4};}});
vm.runInContext(source.slice(source.indexOf('function renderDependencyReview('),source.indexOf('function renderManual(')),context);
(async()=>{
 context.renderDependencyReview(el(),review);
 const save=buttons.get('Save these decisions and refresh review');
 const select=inputs.get('dependency-'+key);
 assert.equal(select.value,'');
 await assert.rejects(save,/Choose at least/);
 select.change('0');
 context.renderDependencyReview(el(),review); // Language rerender retains the pending decision.
 assert.equal(inputs.get('dependency-'+key).value,'0');
 context.dirty=true;
 await assert.rejects(save,/edited/);
 context.dirty=false;
 const api=context.api;
 context.api=async()=>{throw Error('temporary connection failure');};
 await assert.rejects(save,/temporary/);
 assert.equal(context.finalReview,review);
 context.api=api;
 await save();
 assert.equal(calls[0].route,'resolve-dependencies');
 assert.equal(calls[0].body.review_token,'sealed');
 assert.equal(calls[0].body.selections[0].candidate,'current');
 assert.equal(calls.at(-1),'review');
 assert.match(messages.at(-1),/decisions saved/);
 assert.ok(!calls.some(c=>c.route==='start'));
 assert.ok(texts.some(t=>t.includes('Previous reference range')));
 context.finalReview=review;context.current={id:'isolated',revision:3};
 context.renderDependencyReview(el(),review);
 inputs.get('dependency-'+key).change('retain');
 await buttons.get('Save these decisions and refresh review')();
 const retained=calls.filter(c=>c.route==='resolve-dependencies').at(-1);
 assert.equal(retained.body.selections[0].action,'retain');
 const changedReview={...review,review_token:'new-review'};
 context.renderDependencyReview(el(),changedReview);
 assert.equal(inputs.get('dependency-'+key).value,'');
 console.log('Changed-dependency choices, stale edits, retry feedback and no implicit solve PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
