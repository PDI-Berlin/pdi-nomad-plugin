"""Read-only, fail-closed validation of original NOMAD processing archives.

The original NOMAD classes, references, units, and subsections are resolved
from the *installed* NOMAD Core / nomad-material-processing distributions.
No local metainfo schema or normalizer is declared here.
"""

from __future__ import annotations

from ..lab_library.original_preflight import (
    _check_original_tree,
    _resolve_original_class,
    assert_upstream_normalizer,
)


class OriginalProcessValidationError(ValueError):
    pass


def validate_original_process(data: dict, allowed_schemas: set[str]) -> dict:
    from nomad.datamodel import EntryArchive
    from nomad.datamodel.data import EntryData

    if not isinstance(data, dict):
        raise OriginalProcessValidationError('Missing process data object.')
    schema = data.get('m_def')
    if schema not in allowed_schemas:
        raise OriginalProcessValidationError(f'Unapproved process m_def: {schema!r}')
    try:
        cls = _resolve_original_class(schema)
        if not issubclass(cls, EntryData):
            raise OriginalProcessValidationError(f'{schema} is not an EntryData root.')
        assert_upstream_normalizer(cls)
        # A reference to the recipe and at least one physical substrate are
        # mandatory for this application workflow, even if upstream marks
        # these quantities as optional for general-purpose process entries.
        if not isinstance(data.get('recipe'), str) or not data['recipe'].strip():
            raise OriginalProcessValidationError('Missing original recipe reference.')
        samples = data.get('samples')
        if not isinstance(samples, list) or not samples:
            raise OriginalProcessValidationError(
                'At least one substrate reference is required.'
            )
        for i, sample in enumerate(samples):
            if (
                not isinstance(sample, dict)
                or not isinstance(sample.get('reference'), str)
                or not sample['reference'].strip()
            ):
                raise OriginalProcessValidationError(
                    f'samples[{i}] has no NOMAD reference.'
                )
        # Process steps and instruments are copied from the referenced recipe
        # by the upstream Process normalizer during NOMAD server processing.
        # Supplying duplicates here would reimplement that normalizer.
        if data.get('steps') or data.get('instruments'):
            raise OriginalProcessValidationError(
                'Process steps/instruments must come from the original recipe normalizer.'
            )
        # This validates actual original subsection fields before letting
        # the installed metainfo implementation validate types/references.
        _check_original_tree(data, cls)
        section = cls.m_from_dict(data)
        archive = EntryArchive(data=section)
        reparsed = EntryArchive.m_from_dict(archive.m_to_dict(with_meta=True))
        errors, warnings = reparsed.m_validate()
        if errors:
            raise OriginalProcessValidationError(
                'Original NOMAD m_validate errors: ' + '; '.join(map(str, errors))
            )
        if reparsed.data.m_def.qualified_name() != schema:
            raise OriginalProcessValidationError(
                'Process m_def changed during roundtrip.'
            )
    except OriginalProcessValidationError:
        raise
    except Exception as exc:
        raise OriginalProcessValidationError(
            f'Original NOMAD metainfo validation failed: {exc}'
        ) from exc
    return {
        'valid': True,
        'schema': schema,
        'warnings': [str(w) for w in warnings],
        'normalizer_executed': False,
        'server_parser_executed': False,
    }
