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
        async function addExtraLayers(uploadId, experimentEntryId, plans) {
            if (!plans || !plans.length) throw new Error('Layer plan missing');
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
                const additions = [];
                for (const extra of plan.extra_layer_archives) {
                    const name = extra.thin_film.lab_id;
                    const filename = extra.filename.replace(/\.archive\.yaml$/, '.archive.json');
                    const entryId = await entryIdForFile(uploadId, filename);
                    const existing = await getArchive(entryId, true);
                    if (existing) {
                        if (archiveType(existing) !== FILM || existing.data.lab_id !== name) {
                            throw new Error('Existing archive conflicts with planned layer: ' + name);
                        }
                    } else {
                        await writeNewArchive(uploadId, filename, extra.thin_film);
                    }
                    additions.push({name, uploadId, entryId, reference: ref(uploadId, entryId)});
                }
                if (additions.length) await editStack(found.identity.entryId, additions);
                results.push({stack: plan.stack_id, extraLayers: additions.length});
            }
            return results;
        }
        return {getArchive, writeNewArchive, createFilled, createExperiment, addExtraLayers, editStack};
    }
    return {createClient, ref, refIdentity};
});
