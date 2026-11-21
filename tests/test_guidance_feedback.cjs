const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const calls=[],messages=[],buttons=[],nodes=[],targets=new Map();
function element(){const e={isConnected:true,children:[],attrs:{},append(...v){this.children.push(...v);},replaceChildren(...v){this.children=v;},setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];},scrollIntoView(){this.scrolled=true;},focus(){this.focused=true;}};nodes.push(e);return e;}
const reviewPanel={hidden:true,dispatchEvent(event){assert.equal(event.type,'steadyreach-show-panel');this.hidden=false;}};
const panel=element(),outer={tagName:'DETAILS',open:false},target=element();target.parentElement=outer;target.closest=()=>reviewPanel;targets.set('qa-tool-coverage',target);targets.set('qa-tool-qa',element());
let resolve,reject;
const context=vm.createContext({Map,CustomEvent:class {constructor(type){this.type=type;}},current:{id:'trial',revision:1,summary:{sha256:'run'}},tr:en=>en,
 el:element,details:parent=>{const n=element();parent.append(n);return n;},table(){},sensitivityParameterLabel:x=>x,
 document:{getElementById:id=>targets.get(id)},notify:x=>messages.push(x),
 button(en,zh,fn){buttons.push({name:en,fn});return element();},
 api:async(route,body)=>{calls.push({route,body});return new Promise((a,b)=>{resolve=a;reject=b;});}});
const packet={issue_count:2,verified_study_count:1,actions:[{title:{en:'Coverage'},explanation:{en:'Review'},records:2,locations:[['Q100','100']],target:'coverage'}]};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../ras_workflow/templates/app_guidance.js'),'utf8'),context);
 context.renderGuidance(panel);assert.equal(calls[0].route,'qa-guidance');assert.equal(calls[0].body.summary_hash,'run');
 resolve(packet);await flush();await buttons.find(v=>v.name==='Open relevant review tool').fn();
 assert.equal(reviewPanel.hidden,false);assert.equal(outer.open,true);assert.equal(target.focused,true);assert.equal(target.scrolled,true);
 assert.ok(messages.at(-1).includes('No input changed'));assert.equal(calls.length,1);
 const count=buttons.length;context.renderGuidance(panel);context.current={id:'different',revision:1,summary:{sha256:'other'}};
 resolve(packet);await flush();assert.equal(buttons.length,count,'stale project result must not render');
 context.renderGuidance(panel);reject(Error('changed source'));await flush();
 assert.ok(buttons.some(v=>v.name==='Retry next-step guidance'));
 const retry=buttons.find(v=>v.name==='Retry next-step guidance').fn();resolve(packet);await retry;
 assert.equal(calls.length,4);assert.ok(calls.every(v=>v.route==='qa-guidance'));
 console.log('Automatic guidance loading, read-only navigation, stale response rejection and retry PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
