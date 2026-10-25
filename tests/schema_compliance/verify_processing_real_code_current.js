'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const source = fs.readFileSync(path.join(root, 'src/pdi_nomad_plugin/mbe/processing/static/app.js'), 'utf8');
const stop = source.indexOf("window.addEventListener('message'");
assert.ok(stop > 0, 'Cannot isolate Processing functions');
const calls = [];
let rejectValidation = false;
const sample = {
  m_def: 'pdi_nomad_plugin.mbe.materials.SubstrateMbe',
  lab_id: 'MN2490_4',
  description: 'Crystal ID: MN2490\nCharge ID: 04',
  components: [{pure_substance: {molecular_formula: 'SrTiO3'}}],
  crystal_properties: {surface_orientation: {hkl_reciprocal: {h_index: 0, k_index: 0, l_index: 1}}},
  geometry: {m_def: 'nomad_material_processing.general.SquareCuboid', width: 0.01, length: 0.01, height: 0.0005}
};
const ctx = {
  window: {NOMAD_API_BASE: '/nomad-oasis/api/v1', location: {pathname: '/nomad-oasis/dashboards/processing/'}},
  document: {getElementById: () => ({})},
  console, URLSearchParams, Date, Set, Map, Promise,
  fetch: async (url, options = {}) => {
    calls.push({url, options});
    if (url.endsWith('/entries/query')) {
      assert.equal(options.method, 'POST');
      const body = JSON.parse(options.body);
      assert.equal(body.query['section_defs.definition_qualified_name'],
        'pdi_nomad_plugin.mbe.materials.SubstrateMbe');
      return {ok: true, json: async () => ({
        data: [{entry_id: 'entry1', upload_id: 'up1', entry_name: 'MN2490_4'}],
        pagination: {}
      })};
    }
    if (url.endsWith('/entries/entry1/archive')) {
      return {ok: true, json: async () => ({
        data: {archive: {data: sample}}
      })};
    }
    if (url === './validate-process') return {ok: !rejectValidation, status: rejectValidation ? 422 : 200,
      json: async () => rejectValidation ? {detail: 'Rejected by original m_def'} :
        {valid: true, schema: 'nomad_material_processing.general.Cleaning'}};
    if (url.includes('/uploads/')) return {ok: true, json: async () => ({processing: {entry: {entry_id: 'saved'}}})};
    throw new Error('Unexpected fetch: ' + url);
  }
};
// This fixture contains no existing Sample Cuts.
ctx.cutExistingEntries = async () => [];
vm.createContext(ctx);
vm.runInContext(source.slice(0, stop), ctx);
(async () => {
  const entries = await vm.runInContext('loadSubstrates()', ctx);
  assert.equal(entries.length, 1);
  assert.equal(ctx.window.processingCutHistoryError, '',
    'Sample Cut history must load without errors');
  assert.equal(entries[0].material, 'SrTiO3');
  assert.equal(entries[0].orientation, '0 0 1');
  assert.equal(entries[0].crystalId, 'MN2490');
  assert.equal(entries[0].chargeId, '04');
  assert.equal(entries[0].parentSample, undefined);
  vm.runInContext("recipeSchemas = {cleaning:{label:'Cleaning',processSchema:'nomad_material_processing.general.Cleaning'}}", ctx);
  const archive = vm.runInContext('processArchiveData', ctx)(
    {type: 'cleaning', datetime: '2026-10-16T14:00:00', recipe: {entryId: 'r1', uploadId: 'up2'}}, entries, 0);
  assert.equal(archive.m_def, 'nomad_material_processing.general.Cleaning');
  assert.equal(archive.samples[0].reference, '../uploads/up1/archive/entry1#/data');
  assert.equal(archive.recipe, '../uploads/up2/archive/r1#/data');
  const uploader = vm.runInContext('uploadArchive', ctx);
  await uploader('up1', 'test.archive.json', archive);
  assert.ok(calls.some(c => c.url === './validate-process'));
  assert.ok(calls.some(c => c.url.includes('/uploads/')));
  assert.ok(calls.findIndex(c => c.url === './validate-process') < calls.findIndex(c => c.url.includes('/uploads/')));
  calls.length = 0;
  rejectValidation = true;
  await assert.rejects(uploader('up1', 'blocked.archive.json', archive), /Rejected by original m_def/);
  assert.equal(calls.some(c => c.url.includes('/uploads/')), false, 'preflight must block writes');
  assert.throws(() => vm.runInContext('processArchiveData', ctx)(
    {type: 'unknown', datetime: '2026-10-16T14:00:00', recipe: {entryId: 'r1', uploadId: 'up2'}}, entries, 0
  ), /Unsupported process type/);
  console.log('Processing original-only read/write boundary: 13 JS assertions passed');
})().catch(e => {console.error(e); process.exit(1)});
