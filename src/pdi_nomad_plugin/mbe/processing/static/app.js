// FIX: this used to guess the deployment base path by searching
// window.location.pathname for '/gui/' or '/dashboards/'. That breaks when
// the page is loaded in a context where neither substring appears in the
// URL (e.g. embedded inside NOMAD GUI v2), silently sending every API call
// to the wrong, unprefixed URL (404). The backend now injects the real
// base path as window.NOMAD_API_BASE (see processing/app.py); prefer that,
// and only fall back to the old URL-guessing if it is ever missing.
function nomadApiBase() {
    if (window.NOMAD_API_BASE) {
        return window.NOMAD_API_BASE;
    }
    const pathname = window.location.pathname;
    const markers = ['/gui/', '/dashboards/'];
    for (const marker of markers) {
        const index = pathname.indexOf(marker);
        if (index >= 0) return pathname.slice(0, index) + '/api/v1';
    }
    return '/api/v1';
}

let recipeSchemas = {};


async function loadProcessTypes() {
    const response = await fetch('./process-types');
    if (!response.ok) {
        throw new Error(
            'Could not load process types: ' + response.status
        );
    }

    const result = await response.json();

    if (
        !result ||
        typeof result !== 'object' ||
        !Object.keys(result).length
    ) {
        throw new Error('No process types configured.');
    }

    return result;
}

let substrates = [];
let recipes = [];
let treatmentHistoryState = [];
let processCounter = 0;

function nomadArchiveReference(uploadId, entryId) {
    return '../uploads/' + uploadId + '/archive/' + entryId + '#/data';
}

// FIX: /entries/query (the plain search endpoint) only accepts pre-indexed
// "doc quantities" in required.include (entry_id, upload_id, results.*, ...).
// It cannot return archive content like data.lab_id -- NOMAD rejects that
// with 422 "data.lab_id is not a doc quantity". Archive content (anything
// under "data") has to come from /entries/archive/query instead, which
// takes a nested required shape: {metadata: {...}, data: {...}}.
//
// Still accepts the same flat 'include' list callers already pass (e.g.
// ['entry_id', 'upload_id', 'entry_name', 'data.lab_id']) and splits it
// internally, so no call site needs to change. Returned objects keep the
// same shape callers already expect (entry.data.x, entry.entry_name, ...).
async function queryEntries(schema, pageSize, include) {
    const fields = include || ['entry_id', 'upload_id', 'entry_name'];
    const metadataRequired = {};
    const dataRequired = {};
    let wantsFullData = false;

    for (const field of fields) {
        if (field === 'entry_id' || field === 'upload_id') {
            continue;
        }
        if (field === 'data') {
            wantsFullData = true;
        } else if (field.startsWith('data.')) {
            dataRequired[field.slice('data.'.length)] = '*';
        } else {
            metadataRequired[field] = '*';
        }
    }

    const required = {};
    if (Object.keys(metadataRequired).length) {
        required.metadata = metadataRequired;
    }
    if (wantsFullData) {
        required.data = '*';
    } else if (Object.keys(dataRequired).length) {
        required.data = dataRequired;
    }

    const response = await fetch(nomadApiBase() + '/entries/archive/query', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            // FIX: without an explicit owner NOMAD defaults to owner="public",
            // which only returns PUBLISHED entries. Lab data lives in unpublished
            // uploads, so every query came back empty. "visible" = public + everything
            // the logged-in user can see (login is sent automatically via cookie).
            owner: 'visible',
            query: {'section_defs.definition_qualified_name': schema},
            pagination: {page_size: pageSize},
            required: required
        })
    });
    if (!response.ok) throw new Error('NOMAD query failed for ' + schema + ': ' + response.status);
    const result = await response.json();
    return (result.data || []).map(function(entry) {
        const archive = entry.archive || {};
        return Object.assign(
            {
                entry_id: entry.entry_id,
                upload_id: entry.upload_id,
                data: archive.data || {}
            },
            archive.metadata || {}
        );
    });
}

function substrateStatus(substrate) {
    if (substrate.grown) return 'grown';
    if (substrate.processed) return 'processed';
    if (substrate.asDelivered) return 'as_delivered';
    return '';
}

