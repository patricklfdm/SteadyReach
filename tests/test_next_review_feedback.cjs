const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const buttons=new Map(),notes=[],calls=[];
const node=()=>({append(){},replaceChildren(){}});
const panel={open:false};
const target={closest:()=>panel,scrollIntoView(){this.scrolled=true}};
const context=vm.createContext({current:{id:'test',revision:2},tr:(en,zh)=>en,
 el:(tag,text)=>{if(text)notes.push(text);return node()},details:node,
 button:(en,zh,fn)=>{buttons.set(en,fn);return node()},
 api:async(route,body)=>calls.push({route,body}),open:async()=>{},document:{getElementById:id=>target}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../ras_workflow/templates/app_results.js'),'utf8'),context);
(async()=>{
 context.renderNextReview(node());await buttons.get('Prepare next review automatically')();
 assert.equal(calls.at(-1).route,'next-review');assert.equal(calls.at(-1).body.revision,2);
 context.current.next_review={status:'PREVIEW_READY',reason:'WET_SECTION_ENDS',action:'coverage',preview:{},changes:5,options:{maximum_rounds:3,maximum_width_ft:2000}};
 buttons.clear();notes.length=0;context.renderNextReview(node());
 assert.ok(notes.some(x=>x.includes('starts no additional solver')));assert.ok(notes.some(x=>x.includes('first-round extensions: 5')));
 assert.ok(!buttons.has('Prepare next review automatically'));
 buttons.get('Inspect the prepared review')();assert.equal(panel.open,true);assert.equal(target.scrolled,true);
 context.current.next_review={status:'PREPARATION_FAILED',error:'test failure'};buttons.clear();notes.length=0;
 context.renderNextReview(node());assert.ok(notes.includes('test failure'));assert.ok(buttons.has('Prepare next review automatically'));
 context.current.next_review={status:'CONFIRMED_SEPARATELY'};buttons.clear();context.renderNextReview(node());
 assert.equal(buttons.size,0);assert.ok(notes.some(x=>x.includes('confirmed separately')));
 assert.ok(!calls.some(x=>['start','study-start','checks-start'].includes(x.route)));
 console.log('Automatic preparation, explicit consent separation, preview navigation and recoverable failure PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
