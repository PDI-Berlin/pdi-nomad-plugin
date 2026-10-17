"""NOMAD parser and serializer integration tests for Lab Library recipes."""

import importlib

import pytest

from pdi_nomad_plugin.mbe.lab_library.app import LIBRARY_TYPES

CASES = {
    'cleaning': {
        'method': 'IPA cleaning',
        'duration': 120.0,
        'steps': [
            {
                'duration': 120.0,
                'temperature': 25.0,
                'comment': 'Ultrasonic cleaning',
            }
        ],
    },
    'annealing': {
        'method': 'Tube furnace',
        'duration': 3600.0,
        'steps': [
            {
                'duration': 3600.0,
                'starting_temperature': 25.0,
                'ending_temperature': 850.0,
            }
        ],
    },
    'etching': {
        'method': 'Chemical etching',
        'steps': [
            {
                'duration': 60.0,
                'temperature': 25.0,
                'comment': 'Etching step',
            }
        ],
    },
}


@pytest.mark.parametrize('kind', list(CASES))
def test_recipe_nomad_roundtrip(kind):
    spec = LIBRARY_TYPES['processing_recipe']['schemas'][kind]
    module, name = spec['schema'].rsplit('.', 1)
    cls = getattr(importlib.import_module(module), name)

    data = {
        'm_def': spec['schema'],
        'name': 'Integration test ' + kind,
        'description': 'Preserve complete recipe metadata',
        **CASES[kind],
    }

    recipe = cls.m_from_dict(data)
    serialized = recipe.m_to_dict(with_meta=True)
    restored = cls.m_from_dict(serialized)

    assert restored.name == data['name']
    assert restored.description == data['description']
    assert restored.method == data['method']
    assert len(restored.steps) == 1
    assert serialized == restored.m_to_dict(with_meta=True)

    for field, value in CASES[kind].items():
        if field in ('steps', 'coating_reagents'):
            continue
        actual = getattr(restored, field)
        if isinstance(value, float):
            assert getattr(actual, 'magnitude', actual) == pytest.approx(value)
        else:
            assert actual == value

    for field, value in CASES[kind]['steps'][0].items():
        actual = getattr(restored.steps[0], field)
        if isinstance(value, float):
            assert getattr(actual, 'magnitude', actual) == pytest.approx(value)
        else:
            assert actual == value

    if kind == 'back_side_coating':
        assert restored.coating_reagents is None


def test_unverified_back_coating_is_not_a_valid_library_recipe():
    assert 'back_side_coating' not in LIBRARY_TYPES['processing_recipe']['schemas']
