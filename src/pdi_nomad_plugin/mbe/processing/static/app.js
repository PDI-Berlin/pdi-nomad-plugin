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

// These are the actual original m_defs for the supported processing actions.
// The server returns this list; never trust a substituted process m_def from
// configuration, browser state, or an older custom PDI schema registration.
const ORIGINAL_PROCESS_TYPES = Object.freeze({
    cleaning: Object.freeze({
        schema: 'nomad_material_processing.general.CleaningRecipe',
        processSchema: 'nomad_material_processing.general.Cleaning'
    }),
    annealing: Object.freeze({
        schema: 'nomad_material_processing.general.AnnealingRecipe',
        processSchema: 'nomad_material_processing.general.Annealing'
    }),
});


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

    for (const [key, definition] of Object.entries(result)) {
        const approved = ORIGINAL_PROCESS_TYPES[key];
        if (!approved || !definition ||
            definition.schema !== approved.schema ||
            definition.processSchema !== approved.processSchema) {
            throw new Error('Non-original process or recipe m_def rejected: ' + key);
        }
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

const processingCutParentIds = new Set();
const processingVerifiedCutChildren = new Map();
const processingCutHistoryByEntry = new Map();

function recordProcessingCutHistory(entryId, record) {
    if (!entryId) return;
    if (!processingCutHistoryByEntry.has(entryId)) {
        processingCutHistoryByEntry.set(entryId, []);
    }
    processingCutHistoryByEntry.get(entryId).push(record);
}

function processingCutUnavailable(substrate) {
    return processingCutParentIds.has(substrate.entryId) ||
        processingCutAttemptedParents.has(substrate.entryId);
}

function substrateStatus(substrate) {
    if (!substrate || !substrate.entryId) return '';

    const processed = substrate.processed === true ||
        processingCutParentIds.has(substrate.entryId) ||
        treatmentHistoryState.some(function(treatment) {
            return treatmentReferencesSubstrate(
                treatment, substrate.entryId
            );
        });

    return processed ? 'processed' : 'unprocessed';
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

function referenceContainsEntryId(reference, substrateEntryId) {
    // Match the actual referenced entry, not an arbitrary substring of JSON.
    return Boolean(substrateEntryId) &&
        referenceEntryId(reference) === substrateEntryId;
}

function treatmentReferencesSubstrate(treatment, substrateEntryId) {
    if (!treatment || !treatment.data || !substrateEntryId) return false;

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
    // Only the original Process.samples[] reference is verified.
    const rows = treatmentHistoryState.filter(function(treatment) {
        return treatmentReferencesSubstrate(treatment, substrate.entryId);
    }).map(function(treatment) { return {treatment: treatment}; });
    rows.sort(function(a, b) {
        return String(treatmentDate(a.treatment)).localeCompare(String(treatmentDate(b.treatment)));
    });
    return rows;
}

function renderHistoryDetails(container, substrate, history) {
    history.forEach(function(row) {
        const item = document.createElement('div');
        item.className = 'history-item';
        const title = document.createElement('div');
        title.className = 'history-title';
        title.textContent = row.treatment.label + ': ' + row.treatment.entryName;
        item.appendChild(title);
        const date = treatmentDate(row.treatment);
        if (date) {
            const meta = document.createElement('div');
            meta.className = 'history-meta';
            meta.textContent = formatProcessingDateTime(date);
            item.appendChild(meta);
        }
        container.appendChild(item);
    });
}

// The original CrystallineSubstrate has no PDI-only flags or batch fields.
// Read the exact archive produced by the Intake app (Stage 4).
function originalSubstrateFields(data) {
    const components = Array.isArray(data.components) ? data.components : [];
    const substance = (components[0] && components[0].pure_substance) || {};
    const formula = String(substance.molecular_formula || '').trim();
    const crystal = (data.crystal_properties || {});
    const hkl = ((crystal.surface_orientation || {}).hkl_reciprocal || {});
    const hklText = ['h_index', 'k_index', 'l_index'].every(function(k) {
        return hkl[k] !== undefined && hkl[k] !== null;
    }) ? [hkl.h_index, hkl.k_index, hkl.l_index].join(' ') : '';
    const description = String(data.description || '');
    const crystalMatch = description.match(/^Crystal ID:\s*(.*)$/m);
    const chargeMatch = description.match(/^Charge ID:\s*(.*)$/m);
    return {
        formula: formula,
        material: formula,
        crystalId: crystalMatch ? crystalMatch[1].trim() : '',
        chargeId: chargeMatch ? chargeMatch[1].trim() : '',
        orientation: hklText,
    };
}

async function loadSubstrates() {
    const schema = 'pdi_nomad_plugin.mbe.materials.SubstrateMbe';
    const status = document.getElementById('substrateStatus');
    const indexed = [];
    const seen = new Set();
    let cursor = null;
    let complete = false;

    for (let page = 0; page < 50; page++) {
        const pagination = {page_size: 200};
        if (cursor) pagination.page_after_value = cursor;

        const response = await fetch(nomadApiBase() + '/entries/query', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                owner: 'visible',
                query: {'section_defs.definition_qualified_name': schema},
                pagination,
                required: {
                    include: ['entry_id', 'upload_id', 'entry_name']
                }
            })
        });

        if (!response.ok)
            throw new Error('Substrate index: HTTP ' + response.status);

        const result = await response.json();

        for (const entry of result.data || []) {
            if (entry.entry_id && entry.upload_id &&
                !seen.has(entry.entry_id)) {
                indexed.push(entry);
                seen.add(entry.entry_id);
            }
        }

        const next = result.pagination?.next_page_after_value;
        if (!next) {
            complete = true;
            break;
        }
        if (next === cursor)
            throw new Error('Substrate pagination did not advance.');
        cursor = next;
    }

    if (!complete)
        throw new Error('Substrate index pagination incomplete.');

    const accepted = [];
    let position = 0;
    let finished = 0;
    let unavailable = 0;

    async function worker() {
        while (true) {
            const i = position++;
            if (i >= indexed.length) return;
            const entry = indexed[i];

            try {
                const response = await fetch(
                    nomadApiBase() + '/entries/' +
                    encodeURIComponent(entry.entry_id) + '/archive'
                );

                if (response.status === 401 || response.status === 403)
                    throw new Error('ACCESS_ERROR HTTP ' + response.status);

                if (!response.ok) {
                    unavailable++;
                    continue;
                }

                const payload = await response.json();
                const wrapper = payload.data || payload.archive || payload;
                const archive = wrapper.archive || wrapper;
                const data = archive.data || archive;

                if (data.m_def !== schema) continue;

                const fields = originalSubstrateFields(data);
                accepted.push({
                    entryId: entry.entry_id,
                    uploadId: entry.upload_id,
                    labId: data.lab_id || data.name ||
                           entry.entry_name || entry.entry_id,
                    material: fields.material,
                    formula: fields.formula,
                    crystalId: fields.crystalId,
                    chargeId: fields.chargeId,
                    orientation: fields.orientation,
                    geometry: data.geometry || null,
                    processed: data.processed === true,
                    selected: false
                });
            } catch (error) {
                if (error.message.startsWith('ACCESS_ERROR'))
                    throw error;
                unavailable++;
                console.warn('Substrate unavailable:', entry.entry_id, error);
            } finally {
                finished++;
                if (finished % 20 === 0 || finished === indexed.length)
                    status.textContent =
                        'Loading substrates: ' + finished +
                        '/' + indexed.length;
            }
        }
    }

    await Promise.all(
        Array.from(
            {length: Math.min(10, indexed.length)},
            () => worker()
        )
    );

    window.processingUnavailableSubstrates = unavailable;

    const childLinks = new Map();
    const parentIds = new Set();

    for (const [childId, link] of processingVerifiedCutChildren) {
        childLinks.set(childId, link);
        parentIds.add(link.parentId);
    }

    try {
        const cuts = await cutExistingEntries();
        window.processingCutHistoryError = '';
        processingCutHistoryByEntry.clear();

        for (const item of cuts) {
            const data = item.data || {};
            const parentId = cutReferenceEntryId(
                data.parent_sample?.reference
            );
            if (!parentId) continue;

            // Even an incomplete cut must block a blind second attempt.
            parentIds.add(parentId);

            const childIds = (data.children_samples || [])
                .map(child => cutReferenceEntryId(child.reference))
                .filter(Boolean);

            const record = {
                name: data.name || 'Sample Cut',
                datetime: data.datetime || '',
                count: data.number_of_samples || childIds.length
            };

            recordProcessingCutHistory(parentId, {
                ...record, role: 'parent'
            });

            childIds.forEach((childId, index) => {
                recordProcessingCutHistory(childId, {
                    ...record, role: 'child', childIndex: index + 1
                });
            });

            for (const child of data.children_samples || []) {
                const childId = cutReferenceEntryId(child.reference);
                if (childId) childLinks.set(childId, {
                    parentId,
                    uploadId: item.upload_id
                });
            }
        }
    } catch (error) {
        window.processingCutHistoryError = error.message;
        console.error('Cannot load complete Sample Cut history:', error);
        // The Execute action itself independently fails closed.
    }

    processingCutParentIds.clear();
    for (const parentId of parentIds) {
        processingCutParentIds.add(parentId);
    }

    const byId = new Map(accepted.map(item => [item.entryId, item]));
    const missingChildren = [];

    for (const [childId, link] of childLinks) {
        if (byId.has(childId)) {
            byId.get(childId).processed = true;
        } else {
            missingChildren.push({childId, ...link});
        }
    }

    let childPosition = 0;
    let childErrors = 0;

    async function loadChildWorker() {
        while (true) {
            const index = childPosition++;
            if (index >= missingChildren.length) return;

            const {childId, parentId, uploadId} = missingChildren[index];

            try {
                const data = await cutReadArchive(childId);

                if (!data.lab_id || !data.geometry ||
                    cutReferenceEntryId(
                        data.parent_sample?.reference
                    ) !== parentId) {
                    throw new Error('Child archive/parent reference mismatch');
                }

                const fields = originalSubstrateFields(data);

                accepted.push({
                    entryId: childId,
                    uploadId: uploadId,
                    labId: data.lab_id,
                    material: fields.material,
                    formula: fields.formula,
                    crystalId: fields.crystalId,
                    chargeId: fields.chargeId,
                    orientation: fields.orientation,
                    geometry: data.geometry,
                    processed: true,
                    selected: false
                });
            } catch (error) {
                childErrors++;
                console.warn(
                    'Could not load cut child:', childId, error
                );
            }
        }
    }

    await Promise.all(Array.from(
        {length: Math.min(8, missingChildren.length)},
        () => loadChildWorker()
    ));

    for (const item of accepted) {
        if (parentIds.has(item.entryId)) {
            item.processed = true;
            item.selected = false;
        }
    }

    window.processingCutChildLoadErrors = childErrors;

    return accepted.sort((a, b) =>
        String(a.labId).localeCompare(String(b.labId), undefined, {
            numeric: true, sensitivity: 'base'
        })
    );
}

