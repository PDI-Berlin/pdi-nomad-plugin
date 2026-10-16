'use strict';
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const drafts = require(path.join(root, 'src/pdi_nomad_plugin/mbe/new_mbe_experiment/static/mbe_drafts.js'));
const mkRef = (u, e) => `../uploads/${u}/archive/${e}#/data`;
const state = {
  holder: {id:'H5_10', uploadId:'up1', entryId:'holder1'}, growthRunId:'m84325',
  positions: {
    A: {position_usage:'substrate', substrate:{uploadId:'up1',entryId:'sample1'},
        slot_geometry:{m_def:'nomad_material_processing.general.SquareCuboid',width:0.01,length:0.01,height:0.0005}},
    B: {position_usage:'empty', slot_geometry:{m_def:'nomad_material_processing.general.RectangleCuboid',width:0.01,length:0.02,height:0.0005}},
    C: {position_usage:'empty', slot_geometry:{m_def:'nomad_material_processing.general.CylinderSector',radius:0.0254,central_angle:90,height:0.0005}}
  }
};
const result = drafts.build(state,[{composition:'BaSnO3'}],mkRef,(_p,n)=>({x_position:0,y_position:0}));
assert.equal(result.nomad_archive,false);
assert.equal(result.original_sections.filled_holder.positions.length,3);
assert.equal(result.original_sections.filled_holder.positions[0].slot_geometry.m_def,'nomad_material_processing.general.SquareCuboid');
assert.equal(result.original_sections.filled_holder.positions[0].slot_geometry.width,0.01);
assert.equal(result.original_sections.filled_holder.positions[1].slot_geometry.length,0.02);
assert.equal(result.original_sections.filled_holder.positions[2].slot_geometry.central_angle,90);
assert.equal(result.original_sections.mbe.samples.length,1);
assert.equal(result.original_sections.mbe.samples[0].reference,mkRef('up1','sample1'));
assert.equal(result.warnings.length,0);
console.log('MBE original square/rectangular/circular-sector slot geometry: 8 assertions passed');
