"""Enforce ORIGINAL PDI source code for metainfo and normalizers.

This complements runtime m_def checks against NOMAD Core/material_processing:
changing an old class without introducing a new class is not allowed either.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL_MODULES = (
    'src/pdi_nomad_plugin/general/schema.py',
    'src/pdi_nomad_plugin/mbe/materials.py',
    'src/pdi_nomad_plugin/mbe/instrument.py',
    'src/pdi_nomad_plugin/mbe/processes.py',
)


@pytest.mark.parametrize('relative_path', ORIGINAL_MODULES)
def test_pdi_original_schema_and_normalizer_source_is_unchanged(relative_path):
    source = (
        subprocess.check_output(
            ['git', 'show', 'upstream/main:' + relative_path],
            cwd=ROOT,
        )
        .decode('utf-8-sig')
        .replace('\r\n', '\n')
    )
    current = (
        (ROOT / relative_path).read_text(encoding='utf-8-sig').replace('\r\n', '\n')
    )
    assert current == source, f'{relative_path} differs from original upstream/main'


def test_no_unverified_custom_app_contracts():
    src = ROOT / 'src/pdi_nomad_plugin/mbe'
    js = [
        src / 'processing/static/app.js',
        src / 'lab_library/static/app.js',
        src / 'new_mbe_experiment/static/app.js',
    ]
    for path in js:
        text = path.read_text(encoding='utf-8-sig')
        assert 'SampleCutRecipePDI' not in text, str(path)
        assert 'MBENominalLayerPDI' not in text, str(path)
        assert 'RectangularGeometryPDI' not in text, str(path)
    processing = js[0].read_text(encoding='utf-8-sig')
    library = js[1].read_text(encoding='utf-8-sig')
    assert (
        "const CUT_SCHEMA = 'pdi_nomad_plugin.general.schema.SampleCutPDI';"
        in processing
    )
    assert 'sample_cut_recipe' not in library
    assert 'back_side_coating' not in library