// Adapt *existing* legacy library-template geometry for display/validation only.
// Archived cut-template geometry is for read-only display; no cut schema is registered.
async function loadRecipes() {
    const result = [];
    for (const [type, definition] of Object.entries(recipeSchemas)) {
        const entries = await queryEntries(definition.schema, 200, [
            'entry_id', 'upload_id', 'entry_name', 'data.name', 'data.lab_id',
            'data.steps', 'data.instruments'
        ]);
        entries.forEach(function(entry) {
            const data = entry.data || {};
            result.push({
                type: type,
                entryId: entry.entry_id,
                uploadId: entry.upload_id,
                name: data.lab_id || data.name || entry.entry_name || entry.entry_id
            });
        });
    }
    return result;
}

async function loadUploads() {
    const select = document.getElementById('targetUpload');
    const status = document.getElementById('uploadStatus');

    select.replaceChildren(new Option('Loading uploads...', ''));

    try {
        const params = new URLSearchParams();
        params.append('roles', 'main_author');
        params.append('roles', 'coauthor');
        params.append('page_size', '100');

        const response = await fetch(
            nomadApiBase() + '/uploads?' + params.toString()
        );

        if (!response.ok)
            throw new Error('Upload request failed: HTTP ' + response.status);

        const result = await response.json();
        const uploads = (result.data || []).filter(upload =>
            !upload.published && !upload.is_processing
        );

        select.replaceChildren(new Option('Select target upload...', ''));

        uploads.forEach(function(upload) {
            select.add(new Option(
                (upload.upload_name || 'Unnamed upload') +
                ' — ' + upload.upload_id,
                upload.upload_id
            ));
        });

        status.textContent =
            uploads.length + ' writable unpublished upload(s) available.';
        status.style.color = '';

    } catch (error) {
        select.replaceChildren(new Option('Could not load uploads', ''));
        status.textContent = 'Error: ' + error.message;
        status.style.color = '#c62828';
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
    container.innerHTML = '';

    visible.forEach(function(substrate) {
        const history = treatmentHistoryForSubstrate(substrate);
        const cutHistory =
            processingCutHistoryByEntry.get(substrate.entryId) || [];
        const historyCount = history.length + cutHistory.length;
        const row = document.createElement('div');
        row.className = 'result-grid result-row';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = substrate.selected;
        checkbox.disabled = processingCutUnavailable(substrate);
        if (checkbox.disabled) {
            checkbox.checked = false;
            substrate.selected = false;
            checkbox.title =
                'Already cut: parent retained for process history.';
        }
        checkbox.addEventListener('change', function() {
            substrate.selected = checkbox.checked;
            updateSaveSummary();
        });
        row.appendChild(checkbox);

        [
            processingCutShortId(substrate),
            substrate.material || '-',
            substrate.crystalId || substrate.chargeId || '-',
            substrate.orientation || '-'
        ].forEach(function(value, index) {
            const cell = document.createElement('div');
            cell.textContent = value;
            cell.title = index === 0
                ? String(substrate.labId || '')
                : String(value);
            row.appendChild(cell);
        });

        const statusCell = document.createElement('div');
        statusCell.className = 'result-status-cell';
        const statusText = document.createElement('span');
        statusText.textContent = substrateStatus(substrate) || '-';
        statusCell.appendChild(statusText);

        if (historyCount) {
            const historyButton = document.createElement('button');
            historyButton.type = 'button';
            historyButton.className = 'history-toggle';
            historyButton.textContent = historyCount + ' process' + (historyCount === 1 ? '' : 'es') + (substrate.historyOpen ? ' ▴' : ' ▾');
            historyButton.addEventListener('click', function() {
                substrate.historyOpen = !substrate.historyOpen;
                renderSubstrates();
            });
            statusCell.appendChild(historyButton);
        }
        row.appendChild(statusCell);
        container.appendChild(row);

        if (substrate.historyOpen && historyCount) {
            const historyRow = document.createElement('div');
            historyRow.className = 'history-row';
            if (history.length) {
                renderHistoryDetails(historyRow, substrate, history);
            }

            for (const cut of cutHistory) {
                const detail = document.createElement('div');
                detail.className = 'cut-history-record';

                const role = cut.role === 'parent'
                    ? 'Parent → ' + cut.count + ' children'
                    : 'Child ' + cut.childIndex + '/' + cut.count;

                const date = cut.datetime
                    ? new Date(cut.datetime).toLocaleString('de-DE')
                    : '';

                detail.textContent = [
                    'Sample Cut',
                    role,
                    date
                ].filter(Boolean).join(' · ');

                detail.title = cut.name;
                historyRow.appendChild(detail);
            }

            container.appendChild(historyRow);
        }
    });

    document.getElementById('substrateStatus').textContent =
        visible.length + ' matching substrate' + (visible.length === 1 ? '' : 's') +
        '; ' + substrates.filter(function(item) { return item.selected; }).length + ' selected.';
}


// NOMAD Geometry subclasses are identified by m_def, not a custom shape field.
// shape is read only to support old, not-yet-migrated archives.
const NOMAD_GEOMETRY = 'nomad_material_processing.general.';

function updateRecipeSelect(card) {
    const type = card.querySelector('.process-type').value;
    const select = card.querySelector('.recipe-select');
    const matching = recipes.filter(function(recipe) { return recipe.type === type; });
    select.innerHTML = '<option value="">' +
        (matching.length ? 'Select recipe...' : 'No recipes found') + '</option>';
    matching.forEach(function(recipe) {
        const option = document.createElement('option');
        option.value = recipe.entryId;
        option.dataset.uploadId = recipe.uploadId;
        option.textContent = recipe.name;
        select.appendChild(option);
    });
    select.disabled = matching.length === 0;
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

function processDateTimeValue(card) {
    const date = card.querySelector('.process-date').value;
    const hour = card.querySelector('.process-hour').value;
    const minute = card.querySelector('.process-minute').value;

    if (!date || !hour || !minute) return '';

    const value = new Date(date + 'T' + hour + ':' + minute + ':00');
    if (!Number.isFinite(value.getTime())) {
        throw new Error('Invalid process start date/time.');
    }

    const pad = n => String(n).padStart(2, '0');
    const actualDate = [
        value.getFullYear(),
        pad(value.getMonth() + 1),
        pad(value.getDate())
    ].join('-');

    if (actualDate !== date ||
        pad(value.getHours()) !== hour ||
        pad(value.getMinutes()) !== minute) {
        throw new Error('Invalid or nonexistent local process start time.');
    }

    return date + 'T' + hour + ':' + minute + ':00';
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
                <div>
                    <label>Process start date *</label>
                    <div style="display:flex;gap:8px;align-items:center;">
                        <input class="process-date" type="date" required
                            aria-label="Process start date">
                        <button class="process-open-calendar" type="button">Calendar</button>
                    </div>
                </div>
                <div>
                    <label>Process start time *</label>
                    <div style="display:flex;gap:8px;align-items:center;">
                        <select class="process-hour" required aria-label="Hour">
                            <option value="">Hour</option>
                            ${Array.from({length:24}, (_, i) => {
                                const v = String(i).padStart(2, '0');
                                return '<option value="' + v + '">' + v + '</option>';
                            }).join('')}
                        </select>
                        <span>:</span>
                        <select class="process-minute" required aria-label="Minute">
                            <option value="">Minute</option>
                            ${Array.from({length:60}, (_, i) => {
                                const v = String(i).padStart(2, '0');
                                return '<option value="' + v + '">' + v + '</option>';
                            }).join('')}
                        </select>
                    </div>
                </div>
            </div>
            <label class="recipe-label">Recipe</label><select class="recipe-select"></select>
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
        updateSaveSummary();
    });
    const dateInput = card.querySelector('.process-date');
    dateInput.addEventListener('keydown', function(event) {
        if (event.key.length === 1 ||
            ['Backspace', 'Delete'].includes(event.key)) {
            event.preventDefault();
        }
    });
    dateInput.addEventListener('paste', event => event.preventDefault());
    dateInput.addEventListener('drop', event => event.preventDefault());

    card.querySelector('.process-open-calendar').addEventListener(
        'click', function() {
            try {
                if (typeof dateInput.showPicker === 'function') {
                    dateInput.showPicker();
                } else {
                    dateInput.focus();
                }
            } catch (_) {
                dateInput.focus();
            }
        }
    );

    card.querySelectorAll(
        '.process-date, .process-hour, .process-minute'
    ).forEach(input => input.addEventListener('change', updateSaveSummary));

    card.querySelector('.recipe-select').addEventListener('change', updateSaveSummary);
    card.querySelector('.collapse-button').addEventListener('click', function() { card.classList.remove('open'); });
    card.querySelector('.remove-button').addEventListener('click', function() { card.remove(); renumberProcesses(); });
    updateRecipeSelect(card);
    updateSaveSummary();
}

