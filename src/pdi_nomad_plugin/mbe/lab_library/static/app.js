let libraryTypes = {};
let currentType = 'processing_recipe';
let currentSubtype = 'annealing';
let currentItems = [];
let allProcessingCatalogs = {};
let usageCatalogs = {};
let editorMode = 'create';
let editorItem = null;

const SIZE_OPTIONS_MM = [5, 10];

function nomadApiBase() {
    if (window.NOMAD_API_BASE) {
        return String(window.NOMAD_API_BASE).replace(/\/$/, '');
    }
    return '/api/v1';
}

function escapeHtml(value) {
    return String(value === undefined || value === null ? '' : value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function geometryNumber(value) {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (value && typeof value === 'object' && typeof value.magnitude === 'number') {
        return Number(value.magnitude);
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
    return {width, length};
}

function mm(value) {
    const n = geometryNumber(value);
    return Number.isFinite(n) ? n * 1000 : null;
}

function formatNumber(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return Number.isInteger(n) ? String(n) : String(Number(n.toFixed(3)));
}

function formatSquareSize(geometry) {
    const xy = geometryXY(geometry);
    if (!xy) return '—';
    const w = xy.width * 1000;
    const l = xy.length * 1000;
    return formatNumber(w) + ' × ' + formatNumber(l) + ' mm';
}

function tagsArray(value) {
    return String(value || '')
        .split(',')
        .map(function(tag) { return tag.trim(); })
        .filter(Boolean);
}

function safeFilenamePart(value) {
    const cleaned = String(value || '')
        .trim()
        .replace(/[^A-Za-z0-9._-]+/g, '_')
        .replace(/^_+|_+$/g, '');
    return cleaned || 'library_item';
}

function timestampPart() {
    return new Date().toISOString().replace(/[-:TZ.]/g, '').slice(0, 14);
}

function currentDefinition() {
    if (currentType !== 'processing_recipe') return libraryTypes[currentType];
    const parent = libraryTypes.processing_recipe || {};
    return (parent.schemas || {})[currentSubtype] || {};
}

function currentSchema() {
    return currentDefinition().schema;
}

function currentLabel() {
    if (currentType === 'processing_recipe') {
        return currentDefinition().label + ' Recipes';
    }
    return currentDefinition().label;
}

async function queryEntriesBySchema(schema) {
    const response = await fetch(
        nomadApiBase() + '/entries/archive/query',
        {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                owner: 'visible',
                query: {'section_defs.definition_qualified_name': schema},
                pagination: {page_size: 1000},
                required: {
                    metadata: {
                        entry_name: '*',
                        mainfile: '*',
                        published: '*',
                        entry_references: '*'
                    },
                    data: '*'
                }
            })
        }
    );
    if (!response.ok) throw new Error('NOMAD query failed (' + response.status + ')');
    const result = await response.json();
    return (result.data || []).map(function(entry) {
        const archive = entry.archive || {};
        const metadata = archive.metadata || {};
        return {
            entryId: entry.entry_id,
            uploadId: entry.upload_id,
            entryName: metadata.entry_name || entry.entry_id,
            mainfile: metadata.mainfile || '',
            published: Boolean(metadata.published),
            entryReferences: Array.isArray(metadata.entry_references)
                ? metadata.entry_references
                : [],
            data: archive.data || {}
        };
    });
}

async function loadLibraryTypes() {
    const response = await fetch('library-types');
    if (!response.ok) throw new Error('Could not load library type definitions.');
    libraryTypes = await response.json();
}


function definitionUsageSchemas() {
    const definition = currentDefinition() || {};
    return Array.isArray(definition.usage_schemas)
        ? definition.usage_schemas
        : [];
}

async function preloadUsageCatalogs() {
    const schemaSet = new Set();

    Object.values(libraryTypes || {}).forEach(function(definition) {
        if (definition && definition.schemas) {
            Object.values(definition.schemas).forEach(function(subdefinition) {
                (subdefinition.usage_schemas || []).forEach(function(schema) {
                    schemaSet.add(schema);
                });
            });
        } else {
            (definition.usage_schemas || []).forEach(function(schema) {
                schemaSet.add(schema);
            });
        }
    });

    const pairs = await Promise.all(
        Array.from(schemaSet).map(async function(schema) {
            return [schema, await queryEntriesBySchema(schema)];
        })
    );
    usageCatalogs = Object.fromEntries(pairs);
}

function referenceHitsForEntry(item) {
    const targetEntryId = item && item.entryId;
    if (!targetEntryId) return [];

    const hits = [];
    definitionUsageSchemas().forEach(function(schema) {
        (usageCatalogs[schema] || []).forEach(function(source) {
            const refs = Array.isArray(source.entryReferences)
                ? source.entryReferences
                : [];
            refs.forEach(function(ref) {
                if (ref && ref.target_entry_id === targetEntryId) {
                    hits.push({
                        schema: schema,
                        sourceEntryId: source.entryId,
                        sourceEntryName: source.entryName,
                        sourceMainfile: source.mainfile,
                        sourcePath: ref.source_path || '',
                        sourceQuantity: ref.source_quantity || ''
                    });
                }
            });
        });
    });
    return hits;
}

function itemUsage(item) {
    const hits = referenceHitsForEntry(item);
    return {
        count: hits.length,
        hits: hits,
        locked: hits.length > 0
    };
}

function normalizeLabId(value) {
    return String(value || '').trim().toUpperCase();
}

function allIdsForCurrentType() {
    const values = currentType === 'processing_recipe'
        ? (allProcessingCatalogs[currentSubtype] || [])
        : currentItems;
    return values
        .map(function(item) {
            return normalizeLabId((item.data || {}).lab_id || item.entryName);
        })
        .filter(Boolean);
}

function assertUniqueGeneratedId(id) {
    const normalized = normalizeLabId(id);
    if (!normalized) throw new Error('Generated ID is empty.');

    const collision = allIdsForCurrentType().some(function(existing) {
        if (
            editorMode === 'edit' &&
            editorItem &&
            normalizeLabId((editorItem.data || {}).lab_id || editorItem.entryName) === existing
        ) {
            return false;
        }
        return existing === normalized;
    });

    if (collision) {
        throw new Error(
            'ID ' + id + ' already exists. Change the structured fields before saving.'
        );
    }
}

async function preloadProcessingCatalogs() {
    const defs = (libraryTypes.processing_recipe || {}).schemas || {};
    const entries = await Promise.all(
        Object.entries(defs).map(async function([key, def]) {
            return [key, await queryEntriesBySchema(def.schema)];
        })
    );
    allProcessingCatalogs = Object.fromEntries(entries);
}

function renderTypeTabs() {
    const box = document.getElementById('typeTabs');
    box.innerHTML = '';
    Object.entries(libraryTypes).forEach(function([key, def]) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'type-tab' + (key === currentType ? ' active' : '');
        button.textContent = def.label;
        button.addEventListener('click', function() {
            currentType = key;
            renderTypeTabs();
            renderSubtypeTabs();
            loadCurrentType();
        });
        box.appendChild(button);
    });
}

function renderSubtypeTabs() {
    const box = document.getElementById('subtypeTabs');
    if (currentType !== 'processing_recipe') {
        box.classList.add('hidden');
        box.innerHTML = '';
        return;
    }
    box.classList.remove('hidden');
    box.innerHTML = '';
    const defs = (libraryTypes.processing_recipe || {}).schemas || {};
    Object.entries(defs).forEach(function([key, def]) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'subtype-tab' + (key === currentSubtype ? ' active' : '');
        button.textContent = def.label;
        button.addEventListener('click', function() {
            currentSubtype = key;
            renderSubtypeTabs();
            loadCurrentType();
        });
        box.appendChild(button);
    });
}

function itemTitle(item) {
    const data = item.data || {};
    return data.lab_id || data.name || item.entryName || item.entryId;
}

function itemSecondary(item) {
    const data = item.data || {};
    const bits = [];
    if (data.name && data.name !== itemTitle(item)) bits.push(data.name);

    const usage = itemUsage(item);
    if (usage.locked) {
        bits.push('Locked · referenced by ' + usage.count + ' NOMAD entr' +
            (usage.count === 1 ? 'y' : 'ies'));
    } else {
        bits.push(item.published ? 'Published' : 'Unused · editable');
    }
    return bits.join(' · ');
}

function scalarSummary(data) {
    const skip = new Set([
        'm_def', 'name', 'lab_id', 'datetime', 'samples', 'recipe',
        'starting_time', 'ending_time', 'location'
    ]);
    const bits = [];
    Object.entries(data || {}).forEach(function([key, value]) {
        if (skip.has(key)) return;
        if (value === null || value === undefined) return;
        if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
            bits.push(key.replaceAll('_', ' ') + ': ' + String(value));
        }
    });
    return bits.slice(0, 4).join(' · ');
}

function itemDetail(item) {
    const data = item.data || {};
    if (currentType === 'processing_recipe') return scalarSummary(data) || 'Recipe parameters stored in NOMAD';
    if (currentType === 'sample_cut_recipe') {
        return (
            'Parent ' + formatSquareSize(data.input_geometry) +
            ' → ' + (data.number_of_samples || '—') +
            ' × ' + formatSquareSize(data.children_geometry)
        );
    }
    if (currentType === 'holder') {
        const positions = Array.isArray(data.positions) ? data.positions : [];
        const size = inferHolderSizeMm(data);
        return positions.length + ' position(s)' + (size ? ' · ' + formatNumber(size) + ' × ' + formatNumber(size) + ' mm' : '');
    }
    if (currentType === 'insert') {
        return (
            'Outer ' + formatSquareSize(data.outer_geometry) +
            ' · Opening ' + formatSquareSize(data.inner_geometry)
        );
    }
    return '';
}

function filteredItems() {
    const q = document.getElementById('librarySearch').value.trim().toLowerCase();
    if (!q) return currentItems;
    return currentItems.filter(function(item) {
        return JSON.stringify({entryName:item.entryName, data:item.data}).toLowerCase().includes(q);
    });
}

function createRowLabel() {
    if (currentType === 'processing_recipe') return '+ Create new ' + currentDefinition().label.toLowerCase() + ' recipe';
    if (currentType === 'sample_cut_recipe') return '+ Create new sample cut recipe';
    if (currentType === 'holder') return '+ Create new holder';
    if (currentType === 'insert') return '+ Create new insert';
    return '+ Create new item';
}

function renderLibrary() {
    const list = document.getElementById('libraryList');
    const status = document.getElementById('libraryStatus');
    const items = filteredItems();

    status.textContent = items.length + ' of ' + currentItems.length + ' ' + currentLabel().toLowerCase() + ' shown.';
    list.innerHTML = '';

    if (!items.length) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.textContent = 'No matching library items.';
        list.appendChild(empty);
    }

    items.forEach(function(item) {
        const row = document.createElement('div');
        row.className = 'library-row';

        const identity = document.createElement('div');
        identity.innerHTML =
            '<div class="item-title">' + escapeHtml(itemTitle(item)) + '</div>' +
            '<div class="item-subtitle">' + escapeHtml(itemSecondary(item)) + '</div>';

        const type = document.createElement('div');
        type.className = 'item-type';
        type.textContent = currentLabel();

        const detail = document.createElement('div');
        detail.className = 'item-details';
        detail.textContent = itemDetail(item);

        const actions = document.createElement('div');
        actions.className = 'item-actions';

        const view = document.createElement('button');
        view.type = 'button';
        view.textContent = 'View';
        view.addEventListener('click', function() { openView(item); });

        const usage = itemUsage(item);

        const edit = document.createElement('button');
        edit.type = 'button';
        edit.textContent = 'Edit';
        edit.disabled =
            usage.locked ||
            item.published ||
            !item.mainfile ||
            !item.uploadId;
        edit.title = usage.locked
            ? 'Locked because this item is referenced by NOMAD entries.'
            : (
                item.published
                    ? 'Published entries are read-only.'
                    : ''
            );
        edit.addEventListener('click', function() { openEditor('edit', item); });

        const duplicate = document.createElement('button');
        duplicate.type = 'button';
        duplicate.textContent = 'Duplicate';
        duplicate.addEventListener('click', function() { openEditor('duplicate', item); });

        actions.append(view, edit, duplicate);
        row.append(identity, type, detail, actions);
        list.appendChild(row);
    });

    const create = document.createElement('div');
    create.className = 'create-row';
    create.innerHTML = '<span class="create-plus">+</span><span>' + escapeHtml(createRowLabel().replace(/^\+\s*/, '')) + '</span>';
    create.addEventListener('click', function() { openEditor('create', null); });
    list.appendChild(create);
}


