"""Production-client original-schema allowlist, not a substitute for NOMAD runtime tests."""
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / 'src/pdi_nomad_plugin/mbe/processing/static/app.js'


def test_processing_client_rejects_unapproved_mdefs():
    js = SOURCE.read_text(encoding='utf-8')
    assert 'const ORIGINAL_PROCESS_TYPES = Object.freeze({' in js
    for cls in ('Cleaning', 'Annealing', 'Etching'):
        for suffix in ('', 'Recipe'):
            assert "nomad_material_processing.general." + cls + suffix in js
    assert "throw new Error('Non-original process or recipe m_def rejected: ' + key)" in js
    assert 'definition.schema !== approved.schema' in js
    assert 'definition.processSchema !== approved.processSchema' in js


def test_processing_client_never_reimplements_recipe_normalizer():
    js = SOURCE.read_text(encoding='utf-8')
    body = js.split('function processArchiveData(', 1)[1].split('function sampleCutArchiveData(', 1)[0]
    assert 'recipe: nomadArchiveReference(' in body
    assert 'data.steps =' not in body
    assert 'data.instruments =' not in body
