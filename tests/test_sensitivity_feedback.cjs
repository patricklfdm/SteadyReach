const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const buttons=new Map(),inputs=new Map(),checks=[],calls=[],messages=[];
const element=()=>({append(){},replaceChildren(){},addEventListener(event,fn){this[event]=fn;}});
const packet={token:'ranges-1',maximum_parameters:4,notes:[],parameters:[
 {path:'boundary_slopes.downstream',label:{en:'Downstream',zh:'下游'},value:.003,unit:'ft/ft',options:[{id:'adopted',origin:'ADOPTED_RANGE',low:.002,high:.004,basis:'DEM proxy'}],recommended_id:'adopted'},
 {path:'scenario.channel_n',label:{en:'Roughness',zh:'糙率'},value:.04,unit:'n',options:[{id:'source',origin:'UNSELECTED_SOURCE_RANGE',low:.03,high:.05,basis:'Check river match'}],recommended_id:null}
]};
const plan={cases:[{id:'baseline',changes:[]},{id:'low',changes:[{path:'boundary_slopes.downstream',before:.003,after:.002}]}],measurement_topics:[]};
const context=vm.createContext({current:{id:'trial',revision:1},lang:'en',tr:en=>en,el:element,details:element,table(){},
 notify:value=>messages.push(value),open:async()=>{},
 field(parent,id,en,zh,value){const v={...element(),value:String(value??'')};inputs.set(id,v);return v;},
 check(parent,en,zh,value,onchange){const v={checked:value,onchange};checks.push(v);return v;},
 button(en,zh,fn){buttons.set(en,fn);return element();},
 api:async(route,body)=>{calls.push({route,body});if(route==='study-suggest')return packet;return {token:'plan-1',entry:{sha256:'plan-1'},plan};}
});
(async()=>{
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../ras_workflow/templates/app_sensitivity.js'),'utf8'),context);
 assert.equal(context.sensitivityParameterLabel('scenario.channel_n'),'Channel Manning n');
 context.renderSuggestedSensitivity(element());
 await buttons.get('Suggest ranges from calculation inputs')();
 assert.equal(checks[0].checked,true);assert.equal(checks[1].checked,false);
 await buttons.get('Prepare selected cases for one confirmation')();
 assert.equal(calls.at(-1).route,'study-prepare');assert.equal(calls.at(-1).body.range_token,'ranges-1');
 assert.equal(calls.at(-1).body.parameters.length,1);
 await assert.rejects(buttons.get('Confirm and run selected sensitivity cases')(),/confirm/);
 assert.equal(calls.filter(c=>c.route==='study-start').length,0);
 inputs.get('suggested-low-0').value='.0015';inputs.get('suggested-low-0').input();
 await assert.rejects(buttons.get('Confirm and run selected sensitivity cases')(),/confirm/);
 context.lang='zh';context.renderSuggestedSensitivity(element());
 assert.equal(inputs.get('suggested-low-0').value,'.0015');
 await assert.rejects(buttons.get('Confirm and run selected sensitivity cases')(),/confirm/);
 await buttons.get('Prepare selected cases for one confirmation')();
 checks.at(-1).checked=true;
 await buttons.get('Confirm and run selected sensitivity cases')();
 assert.equal(calls.at(-1).route,'study-start');assert.equal(calls.at(-1).body.token,'plan-1');
 await buttons.get('Suggest ranges from calculation inputs')();
 assert.equal(context.current.pending_study_plan,undefined);
 context.renderSuggestedSensitivity(element());
 await assert.rejects(buttons.get('Confirm and run selected sensitivity cases')(),/confirm/);
 assert.ok(messages.some(m=>m.includes('not started')));
 console.log('Suggested range selection, edit invalidation, language persistence and final confirmation PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