const HOLDER_SYSTEM_STATES = [
    'empty',
    'ungrown',
    'grown'
];


function holderSystemState(data) {
    const tags =
        data && Array.isArray(data.tags)
            ? data.tags
            : [];

    if (tags.includes('grown')) return 'grown';
    if (tags.includes('ungrown')) return 'ungrown';
    if (tags.includes('empty')) return 'empty';

    return 'empty';
}


function isPhysicalHolderLibraryItem(item) {
    const data = item.data || {};
    const mDef = String(data.m_def || '');

    if (
        mDef.includes(
            'FilledSubstrateHolderPDI'
        )
    ) {
        return false;
    }

    /*
     * FilledSubstrateHolderPDI contains a reference
     * to the physical holder. This is an additional
     * guard for older entries where m_def is incomplete.
     */
    if (data.substrate_holder) {
        return false;
    }

    return true;
}


function physicalHolderKey(item) {
    const data = item.data || {};

    return String(
        data.lab_id ||
        data.name ||
        item.entryName ||
        item.entryId ||
        ''
    ).trim();
}


function physicalHolderScore(item) {
    const data = item.data || {};
    const tags =
        Array.isArray(data.tags)
            ? data.tags
            : [];

    const positions =
        Array.isArray(data.positions)
            ? data.positions
            : [];

    let score =
        positions.length;

    /*
     * Prefer an entry already carrying our current
     * workflow state.
     */
    if (
        tags.some(function(tag) {
            return HOLDER_SYSTEM_STATES.includes(tag);
        })
    ) {
        score += 10000;
    }

    /*
     * If duplicate physical holder definitions exist,
     * prefer the one already referenced by NOMAD.
     */
    try {
        if (itemUsage(item).locked) {
            score += 1000;
        }
    } catch (_) {}

    return score;
}


function canonicalPhysicalHolderItems(items) {
    const holders =
        new Map();

    (items || [])
        .filter(
            isPhysicalHolderLibraryItem
        )
        .forEach(function(item) {
            const key =
                physicalHolderKey(item);

            if (!key) {
                return;
            }

            const previous =
                holders.get(key);

            if (
                !previous ||
                physicalHolderScore(item) >
                    physicalHolderScore(previous)
            ) {
                holders.set(
                    key,
                    item
                );
            }
        });

    return Array.from(
        holders.values()
    );
}


function managedHolderTags(data) {
    const id =
        String(
            data.lab_id ||
            data.name ||
            ''
        ).trim();

    const state =
        holderSystemState(data);

    return Array.from(
        new Set(
            [id, state].filter(Boolean)
        )
    );
}


function managedInsertTags(data) {
    const id =
        String(
            data.lab_id ||
            data.name ||
            ''
        ).trim();

    return id ? [id] : [];
}


async function loadCurrentType() {
    const status = document.getElementById('libraryStatus');
    status.textContent = 'Loading ' + currentLabel().toLowerCase() + ' from NOMAD...';
    document.getElementById('libraryList').innerHTML = '';
    try {
        if (currentType === 'processing_recipe' && allProcessingCatalogs[currentSubtype]) {
            currentItems = allProcessingCatalogs[currentSubtype];
        } else {
            currentItems = await queryEntriesBySchema(currentSchema());
        }
        if (currentType === 'holder') {
            currentItems =
                canonicalPhysicalHolderItems(
                    currentItems
                );
        }

        currentItems = [...currentItems].sort(function(a,b) {
            return itemTitle(a).localeCompare(itemTitle(b));
        });
        renderLibrary();
    } catch (error) {
        currentItems = [];
        status.textContent = 'Error: ' + error.message;
    }
}

function openModal() { document.getElementById('modalBackdrop').classList.remove('hidden'); }

function closeModal() {
    document.getElementById('modalBackdrop').classList.add('hidden');
    document.getElementById('viewPanel').classList.add('hidden');
    document.getElementById('editorForm').classList.add('hidden');
    editorItem = null;
}

function viewRow(label, value) {
    return '<div class="view-label">' + escapeHtml(label) + '</div><div>' + escapeHtml(value) + '</div>';
}

function readonlyViewField(label, value) {
    const display =
        value === undefined || value === null || value === ''
            ? '—'
            : String(value);

    return `
        <div>
            <label>${escapeHtml(label)}</label>
            <input
                type="text"
                readonly
                value="${escapeHtml(display)}">
        </div>
    `;
}

function readonlyViewTextarea(label, value) {
    const display =
        value === undefined || value === null || value === ''
            ? ''
            : String(value);

    return `
        <div>
            <label>${escapeHtml(label)}</label>
            <textarea readonly>${escapeHtml(display)}</textarea>
        </div>
    `;
}

function yamlScalar(value) {
    if (value === null) return 'null';
    if (typeof value === 'number' || typeof value === 'boolean') {
        return String(value);
    }

    const text = String(value);

    if (
        text !== '' &&
        /^[A-Za-z0-9_.\/+\- ]+$/.test(text) &&
        !/^(true|false|null|yes|no)$/i.test(text)
    ) {
        return text;
    }

    return JSON.stringify(text);
}

function archiveToYaml(value, indent) {
    indent = indent || 0;
    const pad = ' '.repeat(indent);

    if (Array.isArray(value)) {
        if (!value.length) return pad + '[]';

        return value.map(function(item) {
            if (item !== null && typeof item === 'object') {
                return pad + '-\n' + archiveToYaml(item, indent + 2);
            }
            return pad + '- ' + yamlScalar(item);
        }).join('\n');
    }

    if (value !== null && typeof value === 'object') {
        const entries = Object.entries(value);

        if (!entries.length) return pad + '{}';

        return entries.map(function(pair) {
            const key = pair[0];
            const item = pair[1];

            if (item !== null && typeof item === 'object') {
                return pad + key + ':\n' +
                    archiveToYaml(item, indent + 2);
            }

            return pad + key + ': ' + yamlScalar(item);
        }).join('\n');
    }

    return pad + yamlScalar(value);
}

function cleaningReadonlyView(data) {
    const steps =
        Array.isArray(data.steps) && data.steps.length
            ? data.steps
            : [];

    const stepsHtml = steps.map(function(step, index) {
        const reagent = cleaningReagentName(step) || step.name || '—';

        const duration =
            step.duration !== undefined && step.duration !== null
                ? formatNumber(Number(step.duration) / 60)
                : '—';

        const temperature =
            step.temperature !== undefined && step.temperature !== null
                ? formatNumber(Number(step.temperature))
                : '—';

        const agitation = step.agitation || 'None';

        return `
            <div class="cleaning-step-row">
                <div class="cleaning-step-heading">
                    <strong>Step ${index + 1}</strong>
                </div>

                <div class="cleaning-step-primary">
                    ${readonlyViewField('Reagent / medium', reagent)}
                    ${readonlyViewField('Duration (min)', duration)}
                    ${readonlyViewField('Temperature (°C)', temperature)}
                </div>

                <div class="cleaning-step-secondary">
                    ${readonlyViewField('Agitation', agitation)}
                    ${readonlyViewField('Comment', step.comment || '—')}
                </div>
            </div>
        `;
    }).join('');

    return `
        <div class="cleaning-layout">
            <div class="cleaning-left-column">
                <h3>Recipe</h3>

                ${readonlyViewField('Recipe name', data.name || '—')}
                ${readonlyViewField('Treatment type', data.method || '—')}
                ${readonlyViewTextarea('Description', data.description || '')}
            </div>

            <div class="cleaning-right-column">
                <div class="cleaning-steps-heading">
                    <h3>Process steps</h3>
                </div>

                ${
                    stepsHtml ||
                    '<div class="muted">No process steps stored.</div>'
                }
            </div>
        </div>
    `;
}

function annealingReadonlyView(data) {
    const instrument =
        data.location ||
        (
            Array.isArray(data.instruments) &&
            data.instruments[0] &&
            data.instruments[0].name
        ) ||
        '—';

    const atmosphere = data.atmosphere || '—';

    const steps =
        Array.isArray(data.steps) && data.steps.length
            ? data.steps
            : [];

    const stepsHtml = steps.map(function(step, index) {
        const temperature =
            step.operation_temperature !== undefined &&
            step.operation_temperature !== null
                ? formatNumber(Number(step.operation_temperature))
                : '—';

        const duration =
            step.duration !== undefined && step.duration !== null
                ? formatNumber(Number(step.duration) / 60)
                : '—';

        const rampRate =
            step.ramp_rate !== undefined &&
            step.ramp_rate !== null
                ? formatNumber(Number(step.ramp_rate) * 60)
                : '—';

        return `
            <div class="annealing-step-row">
                <div class="annealing-step-heading">
                    <strong>Step ${index + 1}</strong>
                </div>

                <div class="annealing-step-fields">
                    ${readonlyViewField(
                        'Operation temperature (°C)',
                        temperature
                    )}

                    ${readonlyViewField(
                        'Duration (min)',
                        duration
                    )}

                    ${readonlyViewField(
                        'Ramp rate (°C/min)',
                        rampRate
                    )}
                </div>

                ${readonlyViewField(
                    'Comment',
                    step.comment || '—'
                )}
            </div>
        `;
    }).join('');

    let conditions = '';
    conditions += readonlyViewField(
        'Instrument / location',
        instrument
    );
    conditions += readonlyViewField(
        'Gas / atmosphere',
        atmosphere
    );

    if (atmosphere !== 'Vacuum') {
        conditions += readonlyViewField(
            'Gas flow (sccm)',
            data.gas_flow_sccm !== undefined
                ? formatNumber(Number(data.gas_flow_sccm))
                : '—'
        );
    }

    if (instrument === 'MBE growth chamber') {
        conditions += readonlyViewField(
            'RF power (W)',
            data.rf_power_w !== undefined
                ? formatNumber(Number(data.rf_power_w))
                : '—'
        );
    }

    return `
        <div class="annealing-layout">
            <div class="annealing-left-column">
                <h3>Recipe</h3>

                ${readonlyViewField('Recipe name', data.name || '—')}
                ${readonlyViewTextarea(
                    'Description',
                    data.description || ''
                )}
            </div>

            <div class="annealing-right-column">
                <h3>Conditions</h3>

                <div class="field-grid">
                    ${conditions}
                </div>

                <div class="annealing-steps-heading">
                    <h3>Process steps</h3>
                </div>

                ${
                    stepsHtml ||
                    '<div class="muted">No process steps stored.</div>'
                }
            </div>
        </div>
    `;
}

function backSideCoatingReadonlyView(data) {
    const material =
        data.coating_material ||
        (
            data.coating_reagents &&
            data.coating_reagents.name
        ) ||
        '—';

    const thicknessUm =
        data.thickness !== undefined &&
        data.thickness !== null
            ? formatNumber(Number(data.thickness) * 1e6)
            : '—';

    return `
        <h3>Back-side coating</h3>
        <div class="field-grid">
            ${readonlyViewField('Coating material', material)}
            ${readonlyViewField('Thickness (µm)', thicknessUm)}
        </div>
    `;
}


function openView(item) {
    const data = item.data || {};

    document.getElementById('modalTitle').textContent =
        itemTitle(item);

    document.getElementById('modalSubtitle').textContent =
        currentLabel() + ' · ' + item.entryId;

    const panel = document.getElementById('viewPanel');

    document.getElementById('editorForm').classList.add('hidden');
    panel.classList.remove('hidden');

    const usage = itemUsage(item);

    let metadata = '';
    metadata += viewRow('ID', data.lab_id || '—');
    metadata += viewRow(
        'State',
        usage.locked
            ? 'Locked / referenced'
            : (
                item.published
                    ? 'Published / read-only'
                    : 'Unused / editable'
            )
    );
    metadata += viewRow(
        'References',
        usage.count ? String(usage.count) : '0'
    );
    metadata += viewRow(
        'Mainfile',
        item.mainfile || '—'
    );

    let formHtml = '';

    if (
        currentType === 'processing_recipe' &&
        currentSubtype === 'cleaning'
    ) {
        formHtml = cleaningReadonlyView(data);
    } else if (
        currentType === 'processing_recipe' &&
        currentSubtype === 'annealing'
    ) {
        formHtml = annealingReadonlyView(data);
    } else if (
        currentType === 'processing_recipe' &&
        currentSubtype === 'back_side_coating'
    ) {
        formHtml = backSideCoatingReadonlyView(data);
    } else {
        let summary = '';
        summary += viewRow('Type', currentLabel());
        summary += metadata;

        formHtml =
            '<div class="view-grid">' +
            summary +
            '</div>';
    }

    const yamlText =
        'data:\n' + archiveToYaml(data, 2);

    panel.innerHTML = `
        <div style="display:flex; justify-content:flex-end; margin-bottom:12px;">
            <button
                type="button"
                id="toggleRawArchive">
                View YAML
            </button>
        </div>

        <div id="formattedArchiveView">
            ${formHtml}

            <h3>Entry information</h3>
            <div class="view-grid">
                ${metadata}
            </div>
        </div>

        <div id="rawArchiveView" class="hidden">
            <h3>YAML archive</h3>
            <div class="view-raw">${escapeHtml(yamlText)}</div>
        </div>
    `;

    const button =
        document.getElementById('toggleRawArchive');

    const formatted =
        document.getElementById('formattedArchiveView');

    const raw =
        document.getElementById('rawArchiveView');

    button.addEventListener('click', function() {
        const showingRaw =
            !raw.classList.contains('hidden');

        raw.classList.toggle('hidden', showingRaw);
        formatted.classList.toggle('hidden', !showingRaw);

        button.textContent =
            showingRaw
                ? 'View YAML'
                : 'Back to form';
    });

    openModal();
}

