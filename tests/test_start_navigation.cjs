const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../ras_workflow/templates/app.js'), 'utf8');
const resume = source.slice(source.indexOf('async function resumePage()'), source.indexOf('async function home()'));
test('Reload restores the saved screen and never submits a calculation', async () => {
  for (const [view,status,expected] of [
    [null,'',['home']],
    [{project:'x',page:'confirm'},'INPUTS_READY',['open','review']],
    [{project:'x',page:'confirm'},'PROCESSING',['open']],
    [{project:'x',page:'results',resultTab:'delivery'},'RESULTS_READY',['open','result-panel-delivery']],
    [{project:'gone'},'MISSING',['open','home','notice']]
  ]) {
    const calls=[];
    const context={window:{history:{state:{steadyReach:view}}},current:{status,results:status==='RESULTS_READY'},
      open:async()=>{calls.push('open');if(status==='MISSING')throw Error('missing');},home:async()=>calls.push('home'),
      showFinalReview:async()=>calls.push('review'),tr:en=>en,notify:()=>calls.push('notice'),
      document:{getElementById:id=>({dispatchEvent(){calls.push(id);}})},CustomEvent:class {}};
    await vm.runInNewContext(resume+';resumePage()',context);
    assert.deepEqual(calls,expected);
  }
});
const home = source.slice(source.indexOf('async function home()'), source.indexOf('function savedProjectGroups'));
function node() {
  return {children: [],files:[],dataset:{},querySelectorAll(){return [];},setAttribute(){},replaceChildren(...items){this.children=items;},append(...items) { this.children.push(...items); }};
}

for (const hasProjects of [false,true]) {
  test('Home route selection with saved projects = '+hasProjects, async () => {
    const fields = {'#screen': node()};
    const panels = {};
    const buttons={},elements=[],requests=[];
    const survey=[{name:'survey.json',text:async()=>JSON.stringify({files:[{name:'river.tif'}]})},{name:'river.tif'},{name:'unlisted.txt'}];
    const context = {
      poll: null, clearTimeout() {}, rememberView() {}, shell() {}, notify(){}, tr: a => a,
      el(){const e=node();elements.push(e);return e;},button(en,zh,fn){buttons[en]=fn;return node();},check:node,
      renderPractice(){},viewRequest:0,pendingChanges:new Map(),draftKey:()=>'',restoreForm(){
        if(hasProjects)elements.find(e=>e.id==='survey-directory').files=survey;
      },observeForm(){},Event:class{},surveyLimit:()=>'',
      encodeFiles:async files=>Array.from(files,f=>f.name),api:async(route,body)=>{requests.push(body);return {profiles:['event'],files:body.survey_files};},
      $: id => fields[id], nativeSelector(){fields['#native-files']=node();}, scopeFields(){for(const id of ['#project-flow-paths','#project-purpose'])fields[id]={dispatchEvent(){}};}, renderSavedProjects(saved) {
        saved.querySelector = () => hasProjects;
      },
      field(parent,id,en,zh,value) {
        return fields['#'+id] = {...node(),parentElement:node(),value,disabled:false};
      },
      details(parent,en,zh,open) {
        const panel=node();
        panel.parentElement={open};
        panels[en]=panel;
        return panel;
      }
    };
    await vm.runInNewContext(home+';home()', context);
    assert.equal(panels['Start a new project'].parentElement.open,!hasProjects);
    const route=fields['#route'], scope=fields['#model-type'];
    assert.equal(scope.value,'');
    scope.value='river';scope.onchange();
    route.value='survey';route.onchange();
    assert.equal(fields['#latitude'].parentElement.hidden,true);
    assert.equal(scope.value,'river');
    if(hasProjects){
      await buttons['Inspect survey sources and event criteria']();
      assert.deepEqual(requests.at(-1).survey_files,['survey.json','river.tif']);
    }
    route.value='native';route.onchange();
    assert.equal(scope.disabled,true);
    assert.equal(scope.value,'culvert');
    route.value='coordinates';route.onchange();
    assert.equal(fields['#latitude'].parentElement.hidden,false);
    assert.equal(scope.disabled,false);
    assert.equal(scope.value,'river');
  });
}