function referenceEntryId(reference) {
    if (!reference) return null;
    if (typeof reference === 'object' && reference.reference) {
        return referenceEntryId(reference.reference);
    }
    if (typeof reference !== 'string') return null;
    const match = reference.match(/\/archive\/([^/#]+)/);
    return match ? match[1] : null;
}

function cutParentEntryIds() {
    const parentIds = new Set();
    substrates.forEach(function(substrate) {
        const parentEntryId = referenceEntryId(substrate.parentSample);
        if (parentEntryId) parentIds.add(parentEntryId);
    });
    return parentIds;
}

function substrateHasBeenCut(substrate) {
    return Boolean(substrate && substrate.entryId && cutParentEntryIds().has(substrate.entryId));
}

function substrateByEntryId(entryId) {
    if (!entryId) return null;
    return substrates.find(function(substrate) { return substrate.entryId === entryId; }) || null;
}

function substrateLineage(substrate) {
    const lineage = [];
    const seen = new Set();
    let current = substrate;
    while (current && current.entryId && !seen.has(current.entryId)) {
        seen.add(current.entryId);
        lineage.push(current);
        const parentEntryId = referenceEntryId(current.parentSample);
        if (!parentEntryId) break;
        current = substrateByEntryId(parentEntryId);
    }
    return lineage;
}

function referenceContainsEntryId(reference, substrateEntryId) {
    if (!reference || !substrateEntryId) return false;
    if (typeof reference === 'string') {
        return reference.includes(substrateEntryId);
    }
    if (typeof reference === 'object') {
        return JSON.stringify(reference).includes(substrateEntryId);
    }
    return false;
}

function treatmentReferencesSubstrate(treatment, substrateEntryId) {
    if (!treatment || !treatment.data || !substrateEntryId) return false;

    if (referenceContainsEntryId(treatment.data.parent_sample, substrateEntryId)) {
        return true;
    }

    const samples = treatment.data.samples || [];
    return samples.some(function(sample) {
        return sample && referenceContainsEntryId(sample.reference, substrateEntryId);
    });
}

function treatmentDate(treatment) {
    const data = treatment.data || {};
    return data.datetime || data.starting_time || data.start_time || data.ending_time || '';
}

async function loadTreatmentHistoryEntries() {
    const treatments = [];
    for (const [type, definition] of Object.entries(recipeSchemas)) {
        if (!definition.processSchema) continue;
        const entries = await queryEntries(
            definition.processSchema,
            500,
            ['entry_id', 'upload_id', 'entry_name', 'mainfile', 'data']
        );
        entries.forEach(function(entry) {
            treatments.push({
                entryId: entry.entry_id,
                uploadId: entry.upload_id,
                entryName: entry.entry_name || entry.entry_id,
                mainfile: entry.mainfile || '',
                type: type,
                label: definition.label || type,
                data: entry.data || {}
            });
        });
    }
    return treatments;
}

function formatProcessingDateTime(value) {
    if (!value) return '';

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return String(value);
    }

    return date.toLocaleString(undefined, {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });
}


function treatmentHistoryForSubstrate(substrate) {
    const rows = [];
    substrateLineage(substrate).forEach(function(lineageSubstrate, index) {
        treatmentHistoryState.forEach(function(treatment) {
            if (treatmentReferencesSubstrate(treatment, lineageSubstrate.entryId)) {
                rows.push({
                    treatment: treatment,
                    substrate: lineageSubstrate,
                    inherited: index > 0
                });
            }
        });
    });
    rows.sort(function(a, b) {
        return String(treatmentDate(a.treatment)).localeCompare(String(treatmentDate(b.treatment)));
    });
    return rows;
}

function renderHistoryDetails(container, substrate, history) {
    const lineage = substrateLineage(substrate);
    if (lineage.length > 1) {
        const lineageInfo = document.createElement('div');
        lineageInfo.className = 'history-lineage';
        lineageInfo.textContent = 'Lineage: ' + lineage.slice().reverse().map(function(item) {
            return item.labId || item.entryId;
        }).join(' -> ');
        container.appendChild(lineageInfo);
    }

    history.forEach(function(row) {
        const item = document.createElement('div');
        item.className = 'history-item';
        const title = document.createElement('div');
        title.className = 'history-title';
        title.textContent = row.treatment.label + ': ' + row.treatment.entryName;
        item.appendChild(title);

        const details = [];
        const date = treatmentDate(row.treatment);
        if (date) details.push(formatProcessingDateTime(date));
        if (row.inherited) {
            details.push('inherited from ' + (row.substrate.labId || row.substrate.entryId));
        }
        if (details.length) {
            const meta = document.createElement('div');
            meta.className = 'history-meta';
            meta.textContent = details.join(' · ');
            item.appendChild(meta);
        }
        container.appendChild(item);
    });
}

async function loadSubstrates() {
    const entries = await queryEntries('pdi_nomad_plugin.mbe.materials.SubstrateMbe', 1000, [
        'entry_id', 'upload_id', 'entry_name', 'data.lab_id', 'data.material_designation',
        'data.chemical_formula', 'data.crystal_id', 'data.charge_id', 'data.surface_orientation_label',
        'data.m_def', 'data.geometry', 'data.parent_sample', 'data.as_delivered', 'data.processed', 'data.grown'
    ]);
    return entries.filter(function(entry) {
        const data = entry.data || {};
        return data.m_def === 'pdi_nomad_plugin.mbe.materials.SubstrateMbe';
    }).map(function(entry) {
        const data = entry.data || {};
        return {
            entryId: entry.entry_id,
            uploadId: entry.upload_id,
            labId: data.lab_id || entry.entry_name || entry.entry_id,
            material: data.material_designation || data.chemical_formula || '',
            formula: data.chemical_formula || '',
            crystalId: data.crystal_id || '',
            chargeId: data.charge_id || '',
            orientation: data.surface_orientation_label || '',
            geometry: data.geometry || null,
            parentSample: data.parent_sample || null,
            asDelivered: Boolean(data.as_delivered),
            processed: Boolean(data.processed),
            grown: Boolean(data.grown),
            selected: false
        };
    }).sort(function(a, b) {
        return String(a.labId).localeCompare(
            String(b.labId),
            undefined,
            {numeric: true, sensitivity: 'base'}
        );
    });
}

// Adapt *existing* legacy library-template geometry for display/validation only.
// SampleCutPDI execution persists only official NOMAD Geometry subclasses.
function readExistingCutTemplateGeometry(value) {
    if (!value || typeof value !== 'object') return null;
    const existingType = String(value.m_def || '');
    if (existingType.startsWith('nomad_material_processing.general.')) {
        return value;
    }
    const kind = String(value.shape || '').toLowerCase();
    const thickness = geometryNumber(value.height);
    // SampleCutGeometryPDI has optional physical thickness. Retain an explicitly
    // stored value; do not fabricate it when the recipe omits height.
    if (value.height !== undefined && value.height !== null &&
        !(thickness > 0)) return null;
    const width = geometryNumber(value.width);
    const length = geometryNumber(value.length);
    if ((kind === '' || kind === 'rectangle') && width > 0 && length > 0) {
        const square = Math.abs(width - length) <= 1e-9;
        const result = {
            m_def: NOMAD_GEOMETRY + (square ? 'SquareCuboid' : 'RectangleCuboid'),
            width: width,
            length: length
        };
        if (thickness > 0) result.height = thickness;
        return result;
    }
    const radius = geometryNumber(value.radius);
    if (radius > 0 && (kind === 'circle' || kind === 'circular_sector')) {
        const result = {
            m_def: NOMAD_GEOMETRY + (kind === 'circle' ? 'Cylinder' : 'CylinderSector'),
            radius: radius
        };
        if (thickness > 0) result.height = thickness;
        if (kind === 'circular_sector') {
            const angle = geometryNumber(value.central_angle);
            if (!(angle > 0 && angle <= 360)) return null;
            result.central_angle = angle;
        }
        return result;
    }
    return null;
}

async function loadRecipes() {
    const result = [];
    for (const [type, definition] of Object.entries(recipeSchemas)) {
        const isCut = definition.kind === 'sample_cut';
        const include = [
            'entry_id', 'upload_id', 'entry_name', 'data.name', 'data.lab_id'
        ];
        if (isCut) {
            include.push(
                'data.input_geometry', 'data.number_of_samples',
                'data.children_geometry'
            );
        }
        const entries = await queryEntries(definition.schema, 200, include);
        entries.forEach(function(entry) {
            const data = entry.data || {};
            result.push({
                type: type,
                entryId: entry.entry_id,
                uploadId: entry.upload_id,
                name: data.lab_id || data.name || entry.entry_name || entry.entry_id,
                inputGeometry: isCut ? readExistingCutTemplateGeometry(data.input_geometry) : null,
                sourceParentEntryId: null,
                numberOfSamples: data.number_of_samples || null,
                childrenGeometry: isCut ? readExistingCutTemplateGeometry(data.children_geometry) : null
            });
        });

        // Preserve the previous functionality: completed SampleCutPDI actions can
        // still be reused as parameter templates, without ever changing them.
        if (isCut && definition.processSchema !== definition.schema) {
            const historic = await queryEntries(definition.processSchema, 200, [
                'entry_id', 'upload_id', 'entry_name', 'data.name',
                'data.parent_sample', 'data.number_of_samples',
                'data.children_geometry'
            ]);
            historic.forEach(function(entry) {
                const data = entry.data || {};
                result.push({
                    type: type,
                    entryId: entry.entry_id,
                    uploadId: entry.upload_id,
                    name: '(Previous cut) ' +
                        (data.lab_id || data.name || entry.entry_name || entry.entry_id),
                    inputGeometry: null,
                    sourceParentEntryId: referenceEntryId(data.parent_sample),
                    numberOfSamples: data.number_of_samples || null,
                    childrenGeometry: readExistingCutTemplateGeometry(data.children_geometry)
                });
            });
        }
    }
    return result;
}

async function loadUploads() {
    const select = document.getElementById('targetUpload');
    const status = document.getElementById('uploadStatus');
    const params = new URLSearchParams();

    params.append('is_published', 'false');
    params.append('is_processing', 'false');
    params.append('page_size', '100');

    try {
        const [userResponse, uploadsResponse] = await Promise.all([
            fetch(nomadApiBase() + '/users/me'),
            fetch(
                nomadApiBase() +
                '/uploads?' +
                params.toString()
            )
        ]);

        if (!userResponse.ok) {
            throw new Error(
                'User request failed: ' +
                userResponse.status
            );
        }

        if (!uploadsResponse.ok) {
            throw new Error(
                'Upload request failed: ' +
                uploadsResponse.status
            );
        }

        const user = await userResponse.json();
        const result = await uploadsResponse.json();
        const userId = user.user_id;

        if (!userId) {
            throw new Error(
                'Authenticated NOMAD user has no user_id.'
            );
        }

        const uploads = (result.data || []).filter(
            function(upload) {
                const writers = Array.isArray(upload.writers)
                    ? upload.writers
                    : [];

                return (
                    upload.main_author === userId ||
                    writers.includes(userId)
                );
            }
        );

        select.innerHTML =
            '<option value="">Select target upload...</option>';

        uploads.forEach(function(upload) {
            const option =
                document.createElement('option');

            option.value = upload.upload_id;
            option.textContent =
                (upload.upload_name || 'Unnamed upload') +
                ' ? ' +
                upload.upload_id;

            select.appendChild(option);
        });

        status.textContent =
            uploads.length +
            ' directly writable unpublished upload(s).';

    } catch (error) {
        select.innerHTML =
            '<option value="">Could not load uploads</option>';

        status.textContent =
            'Error: ' + error.message;
    }
}

function uniqueSorted(values) {
    return Array.from(new Set(values.filter(Boolean))).sort(function(a, b) { return a.localeCompare(b); });
}

function populateFilter(id, values) {
    const select = document.getElementById(id);
    const previous = select.value;
    select.innerHTML = '<option value="">All</option>';
    uniqueSorted(values).forEach(function(value) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
    });
    if (Array.from(select.options).some(function(option) { return option.value === previous; })) select.value = previous;
}

function filteredSubstrates() {
    const search = document.getElementById('substrateSearch').value.trim().toLowerCase();
    const material = document.getElementById('materialFilter').value;
    const batch = document.getElementById('batchFilter').value;
    const orientation = document.getElementById('orientationFilter').value;
    const status = document.getElementById('statusFilter').value;
    return substrates.filter(function(substrate) {
        if (substrateHasBeenCut(substrate)) return false;
        const searchable = [substrate.labId, substrate.material, substrate.formula, substrate.crystalId, substrate.chargeId, substrate.orientation]
            .filter(Boolean).join(' ').toLowerCase();
        return (!search || searchable.includes(search)) &&
            (!material || substrate.material === material) &&
            (!batch || substrate.crystalId === batch || substrate.chargeId === batch) &&
            (!orientation || substrate.orientation === orientation) &&
            (!status || substrateStatus(substrate) === status);
    });
}

function renderSubstrates() {
    const container = document.getElementById('substrateResults');
    const visible = filteredSubstrates();
    const cutCount = substrates.filter(substrateHasBeenCut).length;
    container.innerHTML = '';

    visible.forEach(function(substrate) {
        const history = treatmentHistoryForSubstrate(substrate);
        const row = document.createElement('div');
        row.className = 'result-grid result-row';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = substrate.selected;
        checkbox.addEventListener('change', function() {
            substrate.selected = checkbox.checked;
            updateSaveSummary();
        });
        row.appendChild(checkbox);

        [
            substrate.labId,
            substrate.material || '-',
            substrate.crystalId || substrate.chargeId || '-',
            substrate.orientation || '-'
        ].forEach(function(value) {
            const cell = document.createElement('div');
            cell.textContent = value;
            row.appendChild(cell);
        });

        const statusCell = document.createElement('div');
        statusCell.className = 'result-status-cell';
        const statusText = document.createElement('span');
        statusText.textContent = substrateStatus(substrate) || '-';
        statusCell.appendChild(statusText);

        if (history.length) {
            const historyButton = document.createElement('button');
            historyButton.type = 'button';
            historyButton.className = 'history-toggle';
            historyButton.textContent = history.length + ' process' + (history.length === 1 ? '' : 'es') + (substrate.historyOpen ? ' ▴' : ' ▾');
            historyButton.addEventListener('click', function() {
                substrate.historyOpen = !substrate.historyOpen;
                renderSubstrates();
            });
            statusCell.appendChild(historyButton);
        }
        row.appendChild(statusCell);
        container.appendChild(row);

        if (substrate.historyOpen && history.length) {
            const historyRow = document.createElement('div');
            historyRow.className = 'history-row';
            renderHistoryDetails(historyRow, substrate, history);
            container.appendChild(historyRow);
        }
    });

    document.getElementById('substrateStatus').textContent =
        visible.length + ' matching substrate' + (visible.length === 1 ? '' : 's') +
        '; ' + substrates.filter(function(item) { return item.selected && !substrateHasBeenCut(item); }).length + ' selected' +
        (cutCount ? '; ' + cutCount + ' cut parent' + (cutCount === 1 ? '' : 's') + ' hidden from physical processing.' : '.');
}


// NOMAD Geometry subclasses are identified by m_def, not a custom shape field.
// shape is read only to support old, not-yet-migrated archives.
const NOMAD_GEOMETRY = 'nomad_material_processing.general.';

function geometryKind(geometry) {
    if (!geometry || typeof geometry !== 'object') return null;
    const type = String(geometry.m_def || '').split('.').pop();
    if (type === 'SquareCuboid') return 'square';
    if (type === 'RectangleCuboid' || type === 'Parallelepiped') return 'rectangle';
    if (type === 'Cylinder') return 'circle';
    if (type === 'CylinderSector') return 'circular_sector';
    if (type === 'IrregularParallelSurfaces') return 'irregular';
    // Legacy read-only compatibility. New archives never use these fields.
    if (geometry.shape === 'rectangle') return 'rectangle';
    if (geometry.shape === 'circle') return 'circle';
    if (geometry.shape === 'circular_sector') return 'circular_sector';
    return null;
}

function geometryFromForm(card) {
    const type = card.querySelector('.cut-shape').value;
    const readMm = function(selector) {
        const input = card.querySelector(selector);
        if (!input || input.value.trim() === '') return null;
        const value = Number(input.value);
        return Number.isFinite(value) && value > 0 ? value / 1000 : null;
    };
    if (type === 'square' || type === 'rectangle') {
        const width = readMm('.cut-width');
        const length = readMm('.cut-length');
        if (!width || !length) {
            throw new Error('Specify positive child width and length (mm).');
        }
        if (type === 'square' && Math.abs(width - length) > 1e-9) {
            throw new Error('Square child geometry needs equal width and length.');
        }
        return {
            m_def: NOMAD_GEOMETRY + (type === 'square' ? 'SquareCuboid' : 'RectangleCuboid'),
            width: width, length: length
        };
    }
    if (type === 'circle' || type === 'circular_sector') {
        const radius = readMm('.cut-radius');
        if (!radius) throw new Error('Specify a positive child radius (mm).');
        const result = {
            m_def: NOMAD_GEOMETRY + (type === 'circle' ? 'Cylinder' : 'CylinderSector'),
            radius: radius
        };
        if (type === 'circular_sector') {
            const angle = Number(card.querySelector('.cut-angle').value);
            if (!(angle > 0 && angle <= 360)) {
                throw new Error('Sector angle must be between 0 and 360 degrees.');
            }
            result.central_angle = angle;
        }
        return result;
    }
    throw new Error('Unsupported child geometry: ' + type);
}

function prefillCutFromSubstrate(card) {
    const selected = substrates.filter(function(s) { return s.selected && !substrateHasBeenCut(s); });
    if (!selected.length || !selected[0].geometry) {
        throw new Error('Select a parent substrate with a NOMAD Geometry first.');
    }
    const parent = selected[0].geometry;
    const kind = geometryKind(parent);
    if (!['square','rectangle','circle','circular_sector'].includes(kind)) {
        throw new Error('Cannot prefill unsupported parent geometry.');
    }
    card.querySelector('.cut-shape').value = kind;
    const setMm = function(selector, value) {
        card.querySelector(selector).value =
            Number.isFinite(geometryNumber(value)) ? 1000 * geometryNumber(value) : '';
    };
    setMm('.cut-width', parent.width);
    setMm('.cut-length', parent.length);
    setMm('.cut-radius', parent.radius);
    // Parent thickness is always inherited at cut execution.
    card.querySelector('.cut-angle').value = kind === 'circular_sector' ?
        geometryNumber(parent.central_angle) || 90 : 90;
    updateCutFieldVisibility(card);
}

function updateCutFieldVisibility(card) {
    const cut = card.querySelector('.sample-cut-manual');
    if (!cut) return;
    const manual = !card.querySelector('.recipe-select').value;
    cut.style.display = manual ? 'block' : 'none';
    const kind = card.querySelector('.cut-shape').value;
    card.querySelectorAll('.cut-rect').forEach(function(field) {
        field.style.display = kind === 'square' || kind === 'rectangle' ? '' : 'none';
    });
    card.querySelectorAll('.cut-round').forEach(function(field) {
        field.style.display = kind === 'circle' || kind === 'circular_sector' ? '' : 'none';
    });
    card.querySelectorAll('.cut-sector').forEach(function(field) {
        field.style.display = kind === 'circular_sector' ? '' : 'none';
    });
}

function geometryNumber(value) {
    if (typeof value === 'number' && Number.isFinite(value)) {
        return value;
    }
    if (
        value &&
        typeof value === 'object' &&
        typeof value.magnitude === 'number' &&
        Number.isFinite(value.magnitude)
    ) {
        return value.magnitude;
    }
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
}

function geometryXY(geometry) {
    if (!geometry || typeof geometry !== 'object') return null;

    const width = geometryNumber(geometry.width);
    let length = geometryNumber(geometry.length);

    if (!Number.isFinite(width)) return null;
    if (!Number.isFinite(length)) length = width;

    return {width: width, length: length};
}

function sampleCutChildGeometry(parentGeometry, recipeGeometry) {
    if (!recipeGeometry || typeof recipeGeometry !== 'object') {
        throw new Error('Child geometry is missing.');
    }
    const kind = geometryKind(recipeGeometry);
    const specifiedHeight = geometryNumber(recipeGeometry.height);
    const parentHeight = geometryNumber(parentGeometry && parentGeometry.height);
    const height = specifiedHeight > 0 ? specifiedHeight : parentHeight;
    if (!(height > 0)) {
        throw new Error('Neither child geometry nor parent geometry specifies a valid thickness.');
    }
    const output = {height: height};
    if (kind === 'square' || kind === 'rectangle') {
        const width = geometryNumber(recipeGeometry.width);
        const length = geometryNumber(recipeGeometry.length);
        if (!(width > 0 && length > 0)) {
            throw new Error('Child width and length must be positive.');
        }
        const square = kind === 'square' || Math.abs(width - length) <= 1e-9;
        output.m_def = NOMAD_GEOMETRY + (square ? 'SquareCuboid' : 'RectangleCuboid');
        output.width = width;
        output.length = length;
        return output;
    }
    if (kind === 'circle' || kind === 'circular_sector') {
        const radius = geometryNumber(recipeGeometry.radius);
        if (!(radius > 0)) throw new Error('Child radius must be positive.');
        output.m_def = NOMAD_GEOMETRY + (kind === 'circle' ? 'Cylinder' : 'CylinderSector');
        output.radius = radius;
        if (kind === 'circular_sector') {
            const angle = geometryNumber(recipeGeometry.central_angle);
            if (!(angle > 0 && angle <= 360)) throw new Error('Invalid sector angle.');
            output.central_angle = angle;
        }
        return output;
    }
    throw new Error('Unsupported existing NOMAD Geometry subclass.');
}

function geometryMatches(first, second) {
    if (!first || !second) return false;
    const a = geometryKind(first);
    const b = geometryKind(second);
    const rectangular = ['square','rectangle'];
    if (a !== b && !(rectangular.includes(a) && rectangular.includes(b))) return false;
    // Linear sizes are in meters. Ignore thickness for matching a cutting footprint.
    const tolerance = 0.00005;
    if (a === 'circle' || a === 'circular_sector') {
        const r1 = geometryNumber(first.radius);
        const r2 = geometryNumber(second.radius);
        if (!(r1 > 0 && r2 > 0 && Math.abs(r1 - r2) <= tolerance)) return false;
        if (a === 'circle') return true;
        const angle1 = geometryNumber(first.central_angle);
        const angle2 = geometryNumber(second.central_angle);
        return angle1 > 0 && angle2 > 0 && Math.abs(angle1 - angle2) < 1e-6;
    }
    const xy1 = geometryXY(first);
    const xy2 = geometryXY(second);
    if (!xy1 || !xy2) return false;
    return (Math.abs(xy1.width - xy2.width) <= tolerance &&
            Math.abs(xy1.length - xy2.length) <= tolerance) ||
           (Math.abs(xy1.width - xy2.length) <= tolerance &&
            Math.abs(xy1.length - xy2.width) <= tolerance);
}

function geometryDisplay(geometry) {
    const kind = geometryKind(geometry);
    if (kind === 'circle' || kind === 'circular_sector') {
        const radius = geometryNumber(geometry.radius);
        const angle = kind === 'circle' ? 360 : geometryNumber(geometry.central_angle);
        return radius > 0 ?
            ('R ' + (1000 * radius).toFixed(2) + ' mm' +
             (kind === 'circular_sector' ? ', ' + angle + '°' : '')) : 'Not specified';
    }
    if (kind !== 'square' && kind !== 'rectangle') return 'Not specified';
    const value = geometryXY(geometry);
    if (!value) return 'Not specified';
    function mm(number) {
        return (number * 1000).toLocaleString(undefined, {maximumFractionDigits: 3});
    }
    return mm(value.width) + ' × ' + mm(value.length) + ' mm';
}

function isSampleCutType(type) {
    return Boolean(
        recipeSchemas[type] &&
        recipeSchemas[type].kind === 'sample_cut'
    );
}

function updateProcessCardMode(card) {
    const type = card.querySelector('.process-type').value;
    const isSampleCut = isSampleCutType(type);
    const recipeLabel = card.querySelector('.recipe-label');
    const details = card.querySelector('.sample-cut-details');

    recipeLabel.textContent = isSampleCut ? 'Cut recipe' : 'Recipe';
    details.style.display = isSampleCut ? 'block' : 'none';

    updateSampleCutDetails(card);
}

function updateSampleCutDetails(card) {
    const details = card.querySelector('.sample-cut-details');
    if (!details || details.style.display === 'none') return;
    const recipeSelect = card.querySelector('.recipe-select');
    const recipe = recipes.find(function(item) { return item.entryId === recipeSelect.value; });
    const parent = card.querySelector('.sample-cut-parent-geometry');
    const output = card.querySelector('.sample-cut-output');
    updateCutFieldVisibility(card);
    if (recipe) {
        const originalParent = substrateByEntryId(recipe.sourceParentEntryId);
        const input = recipe.inputGeometry ||
            (originalParent && originalParent.geometry) || null;
        parent.textContent = input ? geometryDisplay(input) :
            'Previous parent not in current substrate catalogue';
        output.textContent = String(recipe.numberOfSamples || '?') + ' × ' +
            geometryDisplay(recipe.childrenGeometry);
    } else {
        const selected = substrates.filter(function(s) { return s.selected && !substrateHasBeenCut(s); });
        parent.textContent = selected.length ? geometryDisplay(selected[0].geometry) : 'Select parent substrate';
        try {
            const geometry = geometryFromForm(card);
            output.textContent = String(Number(card.querySelector('.cut-count').value) || '?') +
                ' × ' + geometryDisplay(geometry);
        } catch (_) { output.textContent = 'Specify output geometry and child count'; }
    }
}

function planarArea(geometry) {
    const kind = geometryKind(geometry);
    if (kind === 'square' || kind === 'rectangle') {
        const xy = geometryXY(geometry);
        return xy && xy.width > 0 && xy.length > 0 ? xy.width * xy.length : null;
    }
    if (kind === 'circle' || kind === 'circular_sector') {
        const r = geometryNumber(geometry.radius);
        const angle = kind === 'circle' ? 360 : geometryNumber(geometry.central_angle);
        return r > 0 && angle > 0 && angle <= 360 ? Math.PI * r * r * angle / 360 : null;
    }
    return null;
}

function validateSampleCutRecipe(recipe, selectedSubstrates, processIndex) {
    if (!recipe || !Number.isInteger(Number(recipe.numberOfSamples)) ||
        Number(recipe.numberOfSamples) < 1 || !recipe.childrenGeometry) {
        throw new Error('Process ' + (processIndex + 1) +
            ': specify a positive child count and valid child geometry.');
    }
    for (const substrate of selectedSubstrates) {
        if (!substrate.geometry) {
            throw new Error('Parent ' + substrate.labId + ' has no Geometry in NOMAD.');
        }
        if (recipe.inputGeometry && !geometryMatches(substrate.geometry, recipe.inputGeometry)) {
            throw new Error('Process ' + (processIndex + 1) +
                ': parent geometry does not match cut configuration: ' + substrate.labId);
        }
        // Validate the canonical output using this parent's inherited thickness.
        const childGeometry = sampleCutChildGeometry(substrate.geometry, recipe.childrenGeometry);
        const parentArea = planarArea(substrate.geometry);
        const childArea = planarArea(childGeometry);
        if (parentArea !== null && childArea !== null &&
            Number(recipe.numberOfSamples) * childArea > parentArea * 1.000001) {
            throw new Error('Requested child pieces have a greater total area than parent ' +
                substrate.labId + '. Adjust child dimensions or count.');
        }
    }
}

function updateRecipeSelect(card) {
    const type = card.querySelector('.process-type').value;
    const select = card.querySelector('.recipe-select');
    const isCut = isSampleCutType(type);
    const matching = recipes.filter(function(recipe) {
        return recipe.type === type && (!isCut ||
            (recipe.numberOfSamples && recipe.childrenGeometry &&
             (recipe.inputGeometry || recipe.sourceParentEntryId)));
    });
    select.innerHTML = '<option value="">' +
        (isCut ? 'Custom cut (from selected parent)' :
        (matching.length ? 'Select recipe...' : 'No recipes found')) + '</option>';
    matching.forEach(function(recipe) {
        const option = document.createElement('option');
        option.value = recipe.entryId;
        option.dataset.uploadId = recipe.uploadId;
        option.textContent = recipe.name;
        select.appendChild(option);
    });
    select.disabled = !isCut && matching.length === 0;
    updateProcessCardMode(card);
}

function collapseOthers(active) {
    document.querySelectorAll('.process-card').forEach(function(card) {
        if (card !== active) card.classList.remove('open');
    });
}

function renumberProcesses() {
    document.querySelectorAll('.process-card').forEach(function(card, index) {
        card.querySelector('.process-title').textContent = 'Process ' + (index + 1);
    });
    processCounter = document.querySelectorAll('.process-card').length;
    updateSaveSummary();
}

function localDateTimeValue() {
    const now = new Date();
    const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 19);
}

