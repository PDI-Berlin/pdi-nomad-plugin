/* Guard existing NOMAD uploads against duplicate substrate batches.
 * No writes, no custom schema, no custom normalizer. Run before PUT.
 * The original SubstrateBatchMbe normalizer writes child archives with
 * overwrite=True, so both batch and child lab IDs must be checked.
 */
(function () {
    'use strict';

    const PAGE_SIZE = 100;
    const MAX_PAGES = 100; // Fail closed rather than silently skip >10k entries.

    async function readJson(url, fetchImpl) {
        const response = await fetchImpl(url, {cache: 'no-store'});
        if (!response || !response.ok) {
            throw new Error('Cannot verify existing NOMAD entries/files (HTTP ' +
                (response ? response.status : 'unknown') + '). No files were sent.');
        }
        return response.json();
    }

    async function allPages(url, selector, fetchImpl) {
        const values = [];
        for (let page = 1; page <= MAX_PAGES; page++) {
            const query = new URLSearchParams({
                page_size: String(PAGE_SIZE), page: String(page)
            });
            const response = await readJson(url + '?' + query.toString(), fetchImpl);
            const items = selector(response);
            if (!Array.isArray(items)) {
                throw new Error('Cannot verify complete NOMAD listing. No files were sent.');
            }
            values.push(...items);
            const total = response.pagination && response.pagination.total;
            if (typeof total === 'number') {
                if (!Number.isSafeInteger(total) || total < 0 || values.length > total) {
                    throw new Error('Inconsistent NOMAD listing total. No files were sent.');
                }
                if (values.length === total) return values;
                if (items.length === 0) {
                    throw new Error('Incomplete NOMAD listing. No files were sent.');
                }
            } else if (items.length < PAGE_SIZE) {
                return values;
            }
        }
        throw new Error('Upload contains too many entries to verify safely. No files were sent.');
    }

    function basename(value) {
        return String(value || '').replace(/\\/g, '/').split('/').pop();
    }

    function archiveLabId(filename, marker) {
        const name = basename(filename);
        const token = '.' + marker + '.archive.';
        const at = name.lastIndexOf(token);
        return at < 0 ? null : name.slice(0, at);
    }

    function rawFileName(item) {
        if (typeof item === 'string') return basename(item);
        if (!item || typeof item !== 'object') {
            throw new Error('Unrecognized NOMAD file record. No files were sent.');
        }
        const path = item.path || item.name || item.file_name;
        if (typeof path !== 'string' || !path) {
            throw new Error('NOMAD file name missing. No files were sent.');
        }
        return basename(path);
    }

    function assertNoMatches(entries, files, batchId, batchFile, children) {
        const childIds = new Set(children.map(function (item) { return item.lab_id; }));
        const expectedFiles = new Set([
            batchFile, ...children.map(function (item) { return item.filename; })
        ]);

        for (const entry of entries) {
            if (!entry || typeof entry !== 'object') {
                throw new Error('Unrecognized NOMAD entry metadata. No files were sent.');
            }
            const entryName = entry.entry_name || entry.lab_id || '';
            const fileName = basename(entry.mainfile);
            const isBatch = archiveLabId(fileName, 'SubstrateBatch') === batchId;
            const isChild = childIds.has(archiveLabId(fileName, 'Substrate'));
            if (entryName === batchId || childIds.has(entryName) ||
                isBatch || isChild || expectedFiles.has(fileName)) {
                throw new Error('Batch ' + batchId +
                    ' already exists or its generated substrate IDs are occupied ' +
                    'in this upload. No files were sent.');
            }
        }
        for (const item of files) {
            const fileName = rawFileName(item);
            const existingBatchId = archiveLabId(fileName, 'SubstrateBatch');
            const existingChildId = archiveLabId(fileName, 'Substrate');
            if (expectedFiles.has(fileName) || existingBatchId === batchId ||
                childIds.has(existingChildId)) {
                throw new Error('Batch ' + batchId +
                    ' already exists or its generated substrate files are occupied ' +
                    'in this upload. No files were sent.');
            }
        }
    }

    async function assertNoCollision(options) {
        const batchId = options.batchLabId;
        const children = options.expectedChildren;
        if (typeof batchId !== 'string' || !batchId ||
            typeof options.batchFilename !== 'string' ||
            !Array.isArray(children) || children.length < 1 ||
            new Set(children.map(function(x) { return x.lab_id; })).size !== children.length ||
            children.some(function (x) {
                return !x || typeof x.lab_id !== 'string' ||
                    typeof x.filename !== 'string' ||
                    x.lab_id !== batchId + '_' + String(children.indexOf(x) + 1);
            })) {
            throw new Error('Invalid generated batch/child IDs. No files were sent.');
        }
        const base = options.apiBase.replace(/\/$/, '') + '/uploads/' +
            encodeURIComponent(options.uploadId);
        const fetchImpl = options.fetchImpl || window.fetch.bind(window);
        const entries = await allPages(base + '/entries', function (body) {
            return body.data;
        }, fetchImpl);
        const files = await allPages(base + '/rawdir/', function (body) {
            return body.directory_metadata && body.directory_metadata.content;
        }, fetchImpl);
        assertNoMatches(entries, files, batchId, options.batchFilename, children);
        return {checkedEntries: entries.length, checkedFiles: files.length};
    }

    window.pdiIntakeDuplicateGuard = {assertNoCollision: assertNoCollision};
}());
