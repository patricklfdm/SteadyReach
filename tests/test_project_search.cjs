const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('Filtering by edition ID shows its family and clearing restores every row', () => {
  const source = fs.readFileSync(path.join(__dirname, '../ras_workflow/templates/app.js'), 'utf8');
  function element(tag, textContent, className) {
    return {tag, textContent, className, children: [], append(...items) {this.children.push(...items);},
      setAttribute() {}, addEventListener(name, fn) {this[name]=fn;}, focus() {this.focused=true;}};
  }
  const ctx = {el: element, tr: en => en, familyTitle: group => group.title};
  const fn = vm.runInNewContext(source.slice(source.indexOf('let projectFilter='),source.indexOf('async function renderSavedProjects'))+';projectSearch',ctx);
  const rows = ['Midway','Soquel'].map((title,i) => ({group:{title,id:'base'+i,versions:[{title,id:'revision'+i}]},node:{open:true}}));
  function draw() {
    const parent=element();
    fn(parent,rows)();
    const [label,clear,status]=parent.children[0].children;
    return {input:label.children[1],clear,status};
  }
  let {input,clear,status}=draw();
  input.value=' REVISION1 ';input.input();
  assert.deepEqual(rows.map(r=>r.node.hidden),[true,false]);
  assert.match(status.textContent,/1 \/ 2/);
  ({input,clear,status}=draw()); // Refreshing the library keeps the typed filter.
  assert.equal(input.value,' REVISION1 ');
  input.value='unknown';input.input();
  assert.equal(status.textContent,'No matching projects');
  clear.onclick();
  assert.ok(input.focused && clear.hidden);
  assert.deepEqual(rows.map(r=>[r.node.hidden,r.node.open]),[[false,true],[false,true]]);
});