function addProcess() {
    processCounter += 1;
    const card = document.createElement('div');
    card.className = 'process-card open';
    collapseOthers(card);
    const options = Object.entries(recipeSchemas).map(function(entry) {
        return '<option value="' + entry[0] + '">' + entry[1].label + '</option>';
    }).join('');
    card.innerHTML = `
        <div class="process-summary"><div><div class="process-title">Process ${processCounter}</div><div class="process-meta">Cleaning</div></div><div>⌄</div></div>
        <div class="process-body">
            <div class="process-fields">
                <div><label>Process type</label><select class="process-type">${options}</select></div>
                <div><label>Date / Time</label><input class="process-datetime" type="datetime-local" step="1" value="${localDateTimeValue()}"></div>
            </div>
            <label class="recipe-label">Recipe</label><select class="recipe-select"></select>
            <div class="sample-cut-details" style="display:none;">
                <div class="sample-cut-detail-grid">
                    <div>
                        <label>Expected parent geometry</label>
                        <div class="sample-cut-readonly sample-cut-parent-geometry">Select a cut recipe</div>
                    </div>
                    <div>
                        <label>Output per parent</label>
                        <div class="sample-cut-readonly sample-cut-output">Select a cut recipe</div>
                    </div>
                </div>
                <div class="sample-cut-manual">
                    <div class="sample-cut-detail-grid">
                        <div><label>Number of child substrates per parent</label><input class="cut-count" type="number" min="1" step="1" value="2"></div>
                        <div><label>Child geometry</label><select class="cut-shape">
                            <option value="square">Square cuboid</option>
                            <option value="rectangle">Rectangular cuboid</option>
                            <option value="circle">Circular wafer</option>
                            <option value="circular_sector">Circular sector</option>
                        </select></div>
                        <div class="cut-rect"><label>Child width (mm)</label><input class="cut-width" type="number" min="0" step="any"></div>
                        <div class="cut-rect"><label>Child length (mm)</label><input class="cut-length" type="number" min="0" step="any"></div>
                        <div class="cut-round"><label>Child radius (mm)</label><input class="cut-radius" type="number" min="0" step="any"></div>
                        <div class="cut-sector"><label>Central angle (°)</label><input class="cut-angle" type="number" min="0" max="360" step="any" value="90"></div>
                        <div class="sample-cut-note">Thickness is inherited from the selected parent substrate.</div>
                    </div>
                    <button class="prefill-cut-from-parent" type="button">Copy selected parent geometry as starting point</button>
                    <div class="sample-cut-note">Edit dimensions to the actual cut pieces; copying the parent's full size does not automatically divide it.</div>
                </div>
                <div class="sample-cut-note">
                    Select an existing Lab Library cut recipe, use custom settings, or reuse a previous cut as a template. Execution always uses SampleCutPDI.
                </div>
            </div>
            <label>Comments</label><textarea class="process-comments" placeholder="Optional"></textarea>
            <div class="process-footer"><button class="remove-button" type="button">Remove process</button><button class="collapse-button" type="button">Done / collapse</button></div>
        </div>`;
    document.getElementById('processList').appendChild(card);
    const typeSelect = card.querySelector('.process-type');
    const meta = card.querySelector('.process-meta');
    card.querySelector('.process-summary').addEventListener('click', function() {
        card.classList.toggle('open');
        if (card.classList.contains('open')) collapseOthers(card);
    });
    typeSelect.addEventListener('change', function() {
        meta.textContent = recipeSchemas[typeSelect.value].label;
        updateRecipeSelect(card);
        updateProcessCardMode(card);
        updateSaveSummary();
    });
    card.querySelector('.recipe-select').addEventListener('change', function() {
        updateSampleCutDetails(card);
        updateSaveSummary();
    });
    card.querySelector('.prefill-cut-from-parent').addEventListener('click', function() {
        try { prefillCutFromSubstrate(card); updateSampleCutDetails(card); }
        catch (err) { document.getElementById('processStatus').textContent = err.message; }
    });
    card.querySelectorAll('.sample-cut-manual input, .sample-cut-manual select').forEach(function(input) {
        input.addEventListener('input', function() { updateSampleCutDetails(card); });
        input.addEventListener('change', function() { updateSampleCutDetails(card); });
    });
    card.querySelector('.collapse-button').addEventListener('click', function() { card.classList.remove('open'); });
    card.querySelector('.remove-button').addEventListener('click', function() { card.remove(); renumberProcesses(); });
    updateRecipeSelect(card);
    updateSaveSummary();
}

