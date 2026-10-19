
const fs = require('fs');
const vm = require('vm');
const assert = require('assert').strict;
const source = fs.readFileSync(require('path').join(__dirname, '../src/pdi_nomad_plugin/mbe/substrate_intake/static/intake_reference.js'), 'utf8');
const fieldNames = [
 'supplier','supplier_id','material','other_material','crystal_id','charge',
 'polishing','delivery_date','h_index','k_index','l_index','offcut_angle',
 'u_index','v_index','w_index','geometry_shape','width_mm','length_mm',
 'radius_mm','sector_angle_deg','thickness_mm','count','notes','phys_bravais',
 'phys_conductivity','phys_carrier_density','phys_carrier_deviation',
 'phys_resistivity','pdiDopantRows','samplePropReference','samplePropStatus'
];
class Element {
 constructor(id) {
  this.id=id; this.value=''; this.dataset={}; this.style={};
  this.children=[]; this.listeners={}; this.options=[];
  this.tagName=['samplePropReference','polishing','material','geometry_shape',
   'phys_bravais','phys_conductivity'].includes(id) ? 'SELECT' : 'INPUT';
 }
 addEventListener(type, cb) {(this.listeners[type] ||= []).push(cb);}
 dispatch(type){for(const cb of this.listeners[type]||[]) cb();}
 set innerHTML(value) {this._html=value;this.options=[];this.value='';}
 get innerHTML(){return this._html||'';}
 appendChild(child) {this.children.push(child);if(child.tagName==='OPTION')this.options.push(child);}
 replaceChildren() {this.children=[];}
 querySelectorAll(){return []}
}
const elements = Object.fromEntries(fieldNames.map(id=>[id,new Element(id)]));
const refSelect=elements.samplePropReference;
elements.geometry_shape.value='rectangle';
elements.radius_mm.value='25.4';
elements.sector_angle_deg.value='90';
elements.count.value='10';
elements.material.options=[{value:'GdScO3'},{value:'SrTiO3'},{value:'other'}];
elements.polishing.options=[{value:''},{value:'Single-side'},{value:'Double-side'}];
const listeners={};
const document={
 readyState:'loading',
 getElementById:id=>elements[id]||null,
 addEventListener:(type,cb)=>(listeners[type] ||= []).push(cb),
 createElement:tag=>Object.assign(new Element('dynamic'),{tagName:tag.toUpperCase()})
};
const referenceA={
 lab_id:'GSO_reference_1',polishing:'Single-side',
 components:[{pure_substance:{molecular_formula:'GdScO3'}}],
 crystal_properties:{surface_orientation:{hkl_reciprocal:{h_index:1,k_index:1,l_index:0}}},
 geometry:{m_def:'nomad_material_processing.general.SquareCuboid',width:0.01,height:0.0005},
 electronic_properties:{conductivity_type:'Insulating'}
};
const referenceB={
 lab_id:'STO_reference_1',polishing:'Single-side',
 components:[{pure_substance:{molecular_formula:'SrTiO3'}}],
 crystal_properties:{surface_orientation:{hkl_reciprocal:{h_index:0,k_index:0,l_index:1}}},
 geometry:{m_def:'nomad_material_processing.general.SquareCuboid',width:0.015,height:0.0006}
};
const fetchCalls=[];
const fetch=async(url,opts)=>{
 fetchCalls.push(url);
 return {ok:true, json:async()=> url.includes('property-options')
   ? {bravais_lattices:[],conductivity_type:['Insulating']}
   : {data:[{data:referenceA},{data:referenceB}],pagination:{}}};
};
const context={document,fetch,window:{},console,Number,String,Array,Promise,Math,Object,Date};
context.window.document=document;
context.nomadApiBase=()=>'/nomad-oasis/api/v1';
context.updateMaterialFields=()=>{};
context.updateGeometryFields=()=>{};
context.updatePreview=()=>{};
vm.runInNewContext(source,context);
assert.equal(fetchCalls.length,0);
// NOMAD API is loaded automatically; no Refresh button press.
(async()=>{
 for(const cb of listeners.DOMContentLoaded||[]) cb();
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(fetchCalls.length,2);
 assert.equal(refSelect.options.length,2);
 // The box label/user first enters a different physical width.
 elements.width_mm.value='12';elements.width_mm.dispatch('input');
 elements.charge.value='OUR_CHARGE';elements.charge.dispatch('input');
 refSelect.value='0';context.window.pdiIntakeApplyReference();
 assert.equal(elements.polishing.value,'Single-side');
 assert.equal(elements.width_mm.value,'12');
 assert.equal(elements.length_mm.value,'10');
 assert.equal(elements.material.value,'GdScO3');
 assert.equal(elements.charge.value,'OUR_CHARGE');
 assert.equal(elements.h_index.value,'1');
 assert.equal(elements.thickness_mm.value,'0.5');
 // After the reference, OCR/box-label information dominates immediately.
 context.window.pdiIntakeApplyBoxLabelData({
  polishing:'Double-side', width_mm:15, material:'SrTiO3',
  charge:'BOX_CHARGE', orientation:'0 0 1'
 });
 assert.equal(elements.polishing.value,'Double-side');
 assert.equal(elements.width_mm.value,'15');
 assert.equal(elements.material.value,'SrTiO3');
 assert.equal(elements.charge.value,'BOX_CHARGE');
 // Selecting a different reference replaces old reference-derived fields
 // but must NOT undo any of the explicitly entered box data.
 refSelect.value='1';context.window.pdiIntakeApplyReference();
 assert.equal(elements.polishing.value,'Double-side');
 assert.equal(elements.width_mm.value,'15');
 assert.equal(elements.material.value,'SrTiO3');
 assert.equal(elements.h_index.value,'0');
 assert.equal(elements.k_index.value,'0');
 assert.equal(elements.l_index.value,'1');
 assert.equal(elements.thickness_mm.value,'0.6');
 // New reference never changes the source archive object.
 assert.equal(referenceA.polishing,'Single-side');
 assert.equal(referenceA.geometry.width,0.01);
 console.log('PASS: automatic lookup, one-select apply, polishing, box precedence, reference immutable');
})().catch(e=>{console.error(e);process.exit(1)});
