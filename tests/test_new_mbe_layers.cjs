// Regression tests for original PDI multi-layer MBE workflow (Node.js)
const assert = require('node:assert/strict');
const p = require('../src/pdi_nomad_plugin/mbe/new_mbe_experiment/static/mbe_drafts.js');
const slot = {m_def: 'nomad_material_processing.general.SquareCuboid',width:0.01,height:0.001};
const positions = {};
const dims = [['A',0,0],['B',1,0],['C',1,90],['D',1,180],['E',1,270]];
for(const [name,rho,theta] of dims) positions[name] = {rho,theta,slotGeometry:slot,position_usage:'substrate',substrate:{entryId:`id-${name}`,uploadId:'up1'}};
const state={growthRunId:'m84380',holder:{entryId:'holder',uploadId:'up1',id:'H3_10'},positions};
const layers=[{number:1,composition:'BaSnO3',thicknessNm:20},{number:2,composition:'LaInO3',thicknessNm:10},{number:3,composition:'BaSnO3',thicknessNm:5}];
const mkRef=(up,id)=>`../uploads/${up}/archive/${id}#data`;
const coords=pos=>({rho:pos.rho,theta:pos.theta});
const d=p.build(state,layers,mkRef,coords);
assert.equal(d.nomad_archive,false);
assert.equal(d.original_sections.filled_holder.m_def,'pdi_nomad_plugin.mbe.instrument.FilledSubstrateHolderPDI');
assert.equal(d.original_sections.mbe.m_def,'pdi_nomad_plugin.mbe.processes.ExperimentMbePDI');
assert.equal(d.original_sections.mbe.samples,undefined,'samples must NOT block normalizer');
assert.deepEqual(d.original_sections.filled_holder.positions.map(x=>[x.name,x.rho,x.theta]),dims);
assert.deepEqual(d.post_normalization_plan.map(x=>[x.holder_position,x.mandatory_layer_1]),dims.map(x=>[x[0],`m84380_${x[0]}_lyr_1`]));
for(const plan of d.post_normalization_plan){assert.equal(plan.extra_layer_archives.length,2); assert.deepEqual(plan.extra_layer_archives.map(x=>x.thin_film.lab_id),[2,3].map(n=>`m84380_${plan.holder_position}_lyr_${n}`));}
assert.throws(()=>p.build(state,[],mkRef,coords),/at least one/);
assert.equal(p.build(state,[layers[0]],mkRef,coords).post_normalization_plan[0].extra_layer_archives.length,0);
console.log('PASS: 5 holder positions, mandatory Layer 1, optional 2/3, refs, no duplicate auto-layer, original rho/theta');

const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor(tag='div'){this.tag=tag;this.children=[];this.listeners={};this.style={};this.value='';this.textContent='';this.className='';this.dataset={};}
  appendChild(x){this.children.push(x);return x;}
  replaceChildren(...xs){this.children=[...xs];}
  addEventListener(type,fn){this.listeners[type]=fn;}
  getElementById(){return null;}
}
const elems={};
const document={getElementById(k){return elems[k] ||= new Element()},createElement(tag){return new Element(tag)}};
const js=fs.readFileSync(require('node:path').join(__dirname,'../src/pdi_nomad_plugin/mbe/new_mbe_experiment/static/app.js'),'utf8').replace(/initialiseWorkflowV2\(\)\.then\(function\(\) \{[\s\S]*?\}\);\s*$/,'');
const context={document,window:{addEventListener(){}},console,URL,Blob,Math,Number,String,JSON,Set,Map,Date,Promise};vm.createContext(context);
vm.runInContext(js,context);
vm.runInContext('renderNominalLayers()',context);
assert.equal(document.getElementById('layerStackList').children.length,1);
assert.equal(document.getElementById('layerStackList').children[0].children[0].children.length,1);
vm.runInContext('addNominalLayer();addNominalLayer();',context);
assert.equal(document.getElementById('layerStackList').children.length,3);
let composition2=document.getElementById('layerStackList').children[1].children[1].children[0];
composition2.value='LaInO3';composition2.listeners.input();
let comp3=document.getElementById('layerStackList').children[2].children[1].children[0];
comp3.value='BaSnO3';comp3.listeners.input();
assert.equal(vm.runInContext('validateNominalLayers().length',context),3);
assert.equal(vm.runInContext('validateNominalLayers()[0].creation',context),'original-ExperimentMbePDI-normalizer');
assert.equal(vm.runInContext('validateNominalLayers()[1].composition',context),'LaInO3');
assert.equal(vm.runInContext('validateNominalLayers()[2].creation',context),'post-normalization');
let rem = document.getElementById('layerStackList').children[1].children[0].children[1];rem.listeners.click();
assert.equal(vm.runInContext('validateNominalLayers().length',context),2);
assert.equal(vm.runInContext('validateNominalLayers()[1].composition',context),'BaSnO3');
assert.deepEqual(Array.from(vm.runInContext('xyForFilledHolderPosition({rho:1,theta:90},"C") && Object.keys(xyForFilledHolderPosition({rho:1,theta:90},"C"))',context)),['rho','theta']);
assert.equal(vm.runInContext('xyForFilledHolderPosition({rho:1,theta:90},"C").theta',context),90);
assert.equal(vm.runInContext('typeof addNominalLayer',context),'function');
console.log('PASS GUI: layer 1 mandatory, add/remove extras, correct numbering, original polar coords');
