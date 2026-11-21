const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const buttons=new Map(),notes=[],calls=[],opened=[];
const node=()=>({append(){},replaceChildren(){}});
const toolsOpened=[];
const context=vm.createContext({current:{id:'test',revision:2},tr:(en,zh)=>en,
 el:(tag,text)=>{if(text)notes.push(text);return node()},details:node,
 button:(en,zh,fn)=>{buttons.set(en,fn);return node()},
 api:async(route,body)=>calls.push({route,body}),open:async id=>opened.push(id),openGuidanceTool:key=>toolsOpened.push(key)});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../ras_workflow/templates/app_results.js'),'utf8'),context);
(async()=>{
 context.renderNextReview(node());await buttons.get('Prepare next review automatically')();
 assert.equal(calls.at(-1).route,'next-review');assert.equal(calls.at(-1).body.revision,2);
 context.current.next_review={status:'PREVIEW_READY',reason:'WET_SECTION_ENDS',action:'coverage',preview:{},changes:5,options:{maximum_rounds:3,maximum_width_ft:2000}};
 buttons.clear();notes.length=0;context.renderNextReview(node());
 assert.ok(notes.some(x=>x.includes('starts no additional solver')));assert.ok(notes.some(x=>x.includes('first-round extensions: 5')));
 assert.ok(!buttons.has('Prepare next review automatically'));
 buttons.get('Inspect the prepared review')();assert.equal(toolsOpened.at(-1),'coverage');
 context.current.next_review.unresolved=[{rs:100}];buttons.clear();context.renderNextReview(node());
 assert.ok(buttons.has('Prepare joint geometry suggestions'));await buttons.get('Prepare joint geometry suggestions')();
 assert.equal(calls.at(-1).route,'next-review');
 context.current.next_review.joint_revision={status:'DRAFT_READY',project_id:'child',changes:3,rotations:2,geometry_applied:true,unresolved:[{}]};
 buttons.clear();notes.length=0;context.renderNextReview(node());
 assert.ok(notes.some(x=>x.includes('separate joint direction')));assert.ok(notes.some(x=>x.includes('rotations: 2')));
 assert.ok(!buttons.has('Prepare joint geometry suggestions'));
 await buttons.get('Open the prepared geometry revision')();assert.equal(opened.at(-1),'child');
 context.current.next_review.joint_revision.status='EDITED_REVISION';notes.length=0;context.renderNextReview(node());
 assert.ok(notes.some(x=>x.includes('edits are retained')));
 context.current.next_review={status:'PREPARATION_FAILED',error:'test failure'};buttons.clear();notes.length=0;
 context.renderNextReview(node());assert.ok(notes.includes('test failure'));assert.ok(buttons.has('Prepare next review automatically'));
 context.current.next_review={status:'CONFIRMED_SEPARATELY'};buttons.clear();context.renderNextReview(node());
 assert.equal(buttons.size,0);assert.ok(notes.some(x=>x.includes('confirmed separately')));
 assert.ok(!calls.some(x=>['start','study-start','checks-start'].includes(x.route)));
 console.log('Automatic preparation, explicit consent separation, preview navigation and recoverable failure PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
