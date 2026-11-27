import math
import re
import unicodedata
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from nomad.config import config
from nomad_material_processing.general import (
    CrystallineSubstrate,
    Cylinder,
    CylinderSector,
    RectangleCuboid,
    SquareCuboid,
)
from pydantic import BaseModel, Field

app = FastAPI()

STATIC_DIR = Path(__file__).with_name('static')
app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')


ORIENTATION_INDEX_COUNT = 3
DIMENSION_COUNT = 3
GEOMETRY_EQUALITY_TOLERANCE = 1e-9
MAX_SECTOR_ANGLE_DEG = 360.0


class SubstrateIntakePreview(BaseModel):
    supplier: str = ''
    supplier_id: str = ''
    material: str = ''
    material_preset: str = ''  # Intake UI only; never a NOMAD Quantity.
    crystal_id: str = ''
    charge: str = ''
    extended_charge: str = ''
    letter: str = ''
    polishing: str = ''
    delivery_date: date
    orientation: str = ''
    offcut_angle: float | None = None
    offcut_direction: str = ''
    width_mm: float | None = None
    length_mm: float | None = None
    geometry_shape: str = 'rectangle'
    radius_mm: float | None = None
    sector_angle_deg: float | None = None
    thickness_mm: float | None = None
    count: int = 1
    notes: str = ''
    subsections: dict[str, Any] = Field(default_factory=dict)


# All 118 recognized element symbols. Validation is restricted to the UI/API
# adapter; it does not duplicate or replace any NOMAD normalizer.
MILLER_TRIPLET_LENGTH = 3

ELEMENT_SYMBOLS = frozenset(
    'H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og'.split()
)


def validate_chemical_formula(formula: str) -> str:
    """Check chemical syntax and element symbols without creating new schemas.

    Recognizes elemental and grouped formulas with integer or decimal indices;
    it intentionally rejects trade names and ambiguous aliases as formulas.
    """
    value = unicodedata.normalize('NFKC', formula.strip())
    if not value:
        raise ValueError('Select a material or enter its chemical formula.')
    parts = re.findall(r'[A-Z][a-z]?|\(|\)|(?:\d+(?:\.\d+)?)', value)
    if not parts or ''.join(parts) != value:
        raise ValueError(
            'Invalid chemical formula; use real element symbols (e.g. SrTiO3).'
        )

    def parse_group(pos: int, nested: bool = False):
        count = 0
        while pos < len(parts):
            token = parts[pos]
            if token == ')':
                if not nested or count == 0:
                    raise ValueError(
                        'Unmatched or empty parentheses in chemical formula.'
                    )
                return pos + 1, count
            if token == '(':
                pos, _ = parse_group(pos + 1, True)
            elif token in ELEMENT_SYMBOLS:
                pos += 1
            else:
                raise ValueError('Unknown element or invalid formula token: ' + token)
            if pos < len(parts) and re.fullmatch(r'\d+(?:\.\d+)?', parts[pos]):
                if float(parts[pos]) <= 0:
                    raise ValueError('Stoichiometric coefficients must be positive.')
                pos += 1
            count += 1
        if nested:
            raise ValueError('Unclosed parenthesis in chemical formula.')
        return pos, count

    _, n = parse_group(0)
    if n == 0:
        raise ValueError('Chemical formula contains no elements.')
    return value


def safe_id_part(value: str) -> str:
    """Keep original metadata unchanged; sanitize only ID/path components."""
    value = unicodedata.normalize('NFKD', value.strip())
    value = re.sub(r'[\s/\\]+', '-', value)
    value = re.sub(r'[^A-Za-z0-9._-]+', '-', value)
    value = re.sub(r'-+', '-', value)
    return value.strip('-_.')


def derived_crystal_id(material: str, orientation: dict, letter: str = '') -> str:
    indices = [orientation[k] for k in ('h_index', 'k_index', 'l_index')]
    single_digit_limit = 10
    if all(abs(n) < single_digit_limit for n in indices):
        hkl = ''.join(str(n) for n in indices)
    else:
        hkl = '_'.join(f'{axis}{n}' for axis, n in zip('hkl', indices))
    material_id = safe_id_part(material)
    if not material_id:
        raise ValueError('Material is required for Crystal ID.')
    letter = letter.strip().upper()
    if letter and (len(letter) != 1 or not letter.isascii() or not letter.isalpha()):
        raise ValueError('Letter must be a single A-Z character.')
    return f'{material_id}_{hkl}{letter}'


def batch_lab_id(
    supplier_id: str,
    charge_id: str,
    material: str,
    orientation: dict,
    letter: str = '',
) -> str:
    parts = [
        safe_id_part(supplier_id),
        derived_crystal_id(material, orientation, letter),
        safe_id_part(charge_id),
    ]
    if not all(parts):
        raise ValueError('Supplier, material, orientation and charge are required.')
    return '_'.join(parts)


def parse_triplet(value: str, kind: str):
    """Accept three explicit signed indices; legacy (001) is also unambiguous."""
    cleaned = value.strip().strip('()[]').strip()
    if not cleaned:
        return None
    # Legacy (001) input remains valid for image import / existing callers.
    if re.fullmatch(r'\d{3}', cleaned):
        tokens = list(cleaned)
    else:
        tokens = cleaned.replace(',', ' ').split()
    if len(tokens) != MILLER_TRIPLET_LENGTH or not all(
        re.fullmatch(r'[+-]?\d+', x) for x in tokens
    ):
        raise ValueError(f'{kind}: specify three integer indices, e.g. 1 -1 0.')
    indices = tuple(int(t) for t in tokens)
    if indices == (0, 0, 0):
        raise ValueError(f'{kind}: all three indices cannot be zero.')
    return dict(zip(('h_index', 'k_index', 'l_index'), indices))


def parse_orientation(value: str):
    return parse_triplet(value, 'Surface orientation')


def parse_offcut_direction(value: str):
    return parse_triplet(value, 'Offcut direction')


def formatted_indices(indices, brackets):
    if indices is None:
        return None
    left, right = brackets
    return (
        left
        + ' '.join(str(indices[key]) for key in ('h_index', 'k_index', 'l_index'))
        + right
    )


def parse_dimensions(width, length, height):
    """Validate dimensions in mm and serialize original NOMAD geometry."""
    values = (width, length, height)
    if any(value is None for value in values):
        raise ValueError('Specify width, length and thickness in mm.')
    if not all(math.isfinite(v) and v > 0 for v in values):
        raise ValueError('Width, length and thickness must be positive finite numbers.')

    cls = (
        SquareCuboid
        if abs(width - length) <= GEOMETRY_EQUALITY_TOLERANCE
        else RectangleCuboid
    )
    dimensions = {'width': width / 1000, 'height': height / 1000}
    # A SquareCuboid has a single side width (x=y), whereas the original
    # RectangleCuboid needs both independent in-plane dimensions.
    if cls is RectangleCuboid:
        dimensions['length'] = length / 1000
    return cls(**dimensions).m_to_dict(with_meta=True)


def parse_geometry(data: SubstrateIntakePreview):
    if data.geometry_shape == 'rectangle':
        return parse_dimensions(data.width_mm, data.length_mm, data.thickness_mm)

    if data.geometry_shape not in ('circle', 'circular_sector'):
        raise ValueError('Unsupported substrate geometry shape.')

    radius = data.radius_mm if data.radius_mm is not None else 25.4
    angle = (
        360.0
        if data.geometry_shape == 'circle'
        else data.sector_angle_deg
        if data.sector_angle_deg is not None
        else 90.0
    )
    thickness = data.thickness_mm

    if thickness is None:
        raise ValueError('Specify wafer thickness in mm.')

    if not (
        math.isfinite(radius)
        and radius > 0
        and math.isfinite(thickness)
        and thickness > 0
        and math.isfinite(angle)
        and 0 < angle <= MAX_SECTOR_ANGLE_DEG
    ):
        raise ValueError('Radius, thickness and angle must have valid positive values.')

    if data.geometry_shape == 'circle':
        geometry = Cylinder(
            radius=radius / 1000,
            height=thickness / 1000,
        )
    else:
        geometry = CylinderSector(
            radius=radius / 1000,
            height=thickness / 1000,
            central_angle=angle,
        )

    return geometry.m_to_dict(with_meta=True)


def _validate_section_tree(value, expected_cls, label):
    """Strictly validate original NOMAD subsection m_defs and field names."""
    import importlib

    if not isinstance(value, dict):
        raise ValueError(f'{label} must be a JSON object.')
    selected_cls = expected_cls
    m_def = value.get('m_def')
    if m_def is not None:
        if not isinstance(m_def, str) or not m_def.startswith(
            ('nomad.', 'nomad_material_processing.')
        ):
            raise ValueError(f'{label}: only original NOMAD schema m_defs are allowed.')
        try:
            module, name = m_def.rsplit('.', 1)
            selected_cls = getattr(importlib.import_module(module), name)
        except (ValueError, AttributeError, ImportError) as exc:
            raise ValueError(f'{label}: unknown original m_def {m_def}.') from exc
        if not issubclass(selected_cls, expected_cls):
            raise ValueError(f'{label}: {m_def} is not a valid original subtype.')

    definition = selected_cls.m_def
    allowed = (
        set(definition.all_quantities) | set(definition.all_sub_sections) | {'m_def'}
    )
    extra = sorted(set(value) - allowed)
    if extra:
        raise ValueError(f'{label}: unsupported original-schema fields: {extra}')
    if label.endswith(('hkl_reciprocal', 'hkl_direct')):
        indices = [value.get(k) for k in ('h_index', 'k_index', 'l_index')]
        if any(
            type(x) not in (int, float) or not math.isfinite(x) or int(x) != x
            for x in indices
        ) or all(x == 0 for x in indices):
            raise ValueError(
                f'{label}: three nonzero-together integer Miller indices required.'
            )
    for key, subsection in definition.all_sub_sections.items():
        if key not in value or value[key] is None:
            continue
        inner_cls = subsection.sub_section.section_cls
        items = value[key]
        if subsection.repeats:
            if not isinstance(items, list):
                raise ValueError(f'{label}.{key} must be a JSON array.')
        else:
            items = [items]
        for item in items:
            _validate_section_tree(item, inner_cls, f'{label}.{key}')