function processDefinitions() {
    return Array.from(document.querySelectorAll('.process-card')).map(function(card) {
        const type = card.querySelector('.process-type').value;
        const recipeSelect = card.querySelector('.recipe-select');
        const savedRecipe = recipes.find(function(item) { return item.entryId === recipeSelect.value; });
        let recipe = savedRecipe || null;
        if (isSampleCutType(type)) {
            if (savedRecipe) {
                let inputGeometry = savedRecipe.inputGeometry;
                if (!inputGeometry && savedRecipe.sourceParentEntryId) {
                    const source = substrateByEntryId(savedRecipe.sourceParentEntryId);
                    if (!source || !source.geometry) {
                        throw new Error(
                            'Previous cut parent geometry cannot be retrieved. ' +
                            'Use custom settings.'
                        );
                    }
                    inputGeometry = source.geometry;
                }
                if (!inputGeometry) {
                    throw new Error('Selected cut recipe has no usable parent geometry.');
                }
                recipe = Object.assign({}, savedRecipe, {inputGeometry: inputGeometry});
            } else {
                const selected = substrates.filter(function(s) { return s.selected && !substrateHasBeenCut(s); });
                if (!selected.length || !selected[0].geometry) {
                    throw new Error('Select a parent substrate with geometry before configuring SampleCut.');
                }
                recipe = {
                    numberOfSamples: Number(card.querySelector('.cut-count').value),
                    inputGeometry: selected[0].geometry,
                    childrenGeometry: geometryFromForm(card)
                };
            }
        }
        return {
            type: type,
            kind: recipeSchemas[type] ? recipeSchemas[type].kind || 'process' : 'process',
            recipe: recipe || null,
            datetime: card.querySelector('.process-datetime').value,
            comments: card.querySelector('.process-comments').value.trim()
        };
    });
}

