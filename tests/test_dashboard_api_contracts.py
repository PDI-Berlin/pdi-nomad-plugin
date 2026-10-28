import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

NEW_MBE_PY = ROOT / 'src/pdi_nomad_plugin/mbe/new_mbe_experiment/app.py'
NEW_MBE_JS = ROOT / 'src/pdi_nomad_plugin/mbe/new_mbe_experiment/static/app.js'
PROCESSING_PY = ROOT / 'src/pdi_nomad_plugin/mbe/processing/app.py'
PROCESSING_JS = ROOT / 'src/pdi_nomad_plugin/mbe/processing/static/app.js'
INTAKE_PY = ROOT / 'src/pdi_nomad_plugin/mbe/substrate_intake/app.py'


def text(path):
    return path.read_text(encoding='utf-8-sig')


def js_function(source, name):
    match = re.search(
        rf'(?:async\s+)?function\s+{re.escape(name)}\s*\([^)]*\)\s*\{{',
        source,
    )
    if not match:
        raise AssertionError(f'Function {name!r} not found')

    start = match.start()
    brace = source.find('{', match.start())
    depth = 0
    in_single = False
    in_double = False
    in_template = False
    escaped = False

    for index in range(brace, len(source)):
        char = source[index]

        if escaped:
            escaped = False
            continue

        if char == '\\':
            escaped = True
            continue

        if not in_double and not in_template and char == "'":
            in_single = not in_single
            continue

        if not in_single and not in_template and char == '"':
            in_double = not in_double
            continue

        if not in_single and not in_double and char == '`':
            in_template = not in_template
            continue

        if in_single or in_double or in_template:
            continue

        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return source[start : index + 1]

    raise AssertionError(f'Function {name!r} has no matching closing brace')


