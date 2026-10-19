"""Read-only checks of actual upstream metainfo; never writes to NOMAD."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MBE = ROOT / 'src' / 'pdi_nomad_plugin' / 'mbe'
LIB = MBE / 'lab_library'
INTAKE = MBE / 'substrate_intake'


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lab_library_preflight_is_before_http_put():
    code = (LIB / 'static' / 'app.js').read_text(encoding='utf-8')
    start = code.index('async function uploadArchive(')
    end = code.index('async function saveEditor(', start)
    function = code[start:end]
    assert 'await validateRecipeBeforeUpload(data)' in function
    assert function.index('await validateRecipeBeforeUpload(data)') < function.index(
        "method:'PUT'"
    )
    assert "fetch('validate-recipe'" in code
    backend = (LIB / 'app.py').read_text(encoding='utf-8')
    assert "@app.post('/validate-recipe')" in backend
    assert "validate_original_recipe(payload.get('data'), allowed)" in backend


def test_intake_requires_verified_entrydata_root_before_put():
    code = (INTAKE / 'app.py').read_text(encoding='utf-8')
    assert "'upload_supported': True" in code
    start = code.index('async function saveToNomad()')
    guard = code.index('if (preview.upload_supported !== true)', start)
    put = code.index("method: 'PUT'", start)
    assert guard < put
    assert 'SubstrateBatchMbe.m_from_dict(batch_data)' in code
    assert 'EntryArchive(data=section)' in code
    assert 'saveButton.disabled = true;' in code
    assert 'Upload a Substrate Batch and generate substrates' in code
    guard_js = (INTAKE / 'static' / 'intake_duplicate_guard.js').read_text(encoding='utf-8')
    assert 'body.directory_metadata.content' in guard_js
    assert code.index('pdiIntakeDuplicateGuard.assertNoCollision', start) < put


def test_validator_is_original_only_and_never_normalizes_or_uploads():
    code = (LIB / 'original_preflight.py').read_text(encoding='utf-8')
    assert 'cls.m_from_dict(data)' in code
    assert 'EntryArchive(data=section)' in code
    assert 'EntryArchive.m_from_dict(serialized)' in code
    assert 'reparsed.m_validate()' in code
    assert 'subsection.sub_section.section_cls' not in code  # uses definition object
    assert 'definition.sub_section.section_cls' in code
    assert 'pdi_nomad_plugin.' not in code
    assert '.normalize(' not in code
    assert 'requests.' not in code


@pytest.mark.parametrize(
    'schema',
    [
        'nomad_material_processing.general.CleaningRecipe',
        'nomad_material_processing.general.AnnealingRecipe',
        'nomad_material_processing.general.EtchingRecipe',
    ],
)
def test_actual_original_recipe_archive_roundtrip(schema):
    pytest.importorskip('nomad')
    import importlib

    from nomad.datamodel.data import EntryData

    preflight = _load_module(
        LIB / 'original_preflight.py', 'original_preflight_under_test'
    )
    module_name, name = schema.rsplit('.', 1)
    cls = getattr(importlib.import_module(module_name), name)
    assert cls.m_def.qualified_name() == schema
    assert cls.__module__ == module_name
    assert issubclass(cls, EntryData)
    payload = {
        'm_def': schema,
        'name': 'READ_ONLY_PREFLIGHT',
        'lab_id': 'READ_ONLY_PREFLIGHT',
    }
    result = preflight.validate_original_recipe(payload, {schema})
    assert result['valid'] is True
    assert result['schema'] == schema
    assert result['normalizer_executed'] is False
    assert result['server_parser_executed'] is False

    with pytest.raises(preflight.OriginalSchemaValidationError, match='Unknown field'):
        preflight.validate_original_recipe(
            {**payload, 'pdi_invented_field': 1}, {schema}
        )
    with pytest.raises(preflight.OriginalSchemaValidationError):
        preflight.validate_original_recipe(
            {**payload, 'samples': [{'name': 'X'}]}, {schema}
        )


def test_real_intake_payload_and_original_root():
    pytest.importorskip('nomad')
    from nomad.datamodel.data import EntryData
    from nomad_material_processing.general import CrystallineSubstrate
    from pdi_nomad_plugin.mbe.materials import SubstrateBatchMbe, SubstrateMbe

    intake = _load_module(INTAKE / 'app.py', 'substrate_intake_under_test')
    request = intake.SubstrateIntakePreview(
        supplier='Example Supplier',
        supplier_id='S123',
        material='SrTiO3',
        crystal_id='C1',
        charge='B1',
        orientation='001',
        offcut_angle=0.1,
        offcut_direction='110',
        width_mm=10,
        length_mm=10,
        thickness_mm=0.5,
        count=2,
    )
    result = asyncio.run(intake.preview_substrate_batch(request))
    assert len(result['archives']) == 1
    assert len(result['expected_children']) == 2
    assert result['upload_supported'] is True
    assert issubclass(SubstrateMbe, CrystallineSubstrate)
    assert result['root_is_entrydata'] is issubclass(SubstrateBatchMbe, EntryData)
    for archive in result['archives']:
        assert archive['data']['m_def'] == SubstrateBatchMbe.m_def.qualified_name()
        assert SubstrateBatchMbe.m_from_dict(archive['data']) is not None
