"""Fail-closed whole-repository metainfo/normalizer/parser provenance checks.

Do not weaken these checks to fix a failure. Refactor the actual application.
The existing independent EPIC parser is protected, not a schema exception.
"""

from __future__ import annotations

import ast
import hashlib
import re
import subprocess

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib
from .original_contract import ROOT, baseline

PACKAGE_ROOT = ROOT / 'src' / 'pdi_nomad_plugin'
EPIC = PACKAGE_ROOT / 'mbe' / 'epic_parser' / 'parser.py'
EPIC_APPROVED_SHA256 = (
    'e286ab2de63a5742db9be6e5ed20acc3b4330473be9f6a72257e603749d84f9c'
)
EPIC_ENTRYPOINT_SHA256 = (
    '01302f2c0e04dfdde8298864f615b478004c927d5241294b6fb42b7f6f867465'
)
EPIC_FOLDER = EPIC.parent
# Matches qualified PDI classes in Python/JS/JSON/HTML/YAML, rather than ordinary imports.
PDI_CLASS = re.compile(r'\bpdi_nomad_plugin(?:\.[a-zA-Z_]\w*)+\.[A-Z][A-Za-z_0-9]*\b')
CODE_SUFFIXES = {'.py', '.js', '.html', '.json', '.yaml', '.yml'}


def plugin_code_files():
    assert PACKAGE_ROOT.is_dir(), 'Plugin source tree not found'
    return sorted(
        p
        for p in PACKAGE_ROOT.rglob('*')
        if p.is_file()
        and p.suffix.lower() in CODE_SUFFIXES
        and '__pycache__' not in p.parts
    )


def scan_python(text, label):
    """Statically enumerate local Metainfo declarations and normalize() overrides."""
    tree = ast.parse(text, filename=label)
    schemas, normalizers, parsers = [], [], []
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == 'normalize'
        ):
            normalizers.append(f'{label}:{node.lineno}: normalize()')
        if not isinstance(node, ast.ClassDef):
            continue
        is_schema = False
        for member in node.body:
            if isinstance(member, (ast.Assign, ast.AnnAssign)) and isinstance(
                member.value, ast.Call
            ):
                called = member.value.func
                name = (
                    called.id
                    if isinstance(called, ast.Name)
                    else (called.attr if isinstance(called, ast.Attribute) else '')
                )
                if name in {'Quantity', 'SubSection', 'Section', 'SectionProxy'}:
                    is_schema = True
        for base in node.bases:
            base_name = ast.unparse(base).rsplit('.', 1)[-1]
            if base_name in {
                'ArchiveSection',
                'EntryData',
                'Schema',
                'Section',
                'MSection',
                'CompositeSystem',
                'Process',
                'ProcessStep',
                'Recipe',
                'Substrate',
                'CrystallineSubstrate',
                'ThinFilm',
                'ThinFilmStack',
                'SubstrateHolder',
                'FilledSubstrateHolder',
                'InsertReduction',
            }:
                is_schema = True
        if is_schema:
            schemas.append(f'{label}:{node.lineno}: {node.name}')
        if node.name.lower().startswith('parser') or any(
            'Parser' in ast.unparse(base) for base in node.bases
        ):
            parsers.append(f'{label}:{node.lineno}: {node.name}')
    return schemas, normalizers, parsers


def upstream_text(path):
    rel = path.relative_to(ROOT).as_posix()
    p = subprocess.run(
        ['git', 'show', f'upstream/main:{rel}'],
        check=False,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding='utf-8',
    )
    return p.stdout if p.returncode == 0 else ''


def definitions(code, label):
    if not code:
        return set(), set()
    tree = ast.parse(code, filename=label)
    schemas, normalizers = set(), set()
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        if scan_python(ast.unparse(cls), label)[0]:
            schemas.add(cls.name)
        if any(
            isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
            and m.name == 'normalize'
            for m in cls.body
        ):
            normalizers.add(cls.name)
    return schemas, normalizers