MAX_YSZ_Y_ATOMIC_FRACTION = 2 / 5


# UI-only 8YSZ stoichiometry check: 1-x mol ZrO2 + x mol Y2O3.
# Stored quantities are ORIGINAL NOMAD dopant atomic_fraction/mass_fraction.
def ysz_fractions(oxide_fraction: float) -> tuple[float, float]:
    if not math.isfinite(oxide_fraction) or not 0 <= oxide_fraction < 1:
        raise ValueError('Y2O3 oxide fraction must be finite and in [0, 1).')
    y = 2 * oxide_fraction
    zr = 1 - oxide_fraction
    oxygen = 2 + oxide_fraction
    total_mass = zr * 91.224 + y * 88.90584 + oxygen * 15.999
    return (y / (zr + y + oxygen), y * 88.90584 / total_mass)


# Intake-only adaptation for original NOMAD elemental-composition / Dopant logic.
# Neither upstream schemas nor their normalizers are replaced or wrapped.
def apply_ysz_host_composition(base: dict, formula: str, preset: str = '') -> None:
    dopants = base.get('dopants') or []
    ydopants = [d for d in dopants if isinstance(d, dict) and d.get('element') == 'Y']
    if preset == '8ysz' and (
        formula != 'ZrO2' or len(dopants) != 1 or len(ydopants) != 1
    ):
        raise ValueError('8YSZ requires ZrO2 with exactly one Y dopant.')
    if formula != 'ZrO2' or not ydopants:
        return
    if len(dopants) != 1:
        raise ValueError(
            'ZrO2/Y concentration requires one Y dopant; additional dopants cannot be safely combined.'
        )
    a = ydopants[0].get('atomic_fraction')
    w = ydopants[0].get('mass_fraction')
    if a is None or w is None:
        if preset:
            raise ValueError('8YSZ requires both calculated dopant fractions.')
        return
    if not all(type(v) in (float, int) and math.isfinite(v) for v in (a, w)):
        raise ValueError('Invalid Y dopant fractions.')
    x = 3 * a / (2 * (1 - a))
    expected_a, expected_w = ysz_fractions(x)
    if not math.isclose(expected_a, a, rel_tol=1e-7, abs_tol=1e-9) or not math.isclose(
        expected_w, w, rel_tol=1e-6, abs_tol=1e-8
    ):
        raise ValueError('Y dopant fractions do not match the ZrO2/Y2O3 model.')
    if preset == '8ysz' and not math.isclose(x, 0.08, rel_tol=1e-6, abs_tol=1e-8):
        raise ValueError('8YSZ preset requires exactly 8 mol-% Y2O3.')
    # 1-x ZrO2 + x Y2O3 -> Zr=1-x, Y=2x, O=2+x.
    # Only Zr and O are placed here. Y is appended by ORIGINAL Dopant.normalize.
    zr, oxygen, yttrium = 1 - x, 2 + x, 2 * x
    atom_total = zr + oxygen + yttrium
    total_mass = zr * 91.224 + yttrium * 88.90584 + oxygen * 15.999
    base['elemental_composition'] = [
        {
            'element': 'Zr',
            'atomic_fraction': zr / atom_total,
            'mass_fraction': zr * 91.224 / total_mass,
        },
        {
            'element': 'O',
            'atomic_fraction': oxygen / atom_total,
            'mass_fraction': oxygen * 15.999 / total_mass,
        },
    ]


def validate_dopant_fractions(base: dict, additions: dict) -> None:
    def nonfinite(value, location='subsections'):
        if isinstance(value, dict):
            for k, v in value.items():
                nonfinite(v, f'{location}.{k}')
        elif isinstance(value, list):
            for i, v in enumerate(value):
                nonfinite(v, f'{location}[{i}]')
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f'{location}: non-finite numbers (NaN/Inf) are forbidden.')

    nonfinite(additions)
    dopants = additions.get('dopants')
    if not isinstance(dopants, list):
        return  # Existing schema validator reports wrong structures.
    components = base.get('components') or []
    formula = (
        (components[0].get('pure_substance') or {}).get('molecular_formula')
        if components
        else None
    )
    for i, dopant in enumerate(dopants):
        if not isinstance(dopant, dict):
            continue  # Existing schema validator reports this error.
        a = dopant.get('atomic_fraction')
        w = dopant.get('mass_fraction')
        if (a is None) != (w is None):
            raise ValueError(
                f'dopants[{i}]: specify both atomic and mass fractions, or neither.'
            )
        if a is None:
            continue
        if any(
            type(v) not in (int, float) or not math.isfinite(v) or v < 0 or v > 1
            for v in (a, w)
        ):
            raise ValueError(
                f'dopants[{i}]: fractions must be finite numbers in [0,1].'
            )
        if formula == 'ZrO2' and dopant.get('element') == 'Y':
            if a >= MAX_YSZ_Y_ATOMIC_FRACTION:
                raise ValueError('YSZ: Y atomic fraction is outside ZrO2/Y2O3 model.')
            x = 3 * a / (2 * (1 - a))
            _, expected_mass = ysz_fractions(x)
            if not math.isclose(w, expected_mass, rel_tol=1e-6, abs_tol=1e-8):
                raise ValueError(
                    f'dopants[{i}]: Y fractions disagree for ZrO2/Y2O3. '
                    'Choose the YSZ mol-% Y2O3 concentration definition in the GUI.'
                )


def merge_original_subsections(base, additions):
    """Use original m_defs only; never copy identity or lifecycle metadata."""
    if not isinstance(additions, dict):
        raise ValueError('subsections must be a JSON object.')
    available = CrystallineSubstrate.m_def.all_sub_sections
    if set(additions) - set(available):
        raise ValueError(
            'Unknown or forbidden subsection(s): '
            + ', '.join(sorted(set(additions) - set(available)))
        )
    validate_dopant_fractions(base, additions)
    # Reference import may not silently override the three visible hkl fields.
    crystal = additions.get('crystal_properties')
    if isinstance(crystal, dict):
        imported_hkl = (crystal.get('surface_orientation') or {}).get('hkl_reciprocal')
        current_hkl = (
            (base.get('crystal_properties') or {})
            .get('surface_orientation', {})
            .get('hkl_reciprocal')
        )
        if imported_hkl is not None and imported_hkl != current_hkl:
            raise ValueError(
                'Reference hkl differs from the visible orientation inputs. '
                'Update the three hkl fields in the form.'
            )
    for key, value in additions.items():
        if value is None:
            continue
        subsection = available[key]
        section_cls = subsection.sub_section.section_cls
        if subsection.repeats:
            if not isinstance(value, list):
                raise ValueError(f'{key} must be a JSON array.')
            for item in value:
                _validate_section_tree(item, section_cls, key)
        else:
            _validate_section_tree(value, section_cls, key)
        if key == 'crystal_properties':
            # Add scalar crystal properties without deleting the existing
            # hkl/miscut from the three dedicated typed inputs.
            prior = base.get(key) or {}
            merged = {**prior, **value}
            for nested in ('surface_orientation', 'miscut'):
                if isinstance(prior.get(nested), dict) and isinstance(
                    value.get(nested), dict
                ):
                    merged[nested] = {**prior[nested], **value[nested]}
            base[key] = merged
        else:
            base[key] = value
    return base


