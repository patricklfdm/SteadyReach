const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../ras_workflow/templates/app_results.js'), 'utf8');
const spacing = source.slice(source.indexOf('function renderSpacing('), source.indexOf('function renderStudy(parent)'));
const buttons = new Map();
const checks = [];
const calls = [];
const plan = {analysis_kind:'section_spacing', scope:'all',intervals:[], excluded_intervals:[],
  cases:[{id:'baseline',section_count:4,added_sections:[]}]};
const element = () => ({append(){},replaceChildren(){},addEventListener(){}});
const context = vm.createContext({
  current:{id:'isolated',revision:3,model_type:'river',pending_study:{path:'old',sha256:'old'},pending_study_plan:plan},
  tr:en=>en,el:element,details:element,field:(box,id)=>({...element(),value:id==='spacing-limit'?'12':'automatic'}),table(){},notify(){},
  check(){const checkbox={checked:false};checks.push(checkbox);return checkbox;},
  button(en,zh,fn){buttons.set(en,fn);return element();},
  api:async(route,body)=>{calls.push({route,body});return {token:'new',entry:{path:'new-study',sha256:'new'},plan};},
  open:async()=>{},
});

(async()=>{
  vm.runInContext(spacing,context);
  context.renderSpacing(element());
  await buttons.get('Prepare nested spacing preview')();
  assert.equal(calls[0].body.scope,'automatic');
  assert.equal(calls[0].body.maximum_intervals,12);
  assert.equal(context.current.pending_study.sha256,'new');
  assert.equal(context.current.pending_study.path,'new-study');
  // Language switching rerenders from current state.
  context.renderSpacing(element());
  await assert.rejects(buttons.get('Confirm and run three spacing cases')(),/confirm/);
  assert.equal(calls.filter(c=>c.route==='study-start').length,0);
  checks.at(-1).checked=true;
  await buttons.get('Confirm and run three spacing cases')();
  assert.equal(calls.at(-1).route,'study-start');
  assert.equal(calls.at(-1).body.token,'new');
  assert.equal(calls.at(-1).body.confirmed,true);
  buttons.clear();plan.status='NO_ELIGIBLE_INTERVALS';plan.cases=[];plan.selection={unlocated_spacing_issues:[]};plan.excluded_intervals=[{upstream_rs:400,downstream_rs:300,reason_code:'BELOW_TWO_CELL_NESTED_SPACING'}];
  context.renderSpacing(element());
  assert.equal(buttons.has('Confirm and run three spacing cases'),false);
  console.log('Spacing proposal persistence, automatic scope, limits and no-eligible calculation gate PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
