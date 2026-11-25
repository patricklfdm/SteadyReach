const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const templates = path.resolve(__dirname, '../ras_workflow/templates');
const blocks = [];
function el() {
 return {value: '', append(){}, replaceChildren(){}};
}
const src = {sha256: 'one', path: 'sources/official.pdf'};
const flow = {field:'c.scenarios.0.profiles.0.flow_cfs',candidate:'flow',source:src,source_locus:{pdf_page:30},hydrologic_context:{stream:'River',location:'Upper town',aep_percent:1},value:110};
const rough = {field:'c.scenarios.0.channel_n',candidate:'rough',source:src,source_locus:{pdf_page:38},hydrologic_context:{stream:'River'},value:.05};
const fields = [flow,rough].map(row=>({key:row.field,acquisition:{status:'FIS_ROW_SELECTED'},answer:{candidate_record:row},parameter_candidates:[row]}));
const context = vm.createContext({current:{title:'River',intake:{fields}},el,
 details(parent,en,cn,expanded){ blocks.push({en,cn,expanded}); return el(); },
 tr: en=>en,field: (parent,id,en,cn,value)=>Object.assign(el(),{value}),
 button:el,originName:String,document:{createTextNode:String}});
vm.runInContext(fs.readFileSync(path.join(templates,'app_sources.js'),'utf8'),context);
context.renderFisSelection(el());
assert.equal(blocks.at(-1).expanded,false);
assert.match(blocks.at(-1).en,/River · Upper town · 110 cfs/);
fields[1].acquisition.status='FIS_STREAM_MISMATCH';
context.renderFisSelection(el());
assert.equal(blocks.at(-1).expanded,true);
fields.forEach(field=>field.parameter_candidates=[]);
context.renderFisSelection(el());
assert.equal(blocks.length,2);
const makeElement=(tag,text)=>({tag,text,children:[],append(...children){this.children.push(...children);}});
Object.assign(context,{URL,el:makeElement,sourceStatus:String});
const panel=makeElement('main');
const attempts=[{route:'FEMA_FIS_download',status:'DOWNLOAD_FAILED',url:'https://msc.fema.gov/portal/downloadProduct?productID=06087CV001C',error:'connection reset'},
 {route:'inventory',status:'OUTSIDE_PROVIDER_COVERAGE'},{route:'catalog',status:'NO_CATALOG_MATCH'}];
assert.equal(context.showAcquisitionGaps(panel,{attempts:attempts.slice(1)}),false);
assert.equal(context.showAcquisitionGaps(panel,{attempts,documents:[]}),true);
assert.match(JSON.stringify(panel),/06087CV001C.*connection reset/);
assert.doesNotMatch(JSON.stringify(panel),/local PDF with this/);
const recovered=makeElement('main');
context.showAcquisitionGaps(recovered,{attempts,documents:[{source:{original_name:'06087CV001C.pdf'}}]});
assert.match(JSON.stringify(recovered),/local PDF with this/);
const editor=fs.readFileSync(path.join(templates,'app_editor.js'),'utf8');
vm.runInContext(editor.slice(editor.indexOf('function riverBendIndex('),editor.indexOf('function renderRiverMap(')),context);
assert.equal(context.riverBendIndex([[0,0],[10,0]],[5,3]),1);
assert.equal(context.riverBendIndex([[0,0],[10,0],[10,10]],[9,6]),2);
const returned={returned_invert:true,candidate:'return',value:3,basis:'field log',datum:'NAVD88',source:src,evidence_class:'reported'};
function returnActions(existing, evidence_class, other=[]){
 const actions=[];
 Object.assign(context,{button:en=>{actions.push(en);return makeElement('button',en)},sourceFileHref:()=>'/source'});
 context.renderReturnedInverts(makeElement('main'),[{label:{en:'Inlet',zh:'进口'},value:existing,evidence_class,
   key:'g.structure.groups.0.us_invert_ft',parameter_candidates:[returned,...other]}]);
 return actions;
}
assert.ok(returnActions(4,'assumed').includes('Adopt displayed survey returns'));
assert.ok(returnActions(3,'reported').includes('Adopt displayed survey returns'));
for(const actions of [returnActions(4,'reported'),returnActions(4,'assumed',[{source:src,value:5}]),
                      returnActions(3,'assumed',[{...returned,candidate:'duplicate'}])]){
 assert.ok(actions.includes('Review alternatives'));
 assert.ok(!actions.includes('Adopt displayed survey returns'));
}
console.log('PASS current FIS rows, ordered river bends, and survey return conflicts');
