"""Checks against the user's already-migrated source state.

Never relax the repository-wide original-schema policy tests.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'src' / 'pdi_nomad_plugin' / 'mbe'


def assignment(path, name):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f'Missing {name}')


def test_library_write_policy_uses_original_sections_only():
    defs = assignment(APP / 'lab_library' / 'app.py', 'LIBRARY_TYPES')
    for kind in ('cleaning', 'annealing'):
        d = defs['processing_recipe']['schemas'][kind]
        assert d['schema'].startswith('nomad_material_processing.')
        assert d['write_supported'] is True
    for kind in ('holder', 'insert'):
        d = defs[kind]
        assert d['schema'].startswith('nomad_material_processing.')
        assert d['write_supported'] is False
    js = (APP / 'lab_library' / 'static' / 'app.js').read_text(encoding='utf-8')
    save = js.split('async function saveEditor(event) {', 1)[1]
    assert 'definition.write_supported !== true' in save
    assert save.index('definition.write_supported !== true') < save.index(
        'await uploadArchive('
    )


def test_processing_intake_and_search_keep_newer_original_migration():
    proc = assignment(APP / 'processing' / 'app.py', 'PROCESS_TYPES')
    assert set(proc) == {'cleaning', 'annealing'}
    for d in proc.values():
        assert d['schema'].startswith('nomad_material_processing.')
        assert d['processSchema'].startswith('nomad_material_processing.')
    intake = (APP / 'substrate_intake' / 'app.py').read_text(encoding='utf-8')
    assert "'m_def': 'pdi_nomad_plugin.mbe.materials.SubstrateBatchMbe'" not in intake
    assert 'SubstrateBatchMbe.m_def.qualified_name()' in intake
    native = (APP / 'mbe_app' / '__init__.py').read_text(encoding='utf-8')
    assert 'nomad_material_processing.general.CrystallineSubstrate' in native


def test_new_mbe_dashboard_does_not_import_legacy_metainfo():
    app = (APP / 'new_mbe_experiment' / 'app.py').read_text(encoding='utf-8')
    assert (
        'from pdi_nomad_plugin.mbe.' not in app
        and 'from pdi_nomad_plugin.general' not in app
    )
    options = (APP / 'new_mbe_experiment' / 'ui_options.py').read_text(encoding='utf-8')
    assert 'Quantity(' not in options and 'normalize(' not in options


@pytest.mark.parametrize(
    'schema',
    [
        'nomad_material_processing.general.CleaningRecipe',
        'nomad_material_processing.general.AnnealingRecipe',
        'nomad_material_processing.general.EtchingRecipe',
    ],
)
def test_original_recipe_is_actual_entry_root(schema):
    pytest.importorskip('nomad')
    import importlib

    from nomad.datamodel.data import EntryData

    module, name = schema.rsplit('.', 1)
    cls = getattr(importlib.import_module(module), name)
    assert cls.m_def.qualified_name() == schema
    assert issubclass(cls, EntryData)
