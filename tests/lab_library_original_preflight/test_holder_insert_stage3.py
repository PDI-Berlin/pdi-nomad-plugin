"""Verify actual Lab Library writer payloads against live ORIGINAL NOMAD metainfo."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schema_compliance.original_contract import (
    ROOT,
    assert_original_archive_data,
    baseline,
)

APP = ROOT / 'src/pdi_nomad_plugin/mbe/lab_library/app.py'
JS = ROOT / 'src/pdi_nomad_plugin/mbe/lab_library/static/app.js'
HOLDER = 'nomad_material_processing.vapor_deposition.general.SubstrateHolder'
INSERT = 'nomad_material_processing.vapor_deposition.general.InsertReduction'


def _registrations():
    source = ast.parse(APP.read_text(encoding='utf-8-sig'))
    literal = next(
        n.value
        for n in source.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'LIBRARY_TYPES' for t in n.targets)
    )
    return ast.literal_eval(literal)


def _extract_js_function(name):
    text = JS.read_text(encoding='utf-8-sig')
    marker = 'function ' + name + '('
    start = text.index(marker)
    opening = text.index('{', start)
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == '{':
            depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise AssertionError(f'Unclosed JS function {name}')


def test_lab_library_registry_original_only_and_unsupported_features_removed():
    types = _registrations()
    assert set(types) == {'processing_recipe', 'holder', 'insert'}
    assert set(types['processing_recipe']['schemas']) == {
        'cleaning',
        'annealing',
        'etching',
    }
    assert types['holder']['schema'] == HOLDER
    assert types['insert']['schema'] == INSERT
    approved = baseline()

    def iterate(data):
        if isinstance(data, dict):
            for k, v in data.items():
                if k == 'schema':
                    assert v in approved, v
                elif k == 'usage_schemas':
                    assert all(x in approved for x in v)
                else:
                    iterate(v)

    iterate(types)


@pytest.mark.parametrize('kind', ['holder', 'insert'])
def test_holder_and_insert_editor_emit_only_original_fields(kind):
    import quickjs

    ctx = quickjs.Context()
    ctx.eval(
        """
        let currentType = 'holder';
        let editorItem = null;
        let editorMode = 'create';
        function currentSchema() {
            return currentType === 'holder' ? '%s' : '%s';
        }
        function generatedId() { return currentType === 'holder' ? 'H1_10' : 'XPS1'; }
        function assertUniqueGeneratedId(_) {}
        function selectedSquareSize(id, _) { return id === 'insertOuterSize' ? 10 : 5; }
        let fakeRows = [{
            querySelector: function(q) {
                const values = {
                    '.position-name': 'B', '.position-size': '10',
                    '.position-rho': '10', '.position-theta': '0'
                };
                return {value: values[q]};
            }
        }];
        let document = {querySelectorAll: function(_) { return fakeRows; }};
    """.replace("'%s' : '%s'", f"'{HOLDER}' : '{INSERT}'")
    )
    ctx.eval(_extract_js_function('editorArchiveData'))
    ctx.eval('currentType = ' + json.dumps(kind))
    archive = json.loads(ctx.eval('JSON.stringify(editorArchiveData())'))
    assert_original_archive_data(archive, HOLDER if kind == 'holder' else INSERT)
    assert 'tags' not in archive
    if kind == 'holder':
        p = archive['positions'][0]
        assert p['x_position'] == pytest.approx(0.01)
        assert p['y_position'] == pytest.approx(0)
        assert 'rho' not in p and 'theta' not in p
        # A slot's geometry was introduced in the unsupported custom PDI schema.
        assert 'slot_geometry' not in p
    else:
        # Until the ORIGINAL InsertReduction geometry m_def is verified, neither
        # section is fabricated by the editor. The writer is disabled.
        assert 'outer_geometry' not in archive
        assert 'inner_geometry' not in archive
