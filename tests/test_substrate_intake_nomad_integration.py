"""Intake uses original physical schemas and the existing PDI batch normalizer."""

import inspect

import pytest
from fastapi.testclient import TestClient
from nomad.datamodel.data import EntryData
from nomad_material_processing.general import (
    CrystallineSubstrate,
    Cylinder,
    CylinderSector,
    RectangleCuboid,
    SquareCuboid,
)

from pdi_nomad_plugin.mbe.materials import SubstrateBatchMbe, SubstrateMbe
from pdi_nomad_plugin.mbe.substrate_intake.app import app, preview_substrate_batch

BASE = {
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


@pytest.fixture(scope='module')
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize(
    'cls,changes',
    [
        (SquareCuboid, {}),
        (RectangleCuboid, {'length_mm': 5}),
        (Cylinder, {'geometry_shape': 'circle', 'radius_mm': 25.4}),
        (
            CylinderSector,
            {'geometry_shape': 'circular_sector', 'radius_mm': 25.4,
             'sector_angle_deg': 90},
        ),
    ],
)
def test_original_geometry_and_batch_roundtrip(client, cls, changes):
    response = client.post('/api/preview', json={**BASE, **changes})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['expected_substrate_count'] == 3
    assert len(payload['archives']) == 1
    item = payload['archives'][0]
    assert item['filename'] == 'TEST_001_A.SubstrateBatch.archive.json'
    data = item['data']
    assert data['m_def'] == SubstrateBatchMbe.m_def.qualified_name()
    assert data['number_of_substrates'] == 3
    assert data['trigger_create_substrate'] is True
    batch = SubstrateBatchMbe.m_from_dict(data)
    assert isinstance(batch, (EntryData, SubstrateMbe, CrystallineSubstrate))
    assert type(batch.geometry) is cls
    assert batch.geometry.height.magnitude == pytest.approx(0.0005)
    roundtrip = SubstrateBatchMbe.m_from_dict(batch.m_to_dict(with_meta=True))
    assert type(roundtrip.geometry) is cls
    assert payload['expected_children'] == [
        {
            'lab_id': f'TEST_001_A_{index}',
            'filename': f'TEST_001_A_{index}.Substrate.archive.yaml',
        }
        for index in (1, 2, 3)
    ]


def test_batch_retains_crystal_properties_and_physical_metadata(client):
    response = client.post(
        '/api/preview',
        json={**BASE, 'polishing': 'Double-side', 'notes': 'Test'},
    )
    assert response.status_code == 200, response.text
    data = response.json()['archives'][0]['data']
    assert data['supplier_id'] == BASE['supplier_id']
    assert data['crystal_id'] == BASE['crystal_id']
    assert data['charge_id'] == BASE['charge']
    assert data['polishing'] == 'Double-side'
    assert data['components'][0]['pure_substance']['molecular_formula'] == 'SrTiO3'
    assert 'Test' in data['description']
    assert data['crystal_properties']['surface_orientation']['hkl_reciprocal'] == {
        'h_index': 0, 'k_index': 0, 'l_index': 1,
    }
    orientation = data['crystal_properties']['miscut'][
        'cartesian_miscut'
    ]['reference_orientation']
    assert orientation['hkl_direct'] == {
        'h_index': 1, 'k_index': 1, 'l_index': 0,
    }
    assert orientation['angle'] == pytest.approx(0.5)


@pytest.mark.parametrize(
    'changes',
    [
        {'material': 'Xx2'},
        {'orientation': ''},
        {'offcut_angle': 1.0, 'offcut_direction': ''},
        {'width_mm': -5},
        {'count': 0},
        {
            'geometry_shape': 'circular_sector',
            'radius_mm': 25.4,
            'sector_angle_deg': 400,
        },
        {'charge': 'reference', 'count': 3},
    ],
)
def test_invalid_substrate_intake_rejected(client, changes):
    response = client.post('/api/preview', json={**BASE, **changes})
    assert response.status_code == 422, response.text


def test_original_normalizer_and_no_custom_child_factory():
    source = inspect.getsource(SubstrateBatchMbe.normalize)
    for token in (
        'trigger_create_substrate',
        'create_archive(',
        'get_hash_ref(',
        'self.substrates.append(',
        'overwrite=True',
    ):
        assert token in source
    intake = inspect.getsource(preview_substrate_batch)
    assert 'SubstrateBatchMbe.m_from_dict(batch_data)' in intake
    assert 'create_archive(' not in intake
