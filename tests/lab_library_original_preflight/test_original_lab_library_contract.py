"""Read-only Lab Library original schema preflight checks."""

import importlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CONTRACT = json.loads(
    (HERE / 'original_schema_contract.json').read_text(encoding='utf-8')
)


def test_original_registry_classes_at_runtime():
    for label, spec in CONTRACT['original_schema_contract'].items():
        path = spec['schema']
        module, name = path.rsplit('.', 1)
        cls = getattr(importlib.import_module(module), name)
        assert cls.m_def.qualified_name() == path, label
        assert set(cls.m_def.all_quantities) == set(spec['quantities']), label
        assert {
            key: item.sub_section.qualified_name()
            for key, item in cls.m_def.all_sub_sections.items()
        } == spec['subsections'], label
        if 'step_schema' in spec:
            sm, sn = spec['step_schema'].rsplit('.', 1)
            step = getattr(importlib.import_module(sm), sn)
            assert step.m_def.qualified_name() == spec['step_schema']
            assert set(step.m_def.all_quantities) == set(spec['step_quantities'])
            assert {
                key: v.sub_section.qualified_name()
                for key, v in step.m_def.all_sub_sections.items()
            } == spec['step_subsections']


def test_lab_library_only_exposes_verified_original_schemas():
    from pdi_nomad_plugin.mbe.lab_library.app import LIBRARY_TYPES

    allowed = {x['schema'] for x in CONTRACT['original_schema_contract'].values()}
    allowed.update(
        {
            'nomad_material_processing.general.Cleaning',
            'nomad_material_processing.general.Annealing',
            'nomad_material_processing.general.Etching',
            'nomad_material_processing.vapor_deposition.general.FilledSubstrateHolder',
        }
    )
    # Existing PDI classes; their pristine upstream source is verified separately.
    allowed.update(
        {
            'pdi_nomad_plugin.general.schema.SampleCutPDI',
            'pdi_nomad_plugin.mbe.instrument.SubstrateHolderPDI',
            'pdi_nomad_plugin.mbe.instrument.InsertReductionPDI',
        }
    )
    found = []
    for spec in LIBRARY_TYPES.values():
        blocks = spec.get('schemas', {'single': spec})
        for sub in blocks.values():
            found.extend([sub.get('schema'), *sub.get('usage_schemas', [])])
    bad = [x for x in found if x and x not in allowed]
    assert not bad, (
        'Lab Library still publishes unverified/custom schema paths: ' + ', '.join(bad)
    )


def test_no_unsupported_recipe_fields_are_serialized_by_gui():
    # A static smoke guard: full GUI and API payload tests remain required.
    source = (REPO / 'src/pdi_nomad_plugin/mbe/lab_library/static/app.js').read_text(
        encoding='utf-8'
    )
    # These legacy PDI-only quantity names must not appear in archive-write functions.
    start = source.index('function editorArchiveData()')
    end = source.index('async function ', start)
    serializer = source[start:end]
    banned = ('operation_temperature', 'ramp_rate', 'gas_flow_sccm', 'rf_power_w')
    for field in banned:
        assert field not in serializer, f'Legacy field in direct serializer: {field}'
