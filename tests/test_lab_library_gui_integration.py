import json
from pathlib import Path

import pytest
import quickjs


def extract_js_function(source, name):
    start = source.index('function ' + name + '(')
    opening = source.index('{', start)
    depth = 0
    for i in range(opening, len(source)):
        if source[i] == '{':
            depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
    raise AssertionError('Function incomplete: ' + name)


def test_annealing_gui_preserves_nomad_step_fields():
    from nomad_material_processing.general import AnnealingRecipe

    source = (
        Path(__file__).resolve().parents[1]
        / 'src/pdi_nomad_plugin/mbe/lab_library/static/app.js'
    ).read_text(encoding='utf-8')

    ctx = quickjs.Context()
    ctx.eval("""
        var values = {
            annealingRecipeName: "Test annealing",
            annealingDescription: "Original metadata",
            annealingInstrument: "Tube furnace"
        };
        var row = {
            __recipeSourceStep: {starting_temperature: 25, ending_temperature: 800,
                                 operation_temperature: 850, ramp_rate: 0.2,
                                 comment: "Previous comment"},
            querySelector: function(selector) {
                const fields = {
                    ".annealing-starting-temperature": "25",
                    ".annealing-ending-temperature": "850",
                    ".annealing-duration": "60",
                    ".annealing-comment": "Updated comment"
                };
                return {value: fields[selector] || ""};
            }
        };
        var document = {
            getElementById: function(id) {return {value: values[id] || ""};},
            querySelectorAll: function(selector) {
                return selector === ".annealing-step-row" ? [row] : [];
            }
        };
    """)
    for name in (
        'annealingInstrumentName',
        'originalAnnealingStep',
        'readAnnealingFields',
    ):
        ctx.eval(extract_js_function(source, name))
    data = json.loads(
        ctx.eval("""
        JSON.stringify((function() {const data = {}; readAnnealingFields(data); return data;})())
    """)
    )
    assert set(data) <= set(AnnealingRecipe.m_def.all_quantities) | set(
        AnnealingRecipe.m_def.all_sub_sections
    ) | {'m_def'}
    assert set(data['steps'][0]) <= set(
        AnnealingRecipe.m_def.all_sub_sections['steps'].sub_section.all_quantities
    )
    recipe = AnnealingRecipe.m_from_dict(data)
    restored = AnnealingRecipe.m_from_dict(recipe.m_to_dict(with_meta=True))
    step = restored.steps[0]
    assert step.starting_temperature.magnitude == pytest.approx(25)
    assert step.ending_temperature.magnitude == pytest.approx(850)
    assert step.duration.magnitude == pytest.approx(3600)
    assert step.comment == 'Updated comment'
    assert restored.duration.magnitude == pytest.approx(3600)


@pytest.mark.parametrize(
    'selected,has_reference,keep_reference',
    [
        ('Oven Chemlab', True, True),
        ('MBE 2nd transfer chamber', True, False),
        ('Oven Chemlab', False, False),
    ],
)
def test_annealing_instrument_references(selected, has_reference, keep_reference):
    from nomad_material_processing.general import AnnealingRecipe

    source = (
        Path(__file__).resolve().parents[1]
        / 'src/pdi_nomad_plugin/mbe/lab_library/static/app.js'
    ).read_text(encoding='utf-8')

    ref = '../uploads/test-upload/archive/test-entry#data'
    initial = {
        'location': 'Oven Chemlab',
        'instruments': [
            {'name': 'Oven Chemlab', **({'reference': ref} if has_reference else {})}
        ],
    }

    ctx = quickjs.Context()
    ctx.eval('var seed = ' + json.dumps(initial) + ';')
    ctx.eval('var chosen = ' + json.dumps(selected) + ';')
    ctx.eval("""
        var row = {
            __recipeSourceStep: {},
            querySelector: function(selector) {
                const fields = {
                    ".annealing-starting-temperature": "25",
                    ".annealing-ending-temperature": "850",
                    ".annealing-duration": "60",
                    ".annealing-comment": "Test"
                };
                return {value: fields[selector] || ""};
            }
        };
        var document = {
            getElementById: function(id) {
                const fields = {
                    annealingRecipeName: "Test annealing",
                    annealingDescription: "Test",
                    annealingInstrument: chosen,
                };
                return {value: fields[id] || ""};
            },
            querySelectorAll: function(selector) {
                return selector === ".annealing-step-row" ? [row] : [];
            }
        };
    """)

    for name in (
        'annealingInstrumentName',
        'originalAnnealingStep',
        'readAnnealingFields',
    ):
        ctx.eval(extract_js_function(source, name))

    data = json.loads(
        ctx.eval("""
        JSON.stringify((function() {
            readAnnealingFields(seed);
            return seed;
        })())
    """)
    )

    assert data['location'] == selected
    if keep_reference:
        assert data['instruments'] == initial['instruments']
    else:
        assert 'instruments' not in data

    recipe = AnnealingRecipe.m_from_dict(data)
    serialized = recipe.m_to_dict(with_meta=True)
    assert serialized['location'] == selected

    if keep_reference:
        assert serialized['instruments'][0]['reference'] == ref
    else:
        assert not serialized.get('instruments')