function fillSizeSelect(id, includeOther) {
    const select = document.getElementById(id);
    select.innerHTML = '';
    SIZE_OPTIONS_MM.forEach(function(size) {
        const option = document.createElement('option');
        option.value = String(size);
        option.textContent = size + ' × ' + size + ' mm';
        select.appendChild(option);
    });
    if (includeOther !== false) {
        const custom = document.createElement('option');
        custom.value = 'other';
        custom.textContent = 'Other…';
        select.appendChild(custom);
    }
}

function setSizeSelect(selectId, wrapId, customId, sizeMm) {
    const select = document.getElementById(selectId);
    const known = SIZE_OPTIONS_MM.some(function(value) { return Math.abs(value - sizeMm) < 1e-9; });
    if (known) {
        select.value = String(sizeMm);
        document.getElementById(wrapId).classList.add('hidden');
    } else {
        select.value = 'other';
        document.getElementById(wrapId).classList.remove('hidden');
        document.getElementById(customId).value = sizeMm ? formatNumber(sizeMm) : '';
    }
}

function selectedSquareSize(selectId, customId) {
    const selected = document.getElementById(selectId).value;
    if (selected !== 'other') return Number(selected);
    const value = Number(document.getElementById(customId).value);
    if (!Number.isFinite(value) || value <= 0) throw new Error('Custom size must be greater than zero.');
    return value;
}

function attachSizeToggle(selectId, wrapId) {
    document.getElementById(selectId).addEventListener('change', function(event) {
        document.getElementById(wrapId).classList.toggle('hidden', event.target.value !== 'other');
        updateGeneratedId();
    });
}

function inferHolderSizeMm(data) {
    const positions = Array.isArray(data.positions) ? data.positions : [];
    for (const position of positions) {
        const xy = geometryXY(position.slot_geometry);
        if (xy && Math.abs(xy.width - xy.length) < 1e-12) return xy.width * 1000;
    }
    const match = String(data.lab_id || '').match(/^[HM]\d+_(\d+(?:\.\d+)?)$/);
    return match ? Number(match[1]) : null;
}

function parseHolderId(id) {
    const match = String(id || '').match(/^([HM])(\d+)_(\d+(?:\.\d+)?)$/);
    return match ? {material:match[1], number:Number(match[2]), size:Number(match[3])} : null;
}

function parseInsertId(id) {
    const match = String(id || '').match(/^([A-Z][A-Z0-9]*)(\d+)_(\d+(?:\.\d+)?)$/);
    return match ? {family:match[1], number:Number(match[2]), size:Number(match[3])} : null;
}

function nextSequentialId(prefix, items) {
    let max = 0;
    const pattern = new RegExp('^' + prefix + '_(\\d+)$');
    items.forEach(function(item) {
        const match = String((item.data || {}).lab_id || '').match(pattern);
        if (match) max = Math.max(max, Number(match[1]));
    });
    return prefix + '_' + String(max + 1).padStart(3, '0');
}

function recipeNameIdPart(value) {
    return String(value || '')
        .trim()
        .replace(/\s+/g, '_')
        .replace(/[^A-Za-z0-9_-]/g, '')
        .replace(/_+/g, '_')
        .replace(/^_+|_+$/g, '');
}

function nextNamedRecipeId(prefix, recipeName, items) {
    const namePart = recipeNameIdPart(recipeName);

    if (!namePart) {
        return prefix + '_01';
    }

    const base = prefix + '_' + namePart + '_';
    let max = 0;

    (items || []).forEach(function(item) {
        const id = String((item.data || {}).lab_id || '');
        if (!id.startsWith(base)) return;

        const suffix = id.slice(base.length);
        if (/^\d+$/.test(suffix)) {
            max = Math.max(max, Number(suffix));
        }
    });

    return base + String(max + 1).padStart(2, '0');
}

function annealingInstrumentCode(value) {
    const codes = {
        'Tube furnace – MBE lab': 'TF-MBE',
        'Tube furnace – 6th floor': 'TF-6',
        'MBE growth chamber': 'GC',
        'MBE 2nd transfer chamber': 'TC2'
    };
    return codes[String(value || '')] || 'INST';
}

function generatedId() {
    if (
        currentType === 'processing_recipe' &&
        currentSubtype === 'cleaning'
    ) {
        return generatedCleaningRecipeId();
    }

    if (
        currentType === 'processing_recipe' &&
        currentSubtype === 'annealing'
    ) {
        return generatedAnnealingRecipeId();
    }

    if (currentType === 'processing_recipe') {
        const prefix = currentDefinition().id_prefix || 'RECIPE';

        if (editorMode === 'edit' && editorItem && (editorItem.data || {}).lab_id) {
            return editorItem.data.lab_id;
        }

        if (currentSubtype === 'cleaning') {
            const nameInput = document.getElementById('chemicalTreatmentName');
            return nextNamedRecipeId(
                prefix,
                nameInput ? nameInput.value : '',
                allProcessingCatalogs[currentSubtype] || []
            );
        }

        if (currentSubtype === 'annealing') {
            const nameInput = document.getElementById('annealingRecipeName');
            const instrumentInput = document.getElementById('annealingInstrument');

            const instrumentCode = annealingInstrumentCode(
                instrumentInput ? instrumentInput.value : ''
            );

            const recipeName = nameInput ? nameInput.value : '';

            return nextNamedRecipeId(
                prefix,
                instrumentCode + (recipeName ? '_' + recipeName : ''),
                allProcessingCatalogs[currentSubtype] || []
            );
        }

        if (currentSubtype === 'back_side_coating') {
            const materialInput =
                document.getElementById('backCoatingMaterial');

            const thicknessInput =
                document.getElementById('backCoatingThickness');

            const material =
                materialInput ? materialInput.value : 'Ti';

            const raw =
                thicknessInput ? thicknessInput.value.trim() : '';

            let namePart = material;

            if (raw !== '') {
                const thickness = Number(raw);

                if (Number.isFinite(thickness) && thickness > 0) {
                    const token =
                        formatNumber(thickness).replace('.', 'p');

                    namePart += '_' + token + 'um';
                }
            }

            return nextNamedRecipeId(
                prefix,
                namePart,
                allProcessingCatalogs[currentSubtype] || []
            );
        }

        return nextSequentialId(prefix, allProcessingCatalogs[currentSubtype] || []);
    }

    if (currentType === 'sample_cut_recipe') {
        const parent = selectedSquareSize('cutParentSize', 'cutParentCustom');
        const child = selectedSquareSize('cutChildSize', 'cutChildCustom');
        const count = Number(document.getElementById('cutChildCount').value || 1);
        return 'CUT_' + formatNumber(parent) + '_TO_' + formatNumber(count) + 'X' + formatNumber(child);
    }

    if (currentType === 'holder') {
        const material = document.getElementById('holderMaterial').value;
        const number = Number(document.getElementById('holderNumber').value || 1);
        const size = selectedSquareSize('holderSize', 'holderCustomSize');
        return material + String(number) + '_' + formatNumber(size);
    }

    if (currentType === 'insert') {
        let family = document.getElementById('insertFamily').value;
        if (family === 'CUSTOM') {
            family = document.getElementById('insertFamilyCustom').value.trim().toUpperCase();
            if (!/^[A-Z][A-Z0-9]*$/.test(family)) return 'INVALID_FAMILY';
        }
        const number = Number(document.getElementById('insertNumber').value || 1);
        const opening = selectedSquareSize('insertInnerSize', 'insertInnerCustom');
        return family + String(number) + '_' + formatNumber(opening);
    }
    return '—';
}


function recipeIdNumber(value) {
    const number = Number(value);

    if (!Number.isFinite(number)) {
        return '';
    }

    return String(Number(number.toFixed(6)))
        .replace('.', 'p');
}


function cleaningReagentAbbreviation(name) {
    const value = String(name || '').trim();

    const known = {
        'Isobutyl alcohol': 'But',
        'Acetone': 'Ace',
        'Isopropanol': 'prop',
        'DI water': 'DI_H2O',
        'HF': 'HF',
        "King's water": 'KiWa',
        'Kingswater': 'KiWa'
    };

    if (known[value]) {
        return known[value];
    }

    const cleaned = value
        .replace(/[^A-Za-z0-9]+/g, '')
        .trim();

    if (!cleaned) {
        return '';
    }

    if (cleaned.length <= 3) {
        return cleaned;
    }

    return (
        cleaned.charAt(0).toUpperCase() +
        cleaned.slice(1, 3).toLowerCase()
    );
}


function cleaningDurationId(values) {
    const durations = values
        .map(Number)
        .filter(Number.isFinite);

    if (!durations.length) {
        return '';
    }

    /*
     * If all steps are <= 60 min, keep the compact form:
     *
     * 10, 10, 10 -> 10_10_10min
     */
    if (durations.every(value => value <= 60)) {
        return (
            durations
                .map(recipeIdNumber)
                .join('_') +
            'min'
        );
    }

    /*
     * With mixed minutes/hours, put a unit on every value
     * to keep the ID unambiguous.
     *
     * 10, 90, 30 -> 10min_1p5h_30min
     */
    return durations.map(function(minutes) {
        if (minutes > 60) {
            return (
                recipeIdNumber(minutes / 60) +
                'h'
            );
        }

        return (
            recipeIdNumber(minutes) +
            'min'
        );
    }).join('_');
}


function cleaningTemperatureId(values) {
    const temperatures = values
        .map(Number)
        .filter(function(value) {
            return Number.isFinite(value) &&
                   value > 50;
        });

    if (!temperatures.length) {
        return '';
    }

    return (
        temperatures
            .map(recipeIdNumber)
            .join('_') +
        'C'
    );
}


function generatedCleaningRecipeId() {
    const rows = Array.from(
        document.querySelectorAll(
            '#cleaningSteps .cleaning-step-row'
        )
    );

    const reagents = [];
    const durations = [];
    const temperatures = [];
    const devices = [];
    const seenDevices = new Set();

    rows.forEach(function(row) {
        const reagentSelect =
            row.querySelector(
                '.cleaning-reagent'
            );

        let reagent =
            reagentSelect
                ? reagentSelect.value
                : '';

        if (reagent === '__custom__') {
            const custom =
                row.querySelector(
                    '.cleaning-reagent-custom'
                );

            reagent =
                custom
                    ? custom.value.trim()
                    : '';
        }

        const reagentId =
            cleaningReagentAbbreviation(
                reagent
            );

        if (reagentId) {
            reagents.push(reagentId);
        }


        const durationInput =
            row.querySelector(
                '.cleaning-duration'
            );

        if (
            durationInput &&
            durationInput.value !== ''
        ) {
            const duration =
                Number(durationInput.value);

            if (Number.isFinite(duration)) {
                durations.push(duration);
            }
        }


        const temperatureInput =
            row.querySelector(
                '.cleaning-temperature'
            );

        if (
            temperatureInput &&
            temperatureInput.value !== ''
        ) {
            const temperature =
                Number(
                    temperatureInput.value
                );

            if (
                Number.isFinite(temperature) &&
                temperature > 50
            ) {
                temperatures.push(
                    temperature
                );
            }
        }


        const agitation =
            row.querySelector(
                '.cleaning-agitation'
            );

        const value =
            agitation
                ? agitation.value
                : '';

        let device = '';

        if (
            value === 'Ultrasonic bath'
        ) {
            device = 'US';
        } else if (
            value === 'Hot plate' ||
            value === 'Heating plate'
        ) {
            device = 'HP';
        }

        if (
            device &&
            !seenDevices.has(device)
        ) {
            seenDevices.add(device);
            devices.push(device);
        }
    });


    const parts = ['Clean'];

    if (reagents.length) {
        parts.push(
            reagents.join('_')
        );
    }

    const durationPart =
        cleaningDurationId(
            durations
        );

    if (durationPart) {
        parts.push(durationPart);
    }

    const temperaturePart =
        cleaningTemperatureId(
            temperatures
        );

    if (temperaturePart) {
        parts.push(temperaturePart);
    }

    if (devices.length) {
        parts.push(
            devices.join('_')
        );
    }

    return parts.join('_');
}