@app.post('/api/preview')
async def preview_substrate_batch(data: SubstrateIntakePreview):
    try:
        # A reference is an ordinary single SubstrateMbe entry with "reference"
        # in the existing Charge / Batch ID. No extra identifier or new schema.
        is_reference = 'reference' in data.charge.casefold()
        if is_reference and data.count != 1:
            raise ValueError(
                'A charge marked reference requires exactly one substrate. '
                'Set Number of substrates to 1.'
            )
        formula = validate_chemical_formula(data.material)
        if data.material_preset not in ('', '8ysz'):
            raise ValueError('Unknown material preset.')
        if data.material_preset == '8ysz' and formula != 'ZrO2':
            raise ValueError('8YSZ preset requires host chemical formula ZrO2.')
        orientation = parse_orientation(data.orientation)
        if orientation is None:
            raise ValueError('Surface orientation (h k l) is required.')
        material_id = '8YSZ' if data.material_preset == '8ysz' else formula
        if not data.charge.strip() or not data.extended_charge.strip():
            raise ValueError('Charge ID and Extended Charge ID are required.')
        combined_charge = (
            safe_id_part(data.charge) + '_' + safe_id_part(data.extended_charge)
        )
        if not all((safe_id_part(data.charge), safe_id_part(data.extended_charge))):
            raise ValueError('Both charge IDs must contain valid characters.')
        crystal_id = derived_crystal_id(material_id, orientation, data.letter)
        lab_id = batch_lab_id(
            data.supplier_id,
            combined_charge,
            material_id,
            orientation,
            data.letter,
        )
        offcut = parse_offcut_direction(data.offcut_direction)
        if data.offcut_angle is not None:
            if not math.isfinite(data.offcut_angle) or data.offcut_angle < 0:
                raise ValueError(
                    'Offcut angle must be a non-negative number in degrees.'
                )
            if data.offcut_angle > 0 and offcut is None:
                raise ValueError(
                    'Specify offcut direction (h k l) for a nonzero offcut.'
                )
        if offcut is not None and data.offcut_angle is None:
            raise ValueError(
                'Specify offcut angle in degrees for the offcut direction.'
            )
        if data.count < 1:
            raise ValueError('Number of substrates must be at least one.')
        geometry = parse_geometry(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # The existing, unchanged SubstrateBatchMbe normalizer creates physical
    # SubstrateMbe entries and stores their references on the batch.
    # All identifiers and polishing already have their own original quantities.
    # Free-text description is exclusively for user-supplied notes.
    base_data = {
        'm_def': 'pdi_nomad_plugin.mbe.materials.SubstrateMbe',
        'crystal_id': crystal_id,
        'charge_id': combined_charge,
        'supplier': data.supplier.strip(),
        'supplier_id': data.supplier_id.strip(),
        'components': [
            {
                'm_def': 'nomad.datamodel.metainfo.basesections.v1.PureSubstanceComponent',
                'mass_fraction': 1.0,
                'pure_substance': {
                    'm_def': 'nomad.datamodel.metainfo.basesections.v1.PureSubstanceSection',
                    'molecular_formula': formula,
                },
            }
        ],
        'crystal_properties': {
            'surface_orientation': {'hkl_reciprocal': orientation},
        },
        'geometry': geometry,
    }
    if data.notes.strip():
        base_data['description'] = data.notes.strip()
    if data.delivery_date is not None:
        # Original SubstrateMbe.delivery_date is a NOMAD Datetime quantity.
        # A date-only label is represented as midnight UTC, explicitly.
        base_data['delivery_date'] = datetime.combine(
            data.delivery_date, time.min, tzinfo=timezone.utc
        ).isoformat()
    if data.polishing.strip():
        if data.polishing not in ('Single-side', 'Double-side', 'other', 'none'):
            raise HTTPException(status_code=422, detail='Unsupported polishing value.')
        base_data['polishing'] = data.polishing
    if offcut is not None and data.offcut_angle is not None:
        base_data['crystal_properties']['miscut'] = {
            'cartesian_miscut': {
                'reference_orientation': {
                    'hkl_reciprocal': offcut,
                    'angle': data.offcut_angle,
                },
            },
        }

    try:
        merge_original_subsections(base_data, data.subsections)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Pre-populate the host's Zr/O fractions of the COMPLETE YSZ system.
    # The original Dopant normalizer appends Y to results.material itself.
    # Therefore, adding Y here too would double-count the dopant.
    try:
        apply_ysz_host_composition(base_data, formula, data.material_preset)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Only the ORIGINAL PDI batch root is permitted. No custom normalizer is
    # executed during preview; the installed NOMAD parser triggers it on upload.
    from pdi_nomad_plugin.mbe.lab_library.original_preflight import (
        assert_upstream_normalizer,
    )

    assert_upstream_normalizer(CrystallineSubstrate)

    from nomad.datamodel.data import EntryData
    from nomad.datamodel.datamodel import EntryArchive

    from pdi_nomad_plugin.mbe.materials import SubstrateBatchMbe, SubstrateMbe

    if not (
        issubclass(SubstrateBatchMbe, SubstrateMbe)
        and issubclass(SubstrateBatchMbe, EntryData)
    ):
        raise HTTPException(500, 'Existing PDI batch is not a SubstrateMbe EntryData.')
    batch_data = {
        **base_data,
        'm_def': SubstrateBatchMbe.m_def.qualified_name(),
        'name': lab_id,
        'lab_id': lab_id,
        'number_of_substrates': data.count,
        'trigger_create_substrate': True,
    }
    batch_filename = safe_id_part(lab_id) + '.SubstrateBatch.archive.json'

    # These names MUST agree exactly with the unmodified normalizer, which
    # writes "{self.lab_id}_{index}.Substrate.archive.yaml" through create_archive.
    expected_children = [
        {
            'lab_id': f'{lab_id}_{index}',
            'filename': f'{lab_id}_{index}.Substrate.archive.yaml',
        }
        for index in range(1, data.count + 1)
    ]

    try:
        allowed = (
            set(SubstrateBatchMbe.m_def.all_quantities)
            | set(SubstrateBatchMbe.m_def.all_sub_sections)
            | {'m_def'}
        )
        extra = set(batch_data) - allowed
        if extra:
            raise ValueError(f'Unsupported batch fields: {sorted(extra)}')
        section = SubstrateBatchMbe.m_from_dict(batch_data)
        if not isinstance(EntryArchive(data=section).data, EntryData):
            raise ValueError('Batch archive.data is not EntryData')
        if section.number_of_substrates != data.count:
            raise ValueError('Batch count was not preserved by original schema')
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f'Existing SubstrateBatchMbe validation failed: {exc}',
        ) from exc

    return {
        'batch_lab_id': lab_id,
        'archives': [{'filename': batch_filename, 'data': batch_data}],
        'expected_children': expected_children,
        'expected_substrate_count': data.count,
        'upload_supported': True,
        'root_is_entrydata': True,
        'schema': SubstrateBatchMbe.m_def.qualified_name(),
        'reason': 'Existing unchanged SubstrateBatchMbe normalizer creates children.',
    }


@app.get('/api/property-options')
async def physical_property_options():
    """Read actual original MEnum values, never hard-code nonexistent options."""
    from nomad_material_processing.general import (
        ElectronicProperties,
        SubstrateCrystalProperties,
    )

    def values(section_cls, quantity_name):
        quantity = section_cls.m_def.all_quantities[quantity_name]
        enum = quantity.type
        raw = getattr(enum, 'm_enum', None)
        if raw is None:
            raw = getattr(enum, 'm_values', None)
        if raw is None:
            try:
                raw = list(enum)
            except (TypeError, ValueError):
                raw = []
        return [str(item) for item in raw if str(item)]

    return {
        'bravais_lattices': values(SubstrateCrystalProperties, 'bravais_lattices'),
        'conductivity_type': values(ElectronicProperties, 'conductivity_type'),
    }