function processDefinitions() {
    return Array.from(document.querySelectorAll('.process-card')).map(function(card) {
        const type = card.querySelector('.process-type').value;
        if (!Object.hasOwn(ORIGINAL_PROCESS_TYPES, type)) {
            throw new Error('Unsupported processing action: ' + type);
        }
        const recipeSelect = card.querySelector('.recipe-select');
        const recipe = recipes.find(function(item) {
            return item.type === type && item.entryId === recipeSelect.value;
        }) || null;
        return {
            type: type,
            recipe: recipe,
            datetime: processDateTimeValue(card),
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
    // Do not duplicate the upstream Process normalizer. Its original
    // implementation reads the referenced recipe and copies instructions
    // during NOMAD processing. Only a recipe reference belongs here.
    if (definition.comments) data.description = definition.comments;
    return data;
}


async function uploadArchive(uploadId, filename, data) {
    // Server validates against the installed original NOMAD metainfo BEFORE PUT.
    // If validation fails, no archive is written.
    const preflightResponse = await fetch('./validate-process', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
        body: JSON.stringify({data: data})
    });
    const preflightResult = await preflightResponse.json().catch(function() { return {}; });
    if (!preflightResponse.ok || preflightResult.valid !== true || preflightResult.schema !== data.m_def) {
        const detail = preflightResult.detail || 'Original NOMAD process validation failed.';
        throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    }
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

function resetProcessingAfterSuccess(entryIds) {
    const completed = new Set(entryIds);

    substrates.forEach(function(substrate) {
        if (completed.has(substrate.entryId)) {
            substrate.selected = false;
            substrate.historyOpen = false;
        }
    });

    const list = document.getElementById('processList');
    const bar = document.getElementById('processChoiceBar');
    const panel = document.getElementById('sampleCutPanel');

    list.replaceChildren();
    processCounter = 0;

    panel.style.display = 'none';

    // Restore the initial process-choice position.
    list.before(bar);
    bar.style.display = 'flex';

    const cutFields = [
        'cutDate', 'cutHour', 'cutMinute',
        'cutCount', 'cutWidth', 'cutLength',
        'cutRadius', 'cutAngle', 'cutHeight',
        'cutNotes', 'cutOtherLocation'
    ];

    cutFields.forEach(function(id) {
        const input = document.getElementById(id);
        if (input) input.value = '';
    });

    processingCutSyncSelection();
    renderSubstrates();
    updateSaveSummary();

    // Intentionally preserve targetUpload and success messages.
}

async function saveProcesses() {
    const button = document.getElementById('saveProcessesButton');
    const status = document.getElementById('processStatus');
    const uploadId = document.getElementById('targetUpload').value;
    const selected = substrates.filter(function(item) { return item.selected; });
    let definitions;
    try { definitions = processDefinitions(); }
    catch (error) { status.textContent = 'Error: ' + error.message; return; }
    if (!uploadId) { status.textContent = 'Select a target upload first.'; return; }
    if (!selected.length) { status.textContent = 'Select at least one substrate.'; return; }
    if (!definitions.length) { status.textContent = 'Add at least one process.'; return; }

    // Validate every action before writing; never invoke a local PDI normalizer.
    try {
        definitions.forEach(function(definition, i) {
            processArchiveData(definition, selected, i);
        });
    } catch (error) {
        status.textContent = 'Validation failed before upload: ' + error.message;
        return;
    }

    button.disabled = true;
    let saved = 0;
    const uploadedEntries = [];
    try {
        for (let i = 0; i < definitions.length; i++) {
            const definition = definitions[i];
            const stamp = new Date().toISOString().replace(/[-:TZ.]/g, '');
            const data = processArchiveData(definition, selected, i);
            const filename = 'processing_' + safePart(definition.type) + '_' +
                stamp + '_' + String(i + 1) + '.archive.json';
            status.textContent = 'Saving process ' + (i + 1) + ' of ' + definitions.length + '...';
            const result = await uploadArchive(uploadId, filename, data);
            uploadedEntries.push({
                filename: filename,
                entryId: result.processing && result.processing.entry
                    ? result.processing.entry.entry_id : null
            });
            saved += 1;
        }
        let indexed = false;
        let lastRefreshError = null;
        for (let attempt = 0; attempt < 8; attempt++) {
            status.textContent = saved + ' process entries saved; updating NOMAD (' + (attempt + 1) + '/8)...';
            try {
                await refreshProcessingData({catalogs: false});
                indexed = uploadedEntries.every(function(uploaded) {
                    return treatmentHistoryState.some(function(entry) {
                        return entry.uploadId === uploadId && (
                            (uploaded.entryId && entry.entryId === uploaded.entryId) ||
                            String(entry.mainfile || '').split('/').pop() === uploaded.filename
                        );
                    });
                });
                if (indexed) break;
            } catch (error) {
                lastRefreshError = error;
                console.warn('NOMAD refresh failed:', error);
            }
            if (attempt < 7) {
                await new Promise(function(resolve) {
                    setTimeout(resolve, Math.min(1000 * (attempt + 1), 4000));
                });
            }
        }
        if (indexed) {
            resetProcessingAfterSuccess(
                selected.map(function(item) { return item.entryId; })
            );
        }

        status.textContent = indexed
            ? saved + ' process entries saved and visible in NOMAD.'
            : saved + ' process entries saved but not yet all visible in NOMAD. Do not re-upload blindly.' +
              (lastRefreshError ? ' Last refresh error: ' + lastRefreshError.message : '');
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

    if (!selected) {
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

        freshSubstrates.forEach(function(item) {
            item.selected = selectedEntryIds.has(item.entryId) &&
                !processingCutUnavailable(item);
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

        // Load uploads independently, even if a catalog request fails.
        await loadUploads();
        recipeSchemas = await loadProcessTypes();

        const catalogResults = await Promise.allSettled([
            loadSubstrates(),
            loadRecipes(),
            loadTreatmentHistoryEntries()
        ]);

        const catalogNames = ['Substrates', 'Recipes', 'Process history'];
        const catalogErrors = [];

        catalogResults.forEach(function(result, index) {
            if (result.status === 'rejected') {
                catalogErrors.push(
                    catalogNames[index] + ': ' +
                    (result.reason?.message || String(result.reason))
                );
            }
        });

        substrates = catalogResults[0].status === 'fulfilled'
            ? catalogResults[0].value : [];
        recipes = catalogResults[1].status === 'fulfilled'
            ? catalogResults[1].value : [];
        treatmentHistoryState = catalogResults[2].status === 'fulfilled'
            ? catalogResults[2].value : [];

        window.processingCatalogErrors = catalogErrors;
        populateFilter('materialFilter', substrates.map(function(s) { return s.material; }));
        populateFilter('batchFilter', substrates.flatMap(function(s) { return [s.crystalId, s.chargeId]; }));
        populateFilter('orientationFilter', substrates.map(function(s) { return s.orientation; }));
        applyIncomingSelection();
        renderSubstrates();
        // A process is added only after selecting its type.
        document.getElementById('saveProcessesButton').disabled = false;
        updateSaveSummary();

        if (catalogErrors.length) {
            const status = document.getElementById('processStatus');
            status.textContent = 'Loading errors: ' + catalogErrors.join(' | ');
            status.style.color = '#c62828';
            document.getElementById('saveProcessesButton').disabled = true;
        }

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
        document.getElementById('substrateStatus').textContent =
            'Failed to initialize Processing: ' + error.message;
        document.getElementById('processStatus').textContent =
            'Error: ' + error.message;
        document.getElementById('processStatus').style.color = '#c62828';
    }
}

['substrateSearch'].forEach(function(id) { document.getElementById(id).addEventListener('input', renderSubstrates); });
['materialFilter', 'batchFilter', 'orientationFilter', 'statusFilter'].forEach(function(id) { document.getElementById(id).addEventListener('change', renderSubstrates); });
document.getElementById('selectAllButton').addEventListener('click', function() {
    filteredSubstrates().forEach(function(substrate) {
        if (!processingCutUnavailable(substrate)) {
            substrate.selected = true;
        }
    });
    renderSubstrates(); updateSaveSummary();
});
document.getElementById('clearSelectionButton').addEventListener('click', function() {
    substrates.forEach(function(substrate) { substrate.selected = false; });
    renderSubstrates(); updateSaveSummary();
});
document.getElementById('addProcessButton').addEventListener('click', addProcess);
document.getElementById('saveProcessesButton').addEventListener('click', saveProcesses);

initialise();


// PDI_PROCESS_SAMPLE_CUT_V1
let processingCutParent = null;

function processingCutElement(id) {
    return document.getElementById(id);
}

function processingCutShortId(sample) {
    const full = String(sample.labId || '');
    const charge = String(sample.chargeId || '')
        .normalize('NFKD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^A-Za-z0-9._-]+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^[-_.]+|[-_.]+$/g, '');

    const segment = '_' + charge + '_';
    const at = charge ? full.lastIndexOf(segment) : -1;

    return at < 0
        ? full
        : full.slice(0, at) + '_' + full.slice(at + segment.length);
}

function processingCutPositive(id) {
    const value = Number(processingCutElement(id).value);
    if (!Number.isFinite(value) || value <= 0) {
        throw new Error(id + ': enter a positive number.');
    }
    return value;
}

function processingCutValidate(parentOverride) {
    const parent = parentOverride || processingCutParent;
    if (!parent || !parent.entryId || !parent.uploadId) {
        throw new Error('Select one valid parent substrate.');
    }

    const count = Number(processingCutElement('cutCount').value);
    if (!Number.isSafeInteger(count) || count < 1 || count > 100) {
        throw new Error('Child count must be an integer between 1 and 100.');
    }

    const date = processingCutElement('cutDate').value;
    const hour = processingCutElement('cutHour').value;
    const minute = processingCutElement('cutMinute').value;

    if (!date || !hour || !minute) {
        throw new Error('Enter the cut date, hour and minute.');
    }

    const timestamp = new Date(date + 'T' + hour + ':' + minute + ':00');
    if (!Number.isFinite(timestamp.getTime())) {
        throw new Error('Invalid process date or time.');
    }

    const g = parent.geometry || {};
    const w = Number(g.width) * 1000;
    const l = Number(g.length ?? g.width) * 1000;
    const r = Number(g.radius) * 1000;
    const h = Number(g.height) * 1000;

    let parentArea;
    if (w > 0 && l > 0) {
        parentArea = w * l;
    } else if (r > 0) {
        const angle = g.central_angle == null ? 360 : Number(g.central_angle);
        if (!(angle > 0 && angle <= 360)) {
            throw new Error('Invalid parent sector angle.');
        }
        parentArea = Math.PI * r * r * angle / 360;
    } else {
        throw new Error('Parent geometry is missing or unsupported.');
    }

    const height = processingCutPositive('cutHeight');

    if (h > 0 && height > h + 1e-8) {
        throw new Error('Child thickness exceeds parent thickness.');
    }

    const shape = processingCutElement('cutShape').value;
    let area;
    let geometry;

    if (shape === 'rectangle') {
        const cw = processingCutPositive('cutWidth');
        const cl = processingCutPositive('cutLength');

        area = cw * cl;
        geometry = Math.abs(cw - cl) < 1e-8
            ? {
                m_def: 'nomad_material_processing.general.SquareCuboid',
                width: cw / 1000,
                height: height / 1000
            }
            : {
                m_def: 'nomad_material_processing.general.RectangleCuboid',
                width: cw / 1000,
                length: cl / 1000,
                height: height / 1000
            };

        if (w > 0 && l > 0) {
            const grid = (a, b) =>
                Math.floor((w + 1e-8) / a) *
                Math.floor((l + 1e-8) / b);

            if (Math.max(grid(cw, cl), grid(cl, cw)) < count) {
                throw new Error('Children cannot fit in a rectangular grid.');
            }
        }
    } else {
        const cr = processingCutPositive('cutRadius');
        const angle = shape === 'circle'
            ? 360 : processingCutPositive('cutAngle');

        if (angle > 360) throw new Error('Angle exceeds 360 degrees.');

        area = Math.PI * cr * cr * angle / 360;
        geometry = {
            m_def: shape === 'circle'
                ? 'nomad_material_processing.general.Cylinder'
                : 'nomad_material_processing.general.CylinderSector',
            radius: cr / 1000,
            height: height / 1000
        };

        if (shape === 'sector') geometry.central_angle = angle;

        if (r > 0 && cr > r + 1e-8) {
            throw new Error('Child radius exceeds parent radius.');
        }
    }

    if (count * area > parentArea * (1 + 1e-8)) {
        throw new Error(
            'Total child area exceeds parent area: ' +
            (count * area).toFixed(2) + ' > ' +
            parentArea.toFixed(2) + ' mm².'
        );
    }

    const locationChoice = processingCutElement('cutLocation').value;
    const location = locationChoice === 'Elsewhere'
        ? processingCutElement('cutOtherLocation').value.trim()
        : locationChoice;

    if (locationChoice === 'Elsewhere' && !location) {
        throw new Error('Specify the Elsewhere location.');
    }

    return {
        parent: parent,
        count: count,
        geometry: geometry,
        datetime: timestamp.toISOString(),
        location: location,
        name: processingCutElement('cutProcessName').value.trim(),
        description: processingCutElement('cutNotes').value.trim()
    };
}

function processingCutFeedback(message, error) {
    const status = processingCutElement('cutValidationStatus');
    status.textContent = message;
    status.style.color = error ? '#c62828' : '#173b22';
    status.style.fontWeight = error ? '600' : 'normal';
}

function processingCutSyncSelection() {
    const parents = substrates.filter(x => x.selected);
    const info = processingCutElement('cutParentInfo');
    const name = processingCutElement('cutProcessName');

    processingCutParent = parents.length === 1 ? parents[0] : null;

    if (!parents.length) {
        info.textContent = 'No parent substrate selected.';
        name.value = '';
        return;
    }

    if (parents.length === 1) {
        name.value = 'cut_' + processingCutShortId(parents[0]);
    } else {
        name.value = parents.length + ' individual Sample Cut processes';
    }

    info.textContent =
        parents.length + ' parent substrate(s) selected: ' +
        parents.map(processingCutShortId).join(', ');

    const heights = parents.map(x => Number(x.geometry?.height) * 1000);
    const sameHeight = heights.every(x =>
        Number.isFinite(x) && x > 0 &&
        Math.abs(x - heights[0]) < 1e-8
    );

    processingCutElement('cutHeight').value =
        sameHeight ? String(heights[0]) : '';

    processingCutFeedback(
        parents.length + ' parent substrate(s) ready for validation.',
        false
    );
}

function processingCutInitialize() {
    const panel = processingCutElement('sampleCutPanel');
    const open = processingCutElement('addSampleCutButton');

    open.addEventListener('click', function() {
        panel.style.display = panel.style.display === 'none' ? '' : 'none';
    });

    for (let i = 0; i < 24; i++) {
        const n = String(i).padStart(2, '0');
        processingCutElement('cutHour').add(new Option(n, n));
    }
    for (let i = 0; i < 60; i++) {
        const n = String(i).padStart(2, '0');
        processingCutElement('cutMinute').add(new Option(n, n));
    }

    processingCutElement('cutShape').addEventListener('change', function() {
        const shape = this.value;
        document.querySelectorAll('.cutRect').forEach(x =>
            x.style.display = shape === 'rectangle' ? '' : 'none');
        document.querySelectorAll('.cutRound').forEach(x =>
            x.style.display = shape === 'rectangle' ? 'none' : '');
        document.querySelectorAll('.cutSector').forEach(x =>
            x.style.display = shape === 'sector' ? '' : 'none');
    });

    processingCutElement('cutLocation').addEventListener('change', function() {
        processingCutElement('cutOtherLocation').style.display =
            this.value === 'Elsewhere' ? '' : 'none';
    });

    // The left-hand substrate selection is the Sample Cut parent selection.


    const sync = () => queueMicrotask(processingCutSyncSelection);

    document.getElementById('substrateResults')
        .addEventListener('change', sync);

    ['selectAllButton', 'clearSelectionButton'].forEach(id => {
        document.getElementById(id).addEventListener('click', sync);
    });

    processingCutSyncSelection();

    processingCutElement('cutValidateButton').addEventListener(
        'click', function() {
            try {
                const parents = substrates.filter(x => x.selected);
                if (!parents.length) {
                    throw new Error('Select at least one parent substrate.');
                }

                for (const parent of parents) {
                    const cut = processingCutValidate(parent);
                    cutCheckPacking(cut);
                }

                const count = processingCutPositive('cutCount');
                processingCutFeedback(
                    'Geometry valid for ' + parents.length +
                    ' parent substrate(s), ' +
                    (parents.length * count) +
                    ' children in total. No archive was written.',
                    false
                );
            } catch (error) {
                processingCutFeedback('Error: ' + error.message, true);
            }
        }
    );
}

if (document.readyState === 'loading') {
    document.addEventListener(
        'DOMContentLoaded', processingCutInitialize, {once: true}
    );
} else {
    processingCutInitialize();
}


// PDI_PROCESS_SAMPLE_CUT_SAVE_V1
const CUT_SCHEMA = 'pdi_nomad_plugin.general.schema.SampleCutPDI';
const SUBSTRATE_SCHEMA = 'pdi_nomad_plugin.mbe.materials.SubstrateMbe';

async function cutReadArchive(entryId) {
    const response = await fetch(
        nomadApiBase() + '/entries/' +
        encodeURIComponent(entryId) + '/archive'
    );
    if (!response.ok) {
        throw new Error('Cannot read NOMAD archive: HTTP ' + response.status);
    }
    const result = await response.json();
    const wrapper = result.data || result.archive || result;
    const archive = wrapper.archive || wrapper;
    return archive.data || archive;
}

async function cutExistingEntries() {
    const indexed = [];
    const seen = new Set();
    let cursor = null;
    let complete = false;

    for (let page = 0; page < 50; page++) {
        const pagination = {page_size: 200};
        if (cursor) pagination.page_after_value = cursor;

        const response = await fetch(nomadApiBase() + '/entries/query', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                owner: 'visible',
                query: {
                    'section_defs.definition_qualified_name': CUT_SCHEMA
                },
                pagination,
                required: {
                    include: ['entry_id', 'upload_id', 'entry_name']
                }
            })
        });

        if (!response.ok) {
            throw new Error(
                'Sample Cut index query failed: HTTP ' + response.status
            );
        }

        const result = await response.json();

        for (const entry of result.data || []) {
            if (entry.entry_id && entry.upload_id &&
                !seen.has(entry.entry_id)) {
                seen.add(entry.entry_id);
                indexed.push(entry);
            }
        }

        const next = result.pagination?.next_page_after_value;
        if (!next) {
            complete = true;
            break;
        }
        if (next === cursor) {
            throw new Error('Sample Cut pagination did not advance.');
        }
        cursor = next;
    }

    if (!complete) {
        throw new Error('Sample Cut index pagination incomplete.');
    }

    const found = [];
    let position = 0;

    async function worker() {
        while (true) {
            const index = position++;
            if (index >= indexed.length) return;

            const entry = indexed[index];
            let data;

            try {
                data = await cutReadArchive(entry.entry_id);
            } catch (error) {
                // Fail closed: never ignore a potentially existing cut.
                throw new Error(
                    'Cannot verify existing Sample Cut ' +
                    entry.entry_id + ': ' + error.message
                );
            }

            if (data.m_def === CUT_SCHEMA) {
                found.push({
                    entry_id: entry.entry_id,
                    upload_id: entry.upload_id,
                    data: data
                });
            }
        }
    }

    await Promise.all(
        Array.from(
            {length: Math.min(8, indexed.length)},
            () => worker()
        )
    );

    return found;
}

function cutReferenceEntryId(reference) {
    return (String(reference || '').split('/archive/')[1] || '')
        .split('#')[0].split('?')[0].split('/')[0];
}

function cutCheckPacking(cut) {
    const pg = cut.parent.geometry || {};
    const cg = cut.geometry;
    const count = cut.count;

    const pw = Number(pg.width) * 1000;
    const pl = Number(pg.length ?? pg.width) * 1000;
    const pr = Number(pg.radius) * 1000;
    const parentAngle = pg.central_angle == null
        ? 360 : Number(pg.central_angle);

    const cw = Number(cg.width) * 1000;
    const cl = Number(cg.length ?? cg.width) * 1000;
    const cr = Number(cg.radius) * 1000;
    const childAngle = cg.central_angle == null
        ? 360 : Number(cg.central_angle);

    const rectangularParent = pw > 0 && pl > 0;
    const rectangularChild = cw > 0 && cl > 0;

    if (rectangularParent && rectangularChild) {
        const capacity = (w, l) =>
            Math.floor((pw + 1e-8) / w) *
            Math.floor((pl + 1e-8) / l);
        if (Math.max(capacity(cw, cl), capacity(cl, cw)) >= count)
            return;
    } else if (rectangularParent && cr > 0) {
        const diameter = 2 * cr;
        if (Math.floor((pw + 1e-8) / diameter) *
            Math.floor((pl + 1e-8) / diameter) >= count)
            return;
    } else if (pr > 0 && !rectangularChild && cr > 0) {
        if (cg.m_def.endsWith('.CylinderSector') &&
            cr <= pr + 1e-8 &&
            count * childAngle <= parentAngle + 1e-8)
            return;

        if (count === 1 &&
            parentAngle === 360 &&
            cr <= pr + 1e-8)
            return;
    } else if (pr > 0 && rectangularChild &&
               parentAngle === 360 && count === 1) {
        if (Math.hypot(cw, cl) <= 2 * pr + 1e-8)
            return;
    }

    throw new Error(
        'The child geometry cannot be verified to fit within the parent. ' +
        'No archive was written.'
    );
}

async function cutUpload(uploadId, filename, data) {
    const params = new URLSearchParams({
        file_name: filename,
        overwrite_if_exists: 'false',
        trigger_processing: 'true',
        wait_for_processing: 'true',
        include_archive: 'true'
    });

    const response = await fetch(
        nomadApiBase() + '/uploads/' +
        encodeURIComponent(uploadId) + '/raw/?' + params,
        {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({data}, null, 2)
        }
    );

    if (!response.ok) {
        throw new Error('NOMAD upload failed: HTTP ' + response.status);
    }

    const result = await response.json();
    const errors = result?.processing?.entry?.errors || [];

    if (errors.length) {
        throw new Error('NOMAD processing: ' + errors.join('; '));
    }

    return result;
}

async function cutVerifyChildren(uploadId, entryId, original) {
    const processed = await cutReadArchive(entryId);

    if (processed.m_def !== CUT_SCHEMA ||
        processed.lab_id !== original.lab_id ||
        processed.number_of_samples !== original.number_of_samples ||
        processed.trigger_cut_sample === true) {
        throw new Error('Sample Cut archive is inconsistent.');
    }

    const children = processed.children_samples || [];
    if (children.length !== original.number_of_samples) {
        throw new Error(
            'Found ' + children.length + ' of ' +
            original.number_of_samples + ' child references.'
        );
    }

    const fullParentId = original._parentLabId;
    const parentEntryId = cutReferenceEntryId(
        original.parent_sample.reference
    );
    const expectedIds = new Set(
        Array.from(
            {length: original.number_of_samples},
            (_, i) => fullParentId + '.' + (i + 1)
        )
    );
    const seen = new Set();

    for (const child of children) {
        const ref = String(child.reference || '');
        const childEntryId = cutReferenceEntryId(ref);

        if (!childEntryId ||
            seen.has(childEntryId) ||
            !ref.includes('/uploads/' + uploadId + '/archive/')) {
            throw new Error('Invalid or duplicate child reference.');
        }

        seen.add(childEntryId);
        const data = await cutReadArchive(childEntryId);

        if (!expectedIds.delete(data.lab_id) ||
            data.name !== data.lab_id) {
            throw new Error('Unexpected child substrate ID: ' + data.lab_id);
        }

        if (!String(data.parent_sample?.reference || '')
            .includes('/archive/' + parentEntryId)) {
            throw new Error(
                'Missing parent reference for ' + data.lab_id
            );
        }

        if (data.geometry?.m_def !== original.children_geometry.m_def) {
            throw new Error('Child geometry type mismatch.');
        }

        for (const key of [
            'width', 'length', 'height', 'radius', 'central_angle'
        ]) {
            const expected = original.children_geometry[key];
            if (expected === undefined) continue;

            const actual = Number(data.geometry[key]);
            if (!Number.isFinite(actual) ||
                Math.abs(actual - expected) > 1e-8) {
                throw new Error(
                    'Child geometry mismatch for ' +
                    data.lab_id + ': ' + key
                );
            }
        }
    }

    if (expectedIds.size) {
        throw new Error('Not all expected child IDs were found.');
    }

    for (const child of children) {
        processingVerifiedCutChildren.set(
            cutReferenceEntryId(child.reference),
            {
                parentId: parentEntryId,
                uploadId: uploadId
            }
        );
    }

    return children.length;
}

function cutSuccessBanner(count) {
    document.getElementById('processingCutSuccess')?.remove();

    const banner = document.createElement('div');
    banner.id = 'processingCutSuccess';
    banner.setAttribute('role', 'status');
    banner.textContent =
        '✓ Sample Cut successful — ' +
        count + ' child samples created and verified.';

    Object.assign(banner.style, {
        position: 'sticky',
        top: '0',
        zIndex: '1000',
        padding: '12px 16px',
        margin: '0 0 12px',
        background: '#eaf6eb',
        color: '#173b22',
        border: '1px solid #6da778',
        borderRadius: '8px'
    });

    document.body.insertBefore(banner, document.body.firstChild);

    document.addEventListener('click', () => banner.remove(), {
        capture: true,
        once: true
    });
}

// Prevent repeated uploads of parents already attempted in this session.
const processingCutAttemptedParents = new Set();

async function processingCutSave() {
    const button = processingCutElement('cutSaveButton');
    const uploadId = processingCutElement('targetUpload').value;
    const selected = substrates.filter(x => x.selected);
    let attempted = 0;
    let completed = 0;
    let totalChildren = 0;

    button.disabled = true;

    try {
        if (!uploadId) throw new Error('Select a target upload.');
        if (!selected.length) {
            throw new Error('Select at least one parent substrate.');
        }

        // Same timestamp and process parameters for every parent.
        const stamp = new Date().toISOString().replace(/\D/g, '');
        const existing = await cutExistingEntries();
        const existingParentIds = new Set(
            existing.map(item =>
                cutReferenceEntryId(item.data?.parent_sample?.reference)
            ).filter(Boolean)
        );

        const jobs = [];
        const filenames = new Set();

        // Validate ALL parents before creating the first archive.
        for (const parent of selected) {
            if (processingCutAttemptedParents.has(parent.entryId)) {
                throw new Error(
                    'A cut was already attempted for ' +
                    parent.labId + ' in this session. ' +
                    'Inspect NOMAD before attempting it again.'
                );
            }

            if (existingParentIds.has(parent.entryId)) {
                throw new Error(
                    'A Sample Cut already exists for ' + parent.labId +
                    '. Inspect NOMAD before cutting it again.'
                );
            }

            const cut = processingCutValidate(parent);
            cutCheckPacking(cut);

            const parentData = await cutReadArchive(parent.entryId);

            if (parentData.m_def !== SUBSTRATE_SCHEMA ||
                !parentData.lab_id ||
                parentData.lab_id !== parent.labId) {
                throw new Error(
                    'Invalid individual SubstrateMbe: ' + parent.labId
                );
            }

            if (JSON.stringify(parentData.geometry || {}) !==
                JSON.stringify(parent.geometry || {})) {
                throw new Error(
                    'Parent geometry changed for ' + parent.labId +
                    '. Refresh the substrate list.'
                );
            }

            const labId =
                'CUT_' + safePart(parentData.lab_id) + '_' + stamp;

            const data = {
                m_def: CUT_SCHEMA,
                name: selected.length === 1
                    ? (cut.name || 'cut_' + processingCutShortId(parent))
                    : 'cut_' + processingCutShortId(parent),
                lab_id: labId,
                datetime: cut.datetime,
                number_of_samples: cut.count,
                parent_sample: {
                    reference: nomadArchiveReference(
                        parent.uploadId, parent.entryId
                    )
                },
                children_geometry: cut.geometry,
                trigger_cut_sample: true
            };

            if (cut.location) data.location = cut.location;
            if (cut.description) data.description = cut.description;

            const filename = safePart(labId) + '.archive.json';

            if (filenames.has(filename)) {
                throw new Error(
                    'Duplicate cut filename for parent ' + parent.labId
                );
            }

            filenames.add(filename);
            jobs.push({parent, parentData, data, filename, labId});
        }

        // Each SampleCutPDI invokes the ORIGINAL normalizer independently.
        for (let i = 0; i < jobs.length; i++) {
            const job = jobs[i];

            processingCutFeedback(
                'Cutting substrate ' + (i + 1) + '/' + jobs.length +
                ': ' + job.parent.labId,
                false
            );

            // Mark before upload: an uncertain response must not be retried.
            processingCutAttemptedParents.add(job.parent.entryId);
            attempted++;

            const uploadResult = await cutUpload(
                uploadId, job.filename, job.data
            );

            let entryId =
                uploadResult?.processing?.entry?.entry_id || null;

            let verified = null;
            let lastError = null;

            for (let attempt = 0; attempt < 8; attempt++) {
                try {
                    if (!entryId) {
                        const entries = await cutExistingEntries();
                        const found = entries.find(item =>
                            item.upload_id === uploadId &&
                            item.data?.lab_id === job.labId
                        );
                        entryId = found?.entry_id || null;
                    }

                    if (!entryId) {
                        throw new Error('Cut archive not indexed yet.');
                    }

                    verified = await cutVerifyChildren(
                        uploadId,
                        entryId,
                        {
                            ...job.data,
                            _parentLabId: job.parentData.lab_id
                        }
                    );
                    break;
                } catch (error) {
                    lastError = error;
                    if (attempt < 7) {
                        await new Promise(resolve =>
                            setTimeout(resolve, 1000)
                        );
                    }
                }
            }

            if (verified === null) {
                throw lastError || new Error(
                    'Child verification failed for ' + job.parent.labId
                );
            }

            completed++;
            totalChildren += verified;
        }

        processingCutFeedback(
            'Sample Cut successful — ' + completed +
            ' parent substrates cut; ' + totalChildren +
            ' child samples created and verified.',
            false
        );

        cutSuccessBanner(totalChildren);
        resetProcessingAfterSuccess(
            jobs.map(function(job) { return job.parent.entryId; })
        );

        try {
            await refreshProcessingData({catalogs: false});
        } catch (refreshError) {
            console.error('Post-cut refresh failed:', refreshError);
            processingCutFeedback(
                'All cuts verified successfully, but refreshing ' +
                'the substrate list failed: ' + refreshError.message,
                true
            );
        }

    } catch (error) {
        processingCutFeedback(
            completed + ' of ' + selected.length +
            ' cuts completed. ' +
            (attempted > completed
                ? 'A further upload was attempted; do not retry it blindly. '
                : '') +
            'Error: ' + error.message,
            true
        );
    } finally {
        // An attempted upload is never blindly repeated.
        button.disabled = attempted > completed;
    }
}

function processingCutEnableSave() {
    const button = processingCutElement('cutSaveButton');
    button.disabled = false;
    button.addEventListener('click', processingCutSave);
}

if (document.readyState === 'loading') {
    document.addEventListener(
        'DOMContentLoaded', processingCutEnableSave, {once: true}
    );
} else {
    processingCutEnableSave();
}


// PDI_PROCESS_CHOICE_BUTTONS_V1
function initializeProcessChoiceButtons() {
    const bar = document.getElementById('processChoiceBar');
    const list = document.getElementById('processList');
    const oldAdd = document.getElementById('addProcessButton');
    const cutPanel = document.getElementById('sampleCutPanel');
    const oldCut = document.getElementById('addSampleCutButton');

    if (!bar || !list || !oldAdd || !cutPanel || !oldCut) {
        throw new Error('Process selection controls are missing.');
    }

    // Remove the old "add Cleaning immediately" click handler.
    const add = oldAdd.cloneNode(true);
    add.textContent = '+ Add new step';
    oldAdd.replaceWith(add);

    // Keep the existing Sample Cut initialization and validation.
    oldCut.style.display = 'none';

    const saveAll = document.getElementById('saveProcessesButton');
    const syncExecutionButtons = function() {
        const cutActive = getComputedStyle(cutPanel).display !== 'none';
        saveAll.style.display = cutActive ? 'none' : '';
    };
    new MutationObserver(syncExecutionButtons).observe(
        cutPanel, {attributes: true, attributeFilter: ['style']}
    );
    syncExecutionButtons();


    // Show Sample Cut above the "Add another process" button.
    add.parentNode.insertBefore(cutPanel, add);

    bar.querySelectorAll('[data-process-choice]').forEach(function(button) {
        button.addEventListener('click', function() {
            const type = button.dataset.processChoice;

            if (type === 'sample_cut') {
                if (cutPanel.style.display === 'none') {
                    oldCut.click();
                }
                cutPanel.scrollIntoView({
                    behavior: 'smooth',
                    block: 'nearest'
                });
            } else if (type === 'cleaning' || type === 'annealing') {
                addProcess();

                const cards = list.querySelectorAll('.process-card');
                const card = cards[cards.length - 1];
                const select = card?.querySelector('.process-type');

                if (!select) {
                    throw new Error('New process card was not created.');
                }

                select.value = type;
                select.dispatchEvent(new Event('change', {
                    bubbles: true
                }));

                card.scrollIntoView({
                    behavior: 'smooth',
                    block: 'nearest'
                });
            } else {
                throw new Error('Unsupported process type: ' + type);
            }

            bar.style.display = 'none';
        });
    });

    add.addEventListener('click', function() {
        add.insertAdjacentElement('afterend', bar);
        bar.style.display = 'flex';
        bar.scrollIntoView({
            behavior: 'smooth',
            block: 'nearest'
        });
    });
}

if (document.readyState === 'loading') {
    document.addEventListener(
        'DOMContentLoaded',
        initializeProcessChoiceButtons,
        {once: true}
    );
} else {
    initializeProcessChoiceButtons();
}
