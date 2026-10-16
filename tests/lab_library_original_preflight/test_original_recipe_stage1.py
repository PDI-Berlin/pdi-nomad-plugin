'''Original NOMAD recipe storage contracts, stage 1: Cleaning + Etching.

Do not replace or reimplement metainfo schema or normalizers here.
'''
import importlib
import json
from pathlib import Path

import pytest

MODULE = 'nomad_material_processing.general'
REGISTERED = {
    'cleaning': ('CleaningRecipe', 'Cleaning'),
    'etching': ('EtchingRecipe', 'Etching'),
}

def test_registered_recipe_types_are_exact_original_classes():
    from pdi_nomad_plugin.mbe.lab_library.app import LIBRARY_TYPES
    upstream = importlib.import_module(MODULE)
    for name, (recipe_cls, execution_cls) in REGISTERED.items():
        spec = LIBRARY_TYPES['processing_recipe']['schemas'][name]
        assert spec['schema'] == f'{MODULE}.{recipe_cls}'
        assert spec['usage_schemas'] == [f'{MODULE}.{execution_cls}']
        schema = getattr(upstream, recipe_cls)
        assert schema.__module__ == MODULE
        assert schema.m_def.qualified_name() == spec['schema']
        assert getattr(upstream, execution_cls).m_def.qualified_name() == spec['usage_schemas'][0]

@pytest.mark.parametrize('kind,step', [
    ('cleaning', {'name':'Acetone', 'duration':120.0, 'temperature':25.0, 'comment':'Ultrasonic'}),
    ('etching', {'name':'HF', 'duration':30.0, 'temperature':20.0, 'comment':'Dilute HF'}),
])
def test_original_nomad_archive_roundtrip(kind, step):
    from pdi_nomad_plugin.mbe.lab_library.app import LIBRARY_TYPES
    schema_path = LIBRARY_TYPES['processing_recipe']['schemas'][kind]['schema']
    module, clsname = schema_path.rsplit('.', 1)
    cls = getattr(importlib.import_module(module), clsname)
    data = {'m_def':schema_path, 'name':'Original recipe test', 'method':'Chemical treatment', 'steps':[step]}
    restored = cls.m_from_dict(data)
    encoded = restored.m_to_dict(with_meta=True)
    assert encoded['m_def'] == schema_path
    assert len(encoded['steps']) == 1
    assert encoded['steps'][0]['name'] == step['name']
    assert not encoded['steps'][0].get('cleaning_reagents')
    assert cls.m_from_dict(encoded).m_to_dict(with_meta=True) == encoded

def _extract_js_function(source, name):
    start=source.index('function '+name+'(')
    opening=source.index('{',start)
    depth=0
    for i in range(opening,len(source)):
        if source[i]=='{':depth+=1
        if source[i]=='}':
            depth-=1
            if depth==0:return source[start:i+1]
    raise AssertionError(name)

@pytest.mark.parametrize('selected,keep_reference', [
    ('Acetone',True),('Ethanol',False)
])
def test_cleaning_reference_object_and_no_fictitious_reagent(selected, keep_reference):
    quickjs=pytest.importorskip('quickjs')
    root=Path(__file__).resolve().parents[2]
    source=(root/'src/pdi_nomad_plugin/mbe/lab_library/static/app.js').read_text(encoding='utf-8')
    ctx=quickjs.Context()
    ref='../uploads/test-upload/archive/test-entry#data'
    ctx.eval('var originalStep = '+json.dumps({
       'name':'Acetone','duration':120,'temperature':25,
       'cleaning_reagents':{'name':'Acetone','reference':ref}
    })+';')
    ctx.eval('var chosen = '+json.dumps(selected)+';')
    ctx.eval('''
       var row={__recipeSourceStep:originalStep,
        querySelector:function(selector){
           const fields={'.cleaning-reagent':chosen,'.cleaning-reagent-custom':'',
            '.cleaning-duration':'2','.cleaning-temperature':'25',
            '.cleaning-agitation':'__none__','.cleaning-comment':'Test'};
           return {value:fields[selector]||''};
        }};
       var document={getElementById:function(id){
         const fields={chemicalTreatmentName:'Test cleaning',chemicalTreatmentType:'Solvent cleaning',chemicalTreatmentDescription:'Test'};
         return {value:fields[id]||''};
        },querySelectorAll:function(sel){return sel==='.cleaning-step-row'?[row]:[];}};
    ''')
    ctx.eval(_extract_js_function(source,'cleaningReagentName'))
    ctx.eval(_extract_js_function(source,'readCleaningFields'))
    data=json.loads(ctx.eval('JSON.stringify((function(){var result={};readCleaningFields(result);return result;})())'))
    step=data['steps'][0]
    assert step['name']==selected
    if keep_reference:
        assert step['cleaning_reagents']=={'name':'Acetone','reference':ref}
    else:
        assert 'cleaning_reagents' not in step


def test_cleaning_reagents_exact_original_cardinality():
    from nomad_material_processing.general import CleaningRecipe

    recipe = CleaningRecipe.m_def
    steps = recipe.all_sub_sections['steps']
    assert steps.repeats is True
    reagent = steps.sub_section.all_sub_sections['cleaning_reagents']
    assert reagent.repeats is False
    assert reagent.sub_section.qualified_name() == (
        'nomad.datamodel.metainfo.basesections.v1.CompositeSystemReference'
    )

    archive = CleaningRecipe.m_from_dict({
        'name': 'Test original cleaning reagent',
        'steps': [{
            'name': 'Acetone',
            'duration': 120,
            'cleaning_reagents': {
                'name': 'Acetone',
                'reference': '../uploads/test-upload/archive/test-entry#data',
            },
        }],
    })
    data = archive.m_to_dict(with_meta=True)
    assert isinstance(data['steps'], list)
    assert isinstance(data['steps'][0]['cleaning_reagents'], dict)
    assert data['steps'][0]['cleaning_reagents']['reference'].endswith(
        '#data'
    )