@app.get('/', response_class=HTMLResponse)
async def index():
    html = """
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Substrate Check-in</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                background: #f5f6f8;
                color: #222;
            }

            .page {
                max-width: 1500px;
                margin: 0 auto;
                padding: 24px;
            }

            h1 {
                margin-top: 0;
            }

            .layout {
                display: grid;
                grid-template-columns: 1fr 1.4fr 1fr;
                gap: 20px;
                align-items: start;
            }

            .card {
                background: white;
                border: 1px solid #d9dde3;
                border-radius: 8px;
                padding: 18px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            }

            .card h2 {
                margin-top: 0;
                font-size: 18px;
            }

            label {
                display: block;
                margin-top: 12px;
                margin-bottom: 4px;
                font-size: 13px;
                font-weight: bold;
            }

            input, textarea, select {
                width: 100%;
                box-sizing: border-box;
                padding: 8px 10px;
                border: 1px solid #bfc5cc;
                border-radius: 5px;
                font-size: 14px;
            }

            textarea {
                min-height: 90px;
                resize: vertical;
            }

            button {
                padding: 9px 14px;
                border: 0;
                border-radius: 5px;
                cursor: pointer;
                font-size: 14px;
            }

            .primary {
                background: #1976d2;
                color: white;
            }

            .secondary {
                background: #eceff3;
                color: #222;
            }

            .upload-box {
                border: 2px dashed #b7bec8;
                border-radius: 8px;
                padding: 24px;
                text-align: center;
                background: #fafbfc;
            }

            .preview {
                margin-top: 12px;
                max-height: 520px;
                overflow-y: auto;
                border: 1px solid #e0e3e7;
                border-radius: 6px;
                background: #fafafa;
            }

            .preview-item {
                padding: 8px 10px;
                border-bottom: 1px solid #e3e6ea;
                font-family: monospace;
                font-size: 13px;
            }

            .preview-item:last-child {
                border-bottom: none;
            }

            .summary {
                padding: 10px;
                background: #eef4fb;
                border-radius: 6px;
                margin-bottom: 12px;
                font-size: 13px;
            }

            .small {
                font-size: 12px;
                color: #666;
            }

            /* Soft warning style for the 'select a target upload' hint. */
            .warning {
                font-size: 12px;
                color: #8a5a00;
                background: #fff3cd;
                border: 1px solid #ffe69c;
                border-radius: 6px;
                padding: 6px 10px;
                display: inline-block;
            }

            /* SUBSTRATE CHECK-IN GUIDANCE */




            .field-number {
                color: #c62828;
                font-weight: 800;
                margin-right: 3px;
            }

            .triplet { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
            .triplet input { min-width: 0; }

            .reference-picker {
                margin: 12px 0 16px;
                padding: 12px;
                background: #f8fafc;
                border: 1px solid #d9dde3;
                border-radius: 8px;
            }
            .reference-picker h3 { margin: 0 0 6px; font-size: 15px; }
            .reference-picker label { margin-top: 8px; }
            .reference-picker-row { display: flex; gap: 6px; align-items: stretch; }
            .reference-picker-row select { flex: 1; min-width: 0; }
            .reference-refresh { flex: 0 0 38px; padding: 6px; }

            #polishing {
                width: 100%;
                box-sizing: border-box;
                padding: 10px 12px;
                border: 1px solid #cfd4dc;
                border-radius: 6px;
                background: white;
            }

</style>
    </head>

    <body>
        <div class="page">
            <h1>Substrate Check-in</h1>
            <p>
                Create a substrate batch and preview the individual
                substrate entries.
            </p>

            <div class="layout">

                <div class="card">
                    <h2>1. Box label</h2>

                    <div class="reference-picker" id="pdiReferencePicker">
                        <h3>Sample Property Reference</h3>


                        <div class="reference-picker-row">
                            <select id="samplePropReference" onchange="pdiIntakeApplyReference()">
                                <option value="">Loading references...</option>
                            </select>
                            <button type="button" class="secondary reference-refresh"
                                title="Reload available references" aria-label="Reload reference list"
                                onclick="pdiIntakeLoadReferences()">↻</button>
                        </div>
                        <p id="samplePropStatus" class="small" role="status">References load automatically.</p>
                    </div>

                    <div class="upload-box">
    <p><strong>Substrate box image</strong></p>

    <button id="browseBoxImage" class="secondary" type="button">
        Browse Image
    </button>

    <span id="boxPhotoFilename" class="small"></span>

    <input id="boxPhoto" type="file"
        accept=".jpg,.jpeg,.png,image/jpeg,image/png"
        style="display:none">

    <img id="boxPhotoPreview"
        alt="Selected substrate box photo"
        style="display:block;max-width:100%;max-height:420px;
               object-fit:contain;margin:8px 0">

    <p class="small">
        Draw a rectangle around the label text.
    </p>

    <div style="display:flex;gap:8px;justify-content:center;margin:8px 0">
        <button id="extractBoxData" class="secondary"
            type="button" disabled>
            Extract Data
        </button>
    </div>

    <p id="boxOcrStatus" class="small" role="status"></p>

    <style>
        #boxOcrResults {display:none!important}
    </style>

    <div id="boxOcrResults" style="display:none">
        <pre id="boxOcrFields"></pre>
        <pre id="boxOcrRawText"></pre>
    </div>

    <label for="informationSheet">Information Sheet</label>
                        <button id="browseInformationSheet" type="button"
                            class="secondary">Choose File</button>
                        <span id="informationSheetFilename" class="small"></span>
                        <input id="informationSheet" type="file"
                            accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" style="display:none">
                        <p class="small">
                            Files are stored once per batch in NOMAD.
                            All generated substrates reference the same files.
                        </p>
                    </div>






                    <figure style="margin:16px 0 0;">
                        <img
                            src="static/substrate_box_reference.png"
                            alt="Substrate box with numbered red markings"
                            style="width:100%;height:auto;border-radius:10px;"
                        >
                        <figcaption class="small">
                            Numbers 1-5 correspond to the batch data fields.
                        </figcaption>
                    </figure>

                    <p class="small" style="margin-top:16px;">
                        Expected label information:
                        supplier, material, orientation, offcut,
                        batch/charge ID and substrate count.
                    </p>
                </div>


                <div class="card">
                    <h2>2. Batch data</h2>

                    <label for="supplier">
                        <span class="field-number">1.</span> Supplier
                    </label>
                    <input id="supplier" placeholder="e.g. CrysTec">

                    <label for="supplier_id">
                        <span class="field-number">1.</span> Supplier ID
                    </label>
                    <input id="supplier_id" placeholder="e.g. CTC">

                    <label for="material">Material / Crystal (chemical formula)</label>
                    <select id="material" onchange="updateMaterialFields(); updatePreview()">
                        <option value="">Select substrate material...</option>
                        <option value="SrTiO3">SrTiO3</option>
                        <option value="GdScO3">GdScO3</option>
                        <option value="DyScO3">DyScO3</option>
                        <option value="LaAlO3">LaAlO3</option>
                        <option value="KTaO3">KTaO3</option>
                        <option value="BaSnO3">BaSnO3</option>
                        <option value="LaInO3">LaInO3</option>
                        <option value="Al2O3">Al2O3</option>
                        <option value="ZrO2">ZrO2</option>
                        <option value="8ysz">8YSZ (ZrO2 + 8 mol-% Y2O3)</option>
                        <option value="MgO">MgO</option>
                        <option value="Si">Si</option>
                        <option value="other">Other (enter formula)</option>
                    </select>
                    <div id="otherMaterialFields" style="display:none">
                        <label for="other_material">Chemical formula</label>
                        <input id="other_material" placeholder="e.g. Sr2FeMoO6">
                        <p class="small">Real element symbols only; names or abbreviations need a documented formula.</p>
                    </div>

                    <label>Surface orientation (h k l, optional letter)</label>
                    <div class="triplet" role="group" aria-label="Surface orientation Miller indices">
                        <input id="h_index" type="number" step="1" placeholder="h, e.g. 0" aria-label="h" required>
                        <input id="k_index" type="number" step="1" placeholder="k, e.g. 0" aria-label="k" required>
                        <input id="l_index" type="number" step="1" placeholder="l, e.g. 1" aria-label="l" required>
                        <input id="letter" type="text" maxlength="1" placeholder="Letter" aria-label="Letter (optional)" style="text-transform:uppercase">
                    </div>
                    <label for="crystal_id">Crystal ID (automatic)</label>
                    <output id="crystal_id_display">Select material and orientation</output>
                    <input id="crystal_id" type="hidden">
                    <p class="small">Three separate indices, including negative and multi-digit values.</p>

                    <label for="offcut_angle">Offcut angle (°)</label>
                    <input id="offcut_angle" type="number" step="any" min="0" placeholder="e.g. 0.1">

                    <label>Offcut reference orientation (h k l, reciprocal space)</label>
                    <div class="triplet" role="group" aria-label="Offcut direction indices">
                        <input id="u_index" type="number" step="1" placeholder="h, e.g. 1" aria-label="Offcut h">
                        <input id="v_index" type="number" step="1" placeholder="k, e.g. 0" aria-label="Offcut k">
                        <input id="w_index" type="number" step="1" placeholder="l, e.g. 0" aria-label="Offcut l">
                    </div>

                    <label for="charge">
                        <span class="field-number">3.</span> Charge / Batch ID
                    </label>
                    <input id="charge" placeholder="e.g. 0228/0025/25" required>

                    <label for="extended_charge">
                        Extended Charge ID
                    </label>
                    <input id="extended_charge" placeholder="e.g. P46310" required>

                    <label for="polishing">
                        <span class="field-number">4.</span> Polishing
                    </label>
                    <select id="polishing">
                        <option value="">Select polishing...</option>
                        <option value="Single-side">Single-side</option>
                        <option value="Double-side">Double-side</option>
                        <option value="other">other</option>
                        <option value="none">none</option>
                    </select>

                    <label for="delivery_date">Delivery date</label>
                    <input id="delivery_date" type="date" required>
                    <p class="small">Date only; stored in NOMAD as 00:00 UTC.</p>

                    <label for="geometry_shape">Substrate geometry</label>
                    <select id="geometry_shape"
                            onchange="updateGeometryFields(); updatePreview()">
                        <option value="rectangle">Rectangle / square</option>
                        <option value="circle">Full circular wafer</option>
                        <option value="circular_sector">Circular wafer sector</option>
                    </select>
                    <div id="rectGeometryFields">
                        <label for="width_mm">Width [mm]</label>
                        <input id="width_mm" type="number" step="any" min="0"
                            placeholder="e.g. 10">

                        <label for="length_mm">Length [mm]</label>
                        <input id="length_mm" type="number" step="any" min="0"
                            placeholder="e.g. 10">
                    </div>

                    <div id="roundGeometryFields" style="display:none">
                        <label for="radius_mm">Radius [mm] (2-inch wafer: 25.4)</label>
                        <input id="radius_mm" type="number" step="any" min="0"
                            value="25.4">

                        <div id="sectorAngleFields" style="display:none">
                            <label for="sector_angle_deg">Sector angle [degrees]</label>
                            <input id="sector_angle_deg" type="number" step="any"
                                min="0" max="360" value="90">
                        </div>
                    </div>

                    <label for="thickness_mm">Thickness [mm]</label>
                    <input id="thickness_mm" type="number" step="any" min="0"
                        placeholder="e.g. 0.5">

                    <p class="small">To create a property reference, enter
                      "reference" in the existing Charge / Batch ID. The batch
                      then contains exactly one substrate.</p>

                    <label for="count">
                        <span class="field-number">5.</span> Number of substrates
                    </label>
                    <input
                        id="count"
                        type="number"
                        min="1"
                        value="10"
                        oninput="updatePreview()"
                    >

                    <label for="notes">Notes</label>
                    <textarea id="notes"></textarea>
                        <div class="physical-properties" id="pdiPhysicalProperties">
                            <h3>Original substrate properties</h3>
                            <p class="small">Physical values are saved using the existing NOMAD
                            quantities and their native units. Chemical composition is derived
                            from the selected material formula; do not enter it again.</p>
                            <h4>Crystal properties</h4>
                            <label for="phys_bravais">Bravais lattice (original NOMAD enum)</label>
                            <select id="phys_bravais"><option value="">Not specified</option></select>
                            <p class="small">Surface orientation, miscut and geometry are edited above.</p>
                            <h4>Electronic properties</h4>
                            <label for="phys_conductivity">Conductivity type</label>
                            <select id="phys_conductivity"><option value="">Not specified</option></select>
                            <label for="phys_carrier_density">Carrier density [cm⁻³]</label>
                            <input id="phys_carrier_density" type="number" min="0" step="any" placeholder="optional">
                            <label for="phys_carrier_deviation">Carrier-density uncertainty [m⁻³]</label>
                            <input id="phys_carrier_deviation" type="number" min="0" step="any" placeholder="optional">
                            <label for="phys_resistivity">Electrical resistivity [Ω·m]</label>
                            <input id="phys_resistivity" type="number" min="0" step="any" placeholder="optional">
                            <h4>Dopants</h4>
                            <div id="pdiDopantRows"></div>
                            <button class="secondary" type="button" onclick="pdiIntakeAddDopant()">+ Add dopant</button>
                            <p class="small">Dopant concentration is entered in cm⁻³; the original
                            schema stores m⁻³. Conversion is automatic.</p>
                            <p class="small"><strong>Schema limitation:</strong> Mass density and
                            lattice parameters (a, b, c) are not quantities of the original
                            SubstrateCrystalProperties schema in the current NOMAD environment.
                            They cannot be stored here until an existing compatible original
                            section or reference mapping is verified. No custom schema is added.</p>
                        </div>


                </div>


                <div class="card">
                    <h2>3. Archive preview</h2>

                    <label for="targetUpload">Target upload</label>
                    <select id="targetUpload">
                        <option value="">Loading uploads...</option>
                    </select>
                    <p id="uploadStatus" class="small">
                        Loading unpublished NOMAD uploads...
                    </p>

                    <div class="summary">
                        <strong>Substrate group:</strong><br>
                        <span id="batchPreview">Individual original NOMAD substrates</span>
                    </div>

                    <div>
                        <strong>Individual SubstrateMbe archives (existing original PDI schema)</strong>
                    </div>

                    <div id="childPreview" class="preview"></div>
                    <button
                        class="secondary"
                        type="button"
                        style="margin-top:16px; width:100%;"
                        onclick="previewArchive()"
                    >
                        Preview NOMAD archive
                    </button>

                    <pre
                        id="archiveJson"
                        style="
                            margin-top:12px;
                            padding:10px;
                            background:#111;
                            color:#eee;
                            border-radius:6px;
                            overflow:auto;
                            max-height:360px;
                            font-size:12px;
                            white-space:pre-wrap;
                        "
                    >No archive preview yet.</pre>

                    <button
                        id="saveButton"
                        class="primary"
                        type="button"
                        style="margin-top:12px; width:100%;"
                        onclick="saveToNomad()"
                        disabled
                    >
                        Upload a Substrate Batch and generate substrates
                    </button>

                    <p id="saveStatus" class="small">
                        Select an unpublished upload. Staging storage is checked before saving.
                    </p>
                </div>

            </div>
        </div>
        <script src="static/intake_reference.js?v=10"></script>
        <script src="static/ocr/tesseract.min.js?v=7"></script>
        <script src="static/intake_box_ocr.js?v=8"></script>
        <script src="static/intake_upload_feedback.js?v=8"></script>
        <script src="static/intake_duplicate_guard.js?v=10"></script>
        <script>
            function nomadApiBase() {
            if (window.NOMAD_API_BASE) { return window.NOMAD_API_BASE; }
            const pathname = window.location.pathname;
            const markers = ['/gui/', '/dashboards/'];

            for (const marker of markers) {
                const index = pathname.indexOf(marker);
                if (index >= 0) {
                    return pathname.slice(0, index) + '/api/v1';
                }
            }
                return '/api/v1'; // deployed at root
            }

            function cleanPart(value) {
                return (value || '').trim().normalize('NFKD')
                    .replace(/[\\s/\\\\]+/g, '-')
                    .replace(/[^A-Za-z0-9._-]+/g, '-')
                    .replace(/-+/g, '-')
                    .replace(/^[-_.]+|[-_.]+$/g, '');
            }

            function updateMaterialFields() {
                const other = document.getElementById('material').value === 'other';
                document.getElementById('otherMaterialFields').style.display = other ? '' : 'none';
            }

            function readIndices(ids) {
                const parts = ids.map(function(id) { return document.getElementById(id).value.trim(); });
                if (parts.every(function(value) { return value === ''; })) return '';
                return parts.join(' ');
            }

            function updatePreview() {
                const supplierId = cleanPart(
                    document.getElementById('supplier_id').value
                );
                const chargePrimary = cleanPart(
                    document.getElementById('charge').value
                );
                const chargeExtended = cleanPart(
                    document.getElementById('extended_charge').value
                );
                const charge = [chargePrimary, chargeExtended]
                    .filter(Boolean).join('_');

                const countInput = document.getElementById('count');
                const preview = document.getElementById('childPreview');
                const batchPreview = document.getElementById('batchPreview');

                const isSingle = /reference/i.test(document.getElementById('charge').value);
                countInput.disabled = isSingle;
                if (isSingle && countInput.value !== '1') countInput.value = '1';
                let count = parseInt(countInput.value || '0', 10);

                if (count < 0 || Number.isNaN(count)) {
                    count = 0;
                }

                const materialValue = document.getElementById('material').value;
                const material = cleanPart(
                    materialValue === '8ysz' ? '8YSZ' :
                    materialValue === 'other'
                        ? document.getElementById('other_material').value
                        : materialValue
                );
                const hkl = ['h_index', 'k_index', 'l_index'].map(
                    id => document.getElementById(id).value.trim()
                );
                const validHkl = hkl.every(v => /^[+-]?\\d+$/.test(v)) &&
                    hkl.some(v => Number(v) !== 0);

                let crystalId = '';
                if (material && validHkl) {
                    const indices = hkl.map(Number);
                    const orientationId = indices.every(n => Math.abs(n) < 10)
                        ? indices.map(String).join('')
                        : indices.map((n, i) =>
                            ['h', 'k', 'l'][i] + String(n)).join('_');
                    const letter = document.getElementById('letter').value
                        .trim().toUpperCase();
                    crystalId = material + '_' + orientationId + letter;
                }

                document.getElementById('crystal_id').value = crystalId;
                document.getElementById('crystal_id_display').textContent =
                    crystalId || 'Select material and orientation';

                const batchName = [supplierId, crystalId, charge]
                    .filter(Boolean).join('_');

                batchPreview.textContent = batchName;
                batchPreview.title = batchName;
                preview.innerHTML = '';

                for (let i = 1; i <= count; i++) {
                    const item = document.createElement('div');
                    item.className = 'preview-item';
                    item.textContent = batchName + '_' + i;
                    item.title = batchName + '_' + i;
                    preview.appendChild(item);
                }
            }

            [
                'supplier',
                'supplier_id',
                'material',
                'other_material',
                'crystal_id',
                'charge',
                'extended_charge',
                'h_index',
                'k_index',
                'l_index',
                'letter',
                'count'
            ].forEach(function(id) {
                document
                    .getElementById(id)
                    .addEventListener('input', updatePreview);
            });

            function buildPayload() {
                return {
                    supplier: document.getElementById('supplier').value,
                    supplier_id: document.getElementById('supplier_id').value,
                    material: document.getElementById('material').value === '8ysz'
                        ? 'ZrO2'
                        : document.getElementById('material').value === 'other'
                            ? document.getElementById('other_material').value
                            : document.getElementById('material').value,
                    material_preset: document.getElementById('material').value === '8ysz'
                        ? '8ysz' : '',
                    crystal_id: document.getElementById('crystal_id').value,
                    letter: document.getElementById('letter').value.trim().toUpperCase(),
                    charge: document.getElementById('charge').value,
                    extended_charge: document.getElementById('extended_charge').value,
                    polishing: document.getElementById('polishing').value,
                    delivery_date: document.getElementById('delivery_date').value || null,
                    orientation: readIndices(['h_index', 'k_index', 'l_index']),
                    offcut_angle: document.getElementById('offcut_angle').value
                        ? parseFloat(document.getElementById('offcut_angle').value)
                        : null,
                    offcut_direction: readIndices(['u_index', 'v_index', 'w_index']),
                    width_mm: document.getElementById('width_mm').value === ''
                        ? null : Number(document.getElementById('width_mm').value),
                    length_mm: document.getElementById('length_mm').value === ''
                        ? null : Number(document.getElementById('length_mm').value),
                    geometry_shape: document.getElementById('geometry_shape').value,
                    radius_mm: document.getElementById('radius_mm').value === ''
                        ? null : Number(document.getElementById('radius_mm').value),
                    thickness_mm: document.getElementById('thickness_mm').value === ''
                        ? null : Number(document.getElementById('thickness_mm').value),
                    sector_angle_deg:
                        document.getElementById('sector_angle_deg').value === ''
                            ? null
                            : Number(document.getElementById('sector_angle_deg').value),
                    count: parseInt(
                        document.getElementById('count').value || '1',
                        10
                    ),
                    notes: document.getElementById('notes').value,
                    subsections: window.pdiIntakeReadSubsections()
                };
            }

            // Clears the form back to defaults after a successful save,
            // so the next substrate batch can be entered right away.
            function updateGeometryFields() {
                const shape = document.getElementById('geometry_shape').value;
                document.getElementById('rectGeometryFields').style.display =
                    shape === 'rectangle' ? '' : 'none';
                document.getElementById('roundGeometryFields').style.display =
                    shape === 'rectangle' ? 'none' : '';
                document.getElementById('sectorAngleFields').style.display =
                    shape === 'circular_sector' ? '' : 'none';
            }

            function resetForm() {
                document.getElementById('supplier').value = '';
                document.getElementById('supplier_id').value = '';
                document.getElementById('material').value = '';
                document.getElementById('other_material').value = '';
                updateMaterialFields();
                document.getElementById('crystal_id').value = '';
                document.getElementById('crystal_id_display').textContent =
                    'Select material and orientation';
                document.getElementById('charge').value = '';
                document.getElementById('extended_charge').value = '';
                document.getElementById('boxPhoto').value = '';
                document.getElementById('informationSheet').value = '';
                window.pdiIntakeClearAttachments?.();
                const pdfName = document.getElementById('informationSheetFilename');
                if (pdfName) pdfName.textContent = '';
                window.pdiIntakeResetBoxOcr();
                document.getElementById('polishing').value = '';
                document.getElementById('delivery_date').value = '';
                ['h_index', 'k_index', 'l_index', 'letter'].forEach(function(id) {
                    document.getElementById(id).value = '';
                });
                document.getElementById('offcut_angle').value = '';
                ['u_index', 'v_index', 'w_index'].forEach(function(id) {
                    document.getElementById(id).value = '';
                });
                document.getElementById('width_mm').value = '';
                document.getElementById('length_mm').value = '';
                document.getElementById('geometry_shape').value = 'rectangle';
                document.getElementById('radius_mm').value = '25.4';
                document.getElementById('thickness_mm').value = '';
                document.getElementById('sector_angle_deg').value = '90';
                updateGeometryFields();
                document.getElementById('count').value = '10';
                document.getElementById('count').disabled = false;
                document.getElementById('notes').value = '';
                window.pdiIntakeResetPhysicalProperties();
                window.pdiIntakeResetImportOrigins();
                updatePreview();
                for (const id of ['phys_bravais', 'phys_conductivity']) {
                    const field = document.getElementById(id);
                    field.value = '';
                    delete field.dataset.pdiFieldOrigin;
                    delete field.dataset.pdiDefaultApplied;
                }
                if (window.pdiIntakeApplyPhysicalDefaults) {
                    window.pdiIntakeApplyPhysicalDefaults();
                }

            }

            async function previewArchive() {
                const output = document.getElementById('archiveJson');
                output.textContent = 'Loading...';

                try {
                    const payload = buildPayload();
                    const response = await fetch('api/preview', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify(payload)
                    });

                    if (!response.ok) {
                        const failure = await response.json().catch(function() { return {}; });
                        throw new Error(failure.detail ||
                            'Preview request failed: ' + response.status);
                    }

                    const data = await response.json();
                    output.textContent = JSON.stringify(data, null, 2);
                } catch (error) {
                    output.textContent = 'Error: ' + error.message;
                }
            }

            async function verifyRawAttachment(base, filename) {
                const response = await fetch(
                    base + '/rawdir/' + encodeURIComponent(filename),
                    {cache: 'no-store'}
                );
                const result = response.ok
                    ? await response.json().catch(() => ({}))
                    : {};
                if (!response.ok || !result.file_metadata) {
                    throw new Error(
                        'Attachment missing in NOMAD raw files: ' + filename +
                        ' (HTTP ' + response.status + ').'
                    );
                }
            }

            function selectedBatchFiles(batchLabId) {
                const files = [];
                const prefix = cleanPart(batchLabId);

                if (!prefix) {
                    throw new Error('Invalid batch Lab ID.');
                }

                const categories = [
                    {
                        id: 'boxPhoto',
                        field: 'image',
                        stem: 'box_photo',
                        extensions: ['jpg', 'jpeg', 'png']
                    },
                    {
                        id: 'informationSheet',
                        field: 'information_sheet',
                        stem: 'information_sheet',
                        extensions: ['pdf', 'jpg', 'jpeg', 'png']
                    }
                ];

                for (const category of categories) {
                    const selected = Array.from(
                        document.getElementById(category.id).files
                    );

                    selected.forEach((file, index) => {
                        const ext = file.name
                            .split('.').pop().toLowerCase();

                        const mime = ext === 'pdf'
                            ? 'application/pdf'
                            : ext === 'png'
                                ? 'image/png'
                                : 'image/jpeg';

                        if (
                            !category.extensions.includes(ext) ||
                            (file.type && file.type !== mime) ||
                            !file.size
                        ) {
                            throw new Error(
                                'Invalid attachment: ' + file.name
                            );
                        }

                        // Preserve the original filename in NOMAD.
                        const originalName = file.name;

                        if (
                            !originalName.trim() ||
                            originalName === '.' ||
                            originalName === '..' ||
                            originalName.includes('/') ||
                            originalName.includes(String.fromCharCode(92)) ||
                            [...originalName].some(char =>
                                char.charCodeAt(0) < 32 ||
                                char.charCodeAt(0) === 127
                            )
                        ) {
                            throw new Error(
                                'Invalid attachment filename: ' + originalName
                            );
                        }

                        if (files.some(item =>
                            item.filename.toLowerCase() ===
                            originalName.toLowerCase()
                        )) {
                            throw new Error(
                                'Duplicate attachment filename: ' +
                                originalName
                            );
                        }

                        files.push({
                            field: category.field,
                            file: file,
                            filename: prefix + '_' + category.stem + '_' + String(index + 1).padStart(2, '0') + '_' + originalName,
                            mime: mime,
                            primary: index === 0
                        });
                    });
                }

                return files;
            }

            async function saveToNomad() {
                const uploadId = document.getElementById('targetUpload').value;
                const saveButton = document.getElementById('saveButton');
                const saveStatus = document.getElementById('saveStatus');

                const mandatory = new Map();
                document.querySelectorAll(
                    'input[required], select[required], textarea[required]'
                ).forEach(node => mandatory.set(node.id, node));

                ['supplier', 'supplier_id', 'material', 'charge',
                 'crystal_id', 'delivery_date', 'count'].forEach(id => {
                    const node = document.getElementById(id);
                    if (node) mandatory.set(id, node);
                });

                const missing = [];
                if (!uploadId) missing.push('Target upload');

                for (const [id, node] of mandatory) {
                    if (node.disabled) continue;
                    const empty = node.type === 'checkbox'
                        ? !node.checked
                        : !String(node.value || '').trim();
                    if (!empty) continue;
                    const label = document.querySelector(
                        'label[for="' + id + '"]'
                    );
                    missing.push(label
                        ? label.textContent.trim()
                        : id.replaceAll('_', ' '));
                }

                if (missing.length) {
                    saveStatus.className = 'warning';
                    saveStatus.style.color = '#b00020';
                    saveStatus.textContent =
                        'Missing required fields: ' + missing.join(', ');
                    return;
                }

                saveStatus.className = 'small';

                let payload;
                try {
                    payload = buildPayload();
                } catch (error) {
                    saveStatus.textContent = 'Error: ' + error.message;
                    return;
                }

                const parts = [
                    cleanPart(payload.supplier_id),
                    cleanPart(payload.crystal_id),
                    cleanPart(payload.charge)
                ].filter(Boolean);

                if (parts.length !== 3) {
                    saveStatus.textContent =
                        'Supplier ID, Crystal ID and Charge / Batch ID are required.';
                    return;
                }

                if (!Number.isInteger(payload.count) || payload.count < 1) {
                    saveStatus.textContent =
                        'Number of substrates must be at least 1.';
                    return;
                }

                saveButton.disabled = true;
                saveStatus.textContent = 'Preparing archive...';
                let assetWriteAttempted = false;
                let batchSubmitted = false;
                let batchWriteAttempted = false;
                let submittedUploadId = null;

                try {
                    const previewResponse = await fetch('api/preview', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify(payload)
                    });

                    if (!previewResponse.ok) {
                        const errorBody = await previewResponse.json().catch(
                            () => ({})
                        );
                        const detail = errorBody.detail;
                        throw new Error(typeof detail === 'string'
                            ? detail : JSON.stringify(detail || errorBody));
                    }

                    const preview = await previewResponse.json();

                     if (preview.upload_supported !== true) {
                         throw new Error(preview.reason ||
                             'Original substrate entry root is unverified. No upload was made.');
                     }

                     const archives = preview.archives;
                     const expectedChildren = preview.expected_children;
                     if (!Array.isArray(archives) || archives.length !== 1 ||
                         !Array.isArray(expectedChildren) ||
                         expectedChildren.length !== payload.count ||
                         preview.expected_substrate_count !== payload.count) {
                         throw new Error('Preview must contain one original batch and the expected child IDs.');
                     }
                     const batch = archives[0];
                     if (!batch || !batch.data ||
                         batch.data.m_def !== 'pdi_nomad_plugin.mbe.materials.SubstrateBatchMbe' ||
                         batch.data.trigger_create_substrate !== true ||
                         batch.data.number_of_substrates !== payload.count ||
                         !batch.filename.endsWith('.SubstrateBatch.archive.json')) {
                         throw new Error('Invalid original SubstrateBatchMbe archive. No upload performed.');
                     }
                     const generatedNames = [batch.filename, ...expectedChildren.map(x => x.filename)];
                     if (new Set(generatedNames).size !== generatedNames.length) {
                         throw new Error('Batch or generated child filenames collide.');
                     }


                     const base = nomadApiBase() + '/uploads/' +
                         encodeURIComponent(uploadId);
                     const infoResponse = await fetch(base);
                     if (!infoResponse.ok) {
                         throw new Error('Selected upload is unavailable.');
                     }
                     const infoBody = await infoResponse.json();
                     const info = infoBody.data || infoBody;
                     if (info.published || info.process_running) {
                         throw new Error(
                             'Selected upload is published or currently processing.'
                         );
                     }

                     await window.pdiIntakeDuplicateGuard.assertNoCollision({
                         uploadId: uploadId,
                         apiBase: nomadApiBase(),
                         batchLabId: preview.batch_lab_id,
                         batchFilename: batch.filename,
                         expectedChildren: expectedChildren
                     });

                     const attachments = selectedBatchFiles(preview.batch_lab_id);
                     const manifestFilename = cleanPart(preview.batch_lab_id) + '_attachments.json';
                     const formData = new FormData();
                     for (const attachment of attachments) {
                         if (!attachment.file.size) {
                             throw new Error('Empty attachment: ' + attachment.filename);
                         }
                         if (attachment.primary) {
                             batch.data[attachment.field] = attachment.filename;
                         }
                         formData.append('file', attachment.file, attachment.filename);
                     }
                     const manifest = {
                         format: 'pdi-substrate-attachments-v1',
                         batch_lab_id: preview.batch_lab_id,
                         upload_id: uploadId,
                         batch_archive: batch.filename,
                         attachments: attachments.map(item => ({
                             role: item.field,
                             main: item.primary,
                             original_filename: item.file.name,
                             stored_filename: item.filename,
                             mime_type: item.mime,
                             size_bytes: item.file.size
                         }))
                     };

                     const allNames = [
                         batch.filename,
                         manifestFilename,
                         ...attachments.map(item => item.filename),
                         ...expectedChildren.map(item => item.filename)
                     ];

                     if (new Set(allNames.map(x => x.toLowerCase())).size !==
                         allNames.length) {
                         throw new Error('Upload filename collision.');
                     }

                     for (const name of allNames) {
                         if (new TextEncoder().encode(name).length > 255) {
                             throw new Error(
                                 'Filename exceeds 255 bytes: ' + name
                             );
                         }
                     }

                     for (const name of [
                         manifestFilename,
                         ...attachments.map(item => item.filename)
                     ]) {
                         const response = await fetch(
                             base + '/rawdir/' + encodeURIComponent(name),
                             {cache: 'no-store'}
                         );
                         if (response.ok) {
                             throw new Error('File already exists: ' + name);
                         }
                         if (response.status !== 404) {
                             throw new Error(
                                 'Cannot check filename: ' + name +
                                 ' (HTTP ' + response.status + ')'
                             );
                         }
                     }

                     formData.append(
                         'file',
                         new Blob(
                             [JSON.stringify(manifest, null, 2)],
                             {type: 'application/json'}
                         ),
                         manifestFilename
                     );

                     const batchBlob = new Blob(
                         [JSON.stringify({data: batch.data}, null, 2)],
                         {type: 'application/json'}
                     );
                     formData.append('file', batchBlob, batch.filename);

                     const params = new URLSearchParams({
                         trigger_processing: 'true',
                         overwrite_if_exists: 'false'
                     });

                     saveStatus.textContent = 'Uploading batch and attachments...';
                     batchWriteAttempted = true;
                     submittedUploadId = uploadId;

                     const response = await fetch(
                         base + '/raw/?' + params.toString(),
                         {
                             method: 'PUT',
                             headers: {'Accept': 'application/json'},
                             body: formData
                         }
                     );
                     if (!response.ok) {
                         throw new Error(
                             'NOMAD HTTP ' + response.status + ': ' +
                             (await response.text()).slice(0, 1200)
                         );
                     }

                    // A successful PUT is only transfer acknowledgement. The
                    // original batch normalizer generates children asynchronously;
                    // read back every expected entry before reporting success.
                    batchSubmitted = true;
                    await window.pdiIntakeUploadFeedback.waitForEntries({
                        uploadId: submittedUploadId,
                        apiBase: nomadApiBase(),
                        filenames: [batch.filename].concat(
                            expectedChildren.map(function(child) {
                                return child.filename;
                            })
                        ),
                        statusElement: saveStatus
                    });

                    // Verify that processing retained every attachment.
                    for (const attachment of attachments) {
                        await verifyRawAttachment(base, attachment.filename);
                    }
                    await verifyRawAttachment(base, manifestFilename);

                    resetForm();
                    window.pdiIntakeUploadFeedback.showSuccessAndOpenUpload({
                        statusElement: saveStatus,
                        uploadId: submittedUploadId,
                        batchFile: batch.filename,
                        children: expectedChildren.length
                    });
                } catch (error) {
                    saveStatus.className = 'warning';
                    saveStatus.style.color = '#b00020';
                    saveStatus.textContent = batchWriteAttempted
                        ? 'An upload write was attempted; processing or refresh ' +
                          'could not be confirmed: ' + error.message +
                          ' Do NOT upload again until you inspect NOMAD. '
                        : assetWriteAttempted
                            ? 'An attachment upload was attempted: ' +
                              error.message +
                              ' Inspect NOMAD raw files before retrying. '
                            : 'Error before upload: ' + error.message;
                    if (batchWriteAttempted && submittedUploadId) {
                        saveStatus.appendChild(document.createTextNode(
                            ' Upload ID: ' + submittedUploadId + '.'
                        ));
                    }
                } finally {
                    // Never allow a second submission after the server accepted
                    // the batch: the original normalizer may overwrite children.
                    saveButton.disabled = batchWriteAttempted;
                }
            }

            async function loadUploads() {
                const select = document.getElementById('targetUpload');
                const status = document.getElementById('uploadStatus');

                select.innerHTML =
                    '<option value="">Loading uploads...</option>';
                status.textContent =
                    'Loading unpublished NOMAD uploads...';

                const params = new URLSearchParams();
                params.append('roles', 'main_author');
                params.append('roles', 'coauthor');
                params.append('page_size', '100');

                try {
                    const response = await fetch(
                        nomadApiBase() + '/uploads?' + params.toString()
                    );

                    if (!response.ok) {
                        throw new Error(
                            'Upload request failed: ' + response.status
                        );
                    }

                    const result = await response.json();

                    const uploads = (result.data || []).filter(
                        function(upload) {
                            return !upload.published;
                        }
                    );

                    select.innerHTML =
                        '<option value="">Select target upload...</option>';

                    uploads.forEach(function(upload) {
                        const option = document.createElement('option');
                        option.value = upload.upload_id;

                        const name =
                            upload.upload_name || 'Unnamed upload';
                        const entries =
                            upload.entries !== undefined
                                ? upload.entries
                                : '?';

                        option.textContent =
                            name +
                            ' — ' +
                            upload.upload_id +
                            ' (' +
                            entries +
                            ' entries)';

                        select.appendChild(option);
                    });

                    status.textContent =
                        uploads.length +
                        ' unpublished upload(s) listed; staging checked at save.';
                } catch (error) {
                    select.innerHTML =
                        '<option value="">Could not load uploads</option>';
                    status.textContent =
                        'Error: ' + error.message;
                }
            }

            document
                .getElementById('targetUpload')
                .addEventListener('change', function() {
                    const hasUpload = Boolean(this.value);
                    document.getElementById('saveButton').disabled = !hasUpload;
                    const status = document.getElementById('saveStatus');
                    status.className = hasUpload ? 'small' : 'warning';
                    status.textContent =
                        hasUpload ? 'Ready: validated SubstrateMbe upload.'
                            : 'Choose a writable upload before saving.';
                });

            let intakeRefreshPromise = null;

            function refreshIntakeUploads() {
                if (intakeRefreshPromise) {
                    return intakeRefreshPromise;
                }

                const select = document.getElementById('targetUpload');
                const oldUpload = select.value;

                intakeRefreshPromise = loadUploads().then(function() {
                    if (Array.from(select.options).some(function(opt) {
                        return opt.value === oldUpload;
                    })) {
                        select.value = oldUpload;
                    }

                    document.getElementById('saveButton').disabled = !Boolean(select.value);
                }).finally(function() {
                    intakeRefreshPromise = null;
                });

                return intakeRefreshPromise;
            }

            window.addEventListener('message', function(event) {
                if (event.origin !== window.location.origin ||
                    event.source !== window.parent ||
                    !event.data ||
                    event.data.type !== 'pdi-lab:resume') {
                    return;
                }

                refreshIntakeUploads().catch(function(error) {
                    console.error('Intake refresh failed:', error);
                });
            });

            updatePreview();

            loadUploads().finally(function() {
                if (
                    new URLSearchParams(window.location.search)
                        .get('pdi_lab') === '1' &&
                    window.parent !== window
                ) {
                    window.parent.postMessage(
                        {type: 'pdi-lab:ready', app: 'intake'},
                        window.location.origin
                    );
                }
            });
        </script>
        <script src="static/intake_ysz_dopants.js?v=11"></script>
        <script src="static/intake_ysz_preset.js?v=12"></script>

<script>
document.addEventListener('DOMContentLoaded', function () {
    const photo = document.getElementById('boxPhoto');
    const filename = document.getElementById('boxPhotoFilename');
    const browse = document.getElementById('browseBoxImage');

    browse.addEventListener('click', function () {
        photo.click();
    });

    const pdf = document.getElementById('informationSheet');
    const pdfName = document.getElementById('informationSheetFilename');
    document.getElementById('browseInformationSheet')
        .addEventListener('click', () => pdf.click());
    pdf.addEventListener('change', () => {
        pdfName.textContent = pdf.files.length ? pdf.files[0].name : '';
    });

    function installDefault(id, matches) {
        const field = document.getElementById(id);
        const apply = () => {
            if (field.value || field.dataset.pdiFieldOrigin) return;
            const option = Array.from(field.options).find(option =>
                option.value && matches(
                    (option.value + ' ' + option.textContent).toLowerCase()
                )
            );
            if (option) {
                field.value = option.value;
                field.dataset.pdiDefaultApplied = 'true';
            }
        };
        new MutationObserver(apply).observe(
            field, {childList: true, subtree: true}
        );
        return apply;
    }

    const defaultInsulating = installDefault(
        'phys_conductivity', text => /insulat(?:ing|or)/.test(text)
    );
    const defaultBcc = installDefault(
        'phys_bravais', text =>
            /\bci\b|\bbcc\b/.test(text) ||
            (/cubic/.test(text) && /body/.test(text) &&
             /cent(?:er|re)/.test(text))
    );
    window.pdiIntakeApplyPhysicalDefaults = function () {
        defaultInsulating();
        defaultBcc();
    };
    window.pdiIntakeApplyPhysicalDefaults();

    photo.addEventListener('change', function () {
        filename.textContent = photo.files.length
            ? photo.files[0].name : '';
        imageDataImported = false;
    });

    const select = document.getElementById('samplePropReference');
    let previousSelection = select.value;
    let imageDataImported = false;


    // Multiple files per attachment category.
    // The first file is the primary NOMAD archive reference.
    function installIntakeAttachmentDropZone(
        input, button, filenameElement, label, extensions
    ) {
        const zone = document.createElement('div');
        zone.className = 'pdi-attachment-drop-zone';
        zone.setAttribute('role', 'group');
        zone.setAttribute('aria-label', label);
        zone.style.cssText =
            'border:2px dashed #8798ac;border-radius:12px;' +
            'padding:18px 14px;margin:12px 0 18px;' +
            'min-height:120px;box-sizing:border-box;' +
            'display:flex;flex-direction:column;' +
            'align-items:center;gap:10px;text-align:center;';

        const hint = document.createElement('div');
        hint.textContent = label + ' (multiple files allowed)';

        const list = document.createElement('div');
        list.style.cssText = 'width:100%;text-align:left;';

        button.parentNode.insertBefore(zone, button);
        zone.append(hint, button, filenameElement, input, list);

        filenameElement.style.overflowWrap = 'anywhere';
        input.multiple = true;

        let selected = Array.from(input.files);
        let activeSelection = null;
        let displayOrder = Array.from(input.files);
        let internal = false;

        const isImage = input === photo;
        const mimeTypes = isImage
            ? ['image/jpeg', 'image/png']
            : ['application/pdf', 'image/jpeg', 'image/png'];

        function renderList() {
            list.replaceChildren();

            // Keep file rows in their original visual positions.
            displayOrder = displayOrder.filter(
                file => selected.includes(file)
            );
            for (const file of selected) {
                if (!displayOrder.includes(file)) {
                    displayOrder.push(file);
                }
            }

            if (!selected.includes(activeSelection)) {
                activeSelection = null;
            }

            for (const file of displayOrder) {
                const isMain = selected[0] === file;
                const isSelected = activeSelection === file;

                const row = document.createElement('div');
                row.setAttribute('role', 'button');
                row.setAttribute('aria-pressed', String(isSelected));
                row.tabIndex = 0;

                row.style.cssText =
                    'display:flex;flex-direction:column;gap:4px;' +
                    'margin:6px 0;padding:10px;border-radius:8px;' +
                    'border:2px solid ' +
                    (isSelected ? '#287ac0' : '#c5cbd2') + ';' +
                    'background:' +
                    (isSelected ? 'rgba(40,122,192,0.14)' : 'transparent') + ';' +
                    'cursor:pointer;text-align:left;';

                const name = document.createElement('span');
                name.textContent = file.name;
                name.style.cssText =
                    'font-weight:' + (isMain ? '600' : '400') + ';' +
                    'overflow-wrap:anywhere;';
                row.appendChild(name);

                if (isMain) {
                    const label = document.createElement('span');
                    label.textContent = isImage
                        ? 'MAIN IMAGE · OCR'
                        : 'MAIN SHEET';
                    label.style.cssText =
                        'font-size:11px;font-weight:700;color:#287ac0;';
                    row.appendChild(label);
                }

                function choose() {
                    activeSelection = file;
                    renderList();
                }

                row.addEventListener('click', choose);
                row.addEventListener('keydown', event => {
                    if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        choose();
                    }
                });

                list.appendChild(row);
            }

            // Fixed action area BELOW ALL file rows.
            const actions = document.createElement('div');
            actions.style.cssText =
                'display:flex;gap:8px;flex-wrap:wrap;' +
                'margin:14px 0 4px;';

            const mainButton = document.createElement('button');
            mainButton.type = 'button';
            mainButton.className = 'secondary';
            mainButton.textContent = isImage
                ? 'Set as Main Image'
                : 'Set as Main Sheet';
            mainButton.disabled =
                !activeSelection || activeSelection === selected[0];

            mainButton.addEventListener('click', () => {
                const index = selected.indexOf(activeSelection);
                if (index < 0) return;

                selected.splice(index, 1);
                selected.unshift(activeSelection);
                sync(true);
            });

            const deleteButton = document.createElement('button');
            deleteButton.type = 'button';
            deleteButton.className = 'secondary';
            deleteButton.textContent = isImage
                ? 'Delete Image'
                : 'Delete File';
            deleteButton.disabled = !activeSelection;

            deleteButton.addEventListener('click', () => {
                const index = selected.indexOf(activeSelection);
                if (index < 0) return;

                selected.splice(index, 1);
                activeSelection = null;
                sync(true);
            });

            actions.append(mainButton, deleteButton);
            list.appendChild(actions);
        }

        function sync(emitChange) {
            const transfer = new DataTransfer();

            selected.forEach(file => {
                transfer.items.add(file);
            });

            input.files = transfer.files;

            if (emitChange) {
                internal = true;
                try {
                    input.dispatchEvent(
                        new Event('change', {bubbles: true})
                    );
                } finally {
                    internal = false;
                }
            }

            renderList();

            if (isImage && !selected.length) {
                const preview =
                    document.getElementById('boxPhotoPreview');

                if (preview) {
                    preview.removeAttribute('src');
                    preview.style.display = 'none';
                }

                const extract =
                    document.getElementById('extractBoxData');

                if (extract) extract.disabled = true;

                const status =
                    document.getElementById('boxOcrStatus');

                if (status) status.textContent = '';
            }
        }

        function addFiles(files, emitChange) {
            if (!files.length) return;

            for (const file of files) {
                const ext = '.' +
                    file.name.split('.').pop().toLowerCase();

                if (
                    !extensions.includes(ext) ||
                    (file.type && !mimeTypes.includes(file.type)) ||
                    !file.size
                ) {
                    throw new Error(
                        'Unsupported or empty file: ' + file.name
                    );
                }
            }

            for (const file of files) {
                const exists = selected.some(old =>
                    old.name === file.name &&
                    old.size === file.size &&
                    old.lastModified === file.lastModified
                );

                if (!exists) selected.push(file);
            }

            sync(emitChange);
        }

        // The native picker replaces its own selection.
        // Capture the change before other handlers and merge files.
        input.addEventListener('change', () => {
            if (internal) return;

            try {
                addFiles(Array.from(input.files), false);
            } catch (error) {
                sync(false);
                window.alert(error.message);
            }
        }, true);

        zone.addEventListener('dragover', event => {
            event.preventDefault();

            if (event.dataTransfer) {
                event.dataTransfer.dropEffect = 'copy';
            }

            zone.style.borderColor = '#287ac0';
            zone.style.backgroundColor =
                'rgba(40,122,192,0.09)';
        });

        zone.addEventListener('dragleave', event => {
            if (
                !event.relatedTarget ||
                !zone.contains(event.relatedTarget)
            ) {
                zone.style.borderColor = '#8798ac';
                zone.style.backgroundColor = '';
            }
        });

        zone.addEventListener('drop', event => {
            event.preventDefault();
            event.stopPropagation();

            zone.style.borderColor = '#8798ac';
            zone.style.backgroundColor = '';

            try {
                const transfer = event.dataTransfer;
                let dropped = Array.from(transfer?.files || []);

                // Firefox/browser fallback for file drag sources.
                if (!dropped.length && transfer?.items) {
                    dropped = Array.from(transfer.items)
                        .filter(item => item.kind === 'file')
                        .map(item => item.getAsFile())
                        .filter(Boolean);
                }

                if (!dropped.length) {
                    throw new Error(
                        'No file received. Drop a file from your file manager.'
                    );
                }

                const alreadySelected = dropped.every(file =>
                    selected.some(old =>
                        old.name === file.name &&
                        old.size === file.size &&
                        old.lastModified === file.lastModified
                    )
                );

                if (alreadySelected) {
                    window.alert(
                        'File already selected. No duplicate added.'
                    );
                    return;
                }

                addFiles(dropped, true);
            } catch (error) {
                window.alert(error.message);
            }
        }, true);

        renderList();

        return {
            clear: () => {
                selected = [];
                sync(true);
            }
        };
    }

    const imageAttachments = installIntakeAttachmentDropZone(
        photo,
        browse,
        filename,
        'Drop JPG/PNG images here, or use Browse Image',
        ['.jpg', '.jpeg', '.png']
    );

    const pdfAttachments = installIntakeAttachmentDropZone(
        pdf,
        document.getElementById('browseInformationSheet'),
        pdfName,
        'Drop PDF/JPG/PNG files here, or use Choose File',
        ['.pdf', '.jpg', '.jpeg', '.png']
    );

    window.pdiIntakeClearAttachments = () => {
        imageAttachments.clear();
        pdfAttachments.clear();
    };



    // OCR always takes priority over previously loaded references.
    const originalImport = window.pdiIntakeApplyBoxLabelData;

    if (typeof originalImport === 'function') {
        window.pdiIntakeApplyBoxLabelData = function (data) {
            const result = originalImport.apply(this, arguments);
            imageDataImported = true;
            return result;
        };
    }

    const originalReset = window.pdiIntakeResetBoxOcr;

    if (typeof originalReset === 'function') {
        window.pdiIntakeResetBoxOcr = function () {
            const result = originalReset.apply(this, arguments);
            filename.textContent = '';
            imageDataImported = false;
            return result;
        };
    }

    // Ask before a reference overwrites values imported by OCR.
    document.addEventListener('change', function (event) {
        if (event.target !== select || !select.value) return;

        if (imageDataImported) {
            const approved = window.confirm(
                'Load data from this reference and overwrite values ' +
                'imported from the box image?'
            );

            if (!approved) {
                select.value = previousSelection;
                event.stopImmediatePropagation();
                event.preventDefault();
                return;
            }

            window.__pdiIntakeForceReference = true;

            if (typeof window.pdiIntakeResetImportOrigins === 'function') {
                window.pdiIntakeResetImportOrigins();
            }

            window.setTimeout(function () {
                window.__pdiIntakeForceReference = false;
            }, 1000);
        }

        previousSelection = select.value;
    }, true);

    // Release the overwrite permission after applying the reference.
    const originalPreview = window.updatePreview;

    if (typeof originalPreview === 'function') {
        window.updatePreview = function () {
            const result = originalPreview.apply(this, arguments);

            if (window.__pdiIntakeForceReference === true) {
                window.__pdiIntakeForceReference = false;
                imageDataImported = false;
            }

            return result;
        };
    }
});
</script>

</body>
    </html>
    """
    # FIX: nomadApiBase() used to guess its own deployment base path
    # (/nomad-oasis) by searching window.location.pathname for '/gui/' or
    # '/dashboards/'. That breaks whenever this page is loaded in a context
    # where neither substring is present in the URL (e.g. embedded inside
    # NOMAD GUI v2), causing every API call to 404. The backend always
    # knows the real base path, so inject it directly instead of guessing
    # client-side.
    api_base = config.services.api_base_path.rstrip('/') + '/api/v1'
    injection = f'<script>window.NOMAD_API_BASE = {api_base!r};</script>'
    return html.replace('<script>', injection + '<script>', 1)
