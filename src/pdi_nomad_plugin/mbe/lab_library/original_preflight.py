"""Fail-closed, read-only checks using installed ORIGINAL NOMAD metainfo.

Not a parser, schema, or normalizer. No network or upload calls. The actual
NOMAD archive parser/normalization on the server must still be integration-tested.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any

ORIGINAL_MODULE_PREFIXES = ('nomad.', 'nomad_material_processing.')

# Existing PDI schemas introduced in commit 9d8cddb (2024-08-19).
# Explicit exceptions; no general authorization of local PDI schemas.
APPROVED_LEGACY_PDI_CLASSES = frozenset({
    'pdi_nomad_plugin.general.schema.BackSideCoatingPDI',
    'pdi_nomad_plugin.general.schema.BackSideCoatingRecipePDI',
})


class OriginalSchemaValidationError(ValueError):
    pass


def _resolve_original_class(qualified_name: str):
    if not isinstance(qualified_name, str) or not (
        qualified_name.startswith(ORIGINAL_MODULE_PREFIXES)
        or qualified_name in APPROVED_LEGACY_PDI_CLASSES
    ):
        raise OriginalSchemaValidationError(f'Non-original m_def: {qualified_name!r}')
    module_name, sep, name = qualified_name.rpartition('.')
    if not sep:
        raise OriginalSchemaValidationError('m_def must be fully qualified')
    try:
        module = importlib.import_module(module_name)
        cls = getattr(module, name)
    except (ImportError, AttributeError) as exc:
        raise OriginalSchemaValidationError(
            f'Original m_def unavailable: {qualified_name}'
        ) from exc
    if cls.__module__ != module_name or not hasattr(cls, 'm_def'):
        raise OriginalSchemaValidationError(
            f'Invalid original metainfo class: {qualified_name}'
        )
    if cls.m_def.qualified_name() != qualified_name:
        raise OriginalSchemaValidationError(f'm_def mismatch: {qualified_name}')
    # A symbol imported/re-exported from another source is not the installed
    # canonical metainfo class, even when it has the same qualified name.
    try:
        class_source = Path(inspect.getfile(cls)).resolve()
        module_source = Path(inspect.getfile(module)).resolve()
    except (TypeError, OSError) as exc:
        raise OriginalSchemaValidationError(
            'Original m_def source cannot be verified'
        ) from exc
    if class_source != module_source:
        raise OriginalSchemaValidationError(f'm_def source mismatch: {qualified_name}')
    plugin_root = Path(__file__).resolve().parents[2]
    if (
        (plugin_root == class_source or plugin_root in class_source.parents)
        and qualified_name not in APPROVED_LEGACY_PDI_CLASSES
    ):
        raise OriginalSchemaValidationError('Project-local m_def is forbidden')
    return cls


def assert_upstream_normalizer(cls):
    """Prove the effective normalizer is the installed NOMAD implementation.

    A name match or merely an inherited ``normalize`` attribute is not enough:
    the owning class, method module, and source must all belong to original
    packages. This does not invoke any normalizer or define a replacement.
    """
    plugin_root = Path(__file__).resolve().parents[2]
    for ancestor in cls.__mro__:
        if 'normalize' not in ancestor.__dict__:
            continue
        method = ancestor.__dict__['normalize']
        module_name = ancestor.__module__
        approved_pdi_normalizer = (
            cls.m_def.qualified_name() in APPROVED_LEGACY_PDI_CLASSES
            and module_name == 'pdi_nomad_plugin.general.schema'
            and ancestor.__name__ == 'BackSideCoatingPDI'
            and getattr(method, '__module__', '') == module_name
        )
        if not module_name.startswith(ORIGINAL_MODULE_PREFIXES) and not approved_pdi_normalizer:
            raise OriginalSchemaValidationError(
                f'Normalizer for {cls.__name__} comes from non-original {module_name}'
            )
        if (
            not getattr(method, '__module__', '').startswith(ORIGINAL_MODULE_PREFIXES)
            and not approved_pdi_normalizer
        ):
            raise OriginalSchemaValidationError(
                f'Normalizer implementation for {cls.__name__} is not upstream'
            )
        owner_module = importlib.import_module(module_name)
        if getattr(owner_module, ancestor.__name__, None) is not ancestor:
            raise OriginalSchemaValidationError(
                f'Normalizer owner {module_name}.{ancestor.__name__} is not upstream identity'
            )
        try:
            source = Path(inspect.getfile(method)).resolve()
        except (TypeError, OSError) as exc:
            raise OriginalSchemaValidationError(
                'Normalizer source cannot be verified'
            ) from exc
        if approved_pdi_normalizer:
            if source != Path(inspect.getfile(owner_module)).resolve():
                raise OriginalSchemaValidationError(
                    'Approved PDI normalizer source mismatch'
                )
        elif plugin_root == source or plugin_root in source.parents:
            raise OriginalSchemaValidationError('Project-local normalizer forbidden')
        return module_name + '.' + ancestor.__name__
    # No normalizer in the MRO is permitted; do not introduce one.
    return None


def _check_original_tree(data: dict[str, Any], cls, path='data'):
    """Reject unknown fields, invalid subsection shape, and foreign m_defs.

    All accepted quantities, subsections, and their reference/units metadata
    come from cls.m_def; conversion is delegated to cls.m_from_dict.
    """
    if not isinstance(data, dict):
        raise OriginalSchemaValidationError(f'{path} must be a JSON object')
    declared = data.get('m_def')
    if declared is not None:
        actual = _resolve_original_class(declared)
        if not issubclass(actual, cls):
            raise OriginalSchemaValidationError(
                f'{path}.m_def is not a subclass of the original expected schema'
            )
        cls = actual
    quantities = cls.m_def.all_quantities
    subsections = cls.m_def.all_sub_sections
    for key, value in data.items():
        if key == 'm_def':
            continue
        if key in quantities:
            continue  # The ORIGINAL m_from_dict handles types, units, and references.
        if key not in subsections:
            raise OriginalSchemaValidationError(
                f'Unknown field {path}.{key} for {cls.m_def.qualified_name()}'
            )
        definition = subsections[key]
        try:
            child_cls = definition.sub_section.section_cls
        except (AttributeError, ValueError) as exc:
            raise OriginalSchemaValidationError(
                f'Cannot resolve original subsection {path}.{key}'
            ) from exc
        if value is None:
            continue
        if definition.repeats:
            if not isinstance(value, list):
                raise OriginalSchemaValidationError(f'{path}.{key} must be a list')
            for index, item in enumerate(value):
                _check_original_tree(item, child_cls, f'{path}.{key}[{index}]')
        else:
            _check_original_tree(value, child_cls, f'{path}.{key}')


def validate_original_recipe(data: dict, allowed_schemas: set[str]):
    """Validate exactly the GUI's proposed data before a write is attempted.

    Instantiates the installed upstream recipe, builds an EntryArchive, validates
    and round-trips it. Does NOT invoke normalizers or the server parser.
    """
    from nomad.datamodel import EntryArchive
    from nomad.datamodel.data import EntryData

    if not isinstance(data, dict):
        raise OriginalSchemaValidationError('Missing recipe data object')
    qualified_name = data.get('m_def')
    if qualified_name not in allowed_schemas:
        raise OriginalSchemaValidationError(
            f'Unapproved recipe m_def: {qualified_name!r}'
        )
    cls = _resolve_original_class(qualified_name)
    if not issubclass(cls, EntryData):
        raise OriginalSchemaValidationError(
            f'{qualified_name} is not an EntryArchive.data root'
        )
    assert_upstream_normalizer(cls)
    if data.get('samples'):
        raise OriginalSchemaValidationError(
            'Reusable recipes must not embed runtime samples references'
        )

    # Generic instrument names are original NOMAD recipe metadata.
    # Concrete runtime instrument references must remain excluded.
    instruments = data.get('instruments')
    if instruments is not None:
        if not isinstance(instruments, list):
            raise OriginalSchemaValidationError('Recipe instruments must be a list')
        for index, instrument in enumerate(instruments):
            if (
                not isinstance(instrument, dict)
                or set(instrument) != {'name'}
                or not isinstance(instrument.get('name'), str)
                or not instrument['name'].strip()
            ):
                raise OriginalSchemaValidationError(
                    f'Recipe instruments[{index}] must contain only a '
                    'generic name, without lab_id or reference'
                )
    _check_original_tree(data, cls)
    try:
        section = cls.m_from_dict(data)
        archive = EntryArchive(data=section)
        serialized = archive.m_to_dict(with_meta=True)
        reparsed = EntryArchive.m_from_dict(serialized)
        errors, warnings = reparsed.m_validate()
    except Exception as exc:
        raise OriginalSchemaValidationError(
            f'Original NOMAD metainfo validation failed: {exc}'
        ) from exc
    if errors:
        raise OriginalSchemaValidationError(
            'Original NOMAD m_validate errors: ' + '; '.join(map(str, errors))
        )
    if reparsed.data.m_def.qualified_name() != qualified_name:
        raise OriginalSchemaValidationError(
            'Original EntryArchive roundtrip changed the recipe m_def'
        )
    return {
        'valid': True,
        'schema': qualified_name,
        'warnings': [str(w) for w in warnings],
        'checks': [
            'original_m_def',
            'original_quantities_subsections',
            'original_m_from_dict',
            'EntryArchive_roundtrip',
            'original_m_validate',
        ],
        'normalizer_executed': False,
        'server_parser_executed': False,
    }
