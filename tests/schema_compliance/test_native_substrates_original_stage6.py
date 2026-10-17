"""Strict regression checks for native Substrates search app + smoke archives."""

import ast
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = 'nomad_material_processing.general.CrystallineSubstrate'
BASELINE = ROOT / 'tests/schema_compliance/baselines/original_metainfo_approved.json'
APP = ROOT / 'src/pdi_nomad_plugin/mbe/mbe_app/__init__.py'
FIXTURES = ROOT / 'tests/fixtures/dashboard'
EXPECTED = {
    'test_cleaning_recipe.archive.yaml': 'nomad_material_processing.general.CleaningRecipe',
    'test_etching_recipe.archive.yaml': 'nomad_material_processing.general.EtchingRecipe',
    'test_holder.archive.yaml': 'nomad_material_processing.vapor_deposition.general.SubstrateHolder',
}


def test_native_app_uses_exact_original_crystalline_substrate_mdef():
    source = APP.read_text('utf-8')
    tree = ast.parse(source)
    candidates = [
        n.value.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        for t in n.targets
        if isinstance(t, ast.Name)
        and t.id == 'ORIGINAL_SUBSTRATE'
        and isinstance(n.value, ast.Constant)
    ]
    assert candidates == [ORIGINAL]
    assert 'pdi_nomad_plugin.mbe.materials.SubstrateMbe' not in source
    assert 'data.as_delivered' not in source
    assert 'data.processed' not in source
    assert 'data.grown' not in source
    baseline = json.loads(BASELINE.read_text('utf-8'))
    quantities = baseline[ORIGINAL]['quantities']
    for field in ('lab_id', 'name', 'supplier', 'supplier_id'):
        assert field in quantities, field
        assert f'data.{field}#' in source
    assert 'section_defs.definition_qualified_name' in source


def test_dashboard_fixtures_use_only_original_metainfo_and_fields():
    baseline = json.loads(BASELINE.read_text('utf-8'))

    def walk(section, schema):
        assert schema in baseline, schema
        spec = baseline[schema]
        assert section.get('m_def', schema) == schema
        assert set(section) <= (
            set(spec['quantities']) | set(spec['subsections']) | {'m_def'}
        )
        for key, sub in spec['subsections'].items():
            if key not in section:
                continue
            if sub['repeats']:
                assert isinstance(section[key], list), (schema, key)
                for child in section[key]:
                    walk(child, child.get('m_def', sub['schema']))
            else:
                assert isinstance(section[key], dict), (schema, key)
                child = section[key]
                walk(child, child.get('m_def', sub['schema']))

    for filename, schema in EXPECTED.items():
        archive = yaml.safe_load((FIXTURES / filename).read_text('utf-8'))
        assert archive['data']['m_def'] == schema
        walk(archive['data'], schema)