@pytest.mark.parametrize(
    'selected,has_reference,keep_reference',
    [
        ('Acetone', True, True),
        ('Ethanol', True, False),
        ('Acetone', False, False),
    ],
)
def test_cleaning_reagent_references(selected, has_reference, keep_reference):
    """Test the real GUI helper and *original* CleaningRecipe metainfo.

    The original CleaningStep.cleaning_reagents is a SINGLE
    CompositeSystemReference subsection (repeats=False). Missing references
    are left missing, not invented.
    """
    from nomad_material_processing.general import CleaningRecipe

    source = (
        Path(__file__).resolve().parents[1]
        / 'src/pdi_nomad_plugin/mbe/lab_library/static/app.js'
    ).read_text(encoding='utf-8')

    ref = '../uploads/test-upload/archive/test-entry#data'

    original_step = {
        'name': 'Acetone',
        'duration': 120,
        'temperature': 25,
    }
    if has_reference:
        original_step['cleaning_reagents'] = {
            'name': 'Acetone',
            'reference': ref,
        }

    ctx = quickjs.Context()
    ctx.eval('var originalStep = ' + json.dumps(original_step) + ';')
    ctx.eval('var chosen = ' + json.dumps(selected) + ';')

    ctx.eval("""
        var row = {
            __recipeSourceStep: originalStep,
            querySelector: function(selector) {
                const fields = {
                    ".cleaning-reagent": chosen,
                    ".cleaning-reagent-custom": "",
                    ".cleaning-duration": "2",
                    ".cleaning-temperature": "25",
                    ".cleaning-agitation": "__none__",
                    ".cleaning-comment": "Test"
                };
                return {value: fields[selector] || ""};
            }
        };

        var document = {
            getElementById: function(id) {
                const fields = {
                    chemicalTreatmentName: "Cleaning test",
                    chemicalTreatmentType: "Ultrasonic cleaning",
                    chemicalTreatmentDescription: "Reference test"
                };
                return {value: fields[id] || ""};
            },
            querySelectorAll: function(selector) {
                return selector === ".cleaning-step-row" ? [row] : [];
            }
        };
    """)

    # readCleaningFields calls cleaningReagentName at runtime. Load both
    # functions into isolated QuickJS, just as the browser loads both.
    ctx.eval(extract_js_function(source, 'cleaningReagentName'))
    ctx.eval(extract_js_function(source, 'readCleaningFields'))

    data = json.loads(
        ctx.eval("""
        JSON.stringify((function() {
            const data = {};
            readCleaningFields(data);
            return data;
        })())
    """)
    )

    assert data['steps'][0]['name'] == selected
    assert data['steps'][0]['duration'] == 120

    if keep_reference:
        assert data['steps'][0]['cleaning_reagents'] == {
            'name': 'Acetone',
            'reference': ref,
        }
    else:
        assert 'cleaning_reagents' not in data['steps'][0]

    original_path = 'nomad_material_processing.general.CleaningRecipe'
    assert CleaningRecipe.m_def.qualified_name() == original_path
    cleaning_step_def = CleaningRecipe.m_def.all_sub_sections['steps'].sub_section
    assert CleaningRecipe.m_def.all_sub_sections['steps'].repeats is True
    assert cleaning_step_def.all_sub_sections['cleaning_reagents'].repeats is False
    assert (
        cleaning_step_def.all_sub_sections[
            'cleaning_reagents'
        ].sub_section.qualified_name()
        == 'nomad.datamodel.metainfo.basesections.v1.CompositeSystemReference'
    )
    allowed = set(CleaningRecipe.m_def.all_quantities) | set(
        CleaningRecipe.m_def.all_sub_sections
    )
    assert set(data) <= allowed
    allowed_step = set(
        CleaningRecipe.m_def.all_sub_sections['steps'].sub_section.all_quantities
    ) | set(CleaningRecipe.m_def.all_sub_sections['steps'].sub_section.all_sub_sections)
    assert set(data['steps'][0]) <= allowed_step

    # Validate the archive with NOMAD's own parser and serializer.
    recipe = CleaningRecipe.m_from_dict({'m_def': original_path, **data})
    serialized = recipe.m_to_dict(with_meta=True)
    assert serialized['m_def'] == original_path
    assert serialized['steps'][0]['name'] == selected

    if keep_reference:
        assert serialized['steps'][0]['cleaning_reagents']['reference'] == ref
    else:
        assert not serialized['steps'][0].get('cleaning_reagents')

    restored = CleaningRecipe.m_from_dict(serialized)
    assert restored.m_to_dict(with_meta=True) == serialized


