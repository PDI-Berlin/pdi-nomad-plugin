import math
import re
import unicodedata
from pathlib import Path

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
from pydantic import BaseModel

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
    crystal_id: str = ''
    charge: str = ''
    polishing: str = ''
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


def batch_lab_id(supplier_id: str, crystal_id: str, charge_id: str) -> str:
    parts = [safe_id_part(x) for x in (supplier_id, crystal_id, charge_id)]
    if not all(parts):
        raise ValueError('Supplier ID, Crystal ID and Charge ID are required.')
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
    return cls(
        width=width / 1000,
        length=length / 1000,
        height=height / 1000,
    ).m_to_dict(with_meta=True)


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


@app.post('/api/preview')
async def preview_substrate_batch(data: SubstrateIntakePreview):
    try:
        lab_id = batch_lab_id(data.supplier_id, data.crystal_id, data.charge)
        formula = validate_chemical_formula(data.material)
        orientation = parse_orientation(data.orientation)
        if orientation is None:
            raise ValueError('Surface orientation (h k l) is required.')
        offcut = parse_offcut_direction(data.offcut_direction)
        if data.offcut_angle is not None:
            if not math.isfinite(data.offcut_angle) or data.offcut_angle < 0:
                raise ValueError(
                    'Offcut angle must be a non-negative number in degrees.'
                )
            if data.offcut_angle > 0 and offcut is None:
                raise ValueError(
                    'Specify offcut direction [u v w] for a nonzero offcut.'
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

    # There is no verified upstream batch schema that creates child entries.
    # Create one ORIGINAL CrystallineSubstrate archive per physical substrate.
    # The batch grouping exists only in the UI (lab_id prefix), not in metainfo.
    descriptions = [
        f'Crystal ID: {data.crystal_id.strip()}',
        f'Charge ID: {data.charge.strip()}',
    ]
    if data.polishing.strip():
        descriptions.append('Polishing: ' + data.polishing.strip())
    if data.notes.strip():
        descriptions.append(data.notes.strip())

    base_data = {
        'm_def': 'nomad_material_processing.general.CrystallineSubstrate',
        'supplier': data.supplier.strip(),
        'supplier_id': data.supplier_id.strip(),
        'description': '\n'.join(descriptions),
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
    if offcut is not None and data.offcut_angle is not None:
        base_data['crystal_properties']['miscut'] = {
            'cartesian_miscut': {
                'reference_orientation': {
                    'hkl_direct': offcut,
                    'angle': data.offcut_angle,
                },
            },
        }

    # Check the provenance of the real installed implementation. Neither
    # local PDI m_defs nor custom normalizers may enter this workflow.
    from pdi_nomad_plugin.mbe.lab_library.original_preflight import (
        assert_upstream_normalizer,
    )

    assert_upstream_normalizer(CrystallineSubstrate)

    archives = []
    for index in range(1, data.count + 1):
        child_id = f'{lab_id}_{index}'
        child_data = {
            **base_data,
            'name': child_id,
            'lab_id': child_id,
        }
        # Validate against the actual installed NOMAD m_def. No PDI
        # normalizer runs, and no custom schema is imported or used.
        try:
            CrystallineSubstrate.m_from_dict(child_data)
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f'Substrate {child_id}: original-schema validation failed: {exc}',
            ) from exc
        archives.append(
            {
                'filename': child_id + '.archive.json',
                'data': child_data,
            }
        )

    # CrystallineSubstrate is an ORIGINAL ArchiveSection but NOT a verified
    # EntryArchive.data root in the pinned upstream NOMAD runtime. Keep the
    # complete physical-substrate preview, but never offer these as uploadable
    # archives until a legitimate upstream EntryData workflow is established.
    from nomad.datamodel.data import EntryData

    root_supported = issubclass(CrystallineSubstrate, EntryData)
    return {
        'batch_lab_id': lab_id,
        'archives': archives,
        'upload_supported': False,
        'root_is_entrydata': root_supported,
        'reason': 'Original CrystallineSubstrate is not a verified uploadable EntryArchive.data root. No upload was made.',
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

                    <div class="upload-box">
                        <p><strong>Substrate box image</strong></p>
                        <p class="small">
                            Later this will be used for OCR-assisted prefilling.
                        </p>
                        <button class="secondary" type="button">
                            Load from image
                        </button>
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
                        <option value="MgO">MgO</option>
                        <option value="Si">Si</option>
                        <option value="other">Other (enter formula)</option>
                    </select>
                    <div id="otherMaterialFields" style="display:none">
                        <label for="other_material">Chemical formula</label>
                        <input id="other_material" placeholder="e.g. Sr2FeMoO6">
                        <p class="small">Real element symbols only; names or abbreviations need a documented formula.</p>
                    </div>

                    <label for="crystal_id">
                        <span class="field-number">2.</span> Crystal ID
                    </label>
                    <input
                        id="crystal_id"
                        placeholder="e.g. MN2490"
                    >

                    <label>Surface orientation (h k l)</label>
                    <div class="triplet" role="group" aria-label="Surface orientation Miller indices">
                        <input id="h_index" type="number" step="1" placeholder="h, e.g. 0" aria-label="h" required>
                        <input id="k_index" type="number" step="1" placeholder="k, e.g. 0" aria-label="k" required>
                        <input id="l_index" type="number" step="1" placeholder="l, e.g. 1" aria-label="l" required>
                    </div>
                    <p class="small">Three separate indices, including negative and multi-digit values.</p>

                    <label for="offcut_angle">Offcut angle (°)</label>
                    <input id="offcut_angle" type="number" step="any" min="0" placeholder="e.g. 0.1">

                    <label>Offcut direction [u v w] (direct space)</label>
                    <div class="triplet" role="group" aria-label="Offcut direction indices">
                        <input id="u_index" type="number" step="1" placeholder="u, e.g. 1" aria-label="u">
                        <input id="v_index" type="number" step="1" placeholder="v, e.g. 0" aria-label="v">
                        <input id="w_index" type="number" step="1" placeholder="w, e.g. 0" aria-label="w">
                    </div>

                    <label for="charge">
                        <span class="field-number">3.</span> Charge / Batch ID
                    </label>
                    <input id="charge" placeholder="e.g. 0228/0025/25">

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
                </div>


                <div class="card">
                    <h2>3. Archive preview</h2>

                    <label for="targetUpload">Target upload</label>
                    <select id="targetUpload">
                        <option value="">Loading uploads...</option>
                    </select>
                    <p id="uploadStatus" class="small">
                        Loading writable NOMAD uploads...
                    </p>

                    <div class="summary">
                        <strong>Substrate group:</strong><br>
                        <span id="batchPreview">Individual original NOMAD substrates</span>
                    </div>

                    <div>
                        <strong>Individual CrystallineSubstrate entries</strong>
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
                        Upload unavailable (original archive root unverified)
                    </button>

                    <p id="saveStatus" class="small">
                        Preview only: no valid original EntryArchive.data root has been verified.
                    </p>
                </div>

            </div>
        </div>
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
                const crystalId = cleanPart(
                    document.getElementById('crystal_id').value
                );
                const charge = cleanPart(
                    document.getElementById('charge').value
                );

                const countInput = document.getElementById('count');
                const preview = document.getElementById('childPreview');
                const batchPreview = document.getElementById('batchPreview');

                let count = parseInt(countInput.value || '0', 10);

                if (count < 0 || Number.isNaN(count)) {
                    count = 0;
                }

                const parts = [supplierId, crystalId, charge];
                if (parts.some(function(part) { return !part; })) {
                    batchPreview.textContent = 'Enter Supplier ID, Crystal ID and Charge ID';
                    preview.innerHTML = '';
                    return;
                }
                const batchName = parts.join('_');

                batchPreview.textContent = batchName;
                preview.innerHTML = '';

                for (let i = 1; i <= count; i++) {
                    const item = document.createElement('div');
                    item.className = 'preview-item';
                    item.textContent = batchName + '_' + i;
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
                    material: document.getElementById('material').value === 'other'
                        ? document.getElementById('other_material').value
                        : document.getElementById('material').value,
                    crystal_id: document.getElementById('crystal_id').value,
                    charge: document.getElementById('charge').value,
                    polishing:
document.getElementById('polishing').value,
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
                    notes: document.getElementById('notes').value
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
                document.getElementById('charge').value = '';
                document.getElementById('polishing').value = '';
                ['h_index', 'k_index', 'l_index'].forEach(function(id) {
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
                document.getElementById('notes').value = '';
                updatePreview();
            }

            async function previewArchive() {
                const payload = buildPayload();

                const output = document.getElementById('archiveJson');
                output.textContent = 'Loading...';

                try {
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

            async function saveToNomad() {
                const uploadId =
                    document.getElementById('targetUpload').value;
                const saveButton =
                    document.getElementById('saveButton');
                const saveStatus =
                    document.getElementById('saveStatus');

                if (!uploadId) {
                    saveStatus.className = 'warning';
                    saveStatus.textContent =
                        'Please select a target upload before saving.';
                    return;
                }
                saveStatus.className = 'small';

                const payload = buildPayload();

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
                        throw new Error(errorBody.detail ||
                            'Archive generation failed: ' + previewResponse.status);
                    }

                    const preview = await previewResponse.json();

                     if (preview.upload_supported !== true) {
                         throw new Error(preview.reason ||
                             'Original substrate entry root is unverified. No upload was made.');
                     }

                     const archives = preview.archives;
                     if (!Array.isArray(archives) || archives.length !== payload.count) {
                         throw new Error('Preview returned an unexpected number of substrate archives.');
                     }
                     if (archives.some(function(entry) {
                         return !entry || !entry.data ||
                             entry.data.m_def !== 'nomad_material_processing.general.CrystallineSubstrate' ||
                             !entry.filename || !entry.filename.endsWith('.archive.json');
                     })) {
                         throw new Error('Preview contains a non-original substrate schema.');
                     }
                     const unique = new Set(archives.map(function(item) { return item.filename; }));
                     if (unique.size !== archives.length) {
                         throw new Error('Preview contains duplicate substrate filenames.');
                     }

                     // Each physical substrate is a separate original NOMAD archive.
                     // There is no custom batch-normalizer and no implicit child creation.
                     // Do not retry automatically after a partial upload.
                     let saved = 0;
                     for (const archive of archives) {
                         const params = new URLSearchParams();
                         params.append('file_name', archive.filename);
                         params.append('overwrite_if_exists', 'false');
                         params.append('trigger_processing', 'true');
                         params.append('wait_for_processing', 'true');

                         saveStatus.textContent =
                             'Uploading substrate ' + (saved + 1) + '/' + archives.length +
                             ': ' + archive.filename;

                         const response = await fetch(
                             nomadApiBase() + '/uploads/' +
                             encodeURIComponent(uploadId) + '/raw/?' + params.toString(),
                             {
                                 method: 'PUT',
                                 headers: {'Content-Type': 'application/json'},
                                 body: JSON.stringify({data: archive.data}, null, 2)
                             }
                         );
                         if (!response.ok) {
                             let detail = '';
                             try {
                                 const errorData = await response.json();
                                 detail = errorData.detail ? ': ' +
                                     (typeof errorData.detail === 'string'
                                         ? errorData.detail
                                         : JSON.stringify(errorData.detail)) : '';
                             } catch (_) { }
                             throw new Error(
                                 'Saved ' + saved + '/' + archives.length +
                                 ' substrates. Upload failed for ' + archive.filename +
                                 ' (' + response.status + ')' + detail +
                                 '. Check the upload before retrying; do not create duplicates.'
                             );
                         }
                         saved += 1;
                     }

                    // Link to the upload so the user can jump straight to
                    // it, then clear the form for the next batch.
                    const uploadUrl =
                        nomadApiBase().replace(new RegExp('/api/v1$'), '') +
                        '/gui/user/uploads/upload/id/' +
                        encodeURIComponent(uploadId);

                    saveStatus.innerHTML =
                        'Saved ' + archives.length + ' original substrate archives' +
                        '. NOMAD processing has been triggered. ' +
                        '<a href="' + uploadUrl + '" target="_blank">' +
                        'View this upload &rarr;</a>';

                    resetForm();
                } catch (error) {
                    saveStatus.textContent =
                        'Error: ' + error.message;
                } finally {
                    saveButton.disabled = true;
                }
            }

            async function loadUploads() {
                const select = document.getElementById('targetUpload');
                const status = document.getElementById('uploadStatus');

                select.innerHTML =
                    '<option value="">Loading uploads...</option>';
                status.textContent =
                    'Loading writable NOMAD uploads...';

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
                        ' writable unpublished upload(s) available.';
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
                    document.getElementById('saveButton').disabled = true;
                    const status = document.getElementById('saveStatus');
                    status.className = hasUpload ? 'small' : 'warning';
                    status.textContent =
                        'Preview only: original substrate EntryArchive.data root unverified.';
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

                    document.getElementById('saveButton').disabled = true;
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
