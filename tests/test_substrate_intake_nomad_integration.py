"""Real API-to-ORIGINAL NOMAD schema integration tests (no PDI schemas/normalizers)."""

import pytest
from fastapi.testclient import TestClient
from nomad_material_processing.general import (
    CrystallineSubstrate,
    Cylinder,
    CylinderSector,
    RectangleCuboid,
    SquareCuboid,
)

from pdi_nomad_plugin.mbe.substrate_intake.app import app

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
    'name,cls,fields',
    [
        ('square', SquareCuboid, {'geometry_shape': 'rectangle'}),
        ('rectangle', RectangleCuboid, {'geometry_shape': 'rectangle', 'length_mm': 5}),
        ('wafer', Cylinder, {'geometry_shape': 'circle', 'radius_mm': 25.4}),
        (
            'quarter wafer',
            CylinderSector,
            {
                'geometry_shape': 'circular_sector',
                'radius_mm': 25.4,
                'sector_angle_deg': 90,
            },
        ),
    ],
)
def test_original_substrate_geometry_roundtrip(client, name, cls, fields):
    response = client.post('/api/preview', json={**BASE, **fields})
    assert response.status_code == 200, (name, response.text)
    archives = response.json()['archives']
    assert len(archives) == 3
    for index, item in enumerate(archives, 1):
        assert item['filename'] == f'TEST_001_A_{index}.archive.json'
        data = item['data']
        assert data['m_def'] == 'nomad_material_processing.general.CrystallineSubstrate'
        assert data['geometry']['m_def'] == (
            'nomad_material_processing.general.' + cls.__name__
        )
        substrate = CrystallineSubstrate.m_from_dict(data)
        assert type(substrate.geometry) is cls
        assert substrate.lab_id == f'TEST_001_A_{index}'
        assert substrate.geometry.height.magnitude == pytest.approx(0.0005)
        restored = CrystallineSubstrate.m_from_dict(substrate.m_to_dict(with_meta=True))
        assert type(restored.geometry) is cls
        assert restored.geometry.m_to_dict() == substrate.geometry.m_to_dict()


def test_original_substrate_material_orientation_miscut_and_metadata(client):
    response = client.post(
        '/api/preview', json={**BASE, 'polishing': 'both', 'notes': 'Test'}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['batch_lab_id'] == 'TEST_001_A'
    archives = result['archives']
    assert len(archives) == BASE['count']
    assert len({item['filename'] for item in archives}) == BASE['count']
    for item in archives:
        data = item['data']
        assert data['m_def'] == 'nomad_material_processing.general.CrystallineSubstrate'
        assert data['supplier_id'] == BASE['supplier_id']
        assert data['components'][0]['m_def'] == (
            'nomad.datamodel.metainfo.basesections.v1.PureSubstanceComponent'
        )
        assert data['components'][0]['pure_substance']['molecular_formula'] == 'SrTiO3'
        assert 'Crystal ID: 001' in data['description']
        assert 'Charge ID: A' in data['description']
        assert 'Polishing: both' in data['description']
        assert 'Test' in data['description']
        crystal = data['crystal_properties']
        assert crystal['surface_orientation']['hkl_reciprocal'] == {
            'h_index': 0,
            'k_index': 0,
            'l_index': 1,
        }
        offcut = crystal['miscut']['cartesian_miscut']['reference_orientation']
        assert offcut['hkl_direct'] == {'h_index': 1, 'k_index': 1, 'l_index': 0}
        assert offcut['angle'] == pytest.approx(0.5)
        assert CrystallineSubstrate.m_from_dict(data).lab_id == data['lab_id']
        assert 'trigger_create_substrate' not in data
        assert 'SubstrateBatchMbe' not in str(data)


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
    ],
)
def test_invalid_substrate_intake_rejected(client, changes):
    response = client.post('/api/preview', json={**BASE, **changes})
    assert response.status_code == 422, response.text


def test_every_original_substrate_is_independent_and_no_pdi_normalizer(client):
    result = client.post('/api/preview', json=BASE).json()
    assert len(result['archives']) == 3
    assert 'data' not in result, 'A custom batch archive must never be produced'
    assert [item['data']['lab_id'] for item in result['archives']] == [
        'TEST_001_A_1',
        'TEST_001_A_2',
        'TEST_001_A_3',
    ]
    assert CrystallineSubstrate.__module__ == 'nomad_material_processing.general'
    from inspect import getfile

    assert 'pdi_nomad_plugin' not in getfile(CrystallineSubstrate)
