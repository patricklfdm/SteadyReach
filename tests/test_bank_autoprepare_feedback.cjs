const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const actions=[];
function node(tag,text){return {tag,text,children:[],append(...children){this.children.push(...children)}}}
function textTree(n){return [n.text,...n.children.map(textTree)].filter(Boolean).join(' ')}
let chinese=false,selected=null;
const context=vm.createContext({tr:(en,zh)=>chinese?zh:en,el:node,
 details(parent,en,zh){const n=node('details',chinese?zh:en);parent.append(n);return n},
 button(en,zh,action){actions.push(action);return node('button',chinese?zh:en)},
 document:{getElementById(id){selected=id;return null}}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../ras_workflow/templates/app_automation.js'),'utf8'),context);
const data={refreshed_equivalent_fields:['g.test'],bank_preparation:{staged_count:1,deferred_count:2,
 rows:[{index:4,rs:600,before_ft:[20,80],proposed_ft:[25,85]}]}};
for(const lang of [false,true]){
 chinese=lang;const root=node('root');context.renderPreparedBanks(root,data);
 const text=textTree(root);assert.match(text,/600/);assert.match(text,/20.00 \/ 80.00/);assert.match(text,/25.00 \/ 85.00/);
 assert.ok(text.includes(lang?'此处尚未启动计算':'No calculation has started'));
 assert.ok(text.includes(lang?'当前保存值为准':'current saved values'));
}
actions[0]();assert.equal(selected,'input-g.cross_sections.4.bank_stations_ft');
const empty=node('root');context.renderPreparedBanks(empty,{});assert.equal(empty.children.length,0);
console.log('Bilingual automatic-bank draft summary, old/new values, edit link, and legacy absence PASS');
