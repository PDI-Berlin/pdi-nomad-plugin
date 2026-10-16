"""Runtime provenance contract for real installed upstream NOMAD implementations.

Unlike static source scans, these cases import the actual upstream classes and
check their metainfo identity and the effective normalizer implementation.
Existing repository policy tests are never edited by this patch.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from .original_contract import baseline


@pytest.mark.parametrize('class_name', [
    'nomad_material_processing.general.CrystallineSubstrate',
    'nomad_material_processing.general.Cleaning',
    'nomad_material_processing.general.CleaningRecipe',
    'nomad_material_processing.general.Annealing',
    'nomad_material_processing.general.AnnealingRecipe',
    'nomad_material_processing.general.Etching',
    'nomad_material_processing.general.EtchingRecipe',
    'nomad_material_processing.vapor_deposition.general.SubstrateHolder',
    'nomad_material_processing.vapor_deposition.general.FilledSubstrateHolder',
    'nomad_material_processing.vapor_deposition.general.InsertReduction',
])
def test_real_original_schema_and_normalizer(class_name):
    pytest.importorskip('nomad')
    pytest.importorskip('nomad_material_processing')
    from pdi_nomad_plugin.mbe.lab_library.original_preflight import (
        _resolve_original_class,
        assert_upstream_normalizer,
    )

    specs = baseline()
    assert class_name in specs, f'Missing approved baseline: {class_name}'
    cls = _resolve_original_class(class_name)
    assert cls.m_def.qualified_name() == class_name
    assert cls.__module__ == class_name.rsplit('.', 1)[0]
    assert_upstream_normalizer(cls)
    # Exact Quantities, Subsections and units against the unchanged baseline.
    from .original_contract import schema_differences
    assert schema_differences(class_name, specs[class_name]) == []


def test_process_client_does_not_reimplement_recipe_normalization():
    root = Path(__file__).resolve().parents[2]
    source = (root / 'src/pdi_nomad_plugin/mbe/processing/static/app.js').read_text(encoding='utf-8')
    begin = source.index('function processArchiveData(')
    end = source.index('\n\nasync function uploadArchive(', begin)
    process = source[begin:end]
    # The original NOMAD process normalizer consumes the recipe REFERENCE.
    assert 'recipe: nomadArchiveReference(' in process
    assert 'definition.recipe.steps' not in process
    assert 'data.steps =' not in process
    assert 'data.instruments =' not in process
    assert 'function sampleCutArchiveData(' not in source



def test_original_process_preflight_requires_upstream_normalizer():
    root = Path(__file__).resolve().parents[2]
    path = root / 'src/pdi_nomad_plugin/mbe/processing/original_process_preflight.py'
    text = path.read_text(encoding='utf-8')
    assert 'assert_upstream_normalizer(cls)' in text
    assert "if data.get('steps') or data.get('instruments')" in text
