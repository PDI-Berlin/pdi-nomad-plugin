"""Stage 7C: no generic PVD process assumptions in the New MBE app.

The original NOMAD holder m_def paths are intentional and must not be
renamed. This test checks only user-facing text, comments and serializers.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'src/pdi_nomad_plugin/mbe/new_mbe_experiment/static/app.js'

ORIGINAL_HOLDER_MDEFS = (
    'nomad_material_processing.vapor_deposition.general.SubstrateHolder',
    'nomad_material_processing.vapor_deposition.general.FilledSubstrateHolder',
    'nomad_material_processing.vapor_deposition.general.InsertReduction',
)


def test_no_generic_pvd_workflow_language_or_serializers():
    js = APP.read_text(encoding='utf-8')
    assert not re.search(
        r'VaporDeposition|PhysicalVaporDeposition|PVDStep|PVDSampleParameters|\bPVD\b',
        js,
    )
    assert 'original MolecularBeamEpitaxy' in js
    # Unsupported insert geometry was deliberately removed from the UI.
    assert (
        'nomad_material_processing.vapor_deposition.general.InsertReduction' not in js
    )
    assert 'RectangularGeometryPDI' not in js
    assert 'MBENominalLayerPDI' not in js


def test_mbe_writes_remain_fail_closed():
    js = APP.read_text(encoding='utf-8')
    for name in (
        'uploadArchiveData',
        'uploadArchiveDataV2',
        'experimentArchiveData',
        'filledHolderArchiveData',
        'setPhysicalHolderWorkflowStatus',
    ):
        match = re.search(r'(?:async\s+)?function\s+' + name + r'\s*\([^)]*\)\s*\{', js)
        assert match, name
        assert js[match.end() :].lstrip().startswith('throw new Error('), name
