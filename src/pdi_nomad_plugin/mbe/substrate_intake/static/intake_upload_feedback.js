/* Display success only after NOMAD has indexed the submitted batch and all
 * children; then navigate to the refreshed upload view. No archive writes. */
(function () {
    'use strict';

    function pause(ms) {
        return new Promise(function (resolve) {
            window.setTimeout(resolve, ms);
        });
    }

    async function getJson(url, fetchImpl) {
        const response = await fetchImpl(url, {cache: 'no-store'});
        if (!response.ok) {
            throw new Error('NOMAD readback failed (HTTP ' + response.status + ').');
        }
        return response.json();
    }

    function archiveFileName(entry) {
        return String(entry.mainfile || '').split('/').pop();
    }

    function assertNoProcessingErrors(item, description) {
        if (Array.isArray(item.errors) && item.errors.length > 0) {
            throw new Error(description + ' reports processing errors.');
        }
        if (['FAILURE', 'FAILED', 'ERROR'].includes(
            String(item.process_status || '').toUpperCase()
        )) {
            throw new Error(description + ' reports failed processing.');
        }
    }

    async function waitForEntries(options) {
        const uploadId = options.uploadId;
        const filenames = options.filenames;
        const base = options.apiBase.replace(/\/$/, '') + '/uploads/' +
            encodeURIComponent(uploadId);
        const fetchImpl = options.fetchImpl || window.fetch.bind(window);
        const sleep = options.sleep || pause;
        const attempts = options.attempts || 45;
        const waitMs = options.waitMs === undefined ? 2000 : options.waitMs;
        const statusElement = options.statusElement;

        if (!Array.isArray(filenames) || !filenames.length ||
            new Set(filenames).size !== filenames.length) {
            throw new Error('Expected upload filenames are missing or duplicated.');
        }

        for (let attempt = 1; attempt <= attempts; attempt++) {
            if (statusElement) {
                statusElement.textContent =
                    'Batch transferred. Checking NOMAD processing and ' +
                    filenames.length + ' generated entries (' + attempt +
                    '/' + attempts + ')...';
            }

            const infoBody = await getJson(base, fetchImpl);
            const info = infoBody.data || infoBody;
            if (info.upload_id !== uploadId) {
                throw new Error('NOMAD returned an unexpected upload ID.');
            }
            assertNoProcessingErrors(info, 'Upload');

            if (!info.process_running) {
                // A reused upload may already contain hundreds of entries.
                // Never limit readback to ceil(newChildren/100) pages.
                const actual = new Map();
                let received = 0;
                let finished = false;
                for (let page = 1; page <= 100; page++) {
                    const params = new URLSearchParams({
                        page_size: '100', page: String(page)
                    });
                    const body = await getJson(
                        base + '/entries?' + params.toString(), fetchImpl
                    );
                    if (!Array.isArray(body.data)) {
                        throw new Error('NOMAD returned no entry list.');
                    }
                    received += body.data.length;
                    for (const entry of body.data) {
                        const file = archiveFileName(entry);
                        if (file) actual.set(file, entry);
                    }
                    const total = body.pagination && body.pagination.total;
                    if (typeof total === 'number') {
                        if (received > total || (body.data.length === 0 && received < total)) {
                            throw new Error('Incomplete NOMAD entry listing.');
                        }
                        if (received === total) { finished = true; break; }
                    } else if (body.data.length < 100) {
                        finished = true;
                        break;
                    }
                }
                if (!finished) {
                    throw new Error('Too many NOMAD entries to verify safely.');
                }

                const complete = filenames.every(function (file) {
                    const entry = actual.get(file);
                    if (!entry || entry.process_running) return false;
                    assertNoProcessingErrors(entry, 'Entry ' + file);
                    return true;
                });

                if (complete) {
                    return {count: filenames.length, uploadId: uploadId};
                }
            }
            if (attempt < attempts) await sleep(waitMs);
        }

        throw new Error('NOMAD has not confirmed all generated entries yet. ' +
            'The batch was already submitted: do NOT upload it again. ' +
            'Open the upload to check its processing status.');
    }

    // Do not navigate to guessed /gui/user/uploads/... URLs. Those routes
    // are not necessarily supported by the currently installed NOMAD GUI,
    // and inside PDI Lab such navigation can replace the iframe with a 404.
    const SUCCESS_KEY = 'pdiIntake.confirmedUpload.v8';

    function renderSuccess(notice) {
        const status = document.getElementById('saveStatus');
        const message = 'Upload successful: 1 SubstrateBatchMbe + ' +
            notice.children + ' SubstrateMbe entries processed in NOMAD. ' +
            'Batch: ' + notice.batchFile + '. Upload ID: ' + notice.uploadId + '.';
        if (status) {
            status.className = 'success';
            status.textContent = message;
            status.setAttribute('role', 'status');
            status.setAttribute('aria-live', 'polite');
        }
        // The form's upload status is below the fold in the PDI Lab iframe.
        // Keep the acknowledgement prominently visible at the top as well.
        let banner = document.getElementById('pdiIntakeSuccessBanner');
        if (!banner && document.body) {
            banner = document.createElement('div');
            banner.id = 'pdiIntakeSuccessBanner';
            banner.setAttribute('role', 'status');
            banner.setAttribute('aria-live', 'polite');
            banner.style.position = 'sticky';
            banner.style.top = '0';
            banner.style.zIndex = '1000';
            banner.style.padding = '12px 16px';
            banner.style.margin = '0 0 12px';
            banner.style.background = '#eaf6eb';
            banner.style.color = '#173b22';
            banner.style.border = '1px solid #6da778';
            banner.style.borderRadius = '8px';
            document.body.insertBefore(banner, document.body.firstChild);
        }
        if (banner) banner.textContent = message;
    }

    function restoreSuccessAfterRefresh() {
        try {
            const raw = window.sessionStorage.getItem(SUCCESS_KEY);
            if (!raw) return;
            const notice = JSON.parse(raw);
            window.sessionStorage.removeItem(SUCCESS_KEY);
            // The notice must only appear once, after reloading the same
            // intake page, not on unrelated pages or old browser sessions.
            if (!notice || notice.path !== window.location.pathname ||
                !Number.isInteger(notice.children) ||
                typeof notice.uploadId !== 'string' ||
                typeof notice.batchFile !== 'string' ||
                Date.now() - notice.time > 5 * 60 * 1000 ||
                notice.time > Date.now()) return;
            renderSuccess(notice);
        } catch (_error) {
            // Sandboxed/private browsing may block sessionStorage.
            // This must never prevent an already successful upload.
        }
    }

    function showSuccessAndOpenUpload(options) {
        const notice = {
            path: window.location.pathname,
            uploadId: String(options.uploadId),
            batchFile: String(options.batchFile),
            children: options.children,
            time: Date.now()
        };
        if (!notice.uploadId || notice.uploadId === 'undefined' ||
            !Number.isInteger(notice.children) || notice.children < 1) {
            throw new Error('Confirmed upload details are incomplete.');
        }
        renderSuccess(notice);
        try {
            window.sessionStorage.setItem(SUCCESS_KEY, JSON.stringify(notice));
        } catch (_error) {
            // Fallback: leave the success message visible and refresh the
            // local upload chooser, without redirecting to an unknown URL.
            if (typeof window.refreshIntakeUploads === 'function') {
                Promise.resolve(window.refreshIntakeUploads()).catch(function() {});
            }
            return;
        }
        // Reload only the currently working Substrate Check-in iframe URL.
        // NOMAD upload/entry data will be fetched again on page load; the
        // success banner is restored from sessionStorage once after reload.
        window.setTimeout(function() {
            try {
                window.location.reload();
            } catch (_error) {
                try { window.sessionStorage.removeItem(SUCCESS_KEY); }
                catch (_ignored) {}
                renderSuccess(notice);
            }
        }, 1200);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', restoreSuccessAfterRefresh);
    } else {
        restoreSuccessAfterRefresh();
    }

    window.pdiIntakeUploadFeedback = {
        waitForEntries: waitForEntries,
        showSuccessAndOpenUpload: showSuccessAndOpenUpload
    };
}());
