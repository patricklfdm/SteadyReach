const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const elements=[],buttons=[],calls=[],messages=[];
function el(tag,text){const node={tag,text,children:[],attrs:{},isConnected:true,handlers:{},append(...v){this.children.push(...v);},replaceChildren(...v){this.children=v;},setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];},addEventListener(k,fn){this.handlers[k]=fn;},scrollIntoView(){},classList:{add(){}}};elements.push(node);return node;}
let resolve,reject;
const context=vm.createContext({Map,Set,Number,Math,current:{id:'trial',summary:{sha256:'native'}},tr:(en)=>en,el,
 details(parent,en){const d=el('details'),box=el('div');box.parentElement=d;d.append(box);parent.append(d);return box;},guidanceTarget:n=>n,
 api:async(route,body)=>{calls.push({route,body});return new Promise((a,b)=>{resolve=a;reject=b;});},
 button(en,zh,fn){buttons.push({en,fn});return el('button',en);},notify:m=>messages.push(m),table(){},
 field(parent,id,en,zh,value){const n=el('input');n.id=id;n.value=value;parent.append(n);return n;},
 document:{createElementNS:(ns,tag)=>el(tag)},profileGrid(){},svgEl:()=>el('svg-child'),openGuidanceTool(){}});
const flush=()=>new Promise(r=>setImmediate(r));
(async()=>{
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../ras_workflow/templates/app_atlas.js'),'utf8'),context);
 assert.equal(context.atlasNumber(null),'—');assert.equal(context.atlasNumber(0),'0.000');
 const rows=[{profile:'Q100',rs:'100',needs_attention:true,issues:[{code:'DIVIDED'}]},{profile:'Q200',rs:'100',needs_attention:false,issues:[]}];
 assert.equal(context.atlasSelected(rows,'Q100','attention','divided').length,1);assert.equal(context.atlasSelected(rows,'Q200','attention','').length,0);assert.equal(context.atlasSelected(rows,'','all','').length,2);
 const parent=el('div');context.renderResultAtlas(parent);assert.equal(calls.length,0,'closed panel should not load full profiles');
 const outer=parent.children[0];outer.open=true;outer.handlers.toggle();assert.equal(calls[0].route,'qa-atlas');assert.equal(calls[0].body.summary_hash,'native');
 reject(Error('changed raw result'));await flush();assert.ok(buttons.some(b=>b.en==='Retry section review'));
 const retry=buttons.find(b=>b.en==='Retry section review').fn();
 const packet={sections:[],attention_section_profiles:0,located_diagnostic_count:0,diagnostic_count:0,source_errors:[],warning_coverage:'VERIFIED',unlocated_issues:[]};resolve(packet);await retry;
 assert.ok(elements.some(e=>String(e.text).includes('0 section/profile')));assert.equal(calls.length,2);
 outer.handlers.toggle();assert.equal(calls.length,2,'open should reuse already verified view');
 const newParent=el('div');context.renderResultAtlas(newParent);const newOuter=newParent.children[0];newOuter.open=true;newOuter.handlers.toggle();
 const count=elements.length;context.current={id:'other',summary:{sha256:'other'}};resolve(packet);await flush();assert.equal(elements.length,count,'stale project response must not draw');
 assert.ok(calls.every(c=>c.route==='qa-atlas'),'read-only requests only');
 console.log('Atlas lazy load, feedback/retry, filters, null semantics and stale response guard PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