def new_definitions():
    findings = []
    for path in plugin_code_files():
        if path.suffix != '.py' or EPIC_FOLDER in path.parents:
            continue
        rel = path.relative_to(ROOT).as_posix()
        present = definitions(path.read_text(encoding='utf-8-sig'), rel)
        earlier = definitions(upstream_text(path), rel)
        findings.append((rel, present[0] - earlier[0], present[1] - earlier[1]))
    return findings


def test_no_local_metainfo_or_normalizers_anywhere_in_plugin():
    failures = []
    for rel, schemas, normalizers in new_definitions():
        failures.extend(f'NEW METINFO {rel}: {n}' for n in sorted(schemas))
        failures.extend(f'NEW NORMALIZER {rel}: {n}' for n in sorted(normalizers))
    assert not failures, '\n'.join(failures)


def test_no_plugin_schema_class_references_anywhere_in_source():
    new_names = set().union(*(s for _, s, _ in new_definitions()))
    issues = []
    for path in plugin_code_files():
        if EPIC_FOLDER in path.parents:
            continue
        for number, line in enumerate(
            path.read_text(encoding='utf-8-sig', errors='replace').splitlines(), 1
        ):
            for m in PDI_CLASS.finditer(line):
                if m.group().rsplit('.', 1)[-1] in new_names:
                    issues.append(f'{path.relative_to(ROOT)}:{number}: {m.group()}')
    assert not issues, '\n'.join(issues)


def test_plugin_entrypoints_are_exactly_approved_apps_and_independent_epic():
    with (ROOT / 'pyproject.toml').open('rb') as stream:
        entries = tomllib.load(stream)['project']['entry-points']['nomad.plugin']
    old = upstream_text(ROOT / 'pyproject.toml')
    assert old, 'upstream/main baseline unavailable'
    original = tomllib.loads(old)['project']['entry-points']['nomad.plugin']
    assert all(entries.get(k) == v for k, v in original.items()), (
        'Original plugin entrypoints changed'
    )
    assert (
        entries.get('epic_mbe_parser') == 'pdi_nomad_plugin.mbe.epic_parser:epic_parser'
    )
    assert not [k for k in entries.keys() - original.keys() if k.endswith('_schema')]


def test_no_other_parser_classes_and_epic_source_integrity():
    assert EPIC.is_file(), 'Existing EPIC parser disappeared'
    assert (
        hashlib.sha256((EPIC_FOLDER / '__init__.py').read_bytes()).hexdigest()
        == EPIC_ENTRYPOINT_SHA256
    ), 'EPIC parser registration source changed; explicit review required.'
    actual = hashlib.sha256(EPIC.read_bytes()).hexdigest()
    assert actual == EPIC_APPROVED_SHA256, (
        'Existing independently developed EPIC parser changed. '
        'Review provenance and update the approved digest separately, NEVER silently.'
    )
    unexpected = []
    for path in plugin_code_files():
        if path.suffix != '.py' or EPIC_FOLDER in path.parents:
            continue
        _s, _n, parsers = scan_python(
            path.read_text(encoding='utf-8-sig'), str(path.relative_to(ROOT))
        )
        unexpected.extend(parsers)
    assert not unexpected, 'Unreviewed local parsers:\n' + '\n'.join(unexpected)


def test_original_snapshot_is_never_whitelisted_with_pdi_schema():
    approved = baseline()
    assert approved and all(
        x.startswith(('nomad.', 'nomad_material_processing.')) for x in approved
    )
    assert not any('pdi_nomad_plugin' in x for x in approved)


def test_guard_does_not_accept_fabricated_metainfo_or_normalizers():
    """Mutation/self-test: synthetic illegal code MUST be detected."""
    code = """
class Fake(ArchiveSection):
    field = Quantity(type=str)
    def normalize(self, archive, logger):
        return None
"""
    schemas, normalizers, _ = scan_python(code, 'synthetic.py')
    assert schemas and normalizers
    assert PDI_CLASS.search('"m_def": "pdi_nomad_plugin.example.Fake"')
    assert not PDI_CLASS.search('from pdi_nomad_plugin.mbe.lab_library import app')
