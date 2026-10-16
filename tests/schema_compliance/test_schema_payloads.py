"""Guard original archive fields and legacy archive fixtures.

New application integration tests should call assert_original_archive_data() on
actual response / generated upload data, not on hand-built expected objects only.
"""
import re
from pathlib import Path

import pytest

from .original_contract import ROOT, assert_original_archive_data, baseline


def test_original_archive_payload_validator_accepts_original_fields():
    assert_original_archive_data(
        {
            'm_def': 'nomad_material_processing.general.AnnealingRecipe',
            'name': 'Annealing',
            'method': 'Tube furnace',
            'steps': [{
                'm_def': 'nomad_material_processing.general.AnnealingStep',
                'duration': 3600,
                'starting_temperature': 25,
                'ending_temperature': 850,
            }],
        },
        'nomad_material_processing.general.AnnealingRecipe',
    )


@pytest.mark.parametrize('name,payload', [
    ('PDI m_def', {'m_def': 'pdi_nomad_plugin.general.schema.AnnealingRecipePDI'}),
    ('PDI recipe quantity', {'operation_temperature': 850}),
    ('PDI holder position', {
        'positions': [{'name': 'A', 'rho': 0.01, 'theta': 0}],
    }),
])
def test_original_archive_payload_validator_rejects_extensions(name, payload):
    path = ('nomad_material_processing.vapor_deposition.general.SubstrateHolder'
            if name == 'PDI holder position'
            else 'nomad_material_processing.general.AnnealingRecipe')
    with pytest.raises(AssertionError):
        assert_original_archive_data(payload, path)


def test_checked_in_example_archives_only_use_original_mdefs():
    """Checks committed sample archive fixtures, not EPIC raw measurement files."""
    folder = ROOT / 'tests' / 'fixtures'
    original = baseline()
    bad = []
    if folder.exists():
        for path in folder.rglob('*'):
            if not path.is_file() or not path.name.endswith(('.archive.yaml', '.archive.yml')):
                continue
            for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
                match = re.match(r'^\s*m_def:\s*[\x22\x27]?([\w.]+)', line)
                if match and match.group(1) not in original:
                    bad.append(f'{path.relative_to(ROOT)}:{number}: {match.group(1)}')
    assert not bad, 'Archive fixtures reference non-original/unverified m_def:\n' + '\n'.join(bad[:40])
