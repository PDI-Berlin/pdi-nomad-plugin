import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'src' / 'pdi_nomad_plugin' / 'mbe' / 'lab_library'


class LabLibraryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_py = (APP / 'app.py').read_text(encoding='utf-8')
        cls.app_js = (APP / 'static' / 'app.js').read_text(encoding='utf-8')
        cls.index_html = (APP / 'templates' / 'index.html').read_text(encoding='utf-8')
        cls.pyproject = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')

    def test_entry_point_is_registered(self):
        self.assertIn(
            'lab_library = "pdi_nomad_plugin.mbe.lab_library:lab_library"',
            self.pyproject,
        )

    def test_processing_and_physical_library_types_exist(self):
        for label in (
            'Processing Recipes',
            'Sample Cut Recipes',
            'Holders',
            'Inserts',
        ):
            self.assertIn(label, self.app_py)

    def test_usage_schemas_are_declared_for_referenced_items(self):
        for schema in (
            'CleaningPDI',
            'AnnealingPDI',
            'BackSideCoatingPDI',
            'FilledSubstrateHolderPDI',
        ):
            self.assertIn(schema, self.app_py)

    def test_queries_request_nomad_reference_metadata(self):
        self.assertIn("'/entries/archive/query'", self.app_js)
        self.assertIn("owner: 'visible'", self.app_js)
        self.assertIn("entry_references: '*'", self.app_js)
        self.assertIn('target_entry_id === targetEntryId', self.app_js)

    def test_referenced_items_are_not_editable(self):
        self.assertIn('usage.locked ||', self.app_js)
        self.assertIn(
            'This item is locked because it is already referenced by NOMAD entries.',
            self.app_js,
        )
        self.assertIn(
            'This item is now referenced by NOMAD and is locked.',
            self.app_js,
        )

    def test_duplicate_never_overwrites_existing_item(self):
        self.assertIn(
            "params.append('overwrite_if_exists', overwrite ? 'true' : 'false')",
            self.app_js,
        )
        self.assertIn('assertUniqueGeneratedId(data.lab_id)', self.app_js)
        self.assertIn('ID ' + "' + id + '" + ' already exists.', self.app_js)

    def test_duplicate_uses_new_entity_language(self):
        self.assertIn("duplicate.textContent = 'Duplicate'", self.app_js)
        self.assertIn("'Save new ' + entityNoun()", self.app_js)
        self.assertNotIn('Save duplicate', self.app_js)

    def test_edit_rechecks_references_before_write(self):
        self.assertIn(
            'usageCatalogs[schema] = await queryEntriesBySchema(schema)',
            self.app_js,
        )
        self.assertIn('No changes were written.', self.app_js)

    def test_create_action_is_last_list_row(self):
        self.assertNotIn('+ Create New Item', self.index_html)
        self.assertIn('create-row', self.app_js)
        self.assertIn('+ Create new holder', self.app_js)

    def test_holder_id_and_square_geometry_are_structured(self):
        self.assertIn("return material + String(number) + '_'", self.app_js)
        self.assertIn('<option value="H">Haynes</option>', self.index_html)
        self.assertIn('<option value="M">Molybdenum</option>', self.index_html)
        compact_js = ''.join(self.app_js.split())
        self.assertIn(
            'slot_geometry:{width:size/1000,length:size/1000}',
            compact_js,
        )
        self.assertIn('rho:rho/1000', compact_js)
        self.assertIn('theta:theta', compact_js)

    def test_writes_wait_for_processing(self):
        self.assertIn(
            "params.append('wait_for_processing', 'true')",
            self.app_js,
        )


if __name__ == '__main__':
    unittest.main()
