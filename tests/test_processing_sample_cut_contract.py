"""Processing must only register original upstream process/schema definitions.

These tests replace historic SampleCutPDI tests; there is no verified
SampleCut upstream m_def in the three exported runtime modules. We must fail
closed instead of running a local PDI normalizer to create children.
"""
from pathlib import Path
from pdi_nomad_plugin.mbe.processing.app import PROCESS_TYPES
from nomad_material_processing import general as original

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'src/pdi_nomad_plugin/mbe/processing/app.py'
JS = ROOT / 'src/pdi_nomad_plugin/mbe/processing/static/app.js'
HTML = ROOT / 'src/pdi_nomad_plugin/mbe/processing/templates/index.html'
EXPECTED = {
    'cleaning': ('CleaningRecipe', 'Cleaning'),
    'annealing': ('AnnealingRecipe', 'Annealing'),
    'etching': ('EtchingRecipe', 'Etching'),
}


def test_only_original_processing_actions_are_registered():
    assert set(PROCESS_TYPES) == set(EXPECTED)
    for name, (recipe_name, process_name) in EXPECTED.items():
        pair = PROCESS_TYPES[name]
        for field, class_name in (('schema', recipe_name), ('processSchema', process_name)):
            cls = getattr(original, class_name)
            assert cls.m_def.qualified_name() == pair[field]
            assert cls.__module__ == 'nomad_material_processing.general'
            assert pair[field] == 'nomad_material_processing.general.' + class_name


def test_unverified_cut_and_coating_actions_are_not_exposed():
    assert 'sample_cut' not in PROCESS_TYPES
    assert 'back_side_coating' not in PROCESS_TYPES
    assert 'SampleCutPDI' not in APP.read_text(encoding='utf-8')
    assert 'BackSideCoatingPDI' not in APP.read_text(encoding='utf-8')


def test_processing_reads_original_intake_substrates_and_not_pdi_fields():
    js = JS.read_text(encoding='utf-8')
    assert "const schema = 'nomad_material_processing.general.CrystallineSubstrate';" in js
    assert 'originalSubstrateFields(data)' in js
    assert 'substance.molecular_formula' in js
    assert 'crystal.surface_orientation' in js
    assert 'pdi_nomad_plugin.mbe.materials.SubstrateMbe' not in js
    assert 'data.as_delivered' not in js
    assert 'data.processed' not in js
    assert 'data.grown' not in js
    assert 'treatmentReferencesSubstrate(treatment, substrate.entryId)' in js
    assert '<option value="grown">' not in HTML.read_text(encoding='utf-8')
    assert '<option value="unprocessed">Unprocessed</option>' in HTML.read_text(encoding='utf-8')


def test_process_data_includes_original_recipe_steps_and_references():
    js = JS.read_text(encoding='utf-8')
    assert "'data.steps', 'data.instruments'" in js
    assert 'data.steps = JSON.parse(JSON.stringify(definition.recipe.steps));' not in js
    assert 'data.instruments = JSON.parse(JSON.stringify(definition.recipe.instruments));' not in js
    assert 'Only a recipe reference belongs here.' in js
    assert 'm_def: schema.processSchema' in js
    assert 'recipe: nomadArchiveReference(' in js
    assert 'samples: selectedSubstrates.map(' in js


def test_original_upstream_process_fields_are_real():
    for _, (recipe_name, process_name) in EXPECTED.items():
        recipe = getattr(original, recipe_name).m_def
        process = getattr(original, process_name).m_def
        for field in ['name', 'datetime', 'recipe']:
            assert field in process.all_quantities
        for field in ['steps', 'samples', 'instruments']:
            assert field in process.all_sub_sections
            assert process.all_sub_sections[field].repeats is True
        assert 'steps' in recipe.all_sub_sections
    from nomad_material_processing.general import CleaningStep
    assert CleaningStep.m_def.all_sub_sections['cleaning_reagents'].repeats is False
