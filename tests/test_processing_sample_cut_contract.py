import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PY = ROOT / 'src/pdi_nomad_plugin/mbe/processing/app.py'
APP_JS = ROOT / 'src/pdi_nomad_plugin/mbe/processing/static/app.js'


class ProcessingSampleCutContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_py = APP_PY.read_text(encoding='utf-8')
        cls.app_js = APP_JS.read_text(encoding='utf-8')

    def test_sample_cut_is_registered_as_process_action(self):
        self.assertIn("'sample_cut': {", self.app_py)
        self.assertIn(
            "'schema': 'pdi_nomad_plugin.general.schema.SampleCutRecipePDI'",
            self.app_py,
        )
        self.assertIn(
            "'processSchema': 'pdi_nomad_plugin.general.schema.SampleCutPDI'",
            self.app_py,
        )
        self.assertIn("'kind': 'sample_cut'", self.app_py)

    def test_sample_cut_uses_fixed_recipe_parameters(self):
        self.assertIn(
            'number_of_samples: definition.recipe.numberOfSamples', self.app_js
        )
        self.assertIn('children_geometry: sampleCutChildGeometry(', self.app_js)
        self.assertIn(
            'substrate.geometry,\n            definition.recipe.childrenGeometry',
            self.app_js,
        )
        self.assertIn('geometry.height = parentGeometry.height', self.app_js)
        self.assertIn('trigger_cut_sample: true', self.app_js)
        self.assertNotIn('class="child-width', self.app_js)
        self.assertNotIn('class="child-length', self.app_js)

    def test_sample_cut_is_created_per_parent(self):
        self.assertIn(
            'for (let parentIndex = 0; parentIndex < selected.length; parentIndex++)',
            self.app_js,
        )
        self.assertIn('parent_sample: {', self.app_js)
        self.assertIn('sampleCutArchiveData', self.app_js)

    def test_sample_cut_history_uses_parent_reference(self):
        self.assertIn('treatment.data.parent_sample', self.app_js)


if __name__ == '__main__':
    unittest.main()