def test_etching_gui_nomad_roundtrip():
    from nomad_material_processing.general import EtchingRecipe

    source = (
        Path(__file__).resolve().parents[1]
        / 'src/pdi_nomad_plugin/mbe/lab_library/static/app.js'
    ).read_text(encoding='utf-8')

    initial = {
        'name': 'Old recipe',
        'method': 'Wet etching',
        'recipe': '../uploads/example/archive/recipe#data',
        'samples': [{'reference': '../uploads/example/archive/sample#data'}],
        'steps': [
            {
                'name': 'HF etching',
                'duration': 30,
                'temperature': 22,
                'comment': 'Original step metadata',
                'etching_reagents': [{'name': 'HF solution'}],
            }
        ],
    }

    ctx = quickjs.Context()
    ctx.eval('var seed = ' + json.dumps(initial) + ';')

    ctx.eval("""
        var document = {
            getElementById: function(id) {
                const fields = {
                    etchingRecipeName: "HF etching recipe",
                    etchingDescription: "Reusable recipe"
                };
                return {value: fields[id] || ""};
            },
            querySelectorAll: function(selector) {
                if (selector === ".dynamic-field") {
                    return [{
                        dataset: {field: "method", kind: "text"},
                        querySelector: function() {
                            return {value: "Wet etching"};
                        }
                    }];
                }

                if (selector === ".schema-subsection") {
                    return [
                        {
                            dataset: {section: "steps", repeats: "true"},
                            querySelector: function() {
                                return {value: JSON.stringify(seed.steps)};
                            }
                        },
                        {
                            dataset: {section: "samples", repeats: "true"},
                            querySelector: function() {
                                return {value: JSON.stringify(seed.samples)};
                            }
                        }
                    ];
                }

                return [];
            }
        };
    """)

    for name in ('readDynamicFields', 'readEtchingFields'):
        ctx.eval(extract_js_function(source, name))

    data = json.loads(
        ctx.eval("""
        JSON.stringify((function() {
            readEtchingFields(seed);
            return seed;
        })())
    """)
    )

    assert data['name'] == 'HF etching recipe'
    assert data['method'] == 'Wet etching'
    assert 'samples' not in data
    assert 'recipe' not in data

    recipe = EtchingRecipe.m_from_dict(data)
    restored = EtchingRecipe.m_from_dict(recipe.m_to_dict(with_meta=True))

    assert len(restored.steps) == 1
    step = restored.steps[0]

    assert step.duration.magnitude == pytest.approx(30)
    assert step.temperature.magnitude == pytest.approx(22)
    assert step.comment == 'Original step metadata'
    assert step.etching_reagents[0].name == 'HF solution'

    serialized = restored.m_to_dict(with_meta=True)
    assert not serialized.get('samples')
    assert not serialized.get('recipe')


def test_removed_cut_recipe_geometry_editor_stays_removed():
    source = (
        Path(__file__).resolve().parents[1]
        / 'src/pdi_nomad_plugin/mbe/lab_library/static/app.js'
    ).read_text(encoding='utf-8')
    # These serializers belonged to the deleted custom cut-recipe editor.
    for name in ('cutGeometryField', 'cutGeometryPositiveMm', 'readCutRecipeGeometry'):
        assert 'function ' + name + '(' not in source
    assert 'SampleCutRecipePDI' not in source


def test_removed_cut_recipe_shape_fields_stay_removed():
    source = (
        Path(__file__).resolve().parents[1]
        / 'src/pdi_nomad_plugin/mbe/lab_library/static/app.js'
    ).read_text(encoding='utf-8')
    for old_field in (
        'cutParentShape',
        'cutChildShape',
        'cutParentWidth',
        'cutChildWidth',
    ):
        assert old_field not in source
    assert 'RectangularGeometryPDI' not in source
    assert 'SampleCutRecipePDI' not in source


def test_unverified_back_coating_and_cut_recipe_not_exposed():
    from pdi_nomad_plugin.mbe.lab_library.app import LIBRARY_TYPES

    assert 'sample_cut_recipe' not in LIBRARY_TYPES
    assert 'back_side_coating' not in LIBRARY_TYPES['processing_recipe']['schemas']
