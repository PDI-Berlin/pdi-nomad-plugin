"""Schema provenance and original-normalizer contracts (read-only)."""

import hashlib
import importlib
import importlib.metadata
from pathlib import Path

import pytest

from .original_contract import (
    ROOT,
    baseline,
    describe_live_class,
    manifest,
    schema_differences,
)


def test_baseline_integrity_and_count():
    assert len(baseline()) == 92
    assert set(manifest()['source_modules']) == {
        'nomad.datamodel.metainfo.basesections.v1',
        'nomad_material_processing.general',
        'nomad_material_processing.vapor_deposition.general',
    }


@pytest.mark.parametrize('package,expected', sorted(manifest()['packages'].items()))
def test_installed_original_package_versions_match_verified_export(package, expected):
    assert importlib.metadata.version(package) == expected, (
        f'Original package {package} changed: expected {expected}, '
        f'actual {importlib.metadata.version(package)}. Review export; do not silently update baseline.'
    )


@pytest.mark.parametrize('module_name', sorted(manifest()['module_sha256']))
def test_original_module_file_sha256_matches_export(module_name):
    """Detect source replacement, including same-version code modifications."""
    module = importlib.import_module(module_name)
    path = Path(module.__file__).resolve()
    assert (ROOT / 'src' / 'pdi_nomad_plugin').resolve() not in path.parents, (
        f'Upstream source resolves inside PDI project: {path}'
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = manifest()['module_sha256'][module_name]
    assert digest == expected, (
        f'{module_name}: source file differs from the verified runtime snapshot. '
        f'Expected SHA256={expected}, got={digest}. Do not regenerate baseline automatically.'
    )


@pytest.mark.parametrize(
    'module',
    [
        'nomad.datamodel.metainfo.basesections.v1',
        'nomad_material_processing.general',
        'nomad_material_processing.vapor_deposition.general',
    ],
)
def test_installed_original_schema_definition_matches_snapshot(module):
    expected = baseline()
    problems = []
    checked = 0
    for name, spec in sorted(expected.items()):
        if not name.startswith(module + '.'):
            continue
        checked += 1
        try:
            for diff in schema_differences(name, spec):
                problems.append(f'{name}: {diff}')
        except Exception as exc:
            problems.append(f'{name}: unable to inspect: {type(exc).__name__}: {exc}')
    assert checked > 0
    assert not problems, (
        f'{len(problems)} original schema/normalizer deviations:\n'
        + '\n'.join(problems[:60])
    )


def test_original_normalizer_implementations_are_upstream_and_match_snapshot():
    """Checks all 92 effective normalize() owners without running normalizers."""
    problems = []
    for name, entry in baseline().items():
        try:
            actual, _, _ = describe_live_class(name)
            if actual['normalizer'] != entry['normalizer']:
                problems.append(f'{name}: normalizer owner changed')
        except Exception as exc:
            problems.append(f'{name}: {type(exc).__name__}: {exc}')
    assert not problems, '\n'.join(problems[:60])
