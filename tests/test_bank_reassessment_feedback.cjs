const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const context=vm.createContext({tr:(en,zh)=>en,structuredClone,current:{id:'isolated',intake:{geometry_review:{bank_reassessment:{id:'old'}}}}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../ras_workflow/templates/app_automation.js'),'utf8'),context);
const proposal={rows:[
 {index:0,changed:true,proposed_ft:[20,80],recommended:true},
 {index:1,changed:true,proposed_ft:[30,90],recommended:false},
 {index:2,changed:false,proposed_ft:[40,100],recommended:true},
 {index:3,changed:true,proposed_ft:null,recommended:true}
]};
assert.equal(JSON.stringify(context.stableBankChoices(proposal)),'[0]');
assert.equal(JSON.stringify(context.stableBankChoices({rows:[]})),'[]');
assert.equal(context.bankValuesText([null,75]),'— / 75.00');
assert.equal(context.bankValuesText(null),'—');
const refreshed={id:'new-preview',rows:[{index:0}]};
context.retainBankProposal('isolated',refreshed);
assert.equal(context.current.intake.geometry_review.bank_reassessment.id,'new-preview','Language/render restoration must use the newest preview token');
refreshed.rows[0].index=99;
assert.equal(context.current.intake.geometry_review.bank_reassessment.rows[0].index,0);
assert.throws(()=>context.retainBankProposal('another-project',refreshed),/Project changed/);
console.log('Grouped stable-bank selection and current-preview persistence across render/language changes PASS');
