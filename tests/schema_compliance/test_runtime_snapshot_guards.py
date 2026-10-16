"""Regression tests for schema boundary and snapshot canonicalization."""

from .original_contract import baseline, canonical_type, manifest, assert_original_archive_data


def test_baseline_does_not_contain_pdi_schemas():
    assert all(name.startswith(('nomad.', 'nomad_material_processing.')) for name in baseline())
    assert all('pdi_nomad_plugin' not in name for name in baseline())


def test_reference_type_repr_is_stable():
    assert canonical_type('<nomad.metainfo.metainfo.Reference object at 0xDEADBEEF>') == 'Reference'
    assert canonical_type('m_float64(float)') == 'm_float64(float)'


def test_baseline_normalizers_are_explicitly_recorded():
    for name, spec in baseline().items():
        assert 'normalizer' in spec, name
        normalizer = spec['normalizer']
        if normalizer:
            assert normalizer['defined_in'].startswith(('nomad.', 'nomad_material_processing.')), name


def test_original_archive_payload_can_use_original_subsection():
    assert_original_archive_data({
        'm_def': 'nomad_material_processing.general.CrystallineSubstrate',
        'lab_id': 'M001',
        'geometry': {
            'm_def': 'nomad_material_processing.general.CylinderSector',
            'radius': 0.0254,
            'central_angle': 90,
        },
    }, 'nomad_material_processing.general.CrystallineSubstrate')
