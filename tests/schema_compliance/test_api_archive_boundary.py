"""Intake: existing PDI EntryData root, all child sections use original schemas."""

from fastapi.testclient import TestClient
from nomad_material_processing.general import CrystallineSubstrate

from pdi_nomad_plugin.mbe.materials import SubstrateBatchMbe

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
    assert 'data' not in result, 'No unwrapped archive.data in response'
    assert len(result['archives']) == 1
    assert len(result['expected_children']) == 3
    for entry in result['archives']:
        data = entry['data']
        assert data['m_def'] == SubstrateBatchMbe.m_def.qualified_name()
        assert SubstrateBatchMbe.m_from_dict(data).lab_id == data['lab_id']
        allowed = set(CrystallineSubstrate.m_def.all_quantities) | set(
            CrystallineSubstrate.m_def.all_sub_sections
        )
        inherited = {k: v for k, v in data.items() if k in allowed}
        inherited['m_def'] = CrystallineSubstrate.m_def.qualified_name()
        assert_original_archive_data(inherited, inherited['m_def'])
