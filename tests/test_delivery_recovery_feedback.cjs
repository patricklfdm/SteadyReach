const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname,'../ras_workflow/templates/app_results.js'),'utf8');
const code = source.slice(source.indexOf('function renderDeliveryRecovery('),source.indexOf('function renderRevisionComparison('));
async function run(){
 const calls=[],nodes=[];
 const context=vm.createContext({current:{id:'isolated'},tr:en=>en,
  el:(_tag,text)=>({text}),button:(label,_cn,action)=>({label,action}),
  api:async(route,body)=>calls.push([route,body.id]),open:async id=>calls.push(['open',id])});
 vm.runInContext(code,context);
 context.renderDeliveryRecovery({append:(...items)=>nodes.push(...items)},{status:'INCOMPLETE',error:'HTTP Error 502'});
 assert.match(nodes[0].text,/saved.*without solving/);
 assert.match(nodes[1].text,/502/);
 await nodes[2].action();
 assert.deepEqual(calls,[['delivery','isolated'],['open','isolated']]);
 nodes.length=0;context.renderDeliveryRecovery({append:(...items)=>nodes.push(...items)},{status:'READY_FOR_REVIEW'});
 assert.equal(nodes.length,0);
 console.log('PASS failed delivery keeps a direct retry route without invoking the solver');
}
run().catch(error=>{console.error(error);process.exitCode=1;});
