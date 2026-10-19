'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root=path.resolve(__dirname,'..');
const source=fs.readFileSync(path.join(root,'src/pdi_nomad_plugin/mbe/substrate_intake/static/intake_duplicate_guard.js'),'utf8');
const win={};
vm.runInNewContext(source,{window:win,URLSearchParams,Set,String,Number,Error,Promise,Array});
const helper=win.pdiIntakeDuplicateGuard;
const id='CTC_GSO_0223-2345-1241';
const children=Array.from({length:10},(_,i)=>({lab_id:id+'_'+(i+1),filename:id+'_'+(i+1)+'.Substrate.archive.yaml'}));
const batchFile=id+'.SubstrateBatch.archive.json';
const other='CTC_STO_OTHER';
const mock=(entries,files,opts={})=>async function(url){
    if(opts.fail) return {ok:false,status:503};
    let list=url.includes('/rawdir/')?files:entries;
    const pg=Number(new URL(url,'http://localhost').searchParams.get('page'));
    if(opts.badPage && pg===2) return {ok:true,json:async()=>({data:[],pagination:{total:101}})};
    const page=list.slice((pg-1)*100,pg*100);
    return {ok:true,json:async()=>url.includes('/rawdir/')
        ?{directory_metadata:{content:page},pagination:{total:list.length}}
        :{data:page,pagination:{total:list.length}}};
};
const check=(entries,files,extra={})=>helper.assertNoCollision({uploadId:'test-upload',apiBase:'/nomad-oasis/api/v1',batchLabId:id,batchFilename:batchFile,expectedChildren:children,fetchImpl:mock(entries,files,extra)});
(async()=>{
    const existing=[{mainfile:other+'.SubstrateBatch.archive.json',entry_name:other},
        {mainfile:other+'_1.Substrate.archive.yaml',entry_name:other+'_1'}];
    let answer=await check(existing,[{name:other+'.SubstrateBatch.archive.json'},{name:other+'_1.Substrate.archive.yaml'}]);
    assert.equal(answer.checkedEntries,2);
    assert.equal(answer.checkedFiles,2);
    await assert.rejects(check([...existing,{mainfile:batchFile,entry_name:id}],[]),/Batch .* already exists/);
    await assert.rejects(check([...existing,{mainfile:'unknown.json',entry_name:id}],[]),/already exists/);
    await assert.rejects(check([...existing,{mainfile:children[3].filename,entry_name:children[3].lab_id}],[]),/already exists/);
    await assert.rejects(check(existing,[{name:batchFile}]),/already exists/);
    await assert.rejects(check(existing,[{name:id+'_5.Substrate.archive.json'}]),/already exists/);
    const manyEntries=Array.from({length:107},(_,i)=>({mainfile:'other_'+i+'.archive.json',entry_name:'other_'+i}));
    manyEntries.push({entry_name:id,mainfile:'some-other-name.archive.json'});
    await assert.rejects(check(manyEntries,[]),/already exists/);
    const manyFiles=Array.from({length:120},(_,i)=>({name:'untargeted_'+i+'.archive.json'}));
    manyFiles.push({name:id+'_10.Substrate.archive.yaml'});
    await assert.rejects(check([],manyFiles),/already exists/);
    await assert.rejects(check(existing,[],{fail:true}),/No files were sent/);
    await assert.rejects(check(Array.from({length:101},(_,i)=>({mainfile:'junk'+i})),[],{badPage:true}),/Incomplete NOMAD listing/);
    assert.equal((await check(Array.from({length:201},(_,i)=>({entry_name:'other'+i,mainfile:'other'+i})),[])).checkedEntries,201);
    // Readback must find newly created children even when a reused upload
    // already has 100+ entries, not just on page 1.
    const feedbackSource=fs.readFileSync(path.join(root,
        'src/pdi_nomad_plugin/mbe/substrate_intake/static/intake_upload_feedback.js'),'utf8');
    const fbWin={setTimeout:()=>{}, location:{pathname:'/checkin'},sessionStorage:{getItem:()=>null}};
    const fbDoc={readyState:'loading',addEventListener:()=>{}};
    vm.runInNewContext(feedbackSource,{window:fbWin,document:fbDoc,URLSearchParams,Set,Map,String,Date,Array,Number,Error,Promise});
    const allEntries=Array.from({length:116},(_,i)=>({mainfile:'prior_'+i+'.Substrate.archive.yaml',process_running:false}));
    allEntries.push({mainfile:batchFile,process_running:false});
    allEntries.push({mainfile:children[0].filename,process_running:false});
    const fbFetch=async url=>url.includes('/entries?')
        ?{ok:true,json:async()=>{
            const pg=Number(new URL(url,'http://localhost').searchParams.get('page'));
            return {data:allEntries.slice((pg-1)*100,pg*100),pagination:{total:allEntries.length}};
        }}
        :{ok:true,json:async()=>({data:{upload_id:'test-upload',process_running:false,process_status:'READY'}})};
    const result=await fbWin.pdiIntakeUploadFeedback.waitForEntries({
        apiBase:'/api/v1',uploadId:'test-upload',filenames:[batchFile,children[0].filename],
        attempts:1,fetchImpl:fbFetch,sleep:async()=>{}
    });
    assert.equal(result.count,2);
    console.log('PASS: Reusing nonempty upload; batch ID, child IDs, unindexed files, pagination, fail-closed errors.');
})().catch(err=>{console.error(err);process.exitCode=1;});
