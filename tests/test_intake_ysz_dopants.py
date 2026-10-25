"""Intake adapter checks: existing original metainfo; no schema changes."""

import math

import pytest
from fastapi.testclient import TestClient

from pdi_nomad_plugin.mbe.substrate_intake.app import app


def _payload(dopant):
    return {
        'supplier': 'CrysTec',
        'supplier_id': 'CTC',
        'crystal_id': 'YSZ',
        'charge': 'test-ysz-reference',
        'material': 'ZrO2',
        'orientation': '1 0 0',
        'width_mm': 10,
        'length_mm': 10,
        'thickness_mm': 0.5,
        'count': 1,
        'subsections': {'dopants': [dopant]},
    }


def _eight_ysz():
    from pdi_nomad_plugin.mbe.substrate_intake.app import ysz_fractions

    return ysz_fractions(0.08)


def test_8ysz_original_dopant_quantities_without_nan():
    atomic, mass = _eight_ysz()
    assert math.isclose(atomic, 0.05063291139240506, abs_tol=1e-14)
    assert math.isclose(mass, 0.1082328976107106, abs_tol=1e-14)
    with TestClient(app) as client:
        response = client.post(
            '/api/preview',
            json=_payload(
                {
                    'element': 'Y',
                    'atomic_fraction': atomic,
                    'mass_fraction': mass,
                }
            ),
        )
    assert response.status_code == 200, response.text
    archive = response.json()['archives'][0]['data']
    assert archive['m_def'] == 'pdi_nomad_plugin.mbe.materials.SubstrateBatchMbe'
    dopant = archive['dopants'][0]
    assert dopant['element'] == 'Y'
    assert dopant['atomic_fraction'] == atomic
    assert dopant['mass_fraction'] == mass
    assert 'oxide_mol_percent' not in dopant
    assert 'mol_percent' not in dopant


@pytest.mark.parametrize(
    'dopant',
    [
        {'element': 'Y', 'atomic_fraction': 0.08, 'mass_fraction': 0.08},
        {'element': 'Y', 'atomic_fraction': 0.05},
        # Nonfinite values must reach API validation as valid JSON strings.
        {'element': 'Y', 'atomic_fraction': 0.05, 'mass_fraction': 'NaN'},
        {'element': 'Y', 'atomic_fraction': 0.05, 'mass_fraction': 'Infinity'},
    ],
)
def test_incomplete_inconsistent_or_nonfinite_fractions_fail_closed(dopant):
    with TestClient(app) as client:
        response = client.post('/api/preview', json=_payload(dopant))
    assert response.status_code == 422, response.text


def test_concentration_only_remains_optional():
    with TestClient(app) as client:
        response = client.post(
            '/api/preview',
            json=_payload(
                {
                    'element': 'Y',
                    'doping_level': 1e22,
                }
            ),
        )
    assert response.status_code == 200, response.text


def test_ui_serves_actual_ysz_selector():
    with TestClient(app) as client:
        html = client.get('/')
        js = client.get('/static/intake_ysz_dopants.js?v=11')
    assert html.status_code == 200
    assert 'intake_ysz_dopants.js?v=11' in html.text
    assert js.status_code == 200
    assert 'YSZ: mol-% Y2O3 in ZrO2' in js.text
