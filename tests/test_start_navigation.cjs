const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../ras_workflow/templates/app.js'), 'utf8');
const home = source.slice(source.indexOf('async function home()'), source.indexOf('function savedProjectGroups'));
function node() {
  return {children: [], append(...items) { this.children.push(...items); }};
}

for (const hasProjects of [false,true]) {
  test('Home route selection with saved projects = '+hasProjects, async () => {
    const fields = {'#screen': node()};
    const panels = {};
    const context = {
      poll: null, clearTimeout() {}, shell() {}, tr: a => a, el: node, button: node, check() {},
      $: id => fields[id], nativeSelector() {}, scopeFields() {}, renderSavedProjects(saved) {
        saved.querySelector = () => hasProjects;
      },
      field(parent,id,en,zh,value) {
        return fields['#'+id] = {parentElement:node(),value,disabled:false};
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
    route.value='survey';route.onchange();
    assert.equal(fields['#latitude'].parentElement.hidden,true);
    assert.equal(scope.value,'river');
    route.value='native';route.onchange();
    assert.equal(scope.disabled,true);
    assert.equal(scope.value,'culvert');
    route.value='coordinates';route.onchange();
    assert.equal(fields['#latitude'].parentElement.hidden,false);
    assert.equal(scope.disabled,false);
  });
}
