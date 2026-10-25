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
    baseline,
)
from schema_compliance.test_app_schema_policy import verified_original_pdi_schema_paths

APP = ROOT / 'src/pdi_nomad_plugin/mbe/lab_library/app.py'
JS = ROOT / 'src/pdi_nomad_plugin/mbe/lab_library/static/app.js'
HOLDER = 'pdi_nomad_plugin.mbe.instrument.SubstrateHolderPDI'
INSERT = 'pdi_nomad_plugin.mbe.instrument.InsertReductionPDI'


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
    assert set(types) == {'processing_recipe', 'sample_cut', 'holder', 'insert'}
    assert set(types['processing_recipe']['schemas']) == {'cleaning', 'annealing'}
    assert types['holder']['schema'] == HOLDER
    assert types['insert']['schema'] == INSERT
    approved = set(baseline()) | verified_original_pdi_schema_paths()

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
        let document = {
            querySelectorAll: function(_) { return fakeRows; },
            getElementById: function(id) {
                if (id.endsWith('GeometryExtras')) {
                    return {
                        querySelector: function(_) { return {value: ''}; }
                    };
                }
                const values = {
                    holderThickness: '1',
                    insertOuterGeometryType: 'SquareCuboid',
                    insertInnerGeometryType: 'SquareCuboid'
                };
                return {value: values[id] || ''};
            }
        };
    """.replace("'%s' : '%s'", f"'{HOLDER}' : '{INSERT}'")
    )
    ctx.eval(_extract_js_function('readInsertGeometryUi'))
    ctx.eval(_extract_js_function('editorArchiveData'))
    ctx.eval('currentType = ' + json.dumps(kind))
    archive = json.loads(ctx.eval('JSON.stringify(editorArchiveData())'))
    from pdi_nomad_plugin.mbe.instrument import InsertReductionPDI, SubstrateHolderPDI

    cls = SubstrateHolderPDI if kind == 'holder' else InsertReductionPDI
    assert archive['m_def'] == cls.m_def.qualified_name()
    restored = cls.m_from_dict(archive)
    assert restored.m_to_dict(with_meta=True)['m_def'] == archive['m_def']
    assert 'tags' not in archive
    if kind == 'holder':
        p = archive['positions'][0]
        assert p['x_position'] == pytest.approx(0.01)
        assert p['y_position'] == pytest.approx(0)
        assert p['rho'] == pytest.approx(0.01)
        assert p['theta'] == pytest.approx(0)
        assert (
            p['slot_geometry']['m_def']
            == 'nomad_material_processing.general.SquareCuboid'
        )
        assert p['slot_geometry']['width'] == pytest.approx(0.01)
        assert p['slot_geometry']['length'] == pytest.approx(0.01)
        assert archive['thickness'] == pytest.approx(0.001)
    else:
        for side, width in [('outer_geometry', 0.01), ('inner_geometry', 0.005)]:
            geometry = archive[side]
            assert geometry['m_def'] == 'nomad_material_processing.general.SquareCuboid'
            assert geometry['width'] == pytest.approx(width)
            assert geometry['length'] == pytest.approx(width)