function annealingInstrumentAbbreviation(name) {
    const known = {
        'Tube furnace – MBE lab': 'TF',
        'Tube furnace – 6th floor': 'TF',
        'Oven Chemlab': 'OCL',
        'Rapid Thermal Annealing': 'RTA',
        'MBE growth chamber': 'MBE',
        'MBE 2nd transfer chamber': 'MBE2T'
    };

    return known[String(name || '').trim()] || 'Ann';
}


function annealingTemperatureId(values) {
    const temperatures = values
        .map(Number)
        .filter(Number.isFinite);

    if (!temperatures.length) {
        return '';
    }

    return (
        temperatures
            .map(recipeIdNumber)
            .join('_') +
        'C'
    );
}


function generatedAnnealingRecipeId() {
    const instrument =
        document.getElementById('annealingInstrument');

    const atmosphere =
        document.getElementById('annealingAtmosphere');

    const rows = Array.from(
        document.querySelectorAll(
            '#annealingSteps .annealing-step-row'
        )
    );

    const temperatures = [];
    const durations = [];

    rows.forEach(function(row) {
        const temperature =
            row.querySelector(
                '.annealing-operation-temperature'
            );

        if (
            temperature &&
            temperature.value !== ''
        ) {
            const value = Number(temperature.value);

            if (Number.isFinite(value)) {
                temperatures.push(value);
            }
        }

        const duration =
            row.querySelector(
                '.annealing-duration'
            );

        if (
            duration &&
            duration.value !== ''
        ) {
            const value = Number(duration.value);

            if (Number.isFinite(value)) {
                durations.push(value);
            }
        }
    });

    const parts = [
        'Ann',
        annealingInstrumentAbbreviation(
            instrument ? instrument.value : ''
        )
    ];

    const temperaturePart =
        annealingTemperatureId(temperatures);

    if (temperaturePart) {
        parts.push(temperaturePart);
    }

    const durationPart =
        cleaningDurationId(durations);

    if (durationPart) {
        parts.push(durationPart);
    }

    if (
        atmosphere &&
        atmosphere.value
    ) {
        parts.push(atmosphere.value);
    }

    return parts.join('_');
}


function updateGeneratedId() {
    try {
        document.getElementById('generatedIdValue').textContent = generatedId();
    } catch (_) {
        document.getElementById('generatedIdValue').textContent = '—';
    }
}

function clearHolderPositions() {
    document.getElementById('holderPositions').innerHTML = '';
    renderHolderPreview();
}

function holderNominalSizeMm() {
    try {
        const value = selectedSquareSize(
            'holderSize',
            'holderCustomSize'
        );
        return Number.isFinite(value) ? value : 10;
    } catch (_) {
        return 10;
    }
}


function holderPositionSizeMm(position) {
    const geometry =
        position && position.slot_geometry
            ? position.slot_geometry
            : {};

    const width = Number(geometry.width);

    if (Number.isFinite(width) && width > 0) {
        return width * 1000;
    }

    return holderNominalSizeMm();
}


function holderPreviewEscape(value) {
    return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}


function installHolderGeometryUi() {
    const header =
        document.querySelector(
            '.holder-position-header'
        );

    if (header) {
        header.innerHTML =
            '<div>Name</div>' +
            '<div>Size (mm)</div>' +
            '<div>Rho (mm)</div>' +
            '<div>Theta (°)</div>' +
            '<div></div>';

        header.style.gridTemplateColumns =
            '1fr 0.85fr 0.85fr 0.85fr auto';
    }

    const sizeLabel =
        document.querySelector(
            'label[for="holderSize"]'
        );

    if (sizeLabel) {
        sizeLabel.textContent =
            'Slot size';
    }

    const customSizeLabel =
        document.querySelector(
            'label[for="holderCustomSize"]'
        );

    if (customSizeLabel) {
        customSizeLabel.textContent =
            'Custom size (mm)';
    }

    ensureHolderPreview();

    ['holderSize', 'holderCustomSize']
        .forEach(function(id) {
            const element =
                document.getElementById(id);

            if (
                !element ||
                element.dataset.holderPreviewHook === '1'
            ) {
                return;
            }

            element.dataset.holderPreviewHook =
                '1';

            function changed() {
                syncHolderPositionSizes();
                renderHolderPreview();
            }

            element.addEventListener(
                'change',
                changed
            );

            element.addEventListener(
                'input',
                changed
            );
        });
}


function ensureHolderPreview() {
    let wrap =
        document.getElementById(
            'holderGeometryPreview'
        );

    if (wrap) {
        return wrap;
    }

    const positions =
        document.getElementById(
            'holderPositions'
        );

    if (!positions) {
        return null;
    }

    wrap =
        document.createElement('div');

    wrap.id =
        'holderGeometryPreview';

    wrap.style.marginTop =
        '18px';

    wrap.style.marginBottom =
        '18px';

    wrap.innerHTML =
        '<h3 style="margin-bottom:8px;">Holder preview</h3>' +
        '<p class="small" style="margin-top:0;">' +
        'Live view from Size, Rho and Theta.' +
        '</p>' +
        '<div id="holderGeometryPreviewCanvas"></div>';

    positions.insertAdjacentElement(
        'afterend',
        wrap
    );

    return wrap;
}


function syncHolderPositionSizes() {
    const size =
        holderNominalSizeMm();

    document
        .querySelectorAll(
            '.holder-position-row .position-size'
        )
        .forEach(function(input) {
            input.value =
                String(size);
        });
}


function renderHolderPreview() {
    const wrap =
        ensureHolderPreview();

    if (!wrap) {
        return;
    }

    const canvas =
        document.getElementById(
            'holderGeometryPreviewCanvas'
        );

    if (!canvas) {
        return;
    }

    const rows =
        Array.from(
            document.querySelectorAll(
                '.holder-position-row'
            )
        );

    /*
     * Standard PDI MBE holder:
     * 3 inch diameter = 76.2 mm.
     */
    const holderRadius =
        38.1;

    const positions = [];

    rows.forEach(function(row) {
        const nameInput =
            row.querySelector(
                '.position-name'
            );

        const sizeInput =
            row.querySelector(
                '.position-size'
            );

        const rhoInput =
            row.querySelector(
                '.position-rho'
            );

        const thetaInput =
            row.querySelector(
                '.position-theta'
            );

        const name =
            nameInput
                ? nameInput.value.trim()
                : '';

        const size =
            sizeInput
                ? Number(sizeInput.value)
                : NaN;

        const rho =
            rhoInput
                ? Number(rhoInput.value)
                : NaN;

        const theta =
            thetaInput
                ? Number(thetaInput.value)
                : NaN;

        if (
            !Number.isFinite(size) ||
            !Number.isFinite(rho) ||
            !Number.isFinite(theta)
        ) {
            return;
        }

        const rad =
            theta *
            Math.PI /
            180;

        positions.push({
            name:
                name ||
                '?',

            size:
                size,

            rho:
                rho,

            theta:
                theta,

            x:
                rho *
                Math.cos(rad),

            y:
                -rho *
                Math.sin(rad)
        });
    });

    let extent =
        43;

    positions.forEach(
        function(position) {
            extent =
                Math.max(
                    extent,
                    Math.abs(position.x) +
                        position.size /
                        2 +
                        5,
                    Math.abs(position.y) +
                        position.size /
                        2 +
                        5
                );
        }
    );

    const viewSize =
        extent * 2;

    let svg =
        '<svg ' +
        'viewBox="' +
        (-extent) + ' ' +
        (-extent) + ' ' +
        viewSize + ' ' +
        viewSize + '" ' +
        'style="' +
        'width:100%;' +
        'max-width:420px;' +
        'aspect-ratio:1;' +
        'display:block;' +
        'margin:0 auto;' +
        'border:1px solid rgba(128,128,128,.35);' +
        'border-radius:8px;' +
        'background:transparent;' +
        '">';

    svg +=
        '<circle ' +
        'cx="0" cy="0" ' +
        'r="' + holderRadius + '" ' +
        'fill="none" ' +
        'stroke="currentColor" ' +
        'stroke-width="0.7" ' +
        'opacity="0.65" />';

    svg +=
        '<line ' +
        'x1="' + (-holderRadius) + '" ' +
        'y1="0" ' +
        'x2="' + holderRadius + '" ' +
        'y2="0" ' +
        'stroke="currentColor" ' +
        'stroke-width="0.25" ' +
        'opacity="0.25" />';

    svg +=
        '<line ' +
        'x1="0" ' +
        'y1="' + (-holderRadius) + '" ' +
        'x2="0" ' +
        'y2="' + holderRadius + '" ' +
        'stroke="currentColor" ' +
        'stroke-width="0.25" ' +
        'opacity="0.25" />';

    positions.forEach(
        function(position) {
            /*
             * SVG y points downwards.
             * Positive mathematical y therefore
             * becomes negative SVG y.
             */
            const x =
                position.x;

            const y =
                -position.y;

            const half =
                position.size /
                2;

            svg +=
                '<rect ' +
                'x="' + (x - half) + '" ' +
                'y="' + (y - half) + '" ' +
                'width="' + position.size + '" ' +
                'height="' + position.size + '" ' +
                'rx="0.7" ' +
                'fill="none" ' +
                'stroke="currentColor" ' +
                'stroke-width="0.8" />';

            svg +=
                '<text ' +
                'x="' + x + '" ' +
                'y="' + (y + 1.7) + '" ' +
                'text-anchor="middle" ' +
                'font-size="4.5" ' +
                'font-family="sans-serif" ' +
                'fill="currentColor">' +
                holderPreviewEscape(
                    position.name
                ) +
                '</text>';
        }
    );

    svg +=
        '<text ' +
        'x="0" ' +
        'y="' + (holderRadius + 4.5) + '" ' +
        'text-anchor="middle" ' +
        'font-size="3.6" ' +
        'font-family="sans-serif" ' +
        'fill="currentColor" ' +
        'opacity="0.65">' +
        '3-inch holder · 76.2 mm' +
        '</text>';

    svg +=
        '</svg>';

    canvas.innerHTML =
        svg;
}


function addHolderPosition(position) {
    position =
        position || {};

    const row =
        document.createElement(
            'div'
        );

    row.className =
        'holder-position-row';

    row.style.gridTemplateColumns =
        '1fr 0.85fr 0.85fr 0.85fr auto';

    function input(
        className,
        value,
        type,
        step
    ) {
        const element =
            document.createElement(
                'input'
            );

        element.className =
            className;

        element.type =
            type || 'number';

        if (step) {
            element.step =
                step;
        }

        element.value =
            value === undefined ||
            value === null
                ? ''
                : String(value);

        element.addEventListener(
            'input',
            renderHolderPreview
        );

        element.addEventListener(
            'change',
            renderHolderPreview
        );

        return element;
    }

    const nameInput =
        input(
            'position-name',
            position.name || '',
            'text'
        );

    const sizeInput =
        input(
            'position-size',
            holderPositionSizeMm(
                position
            ),
            'number',
            '0.1'
        );

    /*
     * Size is selected once for the holder
     * and shown per position for clarity.
     */
    sizeInput.readOnly =
        true;

    sizeInput.title =
        'Slot size is set by the holder Size field above.';

    const rhoInput =
        input(
            'position-rho',
            mm(position.rho),
            'number',
            '0.1'
        );

    rhoInput.min =
        '0';

    const thetaInput =
        input(
            'position-theta',
            geometryNumber(
                position.theta
            ),
            'number',
            '0.1'
        );

    row.append(
        nameInput,
        sizeInput,
        rhoInput,
        thetaInput
    );

    const remove =
        document.createElement(
            'button'
        );

    remove.type =
        'button';

    remove.className =
        'remove-position';

    remove.textContent =
        '×';

    remove.title =
        'Remove position';

    remove.addEventListener(
        'click',
        function() {
            row.remove();
            renderHolderPreview();
        }
    );

    row.appendChild(
        remove
    );

    document
        .getElementById(
            'holderPositions'
        )
        .appendChild(
            row
        );

    installHolderGeometryUi();
    renderHolderPreview();
}


