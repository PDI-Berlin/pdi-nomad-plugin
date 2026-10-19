"""Stage12: explicit 8YSZ UI preset with original-schema normalization."""

import math

from fastapi.testclient import TestClient

from pdi_nomad_plugin.mbe.substrate_intake.app import app


def _payload(preset='8ysz', dopants=None):
    from pdi_nomad_plugin.mbe.substrate_intake.app import ysz_fractions

    a, w = ysz_fractions(0.08)
    return {
        'supplier': 'CrysTec',
        'supplier_id': 'CTC',
        'crystal_id': 'YSZ',
        'charge': '8ysz-stage12-test',
        'material': 'ZrO2',
        'material_preset': preset,
        'orientation': '1 0 0',
        'width_mm': 10,
        'length_mm': 10,
        'thickness_mm': 0.5,
        'count': 1,
        'subsections': {
            'dopants': dopants
            if dopants is not None
            else [{'element': 'Y', 'atomic_fraction': a, 'mass_fraction': w}]
        },
    }


def test_preset_preview_and_original_composition_fields():
    with TestClient(app) as client:
        html = client.get('/').text
        js = client.get('/static/intake_ysz_preset.js?v=12')
        response = client.post('/api/preview', json=_payload())
    assert '8YSZ (ZrO2 + 8 mol-% Y2O3)' in html
    assert js.status_code == 200
    assert response.status_code == 200, response.text
    data = response.json()['archives'][0]['data']
    assert data['m_def'] == 'pdi_nomad_plugin.mbe.materials.SubstrateBatchMbe'
    assert data['components'][0]['pure_substance']['molecular_formula'] == 'ZrO2'
    assert 'material_preset' not in data
    host = {e['element']: e for e in data['elemental_composition']}
    assert set(host) == {'Zr', 'O'}  # Y appended ONCE by original Dopant.normalize
    a, w = data['dopants'][0]['atomic_fraction'], data['dopants'][0]['mass_fraction']
    assert math.isclose(
        sum(e['atomic_fraction'] for e in host.values()) + a, 1, abs_tol=1e-9
    )
    assert math.isclose(
        sum(e['mass_fraction'] for e in host.values()) + w, 1, abs_tol=1e-9
    )


def test_preset_rejects_mismatching_dopant():
    with TestClient(app) as client:
        bad = client.post(
            '/api/preview',
            json=_payload(
                dopants=[
                    {
                        'element': 'Y',
                        'atomic_fraction': 0.03,
                        'mass_fraction': 0.065,
                    }
                ]
            ),
        )
    assert bad.status_code == 422, bad.text


def test_original_8ysz_normalizer_in_memory_without_writes():
    from nomad.datamodel import EntryArchive
    from nomad.normalizing.metainfo import MetainfoNormalizer

    from pdi_nomad_plugin.mbe.materials import SubstrateMbe

    with TestClient(app) as client:
        response = client.post('/api/preview', json=_payload())
    assert response.status_code == 200, response.text
    batch_data = response.json()['archives'][0]['data']
    child = {
        k: v
        for k, v in batch_data.items()
        if k not in {'trigger_create_substrate', 'substrates', 'number_of_substrates'}
    }
    child['m_def'] = 'pdi_nomad_plugin.mbe.materials.SubstrateMbe'
    child['lab_id'] = 'stage12-test-only-8ysz'
    data = SubstrateMbe.m_from_dict(child)
    from nomad.datamodel import EntryMetadata

    archive = EntryArchive(data=data, metadata=EntryMetadata())
    MetainfoNormalizer().normalize(archive=archive)
    assert archive.results and archive.results.material, (
        'Missing original-normalizer material results'
    )
    result = archive.m_to_dict()['results']['material']['elemental_composition']
    print('Stage12 actual NORMALIZED results.material.elemental_composition:', result)
    vals = {e['element']: e for e in result}
    assert len(result) == 3 and set(vals) == {'Y', 'Zr', 'O'}, (
        'Duplicate/missing elements!'
    )
    a = [vals[k]['atomic_fraction'] for k in ('Y', 'Zr', 'O')]
    w = [vals[k]['mass_fraction'] for k in ('Y', 'Zr', 'O')]
    assert all(isinstance(x, (int, float)) and math.isfinite(x) for x in a + w), (
        'NaN/Inf'
    )
    assert math.isclose(sum(a), 1, abs_tol=1e-7), f'atomic fractions sum to {sum(a)}'
    assert math.isclose(sum(w), 1, abs_tol=1e-7), f'mass fractions sum to {sum(w)}'
    assert math.isclose(vals['Y']['atomic_fraction'], 0.05063291139240506, abs_tol=1e-6)
    assert math.isclose(vals['Y']['mass_fraction'], 0.1082328976107106, abs_tol=1e-6)
