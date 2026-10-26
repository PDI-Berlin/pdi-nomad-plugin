const assert = require('node:assert/strict');
const writer = require('../src/pdi_nomad_plugin/mbe/new_mbe_experiment/static/mbe_nomad_write.js');
const EXP='pdi_nomad_plugin.mbe.processes.ExperimentMbePDI';
const FILLED='pdi_nomad_plugin.mbe.instrument.FilledSubstrateHolderPDI';
const FILM='pdi_nomad_plugin.mbe.materials.ThinFilmMbe';
const STACK='pdi_nomad_plugin.mbe.materials.ThinFilmStackMbePDI';
const archives = new Map();
const requests = [];
const mkId=(up,file)=>`id-${file}`;
const fakeRef=(id)=>writer.ref('upload1',id);
function response(status, data){return {ok:status>=200&&status<300,status,async json(){return data;},async text(){return JSON.stringify(data)}};}
async function fetch(url, options={}) {
  requests.push({url,options});
  const path = url.replace('http://nomad/api/v1','');
  const match = /^\/entries\/([^/]+)\/archive$/.exec(path);
  if(match){const data=archives.get(decodeURIComponent(match[1]));return data?response(200,{data:{archive:{data}}}):response(404,{detail:'no entry'});}
  if(options.method==='PUT'){
    assert(path.startsWith('/uploads/upload1/raw/?overwrite_if_exists=false&wait_for_processing=true'));
    const file=options.body.get('file');
    const data=JSON.parse(await file.text()).data;
    const id=mkId('upload1',file.name);
    assert(!archives.has(id),'overwrite prohibited');archives.set(id,data);
    if (data.m_def === EXP) {
      data.samples=[{reference:fakeRef('stackA')}];
      archives.set('stackA',{m_def:STACK,lab_id:'m84380_A',layers:[
        {name:'earlier',reference:fakeRef('oldFilm')},
        {name:'m84380_A_lyr_1',reference:fakeRef('firstLayer')}
      ]});
      archives.set('firstLayer',{m_def:FILM,lab_id:'m84380_A_lyr_1'});
    }
    return response(200,{success:true});
  }
  if(path==='/entries/stackA/edit' && options.method==='POST') {
    const body=JSON.parse(options.body);
    const layers=archives.get('stackA').layers;
    for(const change of body.changes){assert.match(change.path,/^data\/layers\/\d+$/);const i=Number(change.path.split('/')[2]);assert.equal(i,layers.length);layers.push(change.new_value);}
    return response(200,{entry_id:'stackA'});
  }
  throw new Error('Unexpected request '+(options.method||'GET')+' '+url);
}
(async () => {
 const api=writer.createClient({apiBase:'http://nomad/api/v1',fetch,entryIdForFile:mkId,wait:async()=>{}});
 const filled=await api.createFilled('upload1','filled.archive.json',{m_def:FILLED,name:'loadout',positions:[{name:'A',substrate:{reference:fakeRef('substrate')}}]});
 assert.equal(archives.get(filled.entryId).m_def,FILLED);
 const exp=await api.createExperiment('upload1','m84380_mbe_exp.archive.json',{m_def:EXP,lab_id:'m84380',name:'m84380'},filled.reference);
 assert.equal(archives.get(exp.entryId).substrate_holder.reference,filled.reference);
 const plans=[{stack_id:'m84380_A',mandatory_layer_1:'m84380_A_lyr_1',extra_layer_archives:[2,3].map(n=>({filename:`m84380_A_lyr_${n}.archive.yaml`,thin_film:{m_def:FILM,name:`m84380_A_lyr_${n}`,lab_id:`m84380_A_lyr_${n}`}}))}];
 const results=await api.addExtraLayers('upload1',exp.entryId,plans);
 assert.deepEqual(results,[{stack:'m84380_A',extraLayers:2}]);
 assert.deepEqual(archives.get('stackA').layers.map(l=>l.name),['earlier','m84380_A_lyr_1','m84380_A_lyr_2','m84380_A_lyr_3']);
 const writes=requests.filter(x=>x.options.method==='PUT').length;
 const edits=requests.filter(x=>x.options.method==='POST').length;
 await api.addExtraLayers('upload1',exp.entryId,plans);
 assert.equal(requests.filter(x=>x.options.method==='PUT').length,writes);
 assert.equal(requests.filter(x=>x.options.method==='POST').length,edits);
 await assert.rejects(()=>api.createFilled('upload1','filled.archive.json',{m_def:FILLED,positions:[{substrate:{reference:'test'}}]}),/already exists/);
 await assert.rejects(()=>api.createExperiment('upload1','wrong.archive.json',{m_def:EXP,lab_id:'m84380',samples:[]},filled.reference),/Invalid experiment/);
 await assert.rejects(()=>api.editStack('stackA',[{name:'m84380_A_lyr_1',reference:fakeRef('otherFilm'),uploadId:'upload1',entryId:'otherFilm'}]),/name already exists/);
 assert.equal(writer.refIdentity(writer.ref('upload1','id_xyz')).entryId,'id_xyz');
 console.log('PASS: original PDI write flow, immutable Layer 1, optional Layer 2/3, prior layer kept, retry idempotence and conflicts');
})().catch(error=>{console.error(error);process.exitCode=1;});
