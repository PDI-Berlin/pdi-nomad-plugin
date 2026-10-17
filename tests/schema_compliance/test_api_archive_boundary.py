"""Verify real Substrate Intake API archive payloads against upstream m_def only."""

from fastapi.testclient import TestClient

from .original_contract import assert_original_archive_data


def test_substrate_intake_preview_emits_only_original_schema_fields():
    from pdi_nomad_plugin.mbe.substrate_intake.app import app

    form = {
        'supplier': 'Test Supplier',
        'supplier_id': 'TEST',
        'material': 'SrTiO3',
        'crystal_id': '001',
        'charge': 'A',
        'orientation': '0 0 1',
        'offcut_angle': 0.5,
        'offcut_direction': '1 1 0',
        'width_mm': 10,
        'length_mm': 10,
        'thickness_mm': 0.5,
        'count': 3,
    }
    with TestClient(app) as client:
        response = client.post('/api/preview', json=form)
    assert response.status_code == 200, response.text
    result = response.json()
    assert 'data' not in result, 'A custom batch archive is forbidden'
    assert len(result['archives']) == 3
    assert len({entry['filename'] for entry in result['archives']}) == 3
    for entry in result['archives']:
        data = entry['data']
        assert data['m_def'] == 'nomad_material_processing.general.CrystallineSubstrate'
        assert_original_archive_data(data, data['m_def'])
