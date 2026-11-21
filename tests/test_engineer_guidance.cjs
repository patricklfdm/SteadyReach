const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function loadTemplate(file) {
  const context = vm.createContext({resumePage: async () => {}});
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../ras_workflow/templates', file), 'utf8'), context);
  return context;
}

test('survey priorities retain conditional zeroes and conflicts and omit supported or unrelated fields', () => {
  const {surveyPriorities} = loadTemplate('app_editor.js');
  const field = (key, value, evidence_class, extra) => ({key, value, evidence_class, ...extra});
  const rows = [
    field('g.structure.groups.1.depth_blocked_ft', 0, 'assumed'),
    field('g.structure.groups.1.us_invert_ft', 250, 'reported', {source_conflict: true}),
    field('g.structure.groups.1.ds_invert_ft', 239, 'reported'),
    field('g.structure.road.width_ft', null, 'missing', {missing: true, required: false}),
    field('g.boundary_slopes.downstream', 0.01, 'assumed'),
    field('g.channel_geometry_basis', 'conditional_surface_dem', 'reported')
  ];
  const keys = Array.from(surveyPriorities(rows), group => group.fields[0].key);
  assert.deepEqual(keys, [rows[1].key, rows[0].key, rows[5].key]);
});

test('intersection guide identifies section pairs from the active candidate geometry only', () => {
  const {crossingPairs} = loadTemplate('app_geometry_auto.js');
  const rows = [4400, 4100, 4250].map(rs => ({rs, cutline_xy:[[0,0],[1,1]]}));
  const issues = [
    {code:'INTERSECTING_SECTIONS', sections:[2,0]}, {code:'INTERSECTING_SECTIONS', sections:[2,4]},
    {code:'SELF_INTERSECTING_CUT', sections:[1]}
  ];
  const pairs = Array.from(crossingPairs(issues,rows), pair => Array.from(pair, row => row.rs));
  assert.deepEqual(pairs, [[4250,4400]]);
});