function updateSaveSummary() {
    const selectedCount = substrates.filter(function(item) { return item.selected; }).length;
    const count = document.querySelectorAll('.process-card').length;
    const status = document.getElementById('processStatus');
    if (status) status.textContent = selectedCount + ' substrate(s) selected; ' + count + ' process(es) configured.';
}

function safePart(value) {
    return String(value || '').trim().replace(/\s+/g, '_').replace(/[^A-Za-z0-9._-]/g, '');
}

function processArchiveData(definition, selectedSubstrates, index) {
    if (definition.kind === 'sample_cut') {
        throw new Error(
            'Process ' + (index + 1) +
            ': sample cut must be saved per parent substrate.'
        );
    }
    if (!definition.recipe) throw new Error('Process ' + (index + 1) + ': select a recipe.');
    if (!definition.datetime) throw new Error('Process ' + (index + 1) + ': enter date / time.');
    const schema = recipeSchemas[definition.type];
    if (!schema) throw new Error('Unsupported process type: ' + definition.type);
    selectedSubstrates.forEach(function(substrate) {
        if (!substrate.entryId || !substrate.uploadId) {
            throw new Error(
                'Process ' + (index + 1) +
                ': substrate ' + (substrate.labId || '(unknown)') +
                ' has no valid NOMAD entry/upload reference.'
            );
        }
    });

    const data = {
        m_def: schema.processSchema,
        name: schema.label + ' - ' + selectedSubstrates.length + ' substrate' + (selectedSubstrates.length === 1 ? '' : 's'),
        datetime: new Date(definition.datetime).toISOString(),
        recipe: nomadArchiveReference(definition.recipe.uploadId, definition.recipe.entryId),
        samples: selectedSubstrates.map(function(substrate) {
            return {
                name: substrate.labId,
                lab_id: substrate.labId,
                reference: nomadArchiveReference(substrate.uploadId, substrate.entryId)
            };
        })
    };
    if (definition.comments) data.description = definition.comments;
    return data;
}


