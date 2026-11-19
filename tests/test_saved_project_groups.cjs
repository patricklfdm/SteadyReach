const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../ras_workflow/templates/app.js'), 'utf8');
const groupProjects = vm.runInNewContext(source.slice(
  source.indexOf('function savedProjectGroups('), source.indexOf('async function renderSavedProjects(')
) + '\nsavedProjectGroups');

function project(id, parent) {
  return {id, title: 'Same site', parent_revision: parent && {project_id: parent}};
}

function versions(groups) {
  return Array.from(groups, group => [group.id, ...Array.from(group.versions, row => row.id)]);
}

test('independent starts stay separate and each descendant appears once under its original', () => {
  const rows = [project('final', 'repair'), project('sibling', 'original'), project('same-name'),
    project('repair', 'qa'), project('qa', 'original'), project('original')];
  assert.deepEqual(versions(groupProjects(rows, [])), [
    ['original', 'original', 'final', 'sibling', 'repair', 'qa'], ['same-name', 'same-name']
  ]);
});

test('deleting and restoring the original or an intermediate edition keeps descendants together', () => {
  const root = project('original'), qa = project('qa', root.id), revision = project('revision', qa.id);
  const sibling = project('sibling', root.id);
  const deleted = [qa, root];
  const [group] = groupProjects([revision, sibling], deleted);
  assert.equal(group.original, root);
  assert.deepEqual(versions([group]), [['original', 'revision', 'sibling']]);
  assert.deepEqual(versions(groupProjects([revision, sibling, root], [qa])),
    [['original', 'original', 'revision', 'sibling']]);
  assert.deepEqual(versions(groupProjects([], [root])), []);
});

test('a missing ancestor or a parent loop keeps all available versions accessible', () => {
  const [orphan] = groupProjects([project('b', 'missing'), project('a', 'missing')], []);
  assert.equal(orphan.original, undefined);
  assert.deepEqual(versions([orphan]), [['missing', 'b', 'a']]);
  assert.deepEqual(versions(groupProjects([project('leaf', 'c'), project('b', 'c'), project('c', 'b')], [])),
    [['b', 'b', 'leaf', 'c']]);
});