if (
    document.readyState ===
    'loading'
) {
    document.addEventListener(
        'DOMContentLoaded',
        function() {
            installHolderGeometryUi();
            renderHolderPreview();
        }
    );
} else {
    installHolderGeometryUi();
    renderHolderPreview();
}

function fieldValuesFromCatalog(field) {
    const values = [];
    (allProcessingCatalogs[currentSubtype] || []).forEach(function(item) {
        const value = (item.data || {})[field];
        if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
            if (!values.some(function(existing) { return String(existing) === String(value); })) {
                values.push(value);
            }
        }
    });
    return values;
}

function dynamicScalarFields() {
    const definition = currentDefinition() || {};
    if (Array.isArray(definition.fields)) {
        return definition.fields;
    }
    return [];
}

function friendlyFieldLabel(field) {
    const labels = {
        temperature: 'Temperature',
        duration: 'Duration',
        chemical_formula: 'Chemical formula',
        material: 'Material'
    };
    return labels[field] || field.replaceAll('_', ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });
}


function cleaningReagentName(step) {
    const reagent = step && step.cleaning_reagents;
    if (!reagent) return '';
    if (Array.isArray(reagent)) return reagent[0] && reagent[0].name ? reagent[0].name : '';
    return reagent.name || '';
}

function cleaningStepHtml(step, index) {
    step = step || {};
    const reagent = cleaningReagentName(step);
    const durationMin = step.duration != null ? Number(step.duration) / 60 : '';
    const temperature = step.temperature != null ? step.temperature : '';
    const agitation = step.agitation || '';
    const comment = step.comment || '';

    const knownReagents = [
        'Isobutyl alcohol',
        'Acetone',
        'Isopropanol',
        'DI water',
        'HF',
        "King's water"
    ];

    const customReagent = reagent && !knownReagents.includes(reagent);

    return `
        <div class="cleaning-step-row">
            <div class="cleaning-step-header">
                <strong>Step ${index + 1}</strong>
                <button type="button" class="cleaning-remove-step">Remove step</button>
            </div>

            <div class="cleaning-step-primary">
                <div>
                    <label>Reagent / medium *</label>
                    <select class="cleaning-reagent" required>
                        <option value="">Select...</option>
                        <option value="Isobutyl alcohol" ${reagent === 'Isobutyl alcohol' ? 'selected' : ''}>Isobutyl alcohol</option>
                        <option value="Acetone" ${reagent === 'Acetone' ? 'selected' : ''}>Acetone</option>
                        <option value="Isopropanol" ${reagent === 'Isopropanol' ? 'selected' : ''}>Isopropanol</option>
                        <option value="DI water" ${reagent === 'DI water' ? 'selected' : ''}>DI water</option>
                        <option value="HF" ${reagent === 'HF' ? 'selected' : ''}>HF</option>
                        <option value="__custom__" ${customReagent ? 'selected' : ''}>Custom...</option>
                    </select>

                    <input
                        class="cleaning-reagent-custom ${customReagent ? '' : 'hidden'}"
                        type="text"
                        placeholder="Custom reagent"
                        value="${customReagent ? escapeHtml(reagent) : ''}">
                </div>

                <div>
                    <label>Duration (min) *</label>
                    <input
                        class="cleaning-duration"
                        type="number"
                        required
                        step="0.1"
                        min="0"
                        value="${durationMin}">
                </div>

                <div>
                    <label>Temperature (°C) *</label>
                    <input
                        class="cleaning-temperature"
                        type="number"
                        required
                        step="0.1"
                        value="${temperature}">
                </div>
            </div>

            <div class="cleaning-step-secondary">
                <div>
                    <label>Agitation *</label>
                    <select class="cleaning-agitation" required>
                        <option value="__none__" ${!agitation ? 'selected' : ''}>None</option>
                        <option value="Hot plate" ${agitation === 'Hot plate' ? 'selected' : ''}>Hot plate</option>
                        <option value="Ultrasonic bath" ${agitation === 'Ultrasonic bath' ? 'selected' : ''}>Ultrasonic bath</option>
                    </select>
                </div>

                <div>
                    <label>Comment</label>
                    <input
                        class="cleaning-comment"
                        type="text"
                        value="${escapeHtml(comment)}">
                </div>
            </div>
        </div>
    `;
}

function restoreProcessingTemplateBlock() {
    const block = document.getElementById('processingTemplateBlock');
    const fields = document.getElementById('processingFields');
    const dynamic = document.getElementById('processingDynamicFields');

    if (block && fields && dynamic && block.parentElement !== fields) {
        fields.insertBefore(block, dynamic);
    }
}

function restoreTargetUploadFields() {
    const target = document.getElementById('targetUploadFields');
    const actions = document.querySelector('.modal-actions');
    if (target && actions && target.parentElement !== actions.parentElement) {
        actions.parentElement.insertBefore(target, actions);
    }
}

function renderCleaningFields(seedData) {
    restoreProcessingTemplateBlock();

    const container = document.getElementById('processingDynamicFields');

    if (container.dataset.cleaningIdHook !== '1') {
        container.dataset.cleaningIdHook = '1';

        container.addEventListener(
            'input',
            updateGeneratedId
        );

        container.addEventListener(
            'change',
            updateGeneratedId
        );

        const cleaningIdObserver =
            new MutationObserver(
                function() {
                    updateGeneratedId();
                }
            );

        cleaningIdObserver.observe(
            container,
            {
                childList: true,
                subtree: true
            }
        );
    }

    const method = String((seedData || {}).method || '');
    const acid = /acid|hf/i.test(method);

    container.classList.add('cleaning-editor');

    container.innerHTML = `
        <div class="cleaning-left-column">
            <div>
                <label for="chemicalTreatmentType">Treatment type</label>
                <select id="chemicalTreatmentType">
                    <option value="Solvent cleaning" ${acid ? '' : 'selected'}>Solvent cleaning</option>
                    <option value="Acid treatment" ${acid ? 'selected' : ''}>Acid / HF treatment</option>
                </select>
            </div>

            <div>
                <label for="chemicalTreatmentName">Recipe name</label>
                <input
                    id="chemicalTreatmentName"
                    type="text"
                    required
                    placeholder="e.g. Iso-Ace-Prop_10_US"
                    value="${escapeHtml(
                        (seedData || {}).name &&
                        (seedData || {}).name !== (seedData || {}).lab_id
                            ? (seedData || {}).name
                            : ''
                    )}">
            </div>

            <div>
                <label for="chemicalTreatmentDescription">Description</label>
                <input
                    id="chemicalTreatmentDescription"
                    type="text"
                    value="${escapeHtml((seedData || {}).description || '')}">
            </div>
        </div>

        <div class="cleaning-right-column">
            <div class="cleaning-steps-heading">
                <h3>Process steps</h3>
            </div>

            <div id="cleaningSteps"></div>
            <button type="button" id="addCleaningStep">+ Add step</button>
        </div>
    `;

    const cleaningLeft = container.querySelector('.cleaning-left-column');

    const templateBlock = document.getElementById('processingTemplateBlock');
    if (cleaningLeft && templateBlock) {
        cleaningLeft.insertBefore(templateBlock, cleaningLeft.firstChild);
    }

    const targetUpload = document.getElementById('targetUploadFields');
    if (cleaningLeft && targetUpload) {
        cleaningLeft.appendChild(targetUpload);
    }

    const recipeNameInput = document.getElementById('chemicalTreatmentName');
    if (recipeNameInput) {
        recipeNameInput.addEventListener('input', updateGeneratedId);
    }
    updateGeneratedId();

    const steps = Array.isArray(seedData.steps) && seedData.steps.length
        ? seedData.steps
        : [{}];

    const stepContainer = document.getElementById('cleaningSteps');

    function syncCleaningStepsFromDom() {
        const rows = Array.from(stepContainer.querySelectorAll('.cleaning-step-row'));

        rows.forEach(function(row, index) {
            const reagentSelect = row.querySelector('.cleaning-reagent');
            const reagentCustom = row.querySelector('.cleaning-reagent-custom');

            const reagent = reagentSelect.value === '__custom__'
                ? reagentCustom.value.trim()
                : reagentSelect.value;

            const durationRaw = row.querySelector('.cleaning-duration').value.trim();
            const temperatureRaw = row.querySelector('.cleaning-temperature').value.trim();
            const agitation = row.querySelector('.cleaning-agitation').value;
            const comment = row.querySelector('.cleaning-comment').value.trim();

            const step = {};

            if (reagent) {
                step.name = reagent;
                step.cleaning_reagents = {name: reagent};
            }

            if (durationRaw !== '') {
                step.duration = Number(durationRaw) * 60;
            }

            if (temperatureRaw !== '') {
                step.temperature = Number(temperatureRaw);
            }

            if (agitation && agitation !== '__none__') {
                step.agitation = agitation;
            }
            if (comment) step.comment = comment;

            steps[index] = step;
        });
    }

    function redraw() {
        stepContainer.innerHTML = steps.map(cleaningStepHtml).join('');

        stepContainer.querySelectorAll('.cleaning-reagent').forEach(function(select) {
            select.addEventListener('change', function() {
                const custom =
                    select.parentElement.querySelector('.cleaning-reagent-custom');
                custom.classList.toggle('hidden', select.value !== '__custom__');
            });
        });

        stepContainer.querySelectorAll('.cleaning-remove-step').forEach(function(button, index) {
            button.disabled = steps.length === 1;

            button.addEventListener('click', function() {
                syncCleaningStepsFromDom();
                steps.splice(index, 1);
                redraw();
            });
        });
    }

    document.getElementById('addCleaningStep').addEventListener('click', function() {
        syncCleaningStepsFromDom();
        steps.push({});
        redraw();
    });

    redraw();
}


function annealingInstrumentName(seedData) {
    const instruments = (seedData || {}).instruments;
    if (Array.isArray(instruments) && instruments.length && instruments[0].name) {
        return String(instruments[0].name);
    }
    return 'Tube furnace – MBE lab';
}

function annealingStepHtml(step, index) {
    step = step || {};

    const durationMin =
        step.duration != null ? Number(step.duration) / 60 : '';

    const operationTemperature =
        step.operation_temperature != null
            ? step.operation_temperature
            : (
                step.ending_temperature != null
                    ? step.ending_temperature
                    : (
                        step.starting_temperature != null
                            ? step.starting_temperature
                            : ''
                    )
            );

    // Stored internally as K/s. Display existing values as °C/min.
    const rampRate =
        step.ramp_rate != null ? Number(step.ramp_rate) * 60 : '';

    const comment = step.comment || '';

    return `
        <div class="annealing-step-row">
            <div class="annealing-step-header">
                <strong>Step ${index + 1}</strong>
                <button type="button" class="annealing-remove-step">Remove step</button>
            </div>

            <div class="annealing-step-primary">
                <div>
                    <label>Operation temperature (°C) *</label>
                    <input
                        class="annealing-operation-temperature"
                        type="number"
                        step="0.1"
                        required
                        value="${operationTemperature}">
                </div>

                <div>
                    <label>Duration (min) *</label>
                    <input
                        class="annealing-duration"
                        type="number"
                        step="0.01"
                        min="0.01"
                        required
                        value="${durationMin}">
                </div>

                <div>
                    <label>Ramp rate</label>
                    <div class="annealing-ramp-control">
                        <input
                            class="annealing-ramp-rate"
                            type="number"
                            step="0.1"
                            min="0"
                            value="${rampRate}">
                        <select class="annealing-ramp-unit">
                            <option value="c_per_min" selected>°C/min</option>
                            <option value="c_per_s">°C/s</option>
                        </select>
                    </div>
                </div>
            </div>

            <div class="annealing-step-secondary">
                <div>
                    <label>Comment</label>
                    <input
                        class="annealing-comment"
                        type="text"
                        value="${escapeHtml(comment)}">
                </div>
            </div>
        </div>
    `;
}

