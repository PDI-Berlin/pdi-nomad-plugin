'use strict';
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const assert = require('assert');

const app = fs.readFileSync(path.join(__dirname, '../../src/pdi_nomad_plugin/mbe/lab_library/static/app.js'), 'utf8');

async function scenario(validationOk) {
  const calls = [];
  const context = {
    URLSearchParams,
    window: {addEventListener() {}, location: {origin: 'http://example.invalid'}},
    document: {readyState: 'loading', addEventListener() {}},
    fetch: async (url, opts) => {
      calls.push({url, opts});
      if (url === 'validate-recipe') {
        return {ok: validationOk, status: validationOk ? 200 : 422,
          json: async () => validationOk
            ? {valid: true, schema: 'nomad_material_processing.general.CleaningRecipe'}
            : {detail: 'Invalid original NOMAD recipe'}};
      }
      return {ok: true, json: async () => ({processing: {entry: {errors: []}}})};
    },
  };
  vm.createContext(context);
  vm.runInContext(app, context, {filename: 'app.js'});
  const action = `uploadArchive('upload1', 'test.archive.yaml', {
    m_def:'nomad_material_processing.general.CleaningRecipe', name:'Test'
  }, false)`;
  if (!validationOk) {
    await assert.rejects(vm.runInContext(action, context), /Invalid original NOMAD recipe/);
    assert.strictEqual(calls.length, 1, 'Invalid recipe reached a server upload!');
  } else {
    await vm.runInContext(action, context);
    assert.strictEqual(calls.length, 2);
    assert.strictEqual(calls[0].url, 'validate-recipe');
    assert.strictEqual(calls[0].opts.method, 'POST');
    assert.strictEqual(calls[1].opts.method, 'PUT');
  }
}
(async () => {
  await scenario(false);
  await scenario(true);
  console.log('PASS: invalid original recipe never reaches PUT; valid recipe is preflighted first.');
})().catch(e => {console.error(e); process.exitCode = 1;});
