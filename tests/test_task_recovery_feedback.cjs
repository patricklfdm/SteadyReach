const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function controls(model){
 const buttons=[],calls=[];
 const ui=vm.createContext({el:()=>({}),tr:en=>en,open:async()=>{},api:async(route,body)=>calls.push({route,body}),
  button:(label,cn,action)=>{buttons.push({label,action});return {};},showFinalReview:async()=>calls.push({route:'review'})});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../ras_workflow/templates/app_results.js'),'utf8'),ui);
 ui.renderTaskRecovery({append(){}},{id:'p',revision:3,task:'t',errors:['interrupted'],status:'INTERRUPTED',...model});
 return {buttons,calls};
}
test('retry routes to the failed stage only',async()=>{
 for(const action of ['analyze','acquire','prepare','automatic-prepare','delivery','report','native-export','next-review']){
  const {buttons,calls}=controls({job:{action,status:'FAILED'}});assert.equal(buttons.length,1);
  await buttons[0].action();assert.equal(calls[0].route,action);
 }
});
test('restoring evidence does not start a solver; restarting approved inputs is explicit',async()=>{
 for(const mode of ['RESTORE_RESULT','RESUME_COMPUTATION','REVIEW_INPUTS','RESTORE_EVIDENCE']){
  const {buttons,calls}=controls({job:{action:'run'},calculation_recovery:{mode}});
  if(mode==='RESTORE_EVIDENCE'){assert.equal(buttons.length,0);continue;}
  await buttons[0].action();
  if(mode==='REVIEW_INPUTS'){assert.equal(calls[0].route,'review');continue;}
  assert.equal(calls[0].route,'recover-run');assert.equal(calls[0].body.mode,mode);
  assert.equal(calls[0].body.confirmed===true,mode==='RESUME_COMPUTATION');
 }
});
