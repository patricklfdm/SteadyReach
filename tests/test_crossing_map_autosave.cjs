const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

test('a point added during a save is written with the next project revision',async()=>{
 const editor=fs.readFileSync(path.join(__dirname,'../ras_workflow/templates/app_editor.js'),'utf8');
 const saveCode=editor.slice(editor.indexOf(' async function savePoints()'),editor.indexOf(' for(const input of [width,spacing,gap]'));
 const calls=[];
 let release;
 const context=vm.createContext({
  current:{id:'site',revision:4},groupPicks:{},groupIndex:0,anchors:{inlet:[],outlet:[],upstream:[[1,2]]},
  pointVersion:0,pointsTimer:null,pointsPromise:null,mapDirty:false,pendingMapSave:null,
  width:{value:110},spacing:{value:40},gap:{value:1},status:{},
  api:async(route,body)=>{calls.push(body);if(calls.length===1)await new Promise(resolve=>{release=resolve;});return {id:'site',revision:body.revision+1};},
  save:async()=>{},structuredClone,clearTimeout(){},setTimeout(){},tr:en=>en,refreshCandidateControls(){},
 });
 vm.runInContext(saveCode,context);
 context.queuePoints();
 const save=context.savePoints();
 await new Promise(resolve=>setImmediate(resolve));
 context.anchors.upstream.push([3,4]);context.queuePoints();
 const flush=context.savePoints();
 release();await Promise.all([save,flush]);
 assert.deepEqual(calls.map(body=>[body.revision,body.picks.upstream.length]),[[4,1],[5,2]]);
 assert.equal(context.mapDirty,false);
 assert.equal(context.pendingMapSave,null);
 assert.match(context.status.textContent,/Upstream: 2/);
});
