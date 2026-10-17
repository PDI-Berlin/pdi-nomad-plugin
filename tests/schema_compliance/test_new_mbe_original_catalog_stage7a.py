"""Stage 7A: New MBE read catalogs use original NOMAD schema, writes fail closed.

This is a temporary migration stage. Do not treat its tests as production
approval; archive submission is intentionally disabled until it is refactored.
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JS = (ROOT / 'src/pdi_nomad_plugin/mbe/new_mbe_experiment/static/app.js').read_text(
    'utf8'
)
BASE = json.loads(
    (
        ROOT / 'tests/schema_compliance/baselines/original_metainfo_approved.json'
    ).read_text('utf8')
)

REQUIRED = (
    'nomad_material_processing.general.CrystallineSubstrate',
    'nomad_material_processing.general.CleaningRecipe',
    'nomad_material_processing.general.Cleaning',
    'nomad_material_processing.general.AnnealingRecipe',
    'nomad_material_processing.general.Annealing',
    'nomad_material_processing.general.EtchingRecipe',
    'nomad_material_processing.general.Etching',
    'nomad_material_processing.vapor_deposition.general.SubstrateHolder',
    'nomad_material_processing.vapor_deposition.general.FilledSubstrateHolder',
    'nomad_material_processing.vapor_deposition.general.InsertReduction',
)


def function_start(name):
    found = re.search(r'(?:async\s+)?function\s+' + name + r'\s*\([^)]*\)\s*\{', JS)
    assert found, f'Missing JS function {name}'
    return JS[found.end() : found.end() + 550]


def test_new_mbe_catalog_uses_only_verified_original_mdefs():
    assert 'pdi_nomad_plugin.' not in JS, (
        'A local schema path is still present in New MBE Experiment.'
    )
    # Only these original holder m_defs remain active in the application.
    for schema in (
        'nomad_material_processing.vapor_deposition.general.SubstrateHolder',
        'nomad_material_processing.vapor_deposition.general.FilledSubstrateHolder',
    ):
        assert schema in BASE, f'Not in original runtime m_def contract: {schema}'
        assert schema in JS, f'Original schema not referenced: {schema}'
    assert (
        'nomad_material_processing.vapor_deposition.general.InsertReduction' not in JS
    )
    assert 'RectangularGeometryPDI' not in JS
    assert 'MBENominalLayerPDI' not in JS


def test_new_mbe_writers_are_explicitly_blocked_pending_original_mbe_archive():
    # A successful syntax check alone would not mean the old PDI fields had disappeared.
    # Fail closed before any NOMAD upload until original MBE schema and reference mapping are verified.
    for name in ('uploadArchiveData', 'uploadArchiveDataV2'):
        body = function_start(name).lstrip()
        assert body.startswith('throw new Error('), name
        assert 'saving is disabled' in body, name
    for name in (
        'experimentArchiveData',
        'filledHolderArchiveData',
        'setPhysicalHolderWorkflowStatus',
    ):
        body = function_start(name).lstrip()
        assert body.startswith('throw new Error('), name


def test_original_crystalline_substrate_field_paths():
    cr = BASE['nomad_material_processing.general.CrystallineSubstrate']
    assert 'components' in cr['subsections']
    assert 'crystal_properties' in cr['subsections']
    assert 'geometry' in cr['subsections']
    cp = BASE['nomad_material_processing.general.SubstrateCrystalProperties']
    assert 'miscut' in cp['subsections']
    assert 'surface_orientation' in cp['subsections']
    assert 'originalMbeSubstrateFields(data)' in JS
    assert "'data.as_delivered'" not in JS
    assert "'data.parent_sample'" not in JS


def test_new_mbe_original_substrate_converter_real_js():
    quickjs = pytest.importorskip('quickjs')
    start = JS.index('function originalMbeSubstrateFields(data)')
    end = JS.index('\nasync function initialiseSubstrates()', start)
    ctx = quickjs.Context()
    ctx.eval(JS[start:end])
    archive = {
        'lab_id': 'TEST_STO_01',
        'description': 'Crystal ID: AB-12\nCharge ID: CH-3',
        'components': [{'pure_substance': {'molecular_formula': 'SrTiO3'}}],
        'crystal_properties': {
            'surface_orientation': {
                'hkl_reciprocal': {'h_index': 0, 'k_index': 0, 'l_index': 1}
            },
            'miscut': {
                'cartesian_miscut': {
                    'reference_orientation': {
                        'hkl_direct': {'h_index': 1, 'k_index': 1, 'l_index': 0},
                        'angle': 4,
                    }
                }
            },
        },
    }
    result = json.loads(
        ctx.eval(
            'JSON.stringify(originalMbeSubstrateFields(' + json.dumps(archive) + '))'
        )
    )
    assert result['formula'] == 'SrTiO3'
    assert result['orientation'] == '0 0 1'
    assert result['offcut'] == '4°'
    assert result['offcutDirection'] == '1 1 0'
    assert result['crystalId'] == 'AB-12'
    assert result['chargeId'] == 'CH-3'
