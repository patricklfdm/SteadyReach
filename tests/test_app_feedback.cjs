const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const templates = path.join(__dirname, '..', 'ras_workflow', 'templates');
const app = fs.readFileSync(path.join(templates, 'app.js'), 'utf8');
const geometry = fs.readFileSync(path.join(templates, 'app_geometry_auto.js'), 'utf8');
const polling = app.slice(app.indexOf('async function pollProject('), app.indexOf('async function open('));
const revision = geometry.slice(geometry.indexOf('async function prepareQaRevision('));

async function run() {
  const notices = [];
  const timers = [];
  const context = vm.createContext({
    current: {id: 'original', revision: 1},
    tr: en => en,
    notify: message => notices.push(message),
    setTimeout: (callback, delay) => timers.push({callback, delay}),
    api: async route => route === 'revision'
      ? {id: 'copy', revision: 2}
      : {layouts: [{changed_sections: [1, 2, 3]}]},
    open: async id => { context.current = {id, revision: 2}; },
  });
  vm.runInContext(polling + revision, context);
  await context.prepareQaRevision();
  assert.equal(context.current.id, 'copy');
  assert.match(notices.at(-1), /QA preview saved.*3 proposed section changes/);
  assert.doesNotMatch(notices.at(-1), /Preparing suggestions/);

  context.open = async () => { throw Error('temporary disconnect'); };
  await context.pollProject('copy');
  assert.equal(timers.at(-1).delay, 5000);
  assert.match(notices.at(-1), /retrying/);
  context.current = {id: 'another'};
  const count = timers.length;
  await timers.at(-1).callback();
  assert.equal(timers.length, count);
  console.log('PASS QA completion feedback and polling retry/navigation guards');
}

run().catch(error => { console.error(error); process.exitCode = 1; });
