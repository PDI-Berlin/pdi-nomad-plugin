"""Intake uses the existing batch EntryData root and original normalizer."""

from fastapi.testclient import TestClient
from nomad.datamodel.data import EntryData
from nomad.datamodel.datamodel import EntryArchive
from nomad_material_processing.general import CrystallineSubstrate

from pdi_nomad_plugin.mbe.materials import SubstrateBatchMbe, SubstrateMbe
from pdi_nomad_plugin.mbe.substrate_intake.app import app


def test_existing_entry_root_preview_roundtrip_and_safe_ids():
    assert issubclass(SubstrateBatchMbe, (SubstrateMbe, EntryData))
    assert issubclass(SubstrateMbe, CrystallineSubstrate)
    form = {
        'supplier': 'CrysTec', 'supplier_id': 'CTC', 'crystal_id': 'GSO',
        'charge': 'P 43671/26', 'material': 'GdScO3', 'orientation': '1 1 0',
        'count': 2, 'width_mm': 10, 'length_mm': 10, 'thickness_mm': 0.5,
        'polishing': 'Single-side',
        'subsections': {'electronic_properties': {'conductivity_type': 'Insulating'}},
    }
    with TestClient(app) as client:
        result = client.post('/api/preview', json=form)
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload['upload_supported'] is True
    assert payload['root_is_entrydata'] is True
    assert len(payload['archives']) == 1
    item = payload['archives'][0]
    assert item['filename'] == 'CTC_GSO_P-43671-26.SubstrateBatch.archive.json'
    data = item['data']
    assert data['m_def'] == SubstrateBatchMbe.m_def.qualified_name()
    assert data['lab_id'] == 'CTC_GSO_P-43671-26'
    assert data['number_of_substrates'] == 2
    assert data['trigger_create_substrate'] is True
    assert data['charge_id'] == 'P 43671/26'
    assert data['electronic_properties']['conductivity_type'] == 'Insulating'
    assert data['crystal_properties']['surface_orientation']['hkl_reciprocal'] == {
        'h_index': 1, 'k_index': 1, 'l_index': 0,
    }
    batch = SubstrateBatchMbe.m_from_dict(data)
    assert isinstance(EntryArchive(data=batch).data, EntryData)
    assert [x['filename'] for x in payload['expected_children']] == [
        f'CTC_GSO_P-43671-26_{n}.Substrate.archive.yaml' for n in (1,2)
    ]


def test_bad_polishing_and_bad_reference_hkl_rejected():
    form = {
        'supplier_id': 'CTC',
        'crystal_id': 'GSO',
        'charge': 'P43671',
        'material': 'GdScO3',
        'orientation': '1 1 0',
        'count': 1,
        'width_mm': 10,
        'length_mm': 10,
        'thickness_mm': 0.5,
    }
    with TestClient(app) as client:
        bad = client.post('/api/preview', json={**form, 'polishing': 'both'})
        assert bad.status_code == 422
        mismatch = client.post(
            '/api/preview',
            json={
                **form,
                'subsections': {
                    'crystal_properties': {
                        'surface_orientation': {
                            'hkl_reciprocal': {
                                'h_index': 0,
                                'k_index': 0,
                                'l_index': 1,
                            }
                        }
                    }
                },
            },
        )
        assert mismatch.status_code == 422
