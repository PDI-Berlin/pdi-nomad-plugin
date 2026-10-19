"""Stage 9: original substrate metadata and box-label precedence, no schema edits."""

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pdi_nomad_plugin.mbe.substrate_intake.app import app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def client():
    with TestClient(app) as session:
        yield session


def sample(**changes):
    value = {
        'supplier': 'Crystec',
        'supplier_id': 'CTC',
        'material': 'GdScO3',
        'crystal_id': 'GSO',
        'charge': 'P43671',
        'orientation': '1 1 0',
        'width_mm': 10,
        'length_mm': 10,
        'thickness_mm': 0.5,
        'polishing': 'Single-side',
        'count': 2,
    }
    value.update(changes)
    return value


def test_batch_notes_are_only_free_text_and_date_uses_original_quantity(client):
    response = client.post('/api/preview', json=sample(delivery_date='2026-09-01'))
    assert response.status_code == 200, response.text
    batch = response.json()['archives'][0]['data']
    assert 'description' not in batch
    assert batch['delivery_date'] == '2026-09-01T00:00:00+00:00'
    assert batch['polishing'] == 'Single-side'

    response = client.post('/api/preview', json=sample(notes='Scratched box lid'))
    assert response.status_code == 200, response.text
    assert response.json()['archives'][0]['data']['description'] == 'Scratched box lid'

    response = client.post('/api/preview', json=sample(delivery_date='not-a-date'))
    assert response.status_code == 422


def test_original_square_and_rectangle_geometry_are_not_conflated(client):
    square = client.post('/api/preview', json=sample()).json()['archives'][0]['data'][
        'geometry'
    ]
    assert square['m_def'].endswith('SquareCuboid')
    assert square['width'] == pytest.approx(0.01)
    assert square['height'] == pytest.approx(0.0005)
    assert 'length' not in square

    rectangular = client.post('/api/preview', json=sample(length_mm=15)).json()[
        'archives'
    ][0]['data']['geometry']
    assert rectangular['m_def'].endswith('RectangleCuboid')
    assert rectangular['length'] == pytest.approx(0.015)


def test_reference_gui_is_compact_and_phys_properties_stay_in_batch_column(client):
    response = client.get('/')
    assert response.status_code == 200
    html = response.text
    left = html.index('<h2>1. Box label</h2>')
    right = html.index('<h2>2. Batch data</h2>')
    selector = html.index('id="samplePropReference"')
    physical = html.index('id="pdiPhysicalProperties"')
    assert left < selector < right < physical
    assert 'onchange="pdiIntakeApplyReference()"' in html
    assert 'Copy properties</button>' not in html
    assert 'onclick="pdiIntakeLoadReferences()"' in html  # optional reload only
    assert 'id="delivery_date"' in html
    assert 'static/intake_reference.js?v=9' in html
    assert 'static/intake_upload_feedback.js?v=8' in html
    assert 'id="reference_id"' not in html
    assert 'id="sample_id"' not in html


@pytest.mark.skipif(shutil.which('node') is None, reason='Node.js not installed')
def test_reference_autoload_preserves_box_metadata_and_imports_polishing():
    result = subprocess.run(
        ['node', str(ROOT / 'tests/verify_intake_stage9_reference.cjs')],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(
    not __import__('os').environ.get('PDI_INTAKE_LIVE_UPLOAD_ID'),
    reason='Live read-only check requires an explicit development upload ID',
)
def test_original_normalizer_saved_ten_real_child_references_read_only():
    """Opt-in, read-only integration against an actual NOMAD development upload.

    Never runs against production by default; no creation, reprocessing, or edits.
    """
    import os
    from collections.abc import Mapping

    from nomad.files import StagingUploadFiles
    from nomad.infrastructure import setup_mongo
    from nomad.processing import Entry

    uid = os.environ['PDI_INTAKE_LIVE_UPLOAD_ID']
    expected_count = int(os.environ.get('PDI_INTAKE_LIVE_CHILDREN', '10'))
    setup_mongo()
    entries = list(Entry.objects(upload_id=uid))
    batches = [
        entry for entry in entries if '.SubstrateBatch.archive.' in entry.mainfile
    ]
    children = [entry for entry in entries if '.Substrate.archive.' in entry.mainfile]
    assert len(batches) == 1
    assert len(children) == expected_count
    assert len(entries) == expected_count + 1

    with StagingUploadFiles(uid).read_archive(batches[0].entry_id) as reader:
        record = reader[batches[0].entry_id]
        if hasattr(record, 'to_dict'):
            archive = record.to_dict()
        elif isinstance(record, Mapping):
            archive = dict(record)
        else:
            archive = record.m_to_dict()
        data = archive['data']
        assert data['number_of_substrates'] == expected_count
        assert data['trigger_create_substrate'] is False
        refs = data['substrates']
        assert len(refs) == expected_count
        lookup = {child.entry_id: child for child in children}
        actual = set()
        for ref in refs:
            destination = ref['reference']
            assert destination.startswith(f'../uploads/{uid}/archive/')
            assert destination.endswith('#data')
            entry_id = destination.split('/archive/', 1)[1].removesuffix('#data')
            assert entry_id in lookup
            assert entry_id not in actual
            assert lookup[entry_id].mainfile.startswith(ref['name'] + '.')
            actual.add(entry_id)
        assert actual == set(lookup)
