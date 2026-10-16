"""Strict read-only checks against the user-exported ORIGINAL NOMAD runtime.

This module never imports pdi_nomad_plugin to determine schema provenance.
The baseline is version + SHA256 pinned and must be reviewed when upgraded.
"""
from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINES = Path(__file__).resolve().parent / 'baselines'
SCHEMA_FILE = BASELINES / 'original_metainfo_approved.json'
MANIFEST_FILE = BASELINES / 'baseline_manifest.json'
UPSTREAM_PREFIXES = ('nomad.', 'nomad_material_processing.')
REFERENCE_RE = re.compile(r'^<nomad\.metainfo\.metainfo\.Reference object at 0x[0-9a-fA-F]+>$')


def canonical_type(value):
    """Reference.__repr__ includes a volatile process address."""
    value = str(value)
    return 'Reference' if REFERENCE_RE.fullmatch(value) else value


def manifest():
    return json.loads(MANIFEST_FILE.read_text(encoding='utf-8'))


def baseline():
    info = manifest()
    digest = hashlib.sha256(SCHEMA_FILE.read_bytes()).hexdigest()
    if digest != info['snapshots_sha256']:
        raise AssertionError('Approved original-schema baseline SHA256 mismatch; do not silently regenerate')
    records = json.loads(SCHEMA_FILE.read_text(encoding='utf-8'))
    if len(records) != info['schema_count']:
        raise AssertionError('Approved original-schema baseline count mismatch')
    if not records or any(name != rec['m_def_qualified_name'] for name, rec in records.items()):
        raise AssertionError('Invalid original-schema qualified names')
    return records


def _is_in_project_plugin(path):
    plugin_root = (ROOT / 'src' / 'pdi_nomad_plugin').resolve()
    path = Path(path).resolve()
    return path == plugin_root or plugin_root in path.parents


def _is_upstream_module_name(module_name):
    return module_name.startswith(UPSTREAM_PREFIXES)


def live_normalizer(cls):
    """Find the effective inherited or locally defined method; do not run it."""
    for ancestor in cls.__mro__:
        if 'normalize' not in vars(ancestor):
            continue
        method = vars(ancestor)['normalize']
        source = Path(inspect.getfile(method)).resolve()
        owner = f'{ancestor.__module__}.{ancestor.__qualname__}'
        if not _is_upstream_module_name(ancestor.__module__):
            raise AssertionError(f'{cls.__qualname__} normalizer is owned by non-original {owner}')
        if not _is_upstream_module_name(getattr(method,'__module__','')):
            raise AssertionError(f'{cls.__qualname__} normalize function is not upstream: {method!r}')
        if _is_in_project_plugin(source):
            raise AssertionError(f'Project normalizer substituted into {cls.__qualname__}: {source}')
        owner_module = importlib.import_module(ancestor.__module__)
        if getattr(owner_module, ancestor.__name__, None) is not ancestor:
            raise AssertionError(f'Normalizer owner {owner} is not upstream class identity')
        owner_source = Path(inspect.getfile(ancestor)).resolve()
        if source != owner_source:
            raise AssertionError(f'Normalizer source for {owner} does not match its owner module: {source} != {owner_source}')
        return {'defined_in': owner, 'locally_defined_on_class': ancestor is cls}
    return None


