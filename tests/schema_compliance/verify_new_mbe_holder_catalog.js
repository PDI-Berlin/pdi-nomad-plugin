const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let source = fs.readFileSync(process.argv[2], 'utf8');
source = source.replace(/initialiseWorkflowV2\(\)\.then\(function\(\) \{[\s\S]*$/, '');
const ctx = vm.createContext({
  window: {location:{pathname:'/nomad-oasis/dashboards/new-mbe-experiment/'},
           parent:null, addEventListener(){}},
  document: {}, console, URLSearchParams,
});
vm.runInContext(source, ctx);
const physical = {
  entry_id: 'holder123', upload_id: 'up1',
  data: {m_def: 'nomad_material_processing.vapor_deposition.general.SubstrateHolder',
         lab_id:'H5_10', positions:[{name:'A',rho:0,theta:0}]}
};
const snapshot = {
  entry_id: 'filled123', upload_id: 'up2',
  data: {m_def: 'nomad_material_processing.vapor_deposition.general.FilledSubstrateHolder',
         datetime:'2026-10-16T10:00:00Z',
         substrate_holder:'../uploads/up1/archive/holder123#data',
         positions:[{name:'A',substrate:{reference:'../uploads/up3/archive/sub1#data'}}]}
};
ctx.queryEntriesBySchema = async (name) => name.endsWith('.FilledSubstrateHolder') ? [snapshot] : [physical];
vm.runInContext('queryEntriesBySchema = globalThis.queryEntriesBySchema', ctx);
(async () => {
  const catalog = await vm.runInContext('loadHolderCatalogV2()', ctx);
  assert.equal(catalog.holders.length, 1);
  assert.equal(catalog.currentByPhysical.get('holder123').entry_id, 'filled123');
  assert.equal(vm.runInContext('holderWorkflowStatus({})', ctx), 'not recorded');
  assert.match(vm.runInContext('holderDisplayStatus("not recorded", true)', ctx), /occupancy unverified/);
  assert.equal(vm.runInContext('entryIdFromReference("../uploads/up1/archive/holder123#data")', ctx), 'holder123');
  console.log('PASS: original holder and recorded filled snapshot linked by NOMAD reference, no invented lifecycle');
})().catch(err => {console.error(err);process.exitCode=1;});
