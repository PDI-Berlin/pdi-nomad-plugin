"""Regression tests for production-code fixes. Existing policy tests are untouched."""
from __future__ import annotations

import importlib
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MBE = ROOT / 'src' / 'pdi_nomad_plugin' / 'mbe'
PROCESSING = MBE / 'processing'


def test_processing_preflight_is_really_before_put():
    backend = (PROCESSING / 'app.py').read_text(encoding='utf-8')
    frontend = (PROCESSING / 'static' / 'app.js').read_text(encoding='utf-8')
    assert "@app.post('/validate-process')" in backend
    assert 'validate_original_process(payload.get(\'data\'), allowed)' in backend
    start = frontend.index('async function uploadArchive(')
    end = frontend.index('async function saveProcesses()', start)
    upload = frontend[start:end]
    assert "fetch('./validate-process'" in upload
    assert "method: 'PUT'" in upload
    assert upload.index("fetch('./validate-process'") < upload.index("method: 'PUT'")
    assert 'pdi_nomad_plugin.mbe.materials.SubstrateMbe' not in frontend
    assert "nomad_material_processing.general.CrystallineSubstrate" in frontend


def test_preflight_contains_no_metainfo_reimplementation():
    source = (PROCESSING / 'original_process_preflight.py').read_text(encoding='utf-8')
    assert 'cls.m_from_dict(data)' in source
    assert 'EntryArchive(data=section)' in source
    assert 'reparsed.m_validate()' in source
    assert '_check_original_tree(data, cls)' in source
    assert 'def normalize(' not in source
    assert 'Quantity(' not in source and 'SubSection(' not in source
    assert 'requests.' not in source


def test_pdi_lab_base_path_is_injected_from_nomad_configuration():
    backend = (MBE / 'pdi_lab' / 'app.py').read_text(encoding='utf-8')
    frontend = (MBE / 'pdi_lab' / 'static' / 'app.js').read_text(encoding='utf-8')
    html = (MBE / 'pdi_lab' / 'templates' / 'index.html').read_text(encoding='utf-8')
    assert 'config.services.api_base_path' in backend
    assert 'window.PDI_LAB_BASE' in backend
    assert 'window.PDI_LAB_BASE' in frontend
    assert 'Substrate Check-in' in frontend and 'Substrate Check-in' in html


@pytest.mark.parametrize('process,recipe', [
    ('Cleaning', 'CleaningRecipe'),
    ('Annealing', 'AnnealingRecipe'),
    ('Etching', 'EtchingRecipe'),
])
def test_installed_original_process_contract(process, recipe):
    pytest.importorskip('nomad')
    pytest.importorskip('nomad_material_processing')
    from nomad.datamodel.data import EntryData
    from nomad.datamodel import EntryArchive
    from pdi_nomad_plugin.mbe.processing.app import PROCESS_TYPES

    key = process.lower()
    definition = PROCESS_TYPES[key]
    assert definition['processSchema'] == 'nomad_material_processing.general.' + process
    assert definition['schema'] == 'nomad_material_processing.general.' + recipe
    for name in (process, recipe):
        cls = getattr(importlib.import_module('nomad_material_processing.general'), name)
        assert cls.__module__ == 'nomad_material_processing.general'
        assert cls.m_def.qualified_name() == 'nomad_material_processing.general.' + name
        assert issubclass(cls, EntryData)
        assert 'recipe' in cls.m_def.all_quantities
        assert 'samples' in cls.m_def.all_sub_sections
        assert 'steps' in cls.m_def.all_sub_sections
        original_normalizer_owner = next(c for c in cls.__mro__ if 'normalize' in c.__dict__)
        assert not original_normalizer_owner.__module__.startswith('pdi_nomad_plugin')
        archive = EntryArchive(data=cls(name='TEST_ONLY'))
        errors, _ = archive.m_validate()
        assert not errors


def test_original_process_preflight_rejects_custom_metainfo_and_unknown_fields():
    pytest.importorskip('nomad')
    from pdi_nomad_plugin.mbe.processing.original_process_preflight import (
        OriginalProcessValidationError, validate_original_process,
    )
    schema = 'nomad_material_processing.general.Cleaning'
    refs = {
        'recipe': '../uploads/up/archive/recipe#/data',
        'samples': [{'reference': '../uploads/up/archive/substrate#/data'}],
    }
    with pytest.raises(OriginalProcessValidationError, match='Unapproved'):
        validate_original_process({'m_def': 'pdi_nomad_plugin.mbe.processes.CleaningPDI', **refs}, {schema})
    with pytest.raises(OriginalProcessValidationError, match='Unknown field'):
        validate_original_process({'m_def': schema, **refs, 'pdi_only_field': 42}, {schema})
    with pytest.raises(OriginalProcessValidationError, match='Missing original recipe reference'):
        validate_original_process({'m_def': schema, 'samples': refs['samples']}, {schema})


def test_processing_browser_preflight_blocks_upload():
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    subprocess.run(
        [node, str(ROOT / 'tests/schema_compliance/verify_processing_real_code_current.js')],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )


def test_mbe_draft_supports_original_rectangular_slot_geometry():
    code = (MBE / 'new_mbe_experiment' / 'static' / 'mbe_drafts.js').read_text(encoding='utf-8')
    assert "nomad_material_processing.general.SquareCuboid" in code
    assert "nomad_material_processing.general.RectangleCuboid" in code
    assert "['height', 'width', 'length']" in code
    assert "nomad_archive: false" in code
    node = shutil.which('node')
    if node:
        subprocess.run(
            [node, str(ROOT / 'tests/schema_compliance/verify_mbe_draft_rectangular_slots.js')],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
