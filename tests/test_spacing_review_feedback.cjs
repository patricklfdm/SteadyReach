const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const nodes=[],buttons=[],calls=[];
function el(tag,text){const n={tag,text,children:[],attrs:{},handlers:{},isConnected:true,append(...v){this.children.push(...v);},replaceChildren(...v){this.children=v;},setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];},addEventListener(k,v){this.handlers[k]=v;},classList:{add(){}}};nodes.push(n);return n;}
let resolve,reject;
const context=vm.createContext({Map,Set,Number,Math,current:{id:'test',summary:{sha256:'base'},latest_spacing:{sha256:'study'}},tr:en=>en,el,
 details(parent,en,zh,open=false){const outer=el('details'),box=el('div');outer.open=open;box.parentElement=outer;outer.append(box);parent.append(outer);return box;},
 api:async(route,body)=>{calls.push({route,body});return new Promise((a,b)=>{resolve=a;reject=b;});},button(en,zh,fn){buttons.push({en,fn});return el('button',en);},
 table(){},field(p,id,en,zh,value){const n=el('input');n.id=id;n.value=value;p.append(n);return n;},
 document:{createElementNS:(ns,tag)=>el(tag)},profileGrid(){},svgEl:()=>el('svg-child'),atlasMap(){}});
const flush=()=>new Promise(r=>setImmediate(r));
(async()=>{
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../ras_workflow/templates/app_spacing_review.js'),'utf8'),context);
 assert.equal(context.spacingReviewNumber(null),'—');assert.equal(context.spacingReviewNumber(0),'0.000000');
 const rows=[{profile:'Q100',rs:'100',exceeding_pairs:[1],flags:['WSE']},{profile:'Q100',rs:'200',exceeding_pairs:[],flags:['WET']},{profile:'Q200',rs:'100',exceeding_pairs:[],flags:[]}];
 assert.equal(context.spacingReviewRows(rows,'Q100','changes','').length,1);assert.equal(context.spacingReviewRows(rows,'Q100','attention','').length,2);assert.equal(context.spacingReviewRows(rows,'Q200','all','100').length,1);
 const parent=el('div');context.renderSpacingDiagnostics(parent);assert.equal(calls.length,0);
 const outer=parent.children[0];outer.open=true;outer.handlers.toggle();outer.handlers.toggle();assert.equal(calls.length,1,'busy calls must not repeat');
 assert.equal(calls[0].route,'spacing-diagnostics');assert.equal(calls[0].body.study_token,'study');
 assert.ok(nodes.some(n=>String(n.text).includes('Authenticating')));
 reject(Error('native evidence changed'));await flush();assert.ok(buttons.some(b=>b.en==='Retry spacing comparison'));
 const retry=buttons.find(b=>b.en==='Retry spacing comparison').fn();
 const packet={cases:[],rows:[],pairs:[],section_profiles:0,above_threshold:0,wet_section_profiles:0,missing_results:0,unlocated_issues:[]};resolve(packet);await retry;
 assert.ok(nodes.some(n=>String(n.text).includes('0 section/profile')));outer.handlers.toggle();assert.equal(calls.length,2);
 const second=el('div');context.renderSpacingDiagnostics(second);second.children[0].open=true;second.children[0].handlers.toggle();const count=nodes.length;
 context.current.latest_spacing.sha256='changed';resolve(packet);await flush();assert.equal(nodes.length,count,'stale study response must not draw');
 assert.ok(calls.every(v=>v.route==='spacing-diagnostics'),'must not mutate or solve');
 console.log('Spacing filters, null semantics, lazy loading, busy/retry and stale response checks PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