function renderAnnealingFields(seedData) {
    restoreProcessingTemplateBlock();

    const container = document.getElementById('processingDynamicFields');
    container.classList.remove('cleaning-editor');
    container.classList.add('annealing-editor');

    const instrument = annealingInstrumentName(seedData);
    const atmosphere = String((seedData || {}).atmosphere || 'Vacuum');
    const gasFlow =
        (seedData || {}).gas_flow_sccm != null
            ? (seedData || {}).gas_flow_sccm
            : '';
    const rfPower =
        (seedData || {}).rf_power_w != null
            ? (seedData || {}).rf_power_w
            : '';

    container.innerHTML = `
        <div class="annealing-left-column">
            <div>
                <label for="annealingRecipeName">Recipe name</label>
                <input
                    id="annealingRecipeName"
                    type="text"
                    required
                    placeholder="e.g. STO_O2_950C"
                    value="${escapeHtml(
                        (seedData || {}).name &&
                        (seedData || {}).name !== (seedData || {}).lab_id
                            ? (seedData || {}).name
                            : ''
                    )}">
            </div>

            <div>
                <label for="annealingDescription">Description</label>
                <input
                    id="annealingDescription"
                    type="text"
                    value="${escapeHtml((seedData || {}).description || '')}">
            </div>
        </div>

        <div class="annealing-right-column">
            <div class="annealing-condition-grid">
                <div>
                    <label for="annealingInstrument">Instrument / location *</label>
                    <select id="annealingInstrument" required>
                        <option ${instrument === 'Tube furnace – MBE lab' ? 'selected' : ''}>Tube furnace – MBE lab</option>
                        <option ${instrument === 'Tube furnace – 6th floor' ? 'selected' : ''}>Tube furnace – 6th floor</option>
                        <option ${instrument === 'Oven Chemlab' ? 'selected' : ''}>Oven Chemlab</option>
                        <option ${instrument === 'Rapid Thermal Annealing' ? 'selected' : ''}>Rapid Thermal Annealing</option>
                        <option ${instrument === 'MBE growth chamber' ? 'selected' : ''}>MBE growth chamber</option>
                        <option ${instrument === 'MBE 2nd transfer chamber' ? 'selected' : ''}>MBE 2nd transfer chamber</option>
                    </select>
                </div>

                <div>
                    <label for="annealingAtmosphere">Gas / atmosphere *</label>
                    <select id="annealingAtmosphere" required>
                        <option value="Vacuum" ${atmosphere === 'Vacuum' ? 'selected' : ''}>Vacuum</option>
                        <option value="O2" ${atmosphere === 'O2' ? 'selected' : ''}>O₂</option>
                        <option value="Ar" ${atmosphere === 'Ar' ? 'selected' : ''}>Ar</option>
                        <option value="N2" ${atmosphere === 'N2' ? 'selected' : ''}>N₂</option>
                    </select>
                </div>

                <div>
                    <label for="annealingGasFlow">Gas flow (sccm)</label>
                    <input
                        id="annealingGasFlow"
                        type="number"
                        step="0.1"
                        min="0"
                        value="${gasFlow}">
                </div>

                <div id="annealingRfPowerWrap">
                    <label for="annealingRfPower">RF power (W)</label>
                    <input
                        id="annealingRfPower"
                        type="number"
                        step="0.1"
                        min="0"
                        value="${rfPower}">
                </div>
            </div>

            <div class="annealing-steps-heading">
                <h3>Process steps</h3>
            </div>

            <div id="annealingSteps"></div>
            <button type="button" id="addAnnealingStep">+ Add step</button>
        </div>
    `;

    const left = container.querySelector('.annealing-left-column');

    const templateBlock = document.getElementById('processingTemplateBlock');
    if (left && templateBlock) {
        left.insertBefore(templateBlock, left.firstChild);
    }

    const targetUpload = document.getElementById('targetUploadFields');
    if (left && targetUpload) {
        left.appendChild(targetUpload);
    }

    const nameInput = document.getElementById('annealingRecipeName');
    if (nameInput) {
        nameInput.addEventListener('input', updateGeneratedId);
    }

    const instrumentSelect = document.getElementById('annealingInstrument');
    const atmosphereSelect = document.getElementById('annealingAtmosphere');
    const gasFlowInput = document.getElementById('annealingGasFlow');
    const rfWrap = document.getElementById('annealingRfPowerWrap');

    function updateAnnealingConditions() {
        const currentAtmosphere = atmosphereSelect.value;
        const instrument = instrumentSelect.value;

        let allowedAtmospheres;
        let fallbackAtmosphere = 'Vacuum';

        if (instrument === 'Oven Chemlab') {
            allowedAtmospheres = [
                ['Air', 'Air']
            ];
            fallbackAtmosphere = 'Air';
        } else if (
            instrument === 'Rapid Thermal Annealing'
        ) {
            allowedAtmospheres = [
                ['N2', 'N₂'],
                ['O2', 'O₂'],
                ['Ar', 'Ar'],
                ['Air', 'Air']
            ];
            fallbackAtmosphere = 'Air';
        } else if (
            instrument === 'Tube furnace – MBE lab' ||
            instrument === 'Tube furnace – 6th floor'
        ) {
            allowedAtmospheres = [
                ['Vacuum', 'Vacuum'],
                ['O2', 'O₂'],
                ['Ar', 'Ar'],
                ['N2', 'N₂'],
                ['Air', 'Air']
            ];
        } else {
            allowedAtmospheres = [
                ['Vacuum', 'Vacuum'],
                ['O2', 'O₂'],
                ['Ar', 'Ar']
            ];
        }

        atmosphereSelect.innerHTML = '';

        allowedAtmospheres.forEach(function(pair) {
            const option =
                document.createElement('option');

            option.value = pair[0];
            option.textContent = pair[1];

            atmosphereSelect.appendChild(option);
        });

        if (
            allowedAtmospheres.some(
                function(pair) {
                    return pair[0] ===
                           currentAtmosphere;
                }
            )
        ) {
            atmosphereSelect.value =
                currentAtmosphere;
        } else {
            atmosphereSelect.value =
                fallbackAtmosphere;
        }

        atmosphereSelect.disabled =
            instrument === 'Oven Chemlab';

        const hasRfPlasma =
            instrument === 'MBE growth chamber';

        rfWrap.classList.toggle(
            'hidden',
            !hasRfPlasma
        );

        if (!hasRfPlasma) {
            document
                .getElementById('annealingRfPower')
                .value = '';
        }

        /*
         * Vacuum and ambient air do not require
         * a gas-flow value.
         */
        const needsGasFlow =
            atmosphereSelect.value !== 'Vacuum' &&
            atmosphereSelect.value !== 'Air';

        gasFlowInput.disabled = !needsGasFlow;
        gasFlowInput.required = needsGasFlow;

        if (!needsGasFlow) {
            gasFlowInput.value = '';
        }
    }


    instrumentSelect.addEventListener('change', function() {
        updateAnnealingConditions();
        updateGeneratedId();
    });
    atmosphereSelect.addEventListener('change', function() {
        updateAnnealingConditions();
        updateGeneratedId();
    });
    updateAnnealingConditions();

    const steps =
        Array.isArray(seedData.steps) && seedData.steps.length
            ? seedData.steps
            : [{}];

    const stepContainer = document.getElementById('annealingSteps');

    if (container.dataset.annealingIdHook !== '1') {
        container.dataset.annealingIdHook = '1';

        container.addEventListener(
            'input',
            updateGeneratedId
        );

        container.addEventListener(
            'change',
            updateGeneratedId
        );
    }

    function syncAnnealingStepsFromDom() {
        const rows =
            Array.from(stepContainer.querySelectorAll('.annealing-step-row'));

        rows.forEach(function(row, index) {
            const operationTemperature =
                row.querySelector('.annealing-operation-temperature').value.trim();

            const duration =
                row.querySelector('.annealing-duration').value.trim();

            const rampRate =
                row.querySelector('.annealing-ramp-rate').value.trim();

            const rampUnit =
                row.querySelector('.annealing-ramp-unit').value;

            const comment =
                row.querySelector('.annealing-comment').value.trim();

            const step = {};

            if (operationTemperature !== '') {
                step.operation_temperature = Number(operationTemperature);
            }

            if (duration !== '') {
                step.duration = Number(duration) * 60;
            }

            if (rampRate !== '') {
                const value = Number(rampRate);

                // Internal schema unit: K/s
                step.ramp_rate =
                    rampUnit === 'c_per_min'
                        ? value / 60
                        : value;
            }

            if (comment) step.comment = comment;

            steps[index] = step;
        });
    }

    function redraw() {
        stepContainer.innerHTML =
            steps.map(annealingStepHtml).join('');

        updateGeneratedId();

        stepContainer
            .querySelectorAll('.annealing-remove-step')
            .forEach(function(button, index) {
                button.disabled = steps.length === 1;

                button.addEventListener('click', function() {
                    syncAnnealingStepsFromDom();
                    steps.splice(index, 1);
                    redraw();
                });
            });
    }

    document
        .getElementById('addAnnealingStep')
        .addEventListener('click', function() {
            syncAnnealingStepsFromDom();
            steps.push({});
            redraw();
        });

    redraw();
    updateGeneratedId();
}

function renderBackSideCoatingFields(seedData) {
    restoreProcessingTemplateBlock();

    const container =
        document.getElementById('processingDynamicFields');

    container.classList.remove(
        'cleaning-editor',
        'annealing-editor'
    );

    const material =
        (seedData || {}).coating_material ||
        (
            (seedData || {}).coating_reagents &&
            (seedData || {}).coating_reagents.name
        ) ||
        'Ti';

    const thicknessUm =
        (seedData || {}).thickness !== undefined &&
        (seedData || {}).thickness !== null
            ? Number((seedData || {}).thickness) * 1e6
            : '';

    container.innerHTML = `
        <div class="cleaning-left-column">
            <div>
                <label for="backCoatingMaterial">
                    Coating material
                </label>

                <select id="backCoatingMaterial">
                    <option
                        value="Ti"
                        ${material === 'Ti' ? 'selected' : ''}>
                        Ti
                    </option>

                    <option
                        value="SrRuO3"
                        ${material === 'SrRuO3' ? 'selected' : ''}>
                        SrRuO3
                    </option>
                </select>
            </div>

            <div>
                <label for="backCoatingThickness">
                    Thickness (µm)
                </label>

                <input
                    id="backCoatingThickness"
                    type="number"
                    min="0"
                    step="any"
                    required
                    value="${escapeHtml(thicknessUm)}">
            </div>
        </div>
    `;

    const left =
        container.querySelector('.cleaning-left-column');

    const templateBlock =
        document.getElementById('processingTemplateBlock');

    if (left && templateBlock) {
        left.insertBefore(
            templateBlock,
            left.firstChild
        );
    }

    const target =
        document.getElementById('targetUploadFields');

    if (left && target) {
        left.appendChild(target);
    }

    document
        .getElementById('backCoatingMaterial')
        .addEventListener('change', updateGeneratedId);

    document
        .getElementById('backCoatingThickness')
        .addEventListener('input', updateGeneratedId);

    updateGeneratedId();
}


function renderProcessingDynamicFields(seedData) {
    const container = document.getElementById('processingDynamicFields');
    container.classList.remove('cleaning-editor', 'annealing-editor');

    if (currentSubtype === 'cleaning') {
        renderCleaningFields(seedData || {});
        return;
    }

    if (currentSubtype === 'annealing') {
        renderAnnealingFields(seedData || {});
        return;
    }

    if (currentSubtype === 'back_side_coating') {
        renderBackSideCoatingFields(seedData || {});
        return;
    }

    container.innerHTML = '';
    const fields = dynamicScalarFields();
    if (!fields.length) {
        container.innerHTML = '<div class="helper">No scalar recipe parameters were found in the existing library entries. The new recipe will contain only its generated ID until parameters are added by the schema editor.</div>';
        return;
    }

    fields.forEach(function(field) {
        const wrapper = document.createElement('div');
        wrapper.className = 'dynamic-field';
        wrapper.dataset.field = field;

        const label = document.createElement('label');
        label.textContent = friendlyFieldLabel(field);

        const select = document.createElement('select');
        select.className = 'dynamic-select';
        select.dataset.field = field;

        const blank = document.createElement('option');
        blank.value = '';
        blank.textContent = 'Not set';
        select.appendChild(blank);

        fieldValuesFromCatalog(field).forEach(function(value) {
            const option = document.createElement('option');
            option.value = JSON.stringify(value);
            option.textContent = String(value);
            select.appendChild(option);
        });

        const custom = document.createElement('option');
        custom.value = '__custom__';
        custom.textContent = 'Custom value…';
        select.appendChild(custom);

        const customInput = document.createElement('input');
        customInput.className = 'custom-value hidden';
        customInput.dataset.field = field;
        customInput.placeholder = field === 'chemical_formula' ? 'e.g. SrTiO3' : 'Custom value';

        const initial = (seedData || {})[field];
        if (initial !== undefined && initial !== null) {
            const encoded = JSON.stringify(initial);
            if (Array.from(select.options).some(function(option) { return option.value === encoded; })) {
                select.value = encoded;
            } else {
                select.value = '__custom__';
                customInput.classList.remove('hidden');
                customInput.value = String(initial);
            }
        }

        select.addEventListener('change', function() {
            customInput.classList.toggle('hidden', select.value !== '__custom__');
        });

        wrapper.append(label, select, customInput);
        container.appendChild(wrapper);
    });
}

