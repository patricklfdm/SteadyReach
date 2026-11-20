const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const test=require('node:test');

function page(){
 const buttons=new Map(),fields=new Map(),draw=[],tables=[],calls=[];
 const el=(tag,text)=>({tag,text,children:[],attrs:{},append(...v){this.children.push(...v);},replaceChildren(){this.children=[];},setAttribute(k,v){this.attrs[k]=v;}});
 const current={id:'site_test',revision:3,summary:{sha256:'summary'},extent_review:{sha256:'comparison'}};
 const context=vm.createContext({current,tr:en=>en,el,
  details:(parent,label)=>{const e=el('details',label);parent.append(e);return e;},
  button:(label,_,fn)=>{buttons.set(label,fn);return el('button',label);},
  field:(parent,id,en,zh,value)=>{const e=el('select');e.value=value;fields.set(id,e);parent.append(e);return e;},
  table:(_,headers,rows)=>tables.push({headers,rows}),svgEl:(_,tag,data)=>draw.push({tag,data}),
  document:{createElementNS:(_,name)=>el(name)},notify:()=>{},open:async()=>{},
  api:async(route,body)=>{calls.push({route,body});if(route==='extent-decision')return {station:body.station};return current;}});
 for(const file of ['app_extent.js','app_handoff.js'])
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../ras_workflow/templates',file),'utf8'),context);
 return {context,current,fields,buttons,draw,tables,calls,el};
}

test('comparison opens on peak, plots field location and routes station-specific decisions',async()=>{
 const ui=page(), row={rs:'3000',wse_ft:104,cutline_xy:[[0,0],[40,20]],observations:[
  {xy:[5,5],date:'2011-05-05',kind:'bed',role:'holdout',observed_ft:99,issues:[],source:'survey'}],
  boundary_tests:[{case:'tail_low',parameter:'boundary_slopes.downstream',delta_ft:-.34}]};
 const cases=['old','new'].map(label=>({label,profile:'Q100',rows:[{rs:'4000'},row]}));
 ui.context.drawExtent(ui.el('div'),{classification:'NATIVE_GEOMETRY_COMPARISON',cases,max_wse_change:{station:'3000',signed_ft:-2}});
 assert.equal(ui.fields.get('extent-rs').value,'3000');assert.ok(ui.draw.some(s=>s.tag==='polygon'));
 assert.ok(ui.tables.some(t=>t.rows.some(r=>r.includes('-0.340'))));
 await ui.buttons.get('Request field survey at this station')();
 assert.equal(ui.calls[0].body.station,'3000');assert.equal(ui.calls[0].body.comparison_token,'comparison');
 await ui.buttons.get('Use the second geometry in a new editable revision')();
 assert.equal(ui.calls.at(-1).route,'revision');assert.equal(ui.calls.at(-1).body.confirmed,true);
});

test('handoff stays on demand and only exposes single-file recovery for the current edition',async()=>{
 for(const stale of [true,false]){
  const ui=page(),key='Restore this PDF';
  ui.context.api=async(route,body)=>{ui.calls.push({route,body});return {storage:{originals:[],reinstallable:[]},package:{
   stale,run:'one',edition:'frozen',attachments:[],coordinate_files:{complete:['GIS/Contours.shp']},additional_sources:[],
   pdfs:[{ok:false,package:'minimal',path:'Graph/Exhibit_EN.pdf'}]}};};
  ui.context.renderHandoff(ui.el('div'));assert.equal(ui.calls.length,0);
  await ui.buttons.get('Inspect handoff and storage')();assert.equal(ui.buttons.has(key),!stale);
  if(!stale){await ui.buttons.get(key)();assert.equal(ui.calls[1].route,'handoff-repair');assert.equal(ui.calls[1].body.edition,'frozen');}
 }
});
