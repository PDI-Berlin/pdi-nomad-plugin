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
    etching: Object.freeze({
        schema: 'nomad_material_processing.general.EtchingRecipe',
        processSchema: 'nomad_material_processing.general.Etching'
    })
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

function substrateStatus(substrate) {
    if (!substrate || !substrate.entryId) return '';
    // Never invent as_delivered/processed/grown NOMAD quantities.
    // A substrate with an original Cleaning/Annealing/Etching process
    // referencing it is processed; otherwise it is unprocessed.
    return treatmentHistoryState.some(function(treatment) {
        return treatmentReferencesSubstrate(treatment, substrate.entryId);
    }) ? 'processed' : 'unprocessed';
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
    const schema = 'nomad_material_processing.general.CrystallineSubstrate';
    const entries = await queryEntries(schema, 1000, [
        'entry_id', 'upload_id', 'entry_name', 'data'
    ]);
    return entries.filter(function(entry) {
        return entry.data && entry.data.m_def === schema;
    }).map(function(entry) {
        const data = entry.data;
        const fields = originalSubstrateFields(data);
        return {
            entryId: entry.entry_id,
            uploadId: entry.upload_id,
            labId: data.lab_id || data.name || entry.entry_name || entry.entry_id,
            material: fields.material,
            formula: fields.formula,
            crystalId: fields.crystalId,
            chargeId: fields.chargeId,
            orientation: fields.orientation,
            geometry: data.geometry || null,
            // Status is derived from original processing references.
            selected: false
        };
    }).sort(function(a, b) {
        return String(a.labId).localeCompare(
            String(b.labId), undefined,
            {numeric: true, sensitivity: 'base'}
        );
    });
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
            item.selected = selectedEntryIds.has(item.entryId);
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
