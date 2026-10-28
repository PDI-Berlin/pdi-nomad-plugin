import ast
import unittest
from pathlib import Path

SCHEMA = Path('src/pdi_nomad_plugin/general/schema.py')


class SampleCutRecipeSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = SCHEMA.read_text(encoding='utf-8')
        cls.tree = ast.parse(source)
        cls.recipe = next(
            (
                node
                for node in cls.tree.body
                if isinstance(node, ast.ClassDef) and node.name == 'SampleCutRecipePDI'
            ),
            None,
        )

    def test_recipe_class_exists(self):
        self.assertIsNotNone(self.recipe)

    def test_recipe_inherits_recipe_and_entry_data(self):
        bases = {base.id for base in self.recipe.bases if isinstance(base, ast.Name)}
        self.assertIn('Recipe', bases)
        self.assertIn('EntryData', bases)

    def test_recipe_contains_expected_fields_only(self):
        assigned = {
            target.id
            for node in self.recipe.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }

        self.assertIn('m_def', assigned)
        self.assertIn('lab_id', assigned)
        self.assertIn('input_geometry', assigned)
        self.assertIn('number_of_samples', assigned)
        self.assertIn('children_geometry', assigned)

        self.assertNotIn('trigger_cut_sample', assigned)
        self.assertNotIn('parent_sample', assigned)
        self.assertNotIn('children_samples', assigned)


if __name__ == '__main__':
    unittest.main()
