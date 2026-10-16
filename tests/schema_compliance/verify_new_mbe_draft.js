const assert = require('node:assert/strict');
const drafts = require(process.argv[2]);
const state = {
  growthRunId: 'm84325',
  holder: {id: 'H5_10', entryId: 'holder123', uploadId: 'up1'},
  positions: {
    A: {position_usage: 'substrate', rho: 0, theta: 0,
      substrate: {entryId: 'sample1', uploadId: 'up2'},
      insertReduction: {entryId: 'insert1', uploadId: 'up3'},
      slot_geometry: {m_def: 'nomad_material_processing.general.SquareCuboid', width: .01, length: .01}},
    B: {position_usage: 'si_dummy', rho: .01, theta: 0,
      slot_geometry: {m_def: 'nomad_material_processing.general.CylinderSector', radius: .0254, central_angle: 90}}
  }
};
const ref = (upload, entry) => `../uploads/${upload}/archive/${entry}#data`;
const xy = (p) => ({x_position: p.rho*Math.cos(p.theta*Math.PI/180),
                    y_position: p.rho*Math.sin(p.theta*Math.PI/180)});
const result = drafts.build(state, [{chemical_formula:'BaSnO3',nominal_thickness:1e-8}], ref, xy);
assert.equal(result.nomad_archive, false);
assert.equal(result.original_sections.mbe.lab_id, 'm84325');
assert.equal(result.original_sections.mbe.samples.length, 1);
assert.equal(result.original_sections.mbe.samples[0].reference,
             '../uploads/up2/archive/sample1#data');
assert.equal(result.original_sections.filled_holder.substrate_holder,
             '../uploads/up1/archive/holder123#data');
const pos = result.original_sections.filled_holder.positions;
assert.equal(pos[0].substrate.reference, '../uploads/up2/archive/sample1#data');
assert.equal(pos[0].insert_reduction.reference, '../uploads/up3/archive/insert1#data');
assert.equal(pos[0].slot_geometry, undefined); // SquareCuboid not a Geometry subtype
assert.equal(pos[1].slot_geometry.central_angle, 90);
assert.equal(pos[1].substrate, undefined); // no fake dummy reference
assert.ok(result.warnings.some(x => x.includes('dummy')));
assert.ok(result.warnings.some(x => x.includes('geometry')));
assert.equal(result.local_planning_only.nominal_layers[0].nominal_thickness, 1e-8);
assert.equal(result.original_sections.mbe.nominal_layers, undefined);
assert.throws(() => drafts.build({...state,holder:null}, [1], ref, xy), /holder/);
console.log('PASS: original section draft references, positions, local-only layers, and fail-closed validation');