function sampleCutArchiveData(definition, substrate, index) {
    validateSampleCutRecipe(definition.recipe, [substrate], index);

    if (!definition.datetime) {
        throw new Error(
            'Process ' + (index + 1) + ': enter date / time.'
        );
    }
    if (!substrate.entryId || !substrate.uploadId) {
        throw new Error(
            'Process ' + (index + 1) +
            ': substrate ' + (substrate.labId || '(unknown)') +
            ' has no valid NOMAD entry/upload reference.'
        );
    }

    const schema = recipeSchemas[definition.type];
    if (!schema || schema.kind !== 'sample_cut') {
        throw new Error('Unsupported sample cut type: ' + definition.type);
    }

    const data = {
        m_def: schema.processSchema,
        name: schema.label + ' - ' + substrate.labId,
        datetime: new Date(definition.datetime).toISOString(),
        number_of_samples: definition.recipe.numberOfSamples,
        children_geometry: sampleCutChildGeometry(
            substrate.geometry,
            definition.recipe.childrenGeometry
        ),
        parent_sample: {
            name: substrate.labId,
            reference: nomadArchiveReference(
                substrate.uploadId,
                substrate.entryId
            )
        },
        trigger_cut_sample: true
    };

    if (definition.comments) data.description = definition.comments;

    return data;
}

