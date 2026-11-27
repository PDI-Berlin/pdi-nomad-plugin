/* Write original, unchanged PDI EntryData archives through the NOMAD v1 API.
 * Requires an authenticated, unpublished writable upload. No custom metainfo.
 * No normalizer replacement. Save sequence: loadout -> experiment -> extras.
 */
(function (root, factory) {
    const api = factory();
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    if (root) root.NomadMbeWriter = api;
})(typeof window !== 'undefined' ? window : null, function () {
    'use strict';
    const FILLED = 'pdi_nomad_plugin.mbe.instrument.FilledSubstrateHolderPDI';
    const EXP = 'pdi_nomad_plugin.mbe.processes.ExperimentMbePDI';
    const FILM = 'pdi_nomad_plugin.mbe.materials.ThinFilmMbe';
    const STACK = 'pdi_nomad_plugin.mbe.materials.ThinFilmStackMbePDI';
    const FILM_REF = 'nomad_material_processing.general.ThinFilmReference';
    function ref(uploadId, entryId) {
        return '../uploads/' + uploadId + '/archive/' + entryId + '#data';
    }
    function refIdentity(link) {
        if (link && typeof link === 'object') link = link.reference;
        if (typeof link !== 'string') return null;
        const match = /(?:^|\/)uploads\/([^/]+)\/archive\/([^/#]+)#\/?data$/.exec(link);
        return match ? {uploadId: match[1], entryId: match[2]} : null;
    }
    function archiveFromResponse(result) {
        return (result && result.data && result.data.archive) || (result && result.archive) || null;
    }
    function archiveType(archive) { return archive && archive.data && archive.data.m_def; }
    async function responseError(response, prefix) {
        const text = typeof response.text === 'function' ? (await response.text()).slice(0, 350) : '';
        throw new Error(prefix + ': HTTP ' + response.status + (text ? ': ' + text : ''));
    }
    function createClient(options) {
        const fetcher = options.fetch;
        const apiBase = options.apiBase.replace(/\/$/, '');
        const entryIdForFile = options.entryIdForFile;
        const wait = options.wait || (milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds)));
        async function getArchive(entryId, allowMissing) {
            const response = await fetcher(apiBase + '/entries/' + encodeURIComponent(entryId) + '/archive');
            if (allowMissing && response.status === 404) return null;
            if (!response.ok) await responseError(response, 'Archive read failed');
            const archive = archiveFromResponse(await response.json());
            if (!archive || !archive.data) throw new Error('NOMAD archive has no data section: ' + entryId);
            return archive;
        }
        async function waitForArchive(entryId, expectedDef) {
            for (let attempt = 0; attempt < 25; attempt++) {
                const archive = await getArchive(entryId, true);
                if (archive) {
                    if (archiveType(archive) !== expectedDef) {
                        throw new Error('Unexpected schema for ' + entryId + ': ' + archiveType(archive));
                    }
                    return archive;
                }
                await wait(1000);
            }
            throw new Error('NOMAD has not processed ' + entryId + '. Check the upload processing log; do not create a second entry.');
        }
        async function writeNewArchive(uploadId, filename, data) {
            if (!/^[-\w.]+\.archive\.json$/.test(filename)) throw new Error('Invalid archive filename');
            const entryId = await entryIdForFile(uploadId, filename);
            const existing = await getArchive(entryId, true);
            if (existing) {
                throw new Error('Entry already exists: ' + filename + '. It will NOT be overwritten.');
            }
            const form = new FormData();
            form.append('file', new Blob([JSON.stringify({data}, null, 2)], {type: 'application/json'}), filename);
            const path = apiBase + '/uploads/' + encodeURIComponent(uploadId) +
                '/raw/?overwrite_if_exists=false&wait_for_processing=true';
            const response = await fetcher(path, {method: 'PUT', body: form});
            if (!response.ok) await responseError(response, 'NOMAD upload failed for ' + filename);
            await waitForArchive(entryId, data.m_def);
            return {uploadId, entryId, filename, reference: ref(uploadId, entryId)};
        }
        async function editStack(entryId, additions) {
            const old = await getArchive(entryId);
            if (archiveType(old) !== STACK) throw new Error('Target is not a ThinFilmStackMbePDI');
            const layers = old.data.layers || [];
            if (!Array.isArray(layers)) throw new Error('Stack layers is not a list');
            const existingKeys = new Set(layers.map(x => refIdentity(x)).filter(Boolean).map(x => x.uploadId + ':' + x.entryId));
            const existingNames = new Map(layers.filter(x => x && x.name).map(x => [x.name, x]));
            const pending = [];
            for (const addition of additions) {
                const key = addition.uploadId + ':' + addition.entryId;
                const sameName = existingNames.get(addition.name);
                if (sameName && sameName.reference !== addition.reference) {
                    throw new Error('Layer name already exists with another reference: ' + addition.name);
                }
                if (!existingKeys.has(key)) {
                    pending.push({name: addition.name, lab_id: addition.name, reference: addition.reference});
                    existingKeys.add(key);
                }
            }
            if (!pending.length) return layers.length;
            // API's archive edit endpoint has no concurrency guard. Refuse a stale snapshot.
            const latest = await getArchive(entryId);
            const current = latest.data.layers || [];
            if (JSON.stringify(current) !== JSON.stringify(layers)) {
                throw new Error('Stack changed during editing. Refresh and retry.');
            }
            const changes = pending.map((item, index) => ({
                path: 'data/layers/' + (layers.length + index), action: 'upsert', new_value: item
            }));
            const response = await fetcher(apiBase + '/entries/' + encodeURIComponent(entryId) + '/edit', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({changes})
            });
            if (!response.ok) await responseError(response, 'Stack edit failed');
            for (let attempt = 0; attempt < 25; attempt++) {
                const after = await waitForArchive(entryId, STACK);
                const written = new Set((after.data.layers || []).map(x => refIdentity(x)).filter(Boolean).map(x => x.uploadId + ':' + x.entryId));
                if (additions.every(item => written.has(item.uploadId + ':' + item.entryId))) {
                    return (after.data.layers || []).length;
                }
                await wait(1000);
            }
            throw new Error('Layer references could not be verified after stack edit');
        }
        async function createFilled(uploadId, filename, filled) {
            if (filled.m_def !== FILLED || !Array.isArray(filled.positions)) throw new Error('Invalid original PDI filled holder');
            if (!filled.positions.some(p => p.substrate && p.substrate.reference)) {
                throw new Error('No occupied substrate position selected');
            }
            return writeNewArchive(uploadId, filename, filled);
        }
        async function createExperiment(uploadId, filename, experiment, filledReference) {
            if (experiment.m_def !== EXP || experiment.samples !== undefined) throw new Error('Invalid experiment or prepopulated samples');
            const data = Object.assign({}, experiment, {
                datetime: new Date().toISOString(),
                substrate_holder: {reference: filledReference}
            });
            return writeNewArchive(uploadId, filename, data);
        }

        async function fillFilm(entryId, expected, model) {
            const before = await waitForArchive(entryId,FILM);
            if (before.data.lab_id !== expected.lab_id) {
                throw new Error('Layer identity mismatch.');
            }

            const edits = [];
            for (const k of ['geometry','components','description']) {
                if (
                    expected[k] === undefined ||
                    model.includesFields(before.data[k],expected[k])
                ) continue;

                const old = before.data[k];
                if (
                    old !== undefined && old !== null && old !== '' &&
                    !(Array.isArray(old) && !old.length)
                ) {
                    throw new Error(
                        'Existing '+k+' differs in '+expected.lab_id+
                        '; manual review required.'
                    );
                }

                edits.push({
                    path:'data/'+k,
                    action:'upsert',
                    new_value:expected[k]
                });
            }

            if (edits.length) {
                const fresh = await getArchive(entryId);
                for (const edit of edits) {
                    const k = edit.path.slice(5);
                    if (
                        JSON.stringify(fresh.data[k]) !==
                        JSON.stringify(before.data[k])
                    ) {
                        throw new Error(
                            'Layer changed concurrently: '+expected.lab_id
                        );
                    }
                }

                const response = await fetcher(
                    apiBase+'/entries/'+encodeURIComponent(entryId)+'/edit',
                    {
                        method:'POST',
                        headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({changes:edits})
                    }
                );
                if (!response.ok) {
                    await responseError(
                        response,'Thin-film edit failed'
                    );
                }
            }

            for (let i=0;i<20;i++) {
                const after = await getArchive(entryId);
                if (
                    ['geometry','components','description'].every(
                        k=>expected[k]===undefined ||
                            model.includesFields(after.data[k],expected[k])
                    )
                ) return;
                await wait(500);
            }
            throw new Error(
                'Layer fields not persisted: '+expected.lab_id
            );
        }


        // Film-only chemistry for the stack.
        // Substrate and layer references remain unchanged.
        async function syncStackFilmElements(entryId) {
            const stack = await waitForArchive(entryId, STACK);
            const layers = stack.data.layers || [];

            if (!layers.length) {
                throw new Error(
                    'Cannot derive stack elements: no layers.'
                );
            }

            const elements = [];

            for (const layer of layers) {
                const identity = refIdentity(layer);

                if (!identity) {
                    throw new Error(
                        'Invalid layer reference: ' +
                        (layer.name || entryId)
                    );
                }

                let layerElements = [];

                for (let attempt = 0; attempt < 30; attempt++) {
                    const film = await waitForArchive(
                        identity.entryId, FILM
                    );

                    layerElements = (
                        film.data.elemental_composition || []
                    ).map(item => item && item.element)
                     .filter(Boolean);

                    if (layerElements.length) break;
                    await wait(500);
                }

                if (!layerElements.length) {
                    throw new Error(
                        'Layer composition not normalized: ' +
                        (layer.name || identity.entryId)
                    );
                }

                for (const element of layerElements) {
                    if (!elements.includes(element)) {
                        elements.push(element);
                    }
                }
            }

            const sameElements = (actual, expected) =>
                Array.isArray(actual) &&
                actual.length === expected.length &&
                new Set(actual).size === expected.length &&
                actual.every(e => expected.includes(e));

            const sourceElements = archive =>
                (archive.data.elemental_composition || [])
                    .map(item => item && item.element)
                    .filter(Boolean);

            const resultElements = archive =>
                archive.results &&
                archive.results.material &&
                archive.results.material.elements;

            const expected = elements.map(element => ({
                element
            }));

            if (!sameElements(sourceElements(stack), elements)) {
                // Refuse to overwrite a concurrently edited archive.
                const fresh = await getArchive(entryId);

                if (
                    JSON.stringify(
                        fresh.data.elemental_composition || []
                    ) !==
                    JSON.stringify(
                        stack.data.elemental_composition || []
                    )
                ) {
                    throw new Error(
                        'Stack composition changed concurrently.'
                    );
                }

                const response = await fetcher(
                    apiBase +
                    '/entries/' +
                    encodeURIComponent(entryId) +
                    '/edit',
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            changes: [{
                                path: 'data/elemental_composition',
                                action: 'upsert',
                                new_value: expected
                            }]
                        })
                    }
                );

                if (!response.ok) {
                    await responseError(
                        response,
                        'Stack film-only composition update failed'
                    );
                }
            }

            // Verify both stored data and normalized search results.
            for (let attempt = 0; attempt < 30; attempt++) {
                const checked = await getArchive(entryId);

                if (
                    sameElements(
                        sourceElements(checked), elements
                    ) &&
                    sameElements(
                        resultElements(checked), elements
                    )
                ) {
                    return elements;
                }

                await wait(500);
            }

            throw new Error(
                'Film-only stack elements not verified: ' +
                entryId
            );
        }

        async function addExtraLayers(uploadId, experimentEntryId, plans) {
            if (!plans || !plans.length) throw new Error('Layer plan missing');
            const model = typeof window !== 'undefined' ? window.NomadMbeDrafts : require('./mbe_drafts.js');
            const experiment = await waitForArchive(experimentEntryId, EXP);
            const samples = experiment.data.samples || [];
            if (!samples.length) throw new Error('Normalizer has not created experiment samples; retry after processing.');
            const stacks = new Map();
            for (const sample of samples) {
                const identity = refIdentity(sample);
                if (!identity) throw new Error('Experiment sample has an invalid stack reference');
                const stack = await waitForArchive(identity.entryId, STACK);
                stacks.set(stack.data.lab_id || stack.data.name, {identity, stack});
            }
            const results = [];
            for (const plan of plans) {
                const found = stacks.get(plan.stack_id);
                if (!found) throw new Error('Missing normalized stack: ' + plan.stack_id);
                const initial = found.stack.data.layers || [];
                const mandatory = initial.find(x => x.name === plan.mandatory_layer_1);
                if (!mandatory || !refIdentity(mandatory)) {
                    throw new Error('Original normalizer Layer 1 not found: ' + plan.mandatory_layer_1);
                }
                if (found.identity.uploadId !== uploadId) {
                    throw new Error('Expected stack is in a different upload: ' + plan.stack_id);
                }
                const substrateRef=refIdentity(found.stack.data.substrate);
                if (!substrateRef) {
                    throw new Error(
                        'Stack substrate reference missing: '+plan.stack_id
                    );
                }
                const substrate=await getArchive(substrateRef.entryId);
                if (!substrate.data.geometry) {
                    throw new Error(
                        'Substrate has no geometry: '+plan.stack_id
                    );
                }

                const firstRef=refIdentity(mandatory);
                const first=model.filmData(
                    {
                        m_def:FILM,
                        name:plan.mandatory_layer_1,
                        lab_id:plan.mandatory_layer_1
                    },
                    substrate.data.geometry,
                    plan.mandatory_layer_1_properties
                );
                await fillFilm(firstRef.entryId,first,model);

                const additions = [];
                for (const extra of plan.extra_layer_archives) {
                    const name = extra.thin_film.lab_id;
                    const filename = extra.filename.replace(/\.archive\.yaml$/, '.archive.json');
                    const film=model.filmData(extra.thin_film,substrate.data.geometry,extra.nominal_properties_local_only);
                    const entryId = await entryIdForFile(uploadId, filename);
                    const existing = await getArchive(entryId, true);
                    if (existing) {
                        if (archiveType(existing) !== FILM || existing.data.lab_id !== name) {
                            throw new Error('Existing archive conflicts with planned layer: ' + name);
                        }
                    } else {
                        await writeNewArchive(uploadId, filename, film);
                    }
                    await fillFilm(entryId,film,model);
                    additions.push({name, uploadId, entryId, reference: ref(uploadId, entryId)});
                }
                if (additions.length) await editStack(found.identity.entryId, additions);
                await syncStackFilmElements(found.identity.entryId);
                results.push({stack: plan.stack_id, extraLayers: additions.length});
            }
            return results;
        }
        return {getArchive, writeNewArchive, createFilled, createExperiment, addExtraLayers, editStack};
    }
    return {createClient, ref, refIdentity};
});
