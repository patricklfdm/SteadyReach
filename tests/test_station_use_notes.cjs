const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ctx = vm.createContext({tr: en => en});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../ras_workflow/templates/app_atlas.js'), 'utf8'), ctx);

test('the section view applies limits only to the selected profile and station', () => {
  const rows = [
    {profile: 'Q100', side: 'downstream', threshold_ft: .1, stations: ['1400.00']},
    {profile: 'Q100', excluded: ['1500.0'], verified: ['200.00']},
    {profile: 'Q500', side: 'upstream', threshold_ft: .1, stations: ['200.00']}
  ];
  assert.match(ctx.stationUseNotes(rows, 'Q100', '1400')[0], /downstream/);
  assert.match(ctx.stationUseNotes(rows, 'Q100', '1500')[0], /No verified/);
  assert.match(ctx.stationUseNotes(rows, 'Q100', '200')[0], /common section/);
  assert.equal(ctx.stationUseNotes(rows, 'Q100', '300').length, 0);
  assert.equal(ctx.stationUseNotes(rows, 'Q500', '1400').length, 0);
  assert.match(ctx.stationUseNotes(undefined, 'Q100', '200')[0], /pending/);
});
