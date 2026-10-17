"""No PDI schema/normalizer; local draft fields checked against ORIGINAL NOMAD metadata.

The baseline is a selected copy of NOMAD 1.4.3/material-processing 1.0.6
runtime metainfo. This test must be run again against the actual installed
runtime before production use; it does not assert that MBE has an EntryData root.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'src/pdi_nomad_plugin/mbe/new_mbe_experiment'
JS = (APP / 'static/app.js').read_text(encoding='utf8')
DRAFT = (APP / 'static/mbe_drafts.js').read_text(encoding='utf8')
HTML = (APP / 'templates/index.html').read_text(encoding='utf8')
SCHEMAS = json.loads(
    (
        ROOT / 'tests/schema_compliance/baselines/original_mbe_draft_contract.json'
    ).read_text(encoding='utf8')
)


def test_upstream_original_fields_not_pdi_inventions():
    filled = SCHEMAS[
        'nomad_material_processing.vapor_deposition.general.FilledSubstrateHolder'
    ]
    position = SCHEMAS[
        'nomad_material_processing.vapor_deposition.general.FilledSubstrateHolderPosition'
    ]
    sample = SCHEMAS[
        'nomad.datamodel.metainfo.basesections.v1.CompositeSystemReference'
    ]
    insert = SCHEMAS[
        'nomad_material_processing.vapor_deposition.general.InsertReductionReference'
    ]
    assert 'substrate_holder' in filled['quantities']
    assert (
        filled['subsections']['positions']['schema'] == position['m_def_qualified_name']
    )
    assert (
        position['subsections']['substrate']['schema'] == sample['m_def_qualified_name']
    )
    assert (
        position['subsections']['insert_reduction']['schema']
        == insert['m_def_qualified_name']
    )
    assert position['quantities']['x_position']['unit'] == 'meter'
    assert position['quantities']['y_position']['unit'] == 'meter'
    assert 'tags' not in filled['quantities']
    assert 'position_usage' not in position['quantities']
    assert 'grown' not in filled['quantities']
    assert 'normalizer' in filled
    assert 'normalizer' in position
    assert not re.search(
        r'class\s+\w+\s*\([^)]*(?:EntryData|MolecularBeamEpitaxy)',
        (APP / 'app.py').read_text(),
    )


def test_no_live_upload_or_false_holder_status():
    assert 'current occupancy unverified' in JS
    assert 'no recorded loadout (occupancy unverified)' in JS
    assert 'counts.ungrown' not in JS
    assert 'counts.grown' not in JS
    assert 'data.tags' not in JS
    assert 'discarded_loadout' not in JS
    assert "method: 'PUT'" not in JS
    assert 'method: "PUT"' not in JS
    assert 'configureOriginalSchemaWriteSafety();' in JS
    assert 'button.disabled = true' in JS
    assert 'Export local MBE draft' in HTML
    assert 'NOMAD write disabled' in JS
    assert 'pdi_nomad_plugin.' not in DRAFT


def test_original_section_contracts_and_ui_sidecar_are_separate():
    for section in (
        'nomad_material_processing.vapor_deposition.pvd.mbe.MolecularBeamEpitaxy',
        'nomad_material_processing.vapor_deposition.general.FilledSubstrateHolder',
        'nomad_material_processing.vapor_deposition.general.FilledSubstrateHolderPosition',
        'nomad.datamodel.metainfo.basesections.v1.CompositeSystemReference',
        'nomad_material_processing.vapor_deposition.general.InsertReductionReference',
    ):
        assert section in DRAFT
    assert 'nomad_archive: false' in DRAFT
    assert 'local_planning_only' in DRAFT
    assert 'position_usage: localPositions' in DRAFT
    assert 'slot_geometry = geometry' in DRAFT
    assert 'original_sections: {mbe: mbe, filled_holder: filled}' in DRAFT
    assert (
        'nominal_thickness' not in DRAFT.split('const mbe = {')[1].split('return {')[0]
    )


def test_real_js_draft_and_reference_semantics():
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    test = ROOT / 'tests/schema_compliance/verify_new_mbe_draft.js'
    subprocess.run([node, str(test), str(APP / 'static/mbe_drafts.js')], check=True)


def test_live_original_mbe_metainfo_if_installed():
    """Real m_def assertions, not mock schemas. Runs in the user's NOMAD venv."""
    pytest.importorskip('nomad')
    from nomad.datamodel.data import EntryData
    from nomad.datamodel.metainfo.basesections import CompositeSystemReference
    from nomad_material_processing.vapor_deposition.general import (
        FilledSubstrateHolder,
        FilledSubstrateHolderPosition,
    )
    from nomad_material_processing.vapor_deposition.pvd.mbe import MolecularBeamEpitaxy

    assert not issubclass(MolecularBeamEpitaxy, EntryData)
    assert not issubclass(FilledSubstrateHolder, EntryData)
    assert MolecularBeamEpitaxy.m_def.qualified_name() == (
        'nomad_material_processing.vapor_deposition.pvd.mbe.MolecularBeamEpitaxy'
    )
    assert (
        MolecularBeamEpitaxy.m_def.all_sub_sections['samples'].sub_section.section_cls
        is CompositeSystemReference
    )
    assert (
        FilledSubstrateHolder.m_def.all_sub_sections[
            'positions'
        ].sub_section.section_cls
        is FilledSubstrateHolderPosition
    )
    assert (
        FilledSubstrateHolderPosition.m_def.all_quantities['x_position'].unit
        is not None
    )
    assert 'tags' not in FilledSubstrateHolder.m_def.all_quantities
    assert 'position_usage' not in FilledSubstrateHolderPosition.m_def.all_quantities


def test_real_js_holder_catalog_with_original_references():
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    subprocess.run(
        [
            node,
            str(ROOT / 'tests/schema_compliance/verify_new_mbe_holder_catalog.js'),
            str(APP / 'static/app.js'),
        ],
        check=True,
    )
