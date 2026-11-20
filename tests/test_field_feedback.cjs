const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const messages = [], buttons = new Map(), calls = [], opened = [];
const panel = {append() {}, replaceChildren() {}};
const ui = vm.createContext({
  tr: en => en,
  el: (tag, text) => { if (text) messages.push(text); return panel; },
  table() {},
  button: (en, cn, action) => { buttons.set(en, action); return panel; },
  api: async (route, body) => { calls.push({route, body}); return {id: 'child'}; },
  open: async id => opened.push(id)
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../ras_workflow/templates/app_field_feedback.js'), 'utf8'), ui);

async function run() {
  const row = {rs:'100', original_source:'测量, "A"', reference:'a\nb', uncertainty_ft:0.25};
  const csv = ui.feedbackCsv([row]);
  assert.ok(csv.includes('"测量, ""A"""'));
  assert.ok(csv.includes('"a\nb"'));
  const review = {mode:'event', assumed:true, event:'flood', date:'2019-02-21', flow_cfs:450,
    stages:[], rows:[row], uses:{documented:[], assumed:['100'], unresolved:[]}, blockers:['BOUNDARY_ACCURACY']};
  const req = {id:'parent', revision:2, summary_hash:'original'};
  const preview = {review, token:'saved'};
  ui.feedbackPreview(panel, preview, req);
  assert.ok(messages.some(s => s.includes('ASSUMED FEEDBACK')));
  assert.ok(messages.some(s => s.includes('downstream point identity')));
  assert.equal(buttons.size, 0);
  review.blockers = [];
  ui.feedbackPreview(panel, preview, req);
  assert.equal(calls.length, 0);
  await buttons.get('Confirm and compute this scenario')();
  assert.equal(calls[0].route, 'field/confirm');
  assert.equal(calls[0].body.token, 'saved');
  assert.equal(calls[0].body.confirmed, true);
  assert.equal(calls[0].body.summary_hash, 'original');
  assert.deepEqual(opened, ['child']);
  console.log('Field feedback CSV, assumption display, blockers and explicit confirmation PASS');
}
run().catch(e => { console.error(e); process.exitCode = 1; });
