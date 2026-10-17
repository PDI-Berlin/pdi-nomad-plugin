"""Fail on actual application use of any local schema, or local normalizer override.

Read-only AST/static provenance guard. This deliberately does not remove, change,
import or execute the protected existing EPIC parser.
"""

from __future__ import annotations

import ast
import re
import subprocess

from .original_contract import ROOT, baseline

SOURCE = ROOT / 'src' / 'pdi_nomad_plugin'
APP_ROOT = SOURCE / 'mbe'
SCHEMA_MODULES = [
    SOURCE / 'general' / 'schema.py',
    SOURCE / 'mbe' / 'materials.py',
    SOURCE / 'mbe' / 'instrument.py',
    SOURCE / 'mbe' / 'processes.py',
    SOURCE / 'characterization' / 'schema.py',
]
APP_NAMES = (
    'lab_library',
    'substrate_intake',
    'processing',
    'new_mbe_experiment',
    'substrate_search',
    'pdi_lab',
    'mbe_app',
)
QUALIFIED = re.compile(r'pdi_nomad_plugin(?:\.[A-Za-z_]\w*){2,}')


def iter_gui_and_api_sources():
    for name in APP_NAMES:
        folder = APP_ROOT / name
        if folder.exists():
            for p in sorted(folder.rglob('*')):
                if p.is_file() and p.suffix.lower() in ('.py', '.js', '.html'):
                    yield p


def test_library_registered_schema_paths_are_original():
    path = APP_ROOT / 'lab_library' / 'app.py'
    assert path.exists(), 'Expected Lab Library API source does not exist'
    code = ast.parse(path.read_text(encoding='utf-8-sig'))
    matches = [
        n.value
        for n in code.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'LIBRARY_TYPES' for t in n.targets)
    ]
    assert len(matches) == 1, (
        'LIBRARY_TYPES must be uniquely declared (read-only audit)'
    )
    registrations = ast.literal_eval(matches[0])
    allowed = baseline()
    findings = []

    def check(node, location='LIBRARY_TYPES'):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == 'schema' and isinstance(v, str) and v not in allowed:
                    findings.append(
                        f'{location}.{k}: {v} is not an exported ORIGINAL m_def'
                    )
                elif k == 'usage_schemas' and isinstance(v, (tuple, list)):
                    for item in v:
                        if item not in allowed:
                            findings.append(
                                f'{location}.{k}: {item} is not an exported ORIGINAL m_def'
                            )
                else:
                    check(v, f'{location}.{k}')
        elif isinstance(node, (tuple, list)):
            for n, item in enumerate(node):
                check(item, f'{location}[{n}]')

    check(registrations)
    assert not findings, (
        f'{len(findings)} disallowed schema registrations:\n' + '\n'.join(findings)
    )


def test_app_sources_do_not_reference_pdi_schema_classes():
    """Scan literals, including JavaScript m_def strings, without executing any GUI."""
    findings = []
    for path in iter_gui_and_api_sources():
        content = path.read_text(encoding='utf-8-sig', errors='replace')
        for lineno, line in enumerate(content.splitlines(), 1):
            for match in QUALIFIED.finditer(line):
                candidate = match.group(0)
                final = candidate.rsplit('.', 1)[-1]
                # Only potential schema CLASS paths, not ordinary local APIs/modules.
                if final[:1].isupper():
                    findings.append(f'{path.relative_to(ROOT)}:{lineno}: {candidate}')
    assert not findings, (
        f'{len(findings)} uses of local PDI schema classes in GUI/API code:\n'
        + '\n'.join(findings[:50])
    )


def schema_class_definitions(path):
    """Locate local NOMAD schema classes; do not classify plugin entrypoints as schemas."""
    if not path.exists():
        return [], []
    tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    custom, normalizers = [], []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        fields = []
        has_category = False
        for item in node.body:
            if isinstance(item, (ast.Assign, ast.AnnAssign)):
                value = item.value
                if isinstance(value, ast.Call):
                    fn = value.func
                    called = (
                        fn.id
                        if isinstance(fn, ast.Name)
                        else fn.attr
                        if isinstance(fn, ast.Attribute)
                        else ''
                    )
                    if called in {'Quantity', 'SubSection', 'Section'}:
                        fields.append(called)
                    if called == 'Category':
                        has_category = True
            elif (
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == 'normalize'
            ):
                normalizers.append(
                    f'{path.relative_to(ROOT)}:{item.lineno}: {node.name}.normalize'
                )
        if fields and not has_category:
            custom.append(
                f'{path.relative_to(ROOT)}:{node.lineno}: {node.name} ({", ".join(fields)})'
            )
        elif node.name.endswith('PDI') and not has_category:
            # A local subclass is still a local schema even with zero new fields.
            custom.append(
                f'{path.relative_to(ROOT)}:{node.lineno}: {node.name} (local subclass)'
            )
    return custom, normalizers


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
    assert p.returncode == 0, f'Missing upstream baseline: {rel}'
    return p.stdout


def original_names(path):
    tree = ast.parse(upstream_text(path))
    classes = {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
    normalizers = {
        n.name
        for n in tree.body
        if isinstance(n, ast.ClassDef)
        and any(
            isinstance(m, ast.FunctionDef) and m.name == 'normalize' for m in n.body
        )
    }
    return classes, normalizers


def test_no_project_defined_nomad_schema_classes():
    findings = []
    for path in SCHEMA_MODULES:
        allowed, _ = original_names(path)
        classes, _ = schema_class_definitions(path)
        findings += [
            c for c in classes if c.split(': ', 1)[-1].split(' (')[0] not in allowed
        ]
    assert not findings, 'New PDI schemas relative to upstream/main:\n' + '\n'.join(
        findings
    )


def test_no_project_normalizer_overrides():
    findings = []
    for path in SCHEMA_MODULES:
        _, allowed = original_names(path)
        _, normalizers = schema_class_definitions(path)
        findings += [
            n
            for n in normalizers
            if n.split(': ', 1)[-1].split('.normalize')[0] not in allowed
        ]
    assert not findings, (
        'New normalize overrides relative to upstream/main:\n' + '\n'.join(findings)
    )


def test_existing_epic_parser_is_preserved():
    path = APP_ROOT / 'epic_parser' / 'parser.py'
    registration = APP_ROOT / 'epic_parser' / '__init__.py'
    pyproject = ROOT / 'pyproject.toml'
    assert path.is_file() and registration.is_file(), (
        'Protected EPIC parser files missing'
    )
    names = {
        n.name
        for n in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig')))
        if isinstance(n, ast.ClassDef)
    }
    assert 'ParserEpicPDI' in names, 'EPIC parser class unexpectedly missing'
    assert pyproject.is_file() and 'epic_mbe_parser' in pyproject.read_text(
        encoding='utf-8-sig'
    ), 'Existing EPIC parser entry-point missing from pyproject.toml'


def test_no_local_schema_package_registration():
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib

    with (ROOT / 'pyproject.toml').open('rb') as stream:
        entries = tomllib.load(stream)['project']['entry-points']['nomad.plugin']
    original = tomllib.loads(upstream_text(ROOT / 'pyproject.toml'))['project'][
        'entry-points'
    ]['nomad.plugin']
    keys = (
        'general_schema',
        'characterization_schema',
        'materials_schema',
        'instrument_schema',
        'processes_schema',
    )
    changed = [k for k in keys if k in entries and entries[k] != original.get(k)]
    assert not changed, f'New/modified legacy schema entrypoints: {changed}'
