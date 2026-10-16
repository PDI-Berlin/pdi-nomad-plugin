"""Guard against reintroducing removed SampleCutRecipePDI and related PDI schemas."""
from pathlib import Path
import ast

SCHEMA_FILES = [
    Path('src/pdi_nomad_plugin/general/schema.py'),
    Path('src/pdi_nomad_plugin/mbe/instrument.py'),
    Path('src/pdi_nomad_plugin/mbe/processes.py'),
]
FORBIDDEN = {
    'AnnealingStepPDI', 'CleaningStepPDI', 'SampleCutRecipePDI',
    'RectangularGeometryPDI', 'MBENominalLayerPDI',
}


def test_removed_custom_pdi_schema_classes_stay_removed():
    for path in SCHEMA_FILES:
        root = ast.parse(path.read_text(encoding='utf-8-sig'))
        present = {node.name for node in root.body if isinstance(node, ast.ClassDef)}
        assert not FORBIDDEN.intersection(present), f'{path}: {sorted(FORBIDDEN & present)}'


def test_cut_recipe_not_exposed_in_lab_library():
    app = Path('src/pdi_nomad_plugin/mbe/lab_library/app.py').read_text(encoding='utf-8-sig')
    js = Path('src/pdi_nomad_plugin/mbe/lab_library/static/app.js').read_text(encoding='utf-8-sig')
    assert 'sample_cut_recipe' not in app
    assert 'sample_cut_recipe' not in js
    assert 'SampleCutRecipePDI' not in app