function populateProcessingTemplate(seedData) {
    const select = document.getElementById('processingTemplate');
    select.innerHTML = '<option value="">Blank recipe</option>';
    (allProcessingCatalogs[currentSubtype] || []).forEach(function(item, index) {
        const option = document.createElement('option');
        option.value = String(index);
        option.textContent = itemTitle(item);
        select.appendChild(option);
    });

    select.onchange = function() {
        if (select.value === '') {
            renderProcessingDynamicFields({});
        } else {
            const item = (allProcessingCatalogs[currentSubtype] || [])[Number(select.value)];
            renderProcessingDynamicFields(item ? item.data : {});
        }
    };

    renderProcessingDynamicFields(seedData || {});
}

function populateEditor(data) {
    restoreTargetUploadFields();
    restoreProcessingTemplateBlock();
    data = data || {};
    ['processingFields','sampleCutFields','holderFields','insertFields'].forEach(function(id) {
        document.getElementById(id).classList.add('hidden');
    });

    if (currentType === 'processing_recipe') {
        document.getElementById('processingFields').classList.remove('hidden');
        populateProcessingTemplate(data);
    }

    if (currentType === 'sample_cut_recipe') {
        document.getElementById('sampleCutFields').classList.remove('hidden');
        const parent = geometryXY(data.input_geometry);
        const child = geometryXY(data.children_geometry);
        setSizeSelect('cutParentSize','cutParentCustomWrap','cutParentCustom',parent ? parent.width * 1000 : 10);
        setSizeSelect('cutChildSize','cutChildCustomWrap','cutChildCustom',child ? child.width * 1000 : 5);
        document.getElementById('cutChildCount').value = String(Number(data.number_of_samples) || 4);
    }

    if (currentType === 'holder') {
        document.getElementById('holderFields').classList.remove('hidden');
        const parsed = parseHolderId(data.lab_id);
        document.getElementById('holderMaterial').value = parsed ? parsed.material : 'H';
        document.getElementById('holderNumber').value = parsed ? parsed.number : 1;
        const size = parsed ? parsed.size : (inferHolderSizeMm(data) || 10);
        setSizeSelect('holderSize','holderCustomSizeWrap','holderCustomSize',size);

        clearHolderPositions();
        const positions = Array.isArray(data.positions) ? data.positions : [];
        positions.forEach(addHolderPosition);
        if (!positions.length) {
            ['A','B','C','D','E'].forEach(function(name) { addHolderPosition({name:name}); });
        }
    }

    if (currentType === 'insert') {
        document.getElementById('insertFields').classList.remove('hidden');
        const parsed = parseInsertId(data.lab_id);
        const knownFamily = parsed && ['XPS','MBE'].includes(parsed.family) ? parsed.family : null;
        document.getElementById('insertFamily').value = knownFamily || (parsed ? 'CUSTOM' : 'XPS');
        document.getElementById('insertFamilyCustomWrap').classList.toggle('hidden', Boolean(knownFamily) || !parsed);
        document.getElementById('insertFamilyCustom').value = parsed && !knownFamily ? parsed.family : '';
        document.getElementById('insertNumber').value = parsed ? parsed.number : 1;

        const outer = geometryXY(data.outer_geometry);
        const inner = geometryXY(data.inner_geometry);
        setSizeSelect('insertOuterSize','insertOuterCustomWrap','insertOuterCustom',outer ? outer.width * 1000 : 10);
        setSizeSelect('insertInnerSize','insertInnerCustomWrap','insertInnerCustom',inner ? inner.width * 1000 : 5);
    }

    updateGeneratedId();
}

function entityNoun() {
    if (currentType === 'processing_recipe' || currentType === 'sample_cut_recipe') return 'recipe';
    if (currentType === 'holder') return 'holder';
    if (currentType === 'insert') return 'insert';
    return 'item';
}

async function openEditor(mode, item) {
    if (mode === 'edit' && item) {
        const usage = itemUsage(item);
        if (usage.locked) {
            window.alert(
                'This item is locked because it is already referenced by NOMAD entries. ' +
                'Use Duplicate to create a new independent item.'
            );
            return;
        }
    }

    editorMode = mode;
    editorItem = item || null;
    document.getElementById('viewPanel').classList.add('hidden');
    document.getElementById('editorForm').classList.remove('hidden');
    document.getElementById('editorStatus').textContent = '';

    populateEditor(item ? JSON.parse(JSON.stringify(item.data || {})) : {});

    const target = document.getElementById('targetUploadFields');
    target.classList.toggle('hidden', mode === 'edit');

    if (mode === 'edit') {
        document.getElementById('modalTitle').textContent = 'Edit ' + itemTitle(item);
        document.getElementById('modalSubtitle').textContent = item.mainfile || item.entryId;
        document.getElementById('saveEditorButton').textContent = 'Save changes';
    } else {
        document.getElementById('modalTitle').textContent =
            mode === 'duplicate' ? 'New ' + entityNoun() + ' from ' + itemTitle(item) : 'Create new ' + entityNoun();
        document.getElementById('modalSubtitle').textContent =
            mode === 'duplicate'
                ? 'A new independent NOMAD entry will be created from this definition.'
                : currentLabel();
        document.getElementById('saveEditorButton').textContent = 'Save new ' + entityNoun();
    }

    document.getElementById('generatedIdHint').textContent =
        mode === 'edit'
            ? 'Existing ID is preserved while editing.'
            : 'The ID is generated from the structured fields and cannot be typed freely.';

    openModal();
}

function validateFormula(value) {
    return /^[A-Z][A-Za-z0-9().+\-]*$/.test(value) && !/^(STO|DSO|GSO|BSO|LAO|KTO|LSAT)$/i.test(value);
}

function readDynamicFields(data) {
    document.querySelectorAll('.dynamic-field').forEach(function(wrapper) {
        const field = wrapper.dataset.field;
        const select = wrapper.querySelector('.dynamic-select');
        const custom = wrapper.querySelector('.custom-value');
        if (!select || select.value === '') {
            delete data[field];
            return;
        }

        let value;
        if (select.value === '__custom__') {
            const raw = custom.value.trim();
            if (!raw) throw new Error(friendlyFieldLabel(field) + ' custom value is empty.');

            const examples = fieldValuesFromCatalog(field);
            const numeric = examples.some(function(example) { return typeof example === 'number'; });
            const boolean = examples.some(function(example) { return typeof example === 'boolean'; });

            if (numeric) {
                value = Number(raw);
                if (!Number.isFinite(value)) throw new Error(friendlyFieldLabel(field) + ' must be numeric.');
            } else if (boolean) {
                if (!['true','false'].includes(raw.toLowerCase())) throw new Error(friendlyFieldLabel(field) + ' must be true or false.');
                value = raw.toLowerCase() === 'true';
            } else {
                value = raw;
            }
        } else {
            value = JSON.parse(select.value);
        }

        if ((field === 'chemical_formula' || field === 'material') && typeof value === 'string') {
            if (!validateFormula(value)) {
                throw new Error(
                    friendlyFieldLabel(field) +
                    ' must use the full chemical formula, e.g. SrTiO3, not an abbreviation such as STO.'
                );
            }
        }
        data[field] = value;
    });
}


function readCleaningFields(data) {
    const recipeName =
        document.getElementById('chemicalTreatmentName').value.trim();

    if (!recipeName) {
        throw new Error('Recipe name is required.');
    }

    data.name = recipeName;
    data.method = document.getElementById('chemicalTreatmentType').value;

    const description =
        document.getElementById('chemicalTreatmentDescription').value.trim();

    if (description) data.description = description;
    else delete data.description;

    const rows =
        Array.from(document.querySelectorAll('.cleaning-step-row'));

    if (!rows.length) {
        throw new Error(
            'Chemical treatment requires at least one process step.'
        );
    }

    let totalDuration = 0;

    data.steps = rows.map(function(row, index) {
        const number = index + 1;

        const reagentSelect =
            row.querySelector('.cleaning-reagent');

        const reagentCustom =
            row.querySelector('.cleaning-reagent-custom');

        const reagent =
            reagentSelect.value === '__custom__'
                ? reagentCustom.value.trim()
                : reagentSelect.value;

        if (!reagent) {
            throw new Error(
                'Step ' + number + ': reagent / medium is required.'
            );
        }

        const durationMinutes =
            Number(row.querySelector('.cleaning-duration').value);

        if (!Number.isFinite(durationMinutes) || durationMinutes <= 0) {
            throw new Error(
                'Step ' + number +
                ': duration must be greater than zero.'
            );
        }

        const temperature =
            Number(row.querySelector('.cleaning-temperature').value);

        if (!Number.isFinite(temperature)) {
            throw new Error(
                'Step ' + number + ': temperature is required.'
            );
        }

        const agitation =
            row.querySelector('.cleaning-agitation').value;

        if (!agitation) {
            throw new Error(
                'Step ' + number + ': select an agitation setting.'
            );
        }

        const durationSeconds = durationMinutes * 60;
        totalDuration += durationSeconds;

        const step = {
            name: reagent,
            duration: durationSeconds,
            temperature: temperature,
            cleaning_reagents: {
                name: reagent
            }
        };

        if (agitation !== '__none__') {
            step.agitation = agitation;
        }

        const comment =
            row.querySelector('.cleaning-comment').value.trim();

        if (comment) step.comment = comment;

        return step;
    });

    data.duration = totalDuration;
}


function readAnnealingFields(data) {
    const recipeName =
        document.getElementById('annealingRecipeName').value.trim();

    if (!recipeName) {
        throw new Error('Recipe name is required.');
    }

    data.name = recipeName;

    const description =
        document.getElementById('annealingDescription').value.trim();

    if (description) data.description = description;
    else delete data.description;

    const instrument =
        document.getElementById('annealingInstrument').value;

    if (!instrument) {
        throw new Error('Annealing instrument / location is required.');
    }

    // Keep both the human-readable location and the NOMAD
    // InstrumentReference structure.
    data.location = instrument;
    data.instruments = [{
        name: instrument
    }];

    const atmosphere =
        document.getElementById('annealingAtmosphere').value;

    if (!atmosphere) {
        throw new Error('Gas / atmosphere is required.');
    }

    data.atmosphere = atmosphere;

    const gasFlowInput =
        document.getElementById('annealingGasFlow');

    if (
        atmosphere === 'Vacuum' ||
        atmosphere === 'Air'
    ) {
        delete data.gas_flow_sccm;
    } else {
        const gasFlow = Number(gasFlowInput.value);

        if (!Number.isFinite(gasFlow) || gasFlow <= 0) {
            throw new Error(
                'Gas flow must be greater than zero for ' +
                atmosphere + '.'
            );
        }

        data.gas_flow_sccm = gasFlow;
    }

    const rfInput =
        document.getElementById('annealingRfPower');

    if (instrument === 'MBE growth chamber') {
        const rawRf = rfInput.value.trim();

        if (rawRf === '') {
            delete data.rf_power_w;
        } else {
            const rfPower = Number(rawRf);

            if (!Number.isFinite(rfPower) || rfPower < 0) {
                throw new Error(
                    'RF power must be zero or greater.'
                );
            }

            data.rf_power_w = rfPower;
        }
    } else {
        delete data.rf_power_w;
    }

    const rows =
        Array.from(document.querySelectorAll('.annealing-step-row'));

    if (!rows.length) {
        throw new Error(
            'Annealing requires at least one process step.'
        );
    }

    let totalDuration = 0;

    data.steps = rows.map(function(row, index) {
        const number = index + 1;

        const temperature =
            Number(
                row.querySelector(
                    '.annealing-operation-temperature'
                ).value
            );

        if (!Number.isFinite(temperature)) {
            throw new Error(
                'Step ' + number +
                ': operation temperature is required.'
            );
        }

        const durationMinutes =
            Number(row.querySelector('.annealing-duration').value);

        if (!Number.isFinite(durationMinutes) || durationMinutes <= 0) {
            throw new Error(
                'Step ' + number +
                ': duration must be greater than zero.'
            );
        }

        const durationSeconds = durationMinutes * 60;
        totalDuration += durationSeconds;

        const step = {
            name: 'Step ' + number,
            operation_temperature: temperature,
            duration: durationSeconds
        };

        const rampRaw =
            row.querySelector('.annealing-ramp-rate').value.trim();

        if (rampRaw !== '') {
            const ramp = Number(rampRaw);

            if (!Number.isFinite(ramp) || ramp < 0) {
                throw new Error(
                    'Step ' + number +
                    ': ramp rate must be zero or greater.'
                );
            }

            const unit =
                row.querySelector('.annealing-ramp-unit').value;

            // NOMAD storage unit: K/s.
            // A temperature difference of 1 °C equals 1 K.
            step.ramp_rate =
                unit === 'c_per_min'
                    ? ramp / 60
                    : ramp;
        }

        const comment =
            row.querySelector('.annealing-comment').value.trim();

        if (comment) step.comment = comment;

        return step;
    });

    data.duration = totalDuration;

    // Remove obsolete fields if an older template contained them.
    data.steps.forEach(function(step) {
        delete step.starting_temperature;
        delete step.ending_temperature;
    });
}