def describe_live_class(schema_name):
    module_name, name = schema_name.rsplit('.', 1)
    if module_name not in manifest()['source_modules']:
        raise AssertionError(f'Unverified schema module: {module_name}')
    mod = importlib.import_module(module_name)
    cls = getattr(mod, name)
    if cls.__module__ != module_name:
        raise AssertionError(f'{schema_name} is not defined in its approved module: {cls.__module__}')
    path = Path(inspect.getfile(cls)).resolve()
    mod_path = Path(inspect.getfile(mod)).resolve()
    if path != mod_path or _is_in_project_plugin(path):
        raise AssertionError(f'{schema_name} resolves to unexpected schema source: {path}')
    if not hasattr(cls, 'm_def') or not hasattr(cls.m_def, 'all_quantities'):
        raise AssertionError(f'Not a NOMAD m_def: {schema_name}')
    if cls.m_def.qualified_name() != schema_name:
        raise AssertionError(f'{schema_name} is not its actual m_def name: {cls.m_def.qualified_name()}')
    definition = cls.m_def
    actual = {
        'm_def_qualified_name': definition.qualified_name(),
        'bases': [f'{b.__module__}.{b.__qualname__}' for b in cls.__bases__],
        'quantities': {
            k: {'type': canonical_type(q.type),
                'unit': str(q.unit) if q.unit is not None else None,
                'shape': str(q.shape),
                'description': q.description}
            for k, q in definition.all_quantities.items()
        },
        'subsections': {
            k: {'schema': sub.sub_section.qualified_name(), 'repeats': bool(sub.repeats)}
            for k, sub in definition.all_sub_sections.items()
        },
        'normalizer': live_normalizer(cls),
    }
    return actual, cls, path


def schema_differences(schema_name, expected):
    actual, _cls, _path = describe_live_class(schema_name)
    failures = []
    for kind in ('quantities', 'subsections'):
        desired, got = expected[kind], actual[kind]
        for missing in sorted(desired.keys() - got.keys()):
            failures.append(f'{kind} missing: {missing}')
        for extra in sorted(got.keys() - desired.keys()):
            failures.append(f'{kind} added: {extra}')
        for changed in sorted(got.keys() & desired.keys()):
            if desired[changed] != got[changed]:
                failures.append(f'{kind} changed: {changed}: {desired[changed]!r} -> {got[changed]!r}')
    for key in ('m_def_qualified_name', 'bases', 'normalizer'):
        if expected[key] != actual[key]:
            failures.append(f'{key} changed: {expected[key]!r} -> {actual[key]!r}')
    return failures


def assert_original_archive_data(data, schema_name, *, _ancestry=()):
    """Reject unknown schemas and fields in serialized GUI/API archive payloads.

    Baseline covers 92 schemas, not all of NOMAD. An unexported upstream
    schema fails closed and needs explicit review, not an automatic waiver.
    """
    schemas = baseline()
    if schema_name not in schemas:
        raise AssertionError(f'Unknown/unverified original schema (or PDI schema): {schema_name}')
    if not isinstance(data, dict):
        raise AssertionError(f'{schema_name}: payload must be a dict')
    if data.get('m_def', schema_name) != schema_name:
        raise AssertionError(f'{schema_name}: mismatching m_def: {data.get("m_def")}')
    spec = schemas[schema_name]
    allowed = set(spec['quantities']) | set(spec['subsections']) | {'m_def'}
    extra = sorted(set(data) - allowed)
    if extra:
        raise AssertionError(f'{schema_name}: fields absent from verified ORIGINAL schema: {extra}')
    for field, sub in spec['subsections'].items():
        if field not in data or data[field] is None:
            continue
        target = sub['schema']
        if target not in schemas:
            raise AssertionError(f'{schema_name}.{field}: reference to unverified subsection {target}')
        values = data[field]
        if sub['repeats']:
            if not isinstance(values, list):
                raise AssertionError(f'{schema_name}.{field}: expected list')
        else:
            values = [values]
        for value in values:
            if not isinstance(value, dict):
                raise AssertionError(f'{schema_name}.{field}: expected section object')
            selected = value.get('m_def', target)
            if selected not in schemas:
                raise AssertionError(f'{schema_name}.{field}: unknown/unverified subclass: {selected}')
            if selected != target:
                _spec, target_cls, _ = describe_live_class(target)
                _spec, selected_cls, _ = describe_live_class(selected)
                if not issubclass(selected_cls, target_cls):
                    raise AssertionError(f'{selected}: not an original subtype of {target}')
            assert_original_archive_data(value, selected, _ancestry=(*_ancestry, schema_name))