class DashboardApiContractTests(unittest.TestCase):
    def test_backend_injects_nomad_api_base(self):
        for path in (NEW_MBE_PY, PROCESSING_PY, INTAKE_PY):
            source = text(path)
            with self.subTest(path=path):
                self.assertIn('config.services.api_base_path', source)
                self.assertIn('window.NOMAD_API_BASE', source)

    def test_frontends_prefer_injected_api_base(self):
        for path in (NEW_MBE_JS, PROCESSING_JS):
            function = js_function(text(path), 'nomadApiBase')
            with self.subTest(path=path):
                self.assertIn('window.NOMAD_API_BASE', function)

        self.assertIn('window.NOMAD_API_BASE', text(INTAKE_PY))

    def test_shared_queries_use_archive_endpoint(self):
        mbe_query = js_function(
            text(NEW_MBE_JS),
            'queryEntriesBySchema',
        )
        processing_query = js_function(
            text(PROCESSING_JS),
            'queryEntries',
        )

        self.assertIn('/entries/archive/query', mbe_query)
        self.assertNotIn('/entries/query', mbe_query)

        self.assertIn('/entries/archive/query', processing_query)
        self.assertNotIn('/entries/query', processing_query)

    def test_relevant_queries_use_visible_owner(self):
        mbe = text(NEW_MBE_JS)
        processing = text(PROCESSING_JS)

        functions = [
            js_function(mbe, 'queryEntriesBySchema'),
            js_function(mbe, 'queryExperimentHolderReferences'),
            js_function(mbe, 'loadTreatmentRecipes'),
            js_function(processing, 'queryEntries'),
        ]

        for function in functions:
            with self.subTest(function=function.splitlines()[0]):
                self.assertRegex(
                    function,
                    r"owner\s*:\s*['\"]visible['\"]",
                )

    def test_substrates_and_history_use_shared_helper(self):
        mbe = text(NEW_MBE_JS)

        for name in (
            'loadSubstrates',
            'loadTreatmentHistoryEntries',
        ):
            function = js_function(mbe, name)

            with self.subTest(function=name):
                self.assertIn(
                    'queryEntriesBySchema',
                    function,
                )

                # Guard against a real direct request to the wrong endpoint.
                # Mentions inside explanatory comments are allowed.
                self.assertNotRegex(
                    function,
                    r'fetch\s*\(\s*[^\n]*?/entries/query',
                )

    def test_dashboard_fixtures_exist(self):
        fixture_dir = ROOT / 'tests/fixtures/dashboard'

        expected = {
            'test_cleaning_recipe.archive.yaml': 'CleaningRecipePDI',
            'test_etching_recipe.archive.yaml': 'EtchingRecipePDI',
            'test_holder.archive.yaml': 'SubstrateHolderPDI',
        }

        for filename, schema in expected.items():
            path = fixture_dir / filename

            with self.subTest(path=path):
                self.assertTrue(
                    path.exists(),
                    f'Missing fixture: {path}',
                )
                self.assertIn(
                    schema,
                    text(path),
                )

    def test_growth_preserves_processed_state(self):
        processes = text(ROOT / 'src/pdi_nomad_plugin/mbe/processes.py')

        self.assertIn(
            'processed=sample_holder_position.substrate.reference.processed',
            processes,
        )

        self.assertNotIn(
            'processed=sample_holder_position.substrate.reference.grown',
            processes,
        )

        self.assertIn(
            'grown=True',
            processes,
        )

    def test_new_mbe_contains_no_substrate_cut_ui_or_logic(self):
        mbe_js = text(NEW_MBE_JS)
        mbe_html = text(
            ROOT / 'src/pdi_nomad_plugin/mbe/new_mbe_experiment/templates/index.html'
        )

        forbidden = [
            'saveSubstrateSplit',
            'refreshSplitChildren',
            'substrateSplitGeometry',
            'splitChildSelectionState',
            'id="splitSubstrateButton"',
            'id="splitChildPicker"',
            'SampleCutPDI',
        ]

        for value in forbidden:
            with self.subTest(value=value):
                self.assertNotIn(value, mbe_js)
                self.assertNotIn(value, mbe_html)

        # The backend schema is deliberately retained because cutting will
        # later move into the Substrate Processing dashboard.
        processes = text(ROOT / 'src/pdi_nomad_plugin/mbe/processes.py')
        self.assertIn('SampleCutPDI', processes)

    def test_new_mbe_insert_geometry_and_layout_contract(self):
        repo_root = Path(__file__).resolve().parents[1]

        base = repo_root / 'src' / 'pdi_nomad_plugin' / 'mbe' / 'new_mbe_experiment'

        app = (base / 'static/app.js').read_text(encoding='utf-8-sig')
        css = (base / 'static/styles.css').read_text(encoding='utf-8-sig')
        html = (base / 'templates/index.html').read_text(encoding='utf-8-sig')

        self.assertIn("'data.geometry'", app)
        self.assertIn("'data.inner_geometry'", app)
        self.assertIn("'data.outer_geometry'", app)

        self.assertIn(
            'function geometryMatches(',
            app,
        )
        self.assertIn(
            'function insertFitsPosition(',
            app,
        )
        self.assertIn(
            'function substrateFitsPosition(',
            app,
        )
        self.assertIn(
            'geometry: substrate.geometry || null',
            app,
        )

        self.assertIn(
            'holder-insert-window',
            app,
        )
        self.assertIn(
            '.holder-insert-window',
            css,
        )

        self.assertIn(
            'id="positionControlsPanel"',
            html,
        )
        self.assertIn(
            'positionControlsPanel.appendChild(controls)',
            app,
        )

        self.assertIn(
            '/* FINAL compact holder layout */',
            css,
        )
        self.assertIn(
            'width: 250px !important;',
            css,
        )
        self.assertIn(
            'height: 250px !important;',
            css,
        )

    def test_cut_parent_substrate_is_not_selectable(self):
        repo_root = Path(__file__).resolve().parents[1]

        app = (
            repo_root
            / 'src'
            / 'pdi_nomad_plugin'
            / 'mbe'
            / 'new_mbe_experiment'
            / 'static'
            / 'app.js'
        ).read_text(encoding='utf-8-sig')

        self.assertIn(
            "'data.parent_sample'",
            app,
        )

        self.assertIn(
            'function cutParentEntryIds()',
            app,
        )

        self.assertIn(
            'function substrateHasBeenCut(',
            app,
        )

        self.assertIn(
            'cutParents.has(',
            app,
        )

        self.assertIn(
            'has been cut into child samples and is no longer physically available.',
            app,
        )


if __name__ == '__main__':
    unittest.main()