function readBackSideCoatingFields(data) {
    const material =
        document.getElementById('backCoatingMaterial').value;

    const thicknessUm =
        Number(
            document.getElementById(
                'backCoatingThickness'
            ).value
        );

    if (!['Ti', 'SrRuO3'].includes(material)) {
        throw new Error(
            'Coating material must be Ti or SrRuO3.'
        );
    }

    if (
        !Number.isFinite(thicknessUm) ||
        thicknessUm <= 0
    ) {
        throw new Error(
            'Thickness must be greater than zero.'
        );
    }

    data.coating_material = material;

    // NOMAD storage unit: meter
    data.thickness = thicknessUm / 1e6;

    // Preserve compatibility with the existing
    // BackSideCoatingPDI reagent subsection.
    data.coating_reagents = {
        name: material
    };

    data.name =
        material + ' ' +
        formatNumber(thicknessUm) +
        ' µm back-side coating';

    // These inherited fields are not part of
    // the PDI back-side coating recipe.
    delete data.temperature;
    delete data.duration;
}


function editorArchiveData() {
    const existing = editorItem && editorMode === 'edit'
        ? JSON.parse(JSON.stringify(editorItem.data || {}))
        : {};
    const data = existing;
    data.m_def = currentSchema();
    data.lab_id = generatedId();
    data.name = data.lab_id;

    if (editorMode !== 'edit') {
        assertUniqueGeneratedId(data.lab_id);
    } else if (editorItem && itemUsage(editorItem).locked) {
        throw new Error(
            'This item became referenced after the editor was opened. ' +
            'Editing is blocked; use Duplicate instead.'
        );
    }

    if (currentType === 'processing_recipe') {
        if (editorMode !== 'edit') {
            const template = document.getElementById('processingTemplate').value;
            if (template !== '') {
                Object.assign(data, JSON.parse(JSON.stringify((allProcessingCatalogs[currentSubtype][Number(template)] || {}).data || {})));
                data.m_def = currentSchema();
                data.lab_id = generatedId();
                data.name = data.lab_id;
            }
        }
        if (currentSubtype === 'cleaning') {
            readCleaningFields(data);
        } else if (currentSubtype === 'annealing') {
            readAnnealingFields(data);
        } else if (currentSubtype === 'back_side_coating') {
            readBackSideCoatingFields(data);
        } else {
            readDynamicFields(data);
        }
    }

    if (currentType === 'sample_cut_recipe') {
        const parent = selectedSquareSize('cutParentSize','cutParentCustom');
        const child = selectedSquareSize('cutChildSize','cutChildCustom');
        const count = Number(document.getElementById('cutChildCount').value);
        if (!Number.isInteger(count) || count < 1) throw new Error('Children per parent must be a positive integer.');
        data.input_geometry = {width:parent/1000, length:parent/1000};
        data.number_of_samples = count;
        data.children_geometry = {width:child/1000, length:child/1000};
    }

    if (currentType === 'holder') {
        const rows =
            Array.from(
                document.querySelectorAll(
                    '.holder-position-row'
                )
            );

        if (!rows.length) {
            throw new Error(
                'A holder needs at least one position.'
            );
        }

        const names =
            new Set();

        data.positions =
            rows.map(
                function(row) {
                    const name =
                        row
                            .querySelector(
                                '.position-name'
                            )
                            .value
                            .trim()
                            .toUpperCase();

                    if (
                        !/^[A-Z][A-Z0-9]*$/.test(
                            name
                        )
                    ) {
                        throw new Error(
                            'Holder position names must use uppercase letters/numbers.'
                        );
                    }

                    if (
                        names.has(name)
                    ) {
                        throw new Error(
                            'Holder position names must be unique.'
                        );
                    }

                    names.add(name);

                    const size =
                        Number(
                            row
                                .querySelector(
                                    '.position-size'
                                )
                                .value
                        );

                    const rho =
                        Number(
                            row
                                .querySelector(
                                    '.position-rho'
                                )
                                .value
                        );

                    const theta =
                        Number(
                            row
                                .querySelector(
                                    '.position-theta'
                                )
                                .value
                        );

                    if (
                        !Number.isFinite(size) ||
                        size <= 0
                    ) {
                        throw new Error(
                            'Position ' +
                            name +
                            ' needs a valid size.'
                        );
                    }

                    if (
                        !Number.isFinite(rho) ||
                        rho < 0
                    ) {
                        throw new Error(
                            'Position ' +
                            name +
                            ' needs a valid Rho value.'
                        );
                    }

                    if (
                        !Number.isFinite(theta)
                    ) {
                        throw new Error(
                            'Position ' +
                            name +
                            ' needs a valid Theta value.'
                        );
                    }

                    return {
                        name:
                            name,

                        slot_geometry: {
                            width:
                                size /
                                1000,

                            length:
                                size /
                                1000
                        },

                        rho:
                            rho /
                            1000,

                        theta:
                            theta
                    };
                }
            );

        data.number_of_positions =
            data.positions.length;

                data.tags = managedHolderTags(data);
}

    if (currentType === 'insert') {
        const outer = selectedSquareSize('insertOuterSize','insertOuterCustom');
        const inner = selectedSquareSize('insertInnerSize','insertInnerCustom');
        if (inner > outer) throw new Error('Sample opening cannot be larger than the outer insert size.');
        data.outer_geometry = {width:outer/1000, length:outer/1000};
        data.inner_geometry = {width:inner/1000, length:inner/1000};
        data.tags = managedInsertTags(data);
    }

    return data;
}

async function uploadArchive(uploadId, filename, data, overwrite) {
    const params = new URLSearchParams();
    params.append('file_name', filename);
    params.append('overwrite_if_exists', overwrite ? 'true' : 'false');
    params.append('trigger_processing', 'true');
    params.append('wait_for_processing', 'true');
    params.append('include_archive', 'true');

    const response = await fetch(
        nomadApiBase() + '/uploads/' + encodeURIComponent(uploadId) + '/raw/?' + params.toString(),
        {
            method:'PUT',
            headers:{'Content-Type':'application/json','Accept':'application/json'},
            body:JSON.stringify({data:data}, null, 2)
        }
    );
    if (!response.ok) throw new Error('Archive upload failed (' + response.status + ')');
    const result = await response.json();
    const errors = (((result || {}).processing || {}).entry || {}).errors || [];
    if (errors.length) throw new Error('NOMAD processing failed: ' + errors.join('; '));
    return result;
}

async function saveEditor(event) {
    event.preventDefault();
    const button = document.getElementById('saveEditorButton');
    const status = document.getElementById('editorStatus');
    button.disabled = true;
    try {
        const data = editorArchiveData();
        let uploadId;
        let filename;
        let overwrite = false;

        if (editorMode === 'edit') {
            if (!editorItem || editorItem.published || !editorItem.uploadId || !editorItem.mainfile) {
                throw new Error('This item cannot be edited in place.');
            }

            for (const schema of definitionUsageSchemas()) {
                usageCatalogs[schema] = await queryEntriesBySchema(schema);
            }
            if (itemUsage(editorItem).locked) {
                throw new Error(
                    'This item is now referenced by NOMAD and is locked. ' +
                    'No changes were written.'
                );
            }

            uploadId = editorItem.uploadId;
            filename = editorItem.mainfile;
            overwrite = true;
            status.textContent = 'Saving changes...';
        } else {
            const latestItems = await queryEntriesBySchema(currentSchema());
            if (currentType === 'processing_recipe') {
                allProcessingCatalogs[currentSubtype] = latestItems;
            } else {
                currentItems = latestItems;
            }
            assertUniqueGeneratedId(data.lab_id);

            uploadId = document.getElementById('targetUpload').value;
            if (!uploadId) throw new Error('Select a target upload first.');
            filename = safeFilenamePart(data.lab_id) + '_' + timestampPart() + '.archive.yaml';
            status.textContent = 'Creating new ' + entityNoun() + '...';
        }

        await uploadArchive(uploadId, filename, data, overwrite);
        status.textContent = 'Saved successfully.';

        if (currentType === 'processing_recipe') {
            allProcessingCatalogs[currentSubtype] = await queryEntriesBySchema(currentSchema());
        }
        await loadCurrentType();
        closeModal();
    } catch (error) {
        status.textContent = 'Error: ' + error.message;
    } finally {
        button.disabled = false;
    }
}

async function loadUploads() {
    const select = document.getElementById('targetUpload');
    const status = document.getElementById('uploadStatus');
    select.innerHTML = '<option value="">Loading uploads...</option>';
    try {
        const params = new URLSearchParams();
        params.append('roles','main_author');
        params.append('roles','coauthor');
        params.append('page_size','100');
        const response = await fetch(nomadApiBase() + '/uploads?' + params.toString());
        if (!response.ok) throw new Error('Upload request failed: ' + response.status);
        const result = await response.json();
        const uploads = (result.data || []).filter(function(upload) {
            return !upload.published && !upload.is_processing;
        });
        select.innerHTML = '<option value="">Select target upload...</option>';
        uploads.forEach(function(upload) {
            const option = document.createElement('option');
            option.value = upload.upload_id;
            option.textContent = (upload.upload_name || 'Unnamed upload') + ' — ' + upload.upload_id;
            select.appendChild(option);
        });
        status.textContent = uploads.length + ' writable unpublished upload(s) available.';
    } catch (error) {
        select.innerHTML = '<option value="">Could not load uploads</option>';
        status.textContent = 'Error: ' + error.message;
    }
}

function populateStaticControls() {
    ['cutParentSize','cutChildSize','holderSize','insertOuterSize','insertInnerSize'].forEach(function(id) {
        fillSizeSelect(id, true);
    });

    const childCount = document.getElementById('cutChildCount');
    [1,2,4,6,8,9,16].forEach(function(count) {
        const option = document.createElement('option');
        option.value = String(count);
        option.textContent = String(count);
        childCount.appendChild(option);
    });

    attachSizeToggle('cutParentSize','cutParentCustomWrap');
    attachSizeToggle('cutChildSize','cutChildCustomWrap');
    attachSizeToggle('holderSize','holderCustomSizeWrap');
    attachSizeToggle('insertOuterSize','insertOuterCustomWrap');
    attachSizeToggle('insertInnerSize','insertInnerCustomWrap');

    ['holderMaterial','holderNumber','cutChildCount','insertNumber','insertFamily'].forEach(function(id) {
        document.getElementById(id).addEventListener('input', function() {
            if (id === 'insertFamily') {
                document.getElementById('insertFamilyCustomWrap').classList.toggle(
                    'hidden',
                    document.getElementById('insertFamily').value !== 'CUSTOM'
                );
            }
            updateGeneratedId();
        });
    });

    ['holderCustomSize','cutParentCustom','cutChildCustom','insertOuterCustom','insertInnerCustom','insertFamilyCustom'].forEach(function(id) {
        document.getElementById(id).addEventListener('input', updateGeneratedId);
    });
}

async function initialise() {
    populateStaticControls();

    document.getElementById('librarySearch').addEventListener('input', renderLibrary);
    document.getElementById('closeModalButton').addEventListener('click', closeModal);
    document.getElementById('cancelEditorButton').addEventListener('click', closeModal);
    document.getElementById('editorForm').addEventListener('submit', saveEditor);
    document.getElementById('addHolderPositionButton').addEventListener('click', function() {
        addHolderPosition({name:''});
    });
    document.getElementById('modalBackdrop').addEventListener('click', function(event) {
        if (event.target === event.currentTarget) closeModal();
    });

    try {
        await loadLibraryTypes();
        await Promise.all([
            preloadProcessingCatalogs(),
            preloadUsageCatalogs()
        ]);
        renderTypeTabs();
        renderSubtypeTabs();
        await Promise.all([loadCurrentType(), loadUploads()]);
    } catch (error) {
        document.getElementById('libraryStatus').textContent = 'Error: ' + error.message;
    }
}

document.addEventListener('DOMContentLoaded', initialise);
