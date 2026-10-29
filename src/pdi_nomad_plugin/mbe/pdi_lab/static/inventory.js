'use strict';

const API = String(window.NOMAD_API_BASE || '/api/v1').replace(/\/$/, '');
const SUBSTRATE = 'pdi_nomad_plugin.mbe.materials.SubstrateMbe';
const CUT = 'pdi_nomad_plugin.general.schema.SampleCutPDI';

const OPERATIONS = {
    annealed: [
        'pdi_nomad_plugin.general.schema.AnnealingPDI',
        'nomad_material_processing.general.Annealing'
    ],
    cleaned: [
        'pdi_nomad_plugin.general.schema.CleaningPDI',
        'nomad_material_processing.general.Cleaning'
    ],
    etched: [
        'pdi_nomad_plugin.general.schema.EtchingPDI',
        'nomad_material_processing.general.Etching'
    ],
    backcoated: [
        'pdi_nomad_plugin.general.schema.BackSideCoatingPDI'
    ]
};

const el = id => document.getElementById(id);
const show = (id, value) => el(id).textContent = String(value);

const safe = value => String(value ?? '').replace(
    /[&<>"']/g,
    c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])
);

function refId(ref) {
    const value = typeof ref === 'object' ? ref?.reference : ref;
    return String(value || '').match(/\/archive\/([^/#?]+)/)?.[1] || '';
}

function entryUrl(id) {
    return API.replace(/\/api\/v1$/, '') +
        '/gui/entry/' + encodeURIComponent(id);
}

async function post(path, body) {
    const response = await fetch(API + path, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)
    });
    if (!response.ok) throw new Error(path + ': HTTP ' + response.status);
    return response.json();
}

async function archives(schema) {
    const records = [];
    const seen = new Set();
    let cursor = null;

    for (let page = 0; page < 200; page++) {
        const pagination = {page_size: 100};
        if (cursor) pagination.page_after_value = cursor;

        const result = await post('/entries/archive/query', {
            owner: 'visible',
            query: {'section_defs.definition_qualified_name': schema},
            pagination,
            required: {metadata: {entry_name: '*'}, data: '*'}
        });

        for (const item of result.data || []) {
            const archive = item.archive || {};
            const metadata = archive.metadata || {};
            const id = item.entry_id || metadata.entry_id;
            if (!id || seen.has(id)) continue;
            seen.add(id);
            records.push({
                id,
                data: archive.data || {},
                metadata
            });
        }

        const next = result.pagination?.next_page_after_value;
        if (!next) return records;
        if (next === cursor) throw new Error('Pagination stalled: ' + schema);
        cursor = next;
    }
    throw new Error('Pagination incomplete: ' + schema);
}

async function allEntries() {
    const records = [];
    const seen = new Set();
    let cursor = null;

    for (let page = 0; page < 200; page++) {
        const pagination = {page_size: 200};
        if (cursor) pagination.page_after_value = cursor;

        const result = await post('/entries/query', {
            owner: 'visible',
            pagination
        });

        for (const item of result.data || []) {
            if (item.entry_id && !seen.has(item.entry_id)) {
                records.push(item);
                seen.add(item.entry_id);
            }
        }

        const next = result.pagination?.next_page_after_value;
        if (!next) return records;
        if (next === cursor) throw new Error('Entry pagination stalled');
        cursor = next;
    }
    throw new Error('Entry pagination incomplete');
}

function materialOf(data) {
    const formula = data.components
        ?.map(c => c?.pure_substance?.molecular_formula)
        .find(Boolean);

    const name = String(formula || data.material ||
        data.chemical_formula || '').trim();

    return {
        STO: 'SrTiO3',
        SrTiO3: 'SrTiO3',
        MgO: 'MgO',
        YSZ: 'YSZ',
        GdScO3: 'GdScO3'
    }[name] || name || 'Unspecified material';
}

function millimeters(value) {
    const number = Number(
        value !== null && typeof value === 'object'
            ? value.magnitude : value
    );
    return Number.isFinite(number) && number > 0
        ? number * 1000 : NaN;
}

function sizeOf(geometry) {
    const width = millimeters(geometry?.width);
    const length = millimeters(geometry?.length ?? geometry?.width);
    if (!Number.isFinite(width) || !Number.isFinite(length)) return 'Other';
    if (Math.abs(width - 10) < 0.1 && Math.abs(length - 10) < 0.1) return '10×10';
    if (Math.abs(width - 5) < 0.1 && Math.abs(length - 5) < 0.1) return '5×5';
    return 'Other';
}

function ancestorsOf(id, parents) {
    const ids = new Set([id]);
    let current = id;
    while (parents.has(current) && !ids.has(parents.get(current))) {
        current = parents.get(current);
        ids.add(current);
    }
    return ids;
}

function renderMaterial(name, samples) {
    const keys = ['processed','annealed','cleaned','etched','backcoated'];
    const counts = {total:samples.length,size10:0,size5:0};

    for (const key of keys) counts[key] = 0;
    for (const sample of samples) {
        for (const key of keys) if (sample[key]) counts[key]++;
        if (sample.size === '10×10') counts.size10++;
        if (sample.size === '5×5') counts.size5++;
    }

    const metrics = [
        ['Total',counts.total],
        ['Processed',counts.processed],
        ['10×10',counts.size10],
        ['5×5',counts.size5],
        ['Annealed',counts.annealed],
        ['Backcoated',counts.backcoated],
        ['Cleaned',counts.cleaned],
        ['Etched',counts.etched]
    ];

    const card = document.createElement('div');
    card.className = 'material';
    card.innerHTML = `
        <div class="matheader">
            <strong>${safe(name)}</strong>
            <span>${counts.total} available</span>
        </div>
        <div class="matcounts">
            ${metrics.map(([label,n]) =>
                `<div class="metric"><b>${n}</b><span>${label}</span></div>`
            ).join('')}
        </div>
        <details>
            <summary>Show substrate names ▾</summary>
            <div class="list">
                ${samples.sort((a,b) =>
                    a.name.localeCompare(b.name,undefined,{numeric:true})
                ).map(s => `
                    <a href="${entryUrl(s.id)}" target="_blank" rel="noopener">
                        ${safe(s.name)} · ${s.size}
                        ${s.processed ? ' · processed' : ''}
                    </a>
                `).join('')}
            </div>
        </details>`;
    return card;
}

let recent = [];

function renderRecent() {
    const type = el('entryType').value;
    const query = el('entrySearch').value.trim().toLowerCase();
    const rows = recent.filter(r =>
        (!type || r.type === type) &&
        (!query || [r.name,r.type,r.upload]
            .join(' ').toLowerCase().includes(query))
    );

    show('recentCount', rows.length + ' entries · newest first');
    const body = el('recentRows');
    body.replaceChildren();

    for (const r of rows) {
        const tr = document.createElement('tr');
        const date = document.createElement('td');
        date.textContent = r.date
            ? new Date(r.date).toLocaleString('de-DE') : '—';

        const name = document.createElement('td');
        const link = document.createElement('a');
        link.textContent = r.name;
        link.href = entryUrl(r.id);
        link.target = '_blank';
        link.rel = 'noopener';
        name.appendChild(link);

        const typeCell = document.createElement('td');
        typeCell.textContent = r.type;
        const upload = document.createElement('td');
        upload.textContent = r.upload;
        tr.append(date,name,typeCell,upload);
        body.appendChild(tr);
    }

    if (!rows.length) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 4;
        td.textContent = 'No matching entries.';
        tr.appendChild(td);
        body.appendChild(tr);
    }
}

