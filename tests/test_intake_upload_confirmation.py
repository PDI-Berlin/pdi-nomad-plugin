"""Stage 7: browser feedback must reflect indexed NOMAD entries, not PUT alone."""

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pdi_nomad_plugin.mbe.substrate_intake.app import app

ROOT = Path(__file__).resolve().parents[1]
HELPER = (
    ROOT / 'src/pdi_nomad_plugin/mbe/substrate_intake/static/intake_upload_feedback.js'
)


def test_feedback_asset_is_served_and_post_ack_is_not_false_success():
    with TestClient(app) as client:
        response = client.get('/')
        asset = client.get('/static/intake_upload_feedback.js')
    assert response.status_code == 200
    assert asset.status_code == 200
    assert 'static/intake_upload_feedback.js?v=8' in response.text
    assert 'pdiIntakeUploadFeedback.waitForEntries' in response.text
    assert 'pdiIntakeUploadFeedback.showSuccessAndOpenUpload' in response.text
    assert 'batchWriteAttempted = true' in response.text
    assert 'saveButton.disabled = batchWriteAttempted' in response.text
    assert 'Upload successful' in asset.text
    assert '/entries?' in asset.text
    assert 'do NOT upload it again' in asset.text
    assert 'window.location.reload()' in asset.text
    assert 'sessionStorage.setItem' in asset.text
    assert 'window.top.location.assign' not in asset.text
    assert '/gui/user/uploads/upload/id/' not in response.text


@pytest.mark.skipif(shutil.which('node') is None, reason='Node.js not installed')
def test_browser_success_and_failure_behavior():
    script = r'''
const fs = require('fs');
const vm = require('vm');
const assert = require('assert').strict;
const source = fs.readFileSync(process.argv[1], 'utf8');
const upload = 'test_upload';
const batch = 'CTC_GSO_TEST.SubstrateBatch.archive.json';
const child = 'CTC_GSO_TEST_1.Substrate.archive.yaml';
const store = new Map();
const storage = {
    getItem: k => store.get(k) || null,
    setItem: (k,v) => store.set(k,v),
    removeItem: k => store.delete(k)
};
function response(body) {return {ok:true, json:async()=>body};}
function setup(fetchImpl, denyStorage=false) {
    const state={reloads:0, redirects:0, banners:[],
        status:{textContent:'', className:'', setAttribute(){}}};
    const win={
        fetch:fetchImpl,
        setTimeout: f=>f(),
        location:{pathname:'/nomad-oasis/dashboards/substrate-intake/',
            reload:()=>state.reloads++, assign:()=>state.redirects++},
        top:{location:{assign:()=>state.redirects++}},
        sessionStorage:denyStorage ?
        {getItem:()=>null,setItem:()=>{throw Error('blocked');},removeItem:()=>{}}
        : storage,
        refreshIntakeUploads:()=>Promise.resolve()
    };
    const doc={
        readyState:'complete',
        getElementById:id=>id==='saveStatus'?state.status:
            id==='pdiIntakeSuccessBanner'?state.banners[0]||null:null,
        createElement:()=>({style:{},setAttribute(){},textContent:''}),
        body:{firstChild:null,insertBefore:el=>state.banners.push(el)}
    };
    vm.runInNewContext(source,{window:win,document:doc,URLSearchParams,Promise,Array,Set,String,Date,Number});
    return {helper:win.pdiIntakeUploadFeedback, state};
}
(async function() {
    const ok=setup(async url=>url.includes('/entries?')
        ?response({data:[{mainfile:batch,process_running:false},
                         {mainfile:child,process_running:false}]})
        :response({data:{upload_id:upload,process_running:false,process_status:'READY'}}));
    const answer=await ok.helper.waitForEntries({apiBase:'/nomad-oasis/api/v1',
        uploadId:upload,filenames:[batch,child],attempts:2,sleep:async()=>{},
        statusElement:ok.state.status});
    assert.equal(answer.count,2);
    ok.helper.showSuccessAndOpenUpload({children:1,batchFile:batch,uploadId:upload});
    assert.equal(ok.state.reloads,1);
    assert.equal(ok.state.redirects,0);
    assert.match(ok.state.status.textContent,/Upload successful/);
    assert.equal(store.size,1);
    const afterReload=setup(async()=>response({}));
    assert.match(afterReload.state.status.textContent,
        /1 SubstrateBatchMbe \+ 1 SubstrateMbe/);
    assert.match(afterReload.state.banners[0].textContent,/test_upload/);
    assert.equal(store.size,0);
    assert.equal(afterReload.state.redirects,0);
    const blocked=setup(async()=>response({}),true);
    blocked.helper.showSuccessAndOpenUpload({children:1,batchFile:batch,uploadId:upload});
    assert.equal(blocked.state.reloads,0);
    assert.match(blocked.state.status.textContent,/Upload successful/);
    const incomplete=setup(async url=>url.includes('/entries?')
        ?response({data:[{mainfile:batch}]})
        :response({data:{upload_id:upload,process_running:false,process_status:'READY'}}));
    await assert.rejects(incomplete.helper.waitForEntries({
        apiBase:'/api/v1',uploadId:upload,filenames:[batch,child],
        attempts:2,sleep:async()=>{}
    }),/do NOT upload it again/);
    assert.equal(incomplete.state.reloads,0);
    const failure=setup(async()=>response({data:{
        upload_id:upload,process_running:false,process_status:'FAILURE',errors:['oops']
    }}));
    await assert.rejects(failure.helper.waitForEntries({
        apiBase:'/api/v1',uploadId:upload,filenames:[batch,child],
        attempts:1,sleep:async()=>{}
    }),/processing errors/);
    assert.equal(failure.state.reloads,0);
})().catch(error=>{console.error(error);process.exit(1);});
'''
    result = subprocess.run(
        ['node', '-e', script, str(HELPER)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + '\n' + result.stderr