async function uploadArchive(uploadId, filename, data) {
    const params = new URLSearchParams();
    params.append('file_name', filename);
    params.append('overwrite_if_exists', 'false');
    params.append('trigger_processing', 'true');
    params.append('wait_for_processing', 'true');
    params.append('include_archive', 'true');

    const response = await fetch(
        nomadApiBase() +
        '/uploads/' +
        encodeURIComponent(uploadId) +
        '/raw/?' +
        params.toString(),
        {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({data: data}, null, 2)
        }
    );

    if (!response.ok) {
        let detail = '';
        try {
            const err = await response.json();
            detail = err.detail ? ': ' + JSON.stringify(err.detail) : '';
        } catch (_) {}
        throw new Error('Process upload failed (' + response.status + ')' + detail);
    }

    const result = await response.json();
    const processing = result.processing || {};
    const entry = processing.entry || {};
    const errors = Array.isArray(entry.errors) ? entry.errors : [];
    const warnings = Array.isArray(entry.warnings) ? entry.warnings : [];

    if (errors.length) {
        throw new Error(
            'NOMAD processing failed: ' + errors.join('; ')
        );
    }

    if (warnings.length) {
        console.warn(
            'NOMAD processing warnings for ' + filename + ':',
            warnings
        );
    }

    return result;
}

async function saveProcesses() {
    const button = document.getElementById('saveProcessesButton');
    const status = document.getElementById('processStatus');
    const uploadId = document.getElementById('targetUpload').value;
    const selected = substrates.filter(function(item) { return item.selected && !substrateHasBeenCut(item); });
    const invalidSelected = substrates.filter(function(item) { return item.selected && substrateHasBeenCut(item); });
    let definitions;
    try { definitions = processDefinitions(); }
    catch (err) { status.textContent = 'Error: ' + err.message; return; }
    if (invalidSelected.length) {
        status.textContent = 'Cut parent substrates are no longer physically available and cannot be processed.';
        return;
    }
    if (!uploadId) { status.textContent = 'Select a target upload first.'; return; }
    if (!selected.length) { status.textContent = 'Select at least one substrate.'; return; }
    if (!definitions.length) { status.textContent = 'Add at least one process.'; return; }

    button.disabled = true;
    let saved = 0;
    const uploadedEntries = [];
    try {
        for (let i = 0; i < definitions.length; i++) {
            const definition = definitions[i];
            const stamp = new Date().toISOString().replace(/[-:TZ.]/g, '');

            if (definition.kind === 'sample_cut') {
                validateSampleCutRecipe(definition.recipe, selected, i);

                for (let parentIndex = 0; parentIndex < selected.length; parentIndex++) {
                    const substrate = selected[parentIndex];
                    const data = sampleCutArchiveData(
                        definition,
                        substrate,
                        i
                    );
                    const filename =
                        'processing_sample_cut_' +
                        safePart(substrate.labId) +
                        '_' +
                        stamp +
                        '_' +
                        String(i + 1) +
                        '_' +
                        String(parentIndex + 1) +
                        '.archive.json';

                    status.textContent =
                        'Cutting parent ' +
                        String(parentIndex + 1) +
                        ' of ' +
                        selected.length +
                        ' for process ' +
                        String(i + 1) +
                        '...';

                    const responseData = await uploadArchive(uploadId, filename, data);
                    uploadedEntries.push({
                        filename: filename,
                        entryId: responseData.processing && responseData.processing.entry
                            ? responseData.processing.entry.entry_id : null
                    });
                    saved += 1;
                }
            } else {
                const data = processArchiveData(definition, selected, i);
                const filename =
                    'processing_' +
                    safePart(definition.type) +
                    '_' +
                    stamp +
                    '_' +
                    String(i + 1) +
                    '.archive.json';

                status.textContent =
                    'Saving process ' +
                    String(i + 1) +
                    ' of ' +
                    definitions.length +
                    '...';

                const responseData = await uploadArchive(uploadId, filename, data);
                uploadedEntries.push({
                    filename: filename,
                    entryId: responseData.processing && responseData.processing.entry
                        ? responseData.processing.entry.entry_id : null
                });
                saved += 1;
            }
        }

        let indexed = false;
        let lastRefreshError = null;

        // Wait for NOMAD archive queries to expose all newly saved entries.
        // The upload itself has already completed; never upload again here.
        for (let attempt = 0; attempt < 8; attempt++) {
            status.textContent =
                saved + ' process/action entries saved. ' +
                'Updating NOMAD data (' + (attempt + 1) + '/8)...';

            try {
                await refreshProcessingData({catalogs: false});

                indexed = uploadedEntries.every(function(uploaded) {
                    return treatmentHistoryState.some(function(entry) {
                        return entry.uploadId === uploadId && (
                            (uploaded.entryId &&
                             entry.entryId === uploaded.entryId) ||
                            String(entry.mainfile || '')
                                .split('/').pop() === uploaded.filename
                        );
                    });
                });

                if (indexed) {
                    break;
                }
            } catch (refreshError) {
                lastRefreshError = refreshError;
                console.warn('NOMAD refresh failed:', refreshError);
            }

            if (attempt < 7) {
                await new Promise(function(resolve) {
                    setTimeout(
                        resolve,
                        Math.min(1000 * (attempt + 1), 4000)
                    );
                });
            }
        }

        if (indexed) {
            status.textContent =
                saved + ' process/action entries saved and ' +
                'visible in NOMAD. Processing display updated.';
        } else {
            status.textContent =
                saved + ' process/action entries saved, but not ' +
                'all are visible in NOMAD queries yet. ' +
                'Switch away and back to refresh. ' +
                'Do not upload the same processes again.' +
                (lastRefreshError
                    ? ' Last refresh error: ' + lastRefreshError.message
                    : '');
        }

    } catch (error) {
        status.textContent = (saved ? saved + ' process(es) saved; next process failed: ' : 'Error: ') + error.message;
    } finally {
        button.disabled = false;
    }
}

function selectIncomingSubstrate(entryId) {
    if (!entryId) {
        return false;
    }

    const selected = substrates.find(function(item) {
        return item.entryId === entryId;
    });

    if (!selected || substrateHasBeenCut(selected)) {
        return false;
    }

    selected.selected = true;

    const searchInput =
        document.getElementById('substrateSearch');

    if (searchInput) {
        searchInput.value = selected.labId;
    }

    renderSubstrates();

    return true;
}


function configurePdiLabReturnButton(label) {
    const button =
        document.getElementById('returnButton');

    if (!button) {
        return;
    }

    button.textContent =
        label || 'Back to MBE Experiment';

    button.style.display = 'inline-block';

    button.onclick = function() {
        button.style.display = 'none';

        window.parent.postMessage(
            {
                type: 'pdi-lab:back'
            },
            window.location.origin
        );
    };
}