async function refresh() {
    el('refresh').disabled = true;
    show('error','');
    show('status','Reading NOMAD inventory…');

    try {
        const schemas = [
            ...new Set([SUBSTRATE,CUT,...Object.values(OPERATIONS).flat()])
        ];
        const results = await Promise.all([
            ...schemas.map(archives),
            allEntries()
        ]);
        const catalog = new Map(
            schemas.map((schema,index) => [schema,results[index]])
        );

        const parents = new Map();
        const cutParents = new Set();

        for (const sub of catalog.get(SUBSTRATE)) {
            const parent = refId(sub.data.parent_sample);
            if (parent) {
                parents.set(sub.id,parent);
                cutParents.add(parent);
            }
        }

        for (const cut of catalog.get(CUT)) {
            const parent = refId(cut.data.parent_sample);
            if (parent) cutParents.add(parent);
            for (const child of cut.data.children_samples || []) {
                const id = refId(child);
                if (parent && id) parents.set(id,parent);
            }
        }

        const operations = {};
        for (const [key,types] of Object.entries(OPERATIONS)) {
            const ids = new Set();
            for (const schema of types) {
                for (const record of catalog.get(schema)) {
                    for (const sample of record.data.samples || []) {
                        const id = refId(sample);
                        if (id) ids.add(id);
                    }
                }
            }
            operations[key] = ids;
        }

        const samples = catalog.get(SUBSTRATE)
            .filter(sub =>
                sub.data.m_def === SUBSTRATE &&
                sub.data.grown !== true &&
                !cutParents.has(sub.id)
            ).map(sub => {
                const ancestry = ancestorsOf(sub.id,parents);
                const status = {};
                for (const [key,ids] of Object.entries(operations)) {
                    status[key] = [...ancestry].some(id => ids.has(id));
                }
                return {
                    id: sub.id,
                    name: String(sub.data.lab_id || sub.data.name ||
                        sub.metadata.entry_name || sub.id),
                    material: materialOf(sub.data),
                    size: sizeOf(sub.data.geometry),
                    ...status,
                    processed: sub.data.processed === true ||
                        Object.values(status).some(Boolean)
                };
            });

        const materials = new Map();
        for (const sample of samples) {
            if (!materials.has(sample.material)) {
                materials.set(sample.material,[]);
            }
            materials.get(sample.material).push(sample);
        }

        const box = el('materials');
        box.replaceChildren();
        for (const [name,list] of [...materials].sort(
            (a,b) => a[0].localeCompare(b[0])
        )) {
            box.appendChild(renderMaterial(name,list));
        }
        if (!materials.size) box.textContent = 'No available substrates found.';

        show('total',samples.length);
        show('processed',samples.filter(s => s.processed).length);
        show('size10',samples.filter(s => s.size === '10×10').length);
        show('size5',samples.filter(s => s.size === '5×5').length);

        recent = results[results.length-1].map(r => ({
            id: r.entry_id,
            upload: r.upload_id || '',
            name: r.entry_name || r.entry_id,
            type: r.entry_type || 'Other',
            date: r.entry_create_time || r.upload_create_time ||
                r.processed_time || ''
        })).sort((a,b) =>
            String(b.date).localeCompare(String(a.date))
        );

        const types = [...new Set(recent.map(r => r.type))].sort();
        const previous = el('entryType').value;
        el('entryType').replaceChildren(new Option('All entry types',''));
        for (const type of types) {
            el('entryType').add(new Option(type,type));
        }
        if (types.includes(previous)) el('entryType').value = previous;

        renderRecent();
        show('status',
            `${samples.length} substrates · ${materials.size} materials · ` +
            `${recent.length} NOMAD entries`
        );

    } catch (error) {
        show('error','Inventory incomplete: ' + error.message);
        show('status','NOMAD data could not be loaded reliably.');
        console.error(error);
    } finally {
        el('refresh').disabled = false;
    }
}

el('refresh').addEventListener('click',refresh);
el('entryType').addEventListener('change',renderRecent);
el('entrySearch').addEventListener('input',renderRecent);
refresh();
