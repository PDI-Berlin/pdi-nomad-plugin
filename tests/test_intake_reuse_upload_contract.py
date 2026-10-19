"""Stage 10: reuse a nonempty upload without overwriting any batch/children."""

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pdi_nomad_plugin.mbe.substrate_intake.app import app

ROOT = Path(__file__).resolve().parents[1]


def test_guarded_reuse_requires_duplicate_and_child_collision_checks():
    with TestClient(app) as client:
        response = client.get('/')
        guard = client.get('/static/intake_duplicate_guard.js')
        feedback = client.get('/static/intake_upload_feedback.js')
    assert response.status_code == guard.status_code == feedback.status_code == 200
    html = response.text
    assert 'static/intake_duplicate_guard.js?v=10' in html
    assert 'pdiIntakeDuplicateGuard.assertNoCollision' in html
    assert html.index('pdiIntakeDuplicateGuard.assertNoCollision') < html.index(
        "params.append('file_name'"
    )
    assert "params.append('overwrite_if_exists', 'false')" in html
    assert 'Select a new EMPTY unpublished upload' not in html
    assert "base + '/entries'" in guard.text
    assert "base + '/rawdir/'" in guard.text
    assert 'entry.entry_name' in guard.text
    assert 'expectedChildren' in guard.text
    assert 'too many entries' in guard.text.lower()
    assert 'const pages = Math.ceil(filenames.length / 100)' not in feedback.text


@pytest.mark.skipif(shutil.which('node') is None, reason='Node.js unavailable')
def test_duplicate_detection_against_paginated_nomad_api():
    script = ROOT / 'tests/verify_intake_stage10_guard.cjs'
    proc = subprocess.run(
        ['node', str(script)], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stdout + '\n' + proc.stderr