function applyIncomingSelection() {
    const params =
        new URLSearchParams(window.location.search);

    const entryId =
        params.get('substrate_entry_id');

    const returnUrl =
        params.get('return_url');

    const returnLabel =
        params.get('return_label');

    if (entryId) {
        selectIncomingSubstrate(entryId);
    }

    if (returnUrl) {
        try {
            const target =
                new URL(
                    returnUrl,
                    window.location.origin
                );

            if (
                target.origin ===
                window.location.origin
            ) {
                const button =
                    document.getElementById(
                        'returnButton'
                    );

                button.textContent =
                    returnLabel || 'Back';

                button.style.display =
                    'inline-block';

                button.onclick = function() {
                    window.location.href =
                        target.href;
                };
            }
        } catch (_) {}
    }
}


function refreshProcessCardCatalogs() {
    document.querySelectorAll('.process-card').forEach(function(card) {
        const typeSelect = card.querySelector('.process-type');
        const recipeSelect = card.querySelector('.recipe-select');
        const oldType = typeSelect.value;
        const oldRecipe = recipeSelect.value;

        typeSelect.innerHTML = '';
        Object.entries(recipeSchemas).forEach(function([key, definition]) {
            typeSelect.add(new Option(definition.label || key, key));
        });

        if (oldType && !Array.from(typeSelect.options).some(function(opt) {
            return opt.value === oldType;
        })) {
            const opt = new Option('Unavailable: ' + oldType, oldType);
            opt.disabled = true;
            typeSelect.add(opt);
        }

        typeSelect.value = oldType;
        updateRecipeSelect(card);

        if (oldRecipe && !Array.from(recipeSelect.options).some(function(opt) {
            return opt.value === oldRecipe;
        })) {
            const opt = new Option('Unavailable recipe', oldRecipe);
            opt.disabled = true;
            recipeSelect.add(opt);
        }

        recipeSelect.value = oldRecipe;

        const meta = card.querySelector('.process-meta');
        if (meta && recipeSchemas[oldType]) {
            meta.textContent = recipeSchemas[oldType].label || oldType;
        }

        updateProcessCardMode(card);
    });
}

let processingRefreshPromise = null;

function refreshProcessingData(options) {
    if (processingRefreshPromise) {
        return processingRefreshPromise;
    }

    processingRefreshPromise = (async function() {
        const catalogs = !(options && options.catalogs === false);
        if (catalogs) recipeSchemas = await loadProcessTypes();

        const [freshSubstrates, freshRecipes, freshHistory] =
            await Promise.all([
                loadSubstrates(),
                catalogs ? loadRecipes() : Promise.resolve(null),
                loadTreatmentHistoryEntries()
            ]);

        const selectedEntryIds = new Set(
            substrates
                .filter(function(item) { return item.selected; })
                .map(function(item) { return item.entryId; })
        );

        const openHistoryIds = new Set(
            substrates
                .filter(function(item) { return item.historyOpen; })
                .map(function(item) { return item.entryId; })
        );

        const cutParentIds = new Set(
            freshSubstrates
                .map(function(item) {
                    return referenceEntryId(item.parentSample);
                })
                .filter(Boolean)
        );

        freshSubstrates.forEach(function(item) {
            item.selected =
                selectedEntryIds.has(item.entryId) &&
                !cutParentIds.has(item.entryId);
            item.historyOpen = openHistoryIds.has(item.entryId);
        });

        substrates = freshSubstrates;
        treatmentHistoryState = freshHistory;

        if (catalogs) {
            recipes = freshRecipes;
            refreshProcessCardCatalogs();

            const upload = document.getElementById('targetUpload');
            const oldUpload = upload.value;

            await loadUploads();

            if (Array.from(upload.options).some(function(opt) {
                return opt.value === oldUpload;
            })) {
                upload.value = oldUpload;
            }
        }

        populateFilter(
            'materialFilter',
            substrates.map(function(item) { return item.material; })
        );
        populateFilter(
            'batchFilter',
            substrates.flatMap(function(item) {
                return [item.crystalId, item.chargeId];
            })
        );
        populateFilter(
            'orientationFilter',
            substrates.map(function(item) { return item.orientation; })
        );

        renderSubstrates();
        updateSaveSummary();
    })().finally(function() {
        processingRefreshPromise = null;
    });

    return processingRefreshPromise;
}


window.addEventListener('message', function(event) {
    if (
        event.origin !== window.location.origin ||
        event.source !== window.parent
    ) {
        return;
    }

    const data = event.data || {};

    if (data.type === 'pdi-lab:resume') {
        refreshProcessingData().catch(function(error) {
            console.error('Could not refresh Processing data:', error);
        });
        return;
    }

    if (data.type === 'pdi-lab:activate-processing') {
        configurePdiLabReturnButton(
            'Back to MBE Experiment'
        );

        refreshProcessingData().then(function() {
            selectIncomingSubstrate(data.substrateEntryId);
        }).catch(function(error) {
            console.error('Could not refresh Processing data:', error);
            selectIncomingSubstrate(data.substrateEntryId);
        });

        return;
    }

    if (data.type === 'pdi-lab:return-context') {
        if (data.target === 'experiment') {
            configurePdiLabReturnButton(
                'Back to MBE Experiment'
            );
        }

        return;
    }
});


async function initialise() {
    try {
        document.getElementById('substrateStatus').textContent = 'Loading substrates...';

        recipeSchemas = await loadProcessTypes();

        [substrates, recipes, treatmentHistoryState] = await Promise.all([
            loadSubstrates(),
            loadRecipes(),
            loadTreatmentHistoryEntries()
        ]);

        await loadUploads();
        populateFilter('materialFilter', substrates.map(function(s) { return s.material; }));
        populateFilter('batchFilter', substrates.flatMap(function(s) { return [s.crystalId, s.chargeId]; }));
        populateFilter('orientationFilter', substrates.map(function(s) { return s.orientation; }));
        applyIncomingSelection();
        renderSubstrates();
        addProcess();
        document.getElementById('saveProcessesButton').disabled = false;
        updateSaveSummary();

        const pageParams =
            new URLSearchParams(window.location.search);

        if (
            pageParams.get('pdi_lab') === '1' &&
            window.parent !== window
        ) {
            window.parent.postMessage(
                {
                    type: 'pdi-lab:ready',
                    app: 'processing'
                },
                window.location.origin
            );
        }
    } catch (error) {
        console.error(error);
        document.getElementById('substrateStatus').textContent = 'Failed to load NOMAD data.';
        document.getElementById('processStatus').textContent = String(error);
    }
}

['substrateSearch'].forEach(function(id) { document.getElementById(id).addEventListener('input', renderSubstrates); });
['materialFilter', 'batchFilter', 'orientationFilter', 'statusFilter'].forEach(function(id) { document.getElementById(id).addEventListener('change', renderSubstrates); });
document.getElementById('selectAllButton').addEventListener('click', function() {
    filteredSubstrates().forEach(function(substrate) { substrate.selected = true; });
    renderSubstrates(); updateSaveSummary();
});
document.getElementById('clearSelectionButton').addEventListener('click', function() {
    substrates.forEach(function(substrate) { substrate.selected = false; });
    renderSubstrates(); updateSaveSummary();
});
document.getElementById('addProcessButton').addEventListener('click', addProcess);
document.getElementById('saveProcessesButton').addEventListener('click', saveProcesses);

initialise();
