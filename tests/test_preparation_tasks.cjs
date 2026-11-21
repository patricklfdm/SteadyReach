const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ui = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../ras_workflow/templates/app_sources.js'),'utf8'),ui);
const field=(key,value,more={})=>({key,value,required:true,missing:value==null,label:{en:key,zh:key},...more});
test('next steps separate blockers, source gaps, existing choices and judgment',()=>{
 const rows=[
  field('c.scenarios.0.profiles.0.flow_cfs',null,{unit:'cfs'}),
  field('g.structure.groups.0.us_invert_ft',13,{source_conflict:true}),
  field('g.structure.groups.0.depth_blocked_ft',0),
  field('g.cross_sections.0.bank_stations_ft',null),
  field('g.flow_regime',null,{parameter_candidates:[{value:'mixed'}]}),
  field('c.scenarios.0.channel_n',null),
  field('g.structure.groups.0.name',null,{required:false})
 ];
 const model={intake:{section_count:1,fields:rows,geometry_review:{issues:[{code:'INTERSECTING_SECTIONS'}]}}};
 const groups=ui.preparationActions(model);
 assert.deepEqual(Array.from(groups,g=>g.kind),['repair','conflict','source','banks','candidates','judgment']);
 const request=ui.scopedParameterCsv(groups.find(g=>g.kind==='source').fields);
 assert.equal(request.split('\r\n').length,2);
 assert.match(request,/"c\.scenarios\.0\.profiles\.0\.flow_cfs","","cfs"/);
 assert.doesNotMatch(request,/depth_blocked|invert|bank_stations/);
 assert.equal(ui.preparationActions({...model,native:{}}).length,0);
 assert.equal(ui.preparationActions({...model,results:{}}).length,0);
});
test('a ready draft has no artificial outstanding tasks',()=>{
 const model={intake:{section_count:12,fields:[field('c.scenarios.0.profiles.0.flow_cfs',457)]},missing:[]};
 assert.equal(ui.preparationActions(model).length,0);
 assert.equal(ui.preparationActions({...model,missing:['issue']})[0].kind,'checks');
});
test('one crossing request covers multiple barrels, crest and vertical reference; event flow stays separate',()=>{
 const fields=['g.structure.groups.0.us_invert_ft','g.structure.groups.1.ds_invert_ft','g.structure.road.width_ft',
  'g.vertical_datum','c.scenarios.0.profiles.0.flow_cfs','g.boundaries.downstream.stages_ft'].map(k=>field(k,null));
 const groups=ui.requestBundles(fields);
 assert.deepEqual(Array.from(groups,g=>g.kind),['crossing','flow','control']);
 assert.deepEqual(Array.from(groups,g=>g.fields.length),[4,1,1]);
 const request=ui.scopedParameterCsv(groups[0].fields,groups[0].labels);
 assert.match(request,/request_en,request_zh/);
 assert.match(request,/same datum/);assert.doesNotMatch(request,/flow_cfs/);
 assert.equal(ui.requestBundles([fields[3]])[0].kind,'control');
 const estimated=field('g.structure.groups.0.length_ft',31,{evidence_class:'assumed'});
 const inferred=field('g.structure.groups.0.ds_invert_ft',null,{parameter_candidates:[{evidence_class:'inferred'}]});
 const reported=field('g.structure.groups.0.us_invert_ft',null,{parameter_candidates:[{evidence_class:'reported'}]});
 assert.deepEqual(Array.from(ui.siteEvidenceRequests([estimated,inferred,reported]),f=>f.key),[estimated.key,inferred.key]);
 assert.match(ui.scopedParameterCsv([estimated],groups[0].labels),/"verify_adopted","31","assumed"/);
});
test('a coordinate draft with prepared sections offers automatic derivation once before requesting site data',()=>{
 const draft={route:'coordinates',automation:{},intake:{section_count:8,fields:[field('c.scenarios.0.profiles.0.flow_cfs',null)]}};
 assert.equal(ui.preparationActions(draft)[0].kind,'derive');
 assert.equal(ui.preparationActions({...draft,preparation_result:{}})[0].kind,'source');
});
test('clicking automatic preparation acts on the current saved project',async()=>{
 let click;const calls=[];
 const ctx=vm.createContext({current:{id:'site_test',revision:3},tr:en=>en,
  el:()=>({append(){}}),button:(en,zh,fn)=>{click=fn;return {};},
  saveAll:async()=>{ctx.current.revision=4;},api:async(route,body)=>calls.push([route,body.id,body.revision]),open:async id=>calls.push([id])});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../ras_workflow/templates/app_sources.js'),'utf8'),ctx);
 ctx.renderPreparationActions({append(){}},[{kind:'derive',fields:[]}]);
 await click();assert.deepEqual(calls,[['automatic-prepare','site_test',4],['site_test']]);
});
test('blocking automation checks remain visible on complete fields and spatial checks appear once',()=>{
 const crossing={code:'INTERSECTING_SECTIONS',sections:[1,2]};
 const dependency={code:'DERIVED_INPUT_CHANGED',blocking:true,field:'g.structure.road.width_ft'};
 const model={intake:{section_count:3,fields:[],geometry_review:{issues:[crossing]}},
  missing:[],automation:{checks:{issues:[{...crossing,blocking:true},dependency,{code:'ADVERSE_INVERT',blocking:false}]}}};
 const groups=ui.preparationActions(model);
 assert.deepEqual(Array.from(groups,g=>g.kind),['repair','dependencies']);
 assert.deepEqual(Array.from(groups[1].issues,i=>i.code),['DERIVED_INPUT_CHANGED']);
});
