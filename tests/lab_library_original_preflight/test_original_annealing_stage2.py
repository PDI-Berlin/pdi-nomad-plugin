"""Stage 2: Lab Library Annealing must use unmodified NOMAD metainfo classes."""

import json
from pathlib import Path

import pytest


def test_annealing_recipe_registration_matches_runtime_original():
    from nomad_material_processing.general import (
        Annealing,
        AnnealingRecipe,
        AnnealingStep,
    )

    from pdi_nomad_plugin.mbe.lab_library.app import LIBRARY_TYPES

    spec = LIBRARY_TYPES['processing_recipe']['schemas']['annealing']
    assert spec['schema'] == AnnealingRecipe.m_def.qualified_name()
    assert spec['usage_schemas'] == [Annealing.m_def.qualified_name()]
    assert AnnealingRecipe.__module__ == 'nomad_material_processing.general'
    assert AnnealingStep.__module__ == 'nomad_material_processing.general'
    assert 'ramp_rate' not in AnnealingStep.m_def.all_quantities
    assert 'operation_temperature' not in AnnealingStep.m_def.all_quantities


def test_original_annealing_roundtrip_and_original_normalizer():
    from nomad.datamodel.metainfo.basesections.v1 import Process
    from nomad_material_processing.general import AnnealingRecipe, AnnealingStep

    data = {
        'm_def': AnnealingRecipe.m_def.qualified_name(),
        'name': 'STO anneal',
        'location': 'Tube furnace',
        'duration': 3600.0,
        'steps': [
            {
                'name': 'Ramp',
                'duration': 3600.0,
                'starting_temperature': 25.0,
                'ending_temperature': 850.0,
            }
        ],
    }
    recipe = AnnealingRecipe.m_from_dict(data)
    serialized = recipe.m_to_dict(with_meta=True)
    restored = AnnealingRecipe.m_from_dict(serialized)
    assert restored.m_to_dict(with_meta=True) == serialized
    assert restored.steps[0].ending_temperature.magnitude == pytest.approx(850)
    assert 'ramp_rate' not in serialized['steps'][0]
    assert 'operation_temperature' not in serialized['steps'][0]
    # The original class and its normalizer are imported, not recreated.
    assert (
        AnnealingRecipe.m_def.all_sub_sections['steps'].sub_section.qualified_name()
        == AnnealingStep.m_def.qualified_name()
    )
    assert AnnealingRecipe.normalize is Process.normalize
    assert AnnealingStep.normalize.__module__ == 'nomad.datamodel.data'


def _extract_function(source, name):
    # The JS functions in this test have no brace literals inside strings.
    start = source.index('function ' + name + '(')
    opening = source.index('{', start)
    depth = 0
    for idx in range(opening, len(source)):
        if source[idx] == '{':
            depth += 1
        elif source[idx] == '}':
            depth -= 1
            if not depth:
                return source[start : idx + 1]
    raise AssertionError('Unclosed function: ' + name)


def test_gui_annealing_sends_only_original_mdef_fields():
    quickjs = pytest.importorskip('quickjs')
    from nomad_material_processing.general import AnnealingRecipe, AnnealingStep

    root = Path(__file__).resolve().parents[2]
    source = (root / 'src/pdi_nomad_plugin/mbe/lab_library/static/app.js').read_text(
        encoding='utf8'
    )
    ctx = quickjs.Context()
    ctx.eval("""
       var document={
         getElementById:function(id){return {value:({annealingRecipeName:'STO',
           annealingDescription:'Original only',annealingInstrument:'Tube furnace',
           annealingAtmosphere:'O2',annealingAtmosphereCustom:'',
           annealingGasFlow:''})[id]||''}},
         querySelectorAll:function(){return [{
           __recipeSourceStep:{operation_temperature:950,ramp_rate:1,starting_temperature:25},
           querySelector:function(sel){return {value:({
             '.annealing-starting-temperature':'25',
             '.annealing-ending-temperature':'950',
             '.annealing-duration':'30',
             '.annealing-step-type':'Heating',
             '.annealing-specification':'duration',
             '.annealing-step-atmosphere':'',
             '.annealing-step-atmosphere-custom':'',
             '.annealing-step-gas-flow':'',
             '.annealing-comment':'Test'})[sel]||''}}
         }]}
       };
    """)
    for fn in (
        'annealingInstrumentName',
        'originalAnnealingStep',
        'annealingAtmosphereNote',
        'appendAnnealingNote',
        'annealingStepPayload',
        'readAnnealingFields',
    ):
        ctx.eval(_extract_function(source, fn))
    payload = json.loads(
        ctx.eval(
            'JSON.stringify((function(){var d={atmosphere:"O2",gas_flow_sccm:20,rf_power_w:42}; readAnnealingFields(d); return d;})())'
        )
    )
    allowed = set(AnnealingRecipe.m_def.all_quantities) | set(
        AnnealingRecipe.m_def.all_sub_sections
    )
    assert set(payload) <= allowed
    assert set(payload['steps'][0]) <= set(AnnealingStep.m_def.all_quantities)
    assert payload['steps'][0]['starting_temperature'] == 25
    assert payload['steps'][0]['ending_temperature'] == 950
    assert payload['duration'] == 1800
    assert 'atmosphere' not in payload
    assert 'Atmosphere: O2' in payload['description']
    recipe = AnnealingRecipe.m_from_dict(payload)
    assert recipe.steps[0].ending_temperature.magnitude == pytest.approx(950)


def test_annealing_editor_contains_no_non_original_inputs():
    root = Path(__file__).resolve().parents[2]
    source = (root / 'src/pdi_nomad_plugin/mbe/lab_library/static/app.js').read_text(
        encoding='utf8'
    )
    render = source.split('function renderAnnealingFields(', 1)[1].split(
        '\nfunction ', 1
    )[0]
    assert 'id="annealingAtmosphere"' in render
    assert 'id="annealingGasFlow"' in render
    for obsolete in (
        'annealingRfPower',
        'annealing-ramp-rate',
        'annealing-operation-temperature',
    ):
        assert obsolete not in render
    step_html = source.split('function annealingStepHtml(', 1)[1].split(
        '\nfunction ', 1
    )[0]
    assert 'annealing-starting-temperature' in step_html
    assert 'annealing-ending-temperature' in step_html
