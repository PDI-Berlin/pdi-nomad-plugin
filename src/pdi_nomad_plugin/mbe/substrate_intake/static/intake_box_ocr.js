/* Local substrate-box OCR. Uses existing Intake field importer. */
(function () {
    'use strict';

    const el = id => document.getElementById(id);
    // Temporary OCR diagnostics, visible after recognition.
    const debugStyle = document.createElement('style');
    debugStyle.textContent =
        '#boxOcrResults:has(#boxOcrRawText:not(:empty)) {' +
        'display:block!important;margin-top:12px}' +
        '#boxOcrRawText {white-space:pre-wrap;overflow-wrap:anywhere}';
    document.head.appendChild(debugStyle);


    function setText(id, value) {
        const element = document.getElementById(id);
        if (element) element.textContent = value || '';
    }

    const clean = text => String(text || '')
        .replace(/[\u2080-\u2089]/g,
            c => String('₀₁₂₃₄₅₆₇₈₉'.indexOf(c)))
        .replace(/×/g, 'x')
        .replace(/\u00a0/g, ' ');


    let previousImported = null;
    const trackedFields = [
        'supplier', 'supplier_id', 'material', 'other_material',
        'h_index', 'k_index', 'l_index', 'letter',
        'charge', 'extended_charge', 'offcut_angle',
        'u_index', 'v_index', 'w_index',
        'length_mm', 'width_mm', 'thickness_mm',
        'polishing', 'count'
    ];

    function clearPreviousImported() {
        if (!previousImported) return;
        for (const [id, value] of Object.entries(previousImported)) {
            const input = el(id);
            if (input && input.value === value) input.value = '';
        }
        previousImported = null;
    }

    function rememberImported(fields) {
        const names = {
            orientation: ['h_index', 'k_index', 'l_index'],
            offcut_direction: ['u_index', 'v_index', 'w_index'],
            material: ['material', 'other_material']
        };
        previousImported = {};
        for (const key of Object.keys(fields)) {
            for (const id of names[key] || [key]) {
                if (trackedFields.includes(id) && el(id)) {
                    previousImported[id] = el(id).value;
                }
            }
        }
    }


    // Recognize arbitrary alphabetic charge prefixes near the main charge.
    // Do not guess when several different IDs are plausible.
    function extendedChargeFromLabel(text) {
        const lines = String(text || '').split(/\r?\n/);
        const primary = /\b\d{3,5}\s*\/\s*\d{3,5}\s*\/\s*\d{2,4}\b/g;
        const identifier = /(?:^|[^A-Za-z0-9])([A-Za-z]{1,6})\s*[-:]?\s*(\d{3,8})(?!\d)/g;

        function candidates(line) {
            const remaining = line.replace(primary, ' ');
            return [...remaining.matchAll(identifier)].map(
                match => (match[1] + match[2]).toUpperCase()
            );
        }

        const near = [];
        for (let i = 0; i < lines.length; i++) {
            primary.lastIndex = 0;
            if (primary.test(lines[i])) {
                near.push(...candidates(lines[i]));
                if (i + 1 < lines.length) {
                    near.push(...candidates(lines[i + 1]));
                }
            }
        }

        const nearby = [...new Set(near)];
        if (nearby.length === 1) return nearby[0];
        if (nearby.length > 1) return null;

        const all = [...new Set(lines.flatMap(candidates))];
        return all.length === 1 ? all[0] : null;
    }

    function extract(text) {
        const t = clean(text).replace(
            /\b(GdScO)\s*[;:]\s*(?=\()/gi,
            (_, prefix) => prefix + '3 '
        );
        const result = {};

        if (/crys\s*[tl]ec/i.test(t)) {
            result.supplier = 'CrysTec';
            result.supplier_id = 'CTC';
        }

        const charge = t.match(
            /\b(\d{3,5})\s*\/\s*(\d{3,5})\s*\/\s*(\d{2,4})\b/
        );
        if (charge) {
            result.charge =
                `${charge[1]}/${charge[2]}/${charge[3]}`;
        }

        const material = t.match(
            /\b(GdScO3|DyScO3|SrTiO3|LaAlO3|BaSnO3|KTaO3|LaInO3|Al2O3|MgO|Si|ZrO2)\s*[,;:]?\s*\(\s*([+-]?\d)\s*[, ]?\s*([+-]?\d)\s*[, ]?\s*([+-]?\d)\s*\)\s*([A-Za-z])?/i
        );

        if (material) {
            const formulas = [
                'GdScO3', 'DyScO3', 'SrTiO3',
                'LaAlO3', 'BaSnO3', 'KTaO3',
                'LaInO3', 'Al2O3', 'MgO', 'Si', 'ZrO2'
            ];
            result.material = formulas.find(
                v => v.toLowerCase() === material[1].toLowerCase()
            );
            result.orientation = [
                material[2], material[3], material[4]
            ].join(' ');
            if (material[5]) {
                result.letter = material[5].toUpperCase();
            }
        }


        // OCR corrections for chemistry and site-occupancy notation.
        const corrected = t
            // Interpret 0 as oxygen O in a formula directly before (hkl).
            // Never alter decimal stoichiometry such as La0.7 or dimensions.
            .replace(
                /(?<=[A-Za-z)])0(?=[3sS5]\s*\(\s*[+-]?\d\s*[, ]?\s*[+-]?\d\s*[, ]?\s*[+-]?\d\s*\))/g,
                'O'
            )
            // OCR: (Lu,5c)05 -> (Lu,5c)O5
            .replace(
                /(\(\s*(?:Lu|Sc)\s*,\s*(?:Sc|Lu|5c)\s*\)\s*)0(?=[3sS5;:]\s*\(\s*[+-]?\d)/gi,
                '$1O'
            )
            // OCR: (Nd,La)(Lu,5c)O5 -> (Nd,La)(Lu,Sc)O3
            // Restrict correction to the known mixed-crystal site notation.
            .replace(
                /(\(\s*(?:Nd|La)\s*,\s*(?:La|Nd)\s*\)\s*\(\s*Lu\s*,\s*)5c(?=\s*\))/gi,
                (_, prefix) => prefix + 'Sc'
            )
            .replace(/\bSr\s*Ti\s*[O0]\s*[3sS5;:](?=\s*\()/gi, 'SrTiO3')
            .replace(/\bGdScO[;:](?=\s*\()/g, 'GdScO3')
            .replace(/(\(\s*(?:Nd|La)\s*,\s*(?:La|Nd)\s*\)\s*\(\s*(?:Lu|Sc)\s*,\s*(?:Sc|Lu)\s*\)\s*O)\s*[sS5;:](?=\s*\()/gi,
                (_, prefix) => prefix + '3')
            .replace(/\bNd\s*La\s*Lu\s*Sc\s*O\s*[sS5;:](?=\s*\()/gi,
                'NdLaLuScO3');

        const hklTail =
            String.raw`\s*\(\s*([+-]?\d)\s*[, ]?\s*([+-]?\d)` +
            String.raw`\s*[, ]?\s*([+-]?\d)\s*\)\s*([A-Za-z])?`;

        const mixedPattern = new RegExp(
            String.raw`(\(\s*(?:Nd|La)\s*,\s*(?:La|Nd)\s*\)` +
            String.raw`\s*\(\s*(?:Lu|Sc)\s*,\s*(?:Sc|Lu)\s*\)` +
            String.raw`\s*O[3s])` + hklTail, 'i'
        );

        const mixed = corrected.match(mixedPattern);
        const simple = corrected.match(new RegExp(
            String.raw`\b((?:[A-Z][a-z]?\d*){2,})` + hklTail
        ));

        const candidate = mixed || simple;
        if (candidate) {
            const formula = candidate[1].replace(/\s+/g, '')
                .replace(/Os$/i, 'O3');

            const elements = new Set(
                ('H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca ' +
                'Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr ' +
                'Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba ' +
                'La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta ' +
                'W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa ' +
                'U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs ' +
                'Mt Ds Rg Cn Nh Fl Mc Lv Ts Og').split(' ')
            );

            const valid = mixed || (
                (formula.match(/[A-Z][a-z]?/g) || [])
                    .every(symbol => elements.has(symbol))
            );

            if (valid) {
                result.material = formula;
                result.orientation = [
                    candidate[2], candidate[3], candidate[4]
                ].join(' ');
                if (candidate[5]) {
                    result.letter = candidate[5].toUpperCase();
                }
            }
        }

        // A value such as "4° off tow (011)" denotes a 4° miscut
        // towards the reciprocal-space orientation (0 1 1).
        const offTow = corrected.match(
            /(\d+(?:[.,]\d+)?)\s*°\s*off\s*(?:tow(?:ards?)?)?\s*\(\s*([+-]?\d)\s*[, ]?\s*([+-]?\d)\s*[, ]?\s*([+-]?\d)\s*\)/i
        );
        if (offTow) {
            result.offcut_angle = Number(offTow[1].replace(',', '.'));
            result.offcut_direction = [
                offTow[2], offTow[3], offTow[4]
            ].join(' ');
        }

        const dimensions = t.match(
            /\b(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)\s*(?:mm)?\b/
        );
        if (dimensions) {
            result.length_mm =
                Number(dimensions[1].replace(',', '.'));
            result.width_mm =
                Number(dimensions[2].replace(',', '.'));
            result.thickness_mm =
                Number(dimensions[3].replace(',', '.'));
        }

        if (/einseit(?:i)?g\s+pol(?:iert|\.|)(?=\s|$)|single[\s-]*side(?:d)?\s+polish/i.test(t)) {
            result.polishing = 'Single-side';
        } else if (
            /beidseit(?:i)?g\s+pol(?:iert|\.|)(?=\s|$)|double[\s-]*side(?:d)?\s+polish/i.test(t)
        ) {
            result.polishing = 'Double-side';
        }

        const quantity = t.match(
            /\b(\d{1,4})\s*(?:stk\.?|st[üu]ck|pcs\.?|pieces)\b/i
        );
        if (quantity) {
            result.count = Number(quantity[1]);
        }

        const offcut = t.match(
            /(?:off\s*cut|miscut|angle)\s*(?:angle)?\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(?:°|deg(?:rees)?)?/i
        );
        const direction = t.match(
            /(?:towards?|direction)\s*[:=]?\s*[\[(]\s*([+-]?\d+)\s*[,; ]*\s*([+-]?\d+)\s*[,; ]*\s*([+-]?\d+)\s*[\])]/i
        );
        if (offcut && direction) {
            result.offcut_angle =
                Number(offcut[1].replace(',', '.'));
            result.offcut_direction = [
                direction[1], direction[2], direction[3]
            ].join(' ');
        }

        const detectedCharge = extendedChargeFromLabel(text);
        if (detectedCharge) result.extended_charge = detectedCharge;
        return result;
    }

    let photoUrl = null;


    function chargeCandidates(text) {
        const t = clean(text);
        const result = {};
        const charge = t.match(
            /(?:^|[^A-Za-z0-9])(\d{3,5})\s*\/\s*(\d{3,5})\s*\/\s*(\d{2,4})(?!\d)/m
        );
        if (charge) {
            result.charge = `${charge[1]}/${charge[2]}/${charge[3]}`;
        }
        const detectedCharge = extendedChargeFromLabel(text);
        if (detectedCharge) result.extended_charge = detectedCharge;
        return result;
    }

    function removeHorizontalRules(source) {
        const width = source.width;
        const height = source.height;
        const input = source.getContext('2d')
            .getImageData(0, 0, width, height).data;

        const gray = new Uint8Array(width * height);
        const histogram = new Uint32Array(256);

        for (let i = 0; i < gray.length; i++) {
            const k = i * 4;
            const value = Math.round(
                0.299 * input[k] +
                0.587 * input[k + 1] +
                0.114 * input[k + 2]
            );
            gray[i] = value;
            histogram[value]++;
        }

        // Adaptive Otsu threshold for different lighting conditions.
        let total = 0;
        for (let i = 0; i < 256; i++) {
            total += i * histogram[i];
        }

        let count = 0;
        let sum = 0;
        let bestVariance = -1;
        let threshold = 120;

        for (let i = 0; i < 256; i++) {
            count += histogram[i];
            if (!count) continue;

            const remaining = gray.length - count;
            if (!remaining) break;

            sum += i * histogram[i];

            const difference =
                sum / count - (total - sum) / remaining;
            const variance =
                count * remaining * difference * difference;

            if (variance > bestVariance) {
                bestVariance = variance;
                threshold = i;
            }
        }

        threshold = Math.max(90, Math.min(175, threshold + 20));

        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;

        const ctx = canvas.getContext('2d');
        const output = ctx.createImageData(width, height);

        // Binarize the image.
        for (let i = 0; i < gray.length; i++) {
            const value = gray[i] < threshold ? 0 : 255;
            const k = i * 4;
            output.data[k] = value;
            output.data[k + 1] = value;
            output.data[k + 2] = value;
            output.data[k + 3] = 255;
        }

        // Remove long horizontal dark runs, preserving short glyph strokes.
        const minimumRun = Math.max(35, Math.round(width * 0.05));

        for (let y = 0; y < height; y++) {
            let start = -1;

            for (let x = 0; x <= width; x++) {
                const dark = x < width &&
                    gray[y * width + x] < threshold;

                if (dark && start < 0) start = x;

                if (!dark && start >= 0) {
                    if (x - start >= minimumRun) {
                        for (let j = start; j < x; j++) {
                            const k = (y * width + j) * 4;
                            output.data[k] = 255;
                            output.data[k + 1] = 255;
                            output.data[k + 2] = 255;
                        }
                    }
                    start = -1;
                }
            }
        }

        ctx.putImageData(output, 0, 0);
        return canvas;
    }

    function reset() {
        if (photoUrl) URL.revokeObjectURL(photoUrl);
        photoUrl = null;
        const photo = el('boxPhoto').files[0];
        const preview = el('boxPhotoPreview');
        preview.style.display = 'none';
        preview.removeAttribute('src');
        if (photo) {
            photoUrl = URL.createObjectURL(photo);
            preview.src = photoUrl;
            preview.style.display = 'block';
        }
        el('boxOcrResults').style.display = 'none';
        el('boxOcrRawText').textContent = '';
        el('boxOcrFields').textContent = '';
        const button = el('extractBoxData');
        button.disabled = !el('boxPhoto').files.length;
        el('boxOcrStatus').textContent = '';
    }

    async function run() {
        const file = el('boxPhoto').files[0];
        if (!file) return;

        if (!cropper.hasSelection()) {
            el('boxOcrStatus').textContent =
                'Please select a text area first. ' +
                'Draw a rectangle around the label text.';
            return;
        }

        const button = el('extractBoxData');
        const status = el('boxOcrStatus');
        let worker;

        button.disabled = true;

        try {
            if (!window.Tesseract?.createWorker) {
                throw new Error('Local Tesseract.js is unavailable.');
            }

            const url = name =>
                new URL('static/ocr/' + name, document.baseURI).href;

            status.textContent = 'Loading OCR engine...';

            worker = await Tesseract.createWorker('eng', 1, {
                workerPath: url('worker.min.js'),
                corePath: url('core'),
                langPath: url('lang'),
                workerBlobURL: false,
                logger: message => {
                    if (message.status) {
                        status.textContent = message.status +
                            (Number.isFinite(message.progress)
                                ? ' ' + Math.round(message.progress * 100) + '%'
                                : '');
                    }
                }
            });

            const originalCanvas = cropper.canvas();
            const output = await worker.recognize(originalCanvas);
            let rawText = output.data?.text || '';
            const fields = extract(rawText);

            // Second pass only when at least one Charge ID is missing.
            if (['charge', 'extended_charge', 'material',
                 'orientation', 'polishing', 'count'].some(
                     key => fields[key] === undefined
                 ) || (/off|tow/i.test(rawText) &&
                       fields.offcut_angle === undefined)) {
                status.textContent = 'Reading charge IDs with line removal...';

                const cleaned = removeHorizontalRules(originalCanvas);
                await worker.setParameters({
                    tessedit_pageseg_mode: '6'
                });

                const second = await worker.recognize(cleaned);
                const secondText = second.data?.text || '';
                const candidates = {...extract(secondText), ...chargeCandidates(secondText)};

                for (const key of Object.keys(candidates)) {
                    if (!fields[key] && candidates[key]) {
                        fields[key] = candidates[key];
                    }
                }

                rawText += '\n\n[Charge OCR - lines removed]\n'
                    + secondText;
            }

            el('boxOcrResults').style.display = 'block';
            el('boxOcrRawText').textContent =
                rawText.trim() || '(No text recognized)';
            el('boxOcrFields').textContent =
                Object.keys(fields).length
                    ? Object.entries(fields)
                        .map(([key, value]) => key + ': ' + value)
                        .join('\n')
                    : '(No supported fields extracted)';

            if (!Object.keys(fields).length) {
                status.textContent =
                    'No known fields recognized. Enter data manually.';
                return;
            }

            if (typeof window.pdiIntakeApplyBoxLabelData !== 'function') {
                throw new Error('Form importer is unavailable.');
            }

            clearPreviousImported();

            const detectedIds = [
                ...rawText.matchAll(
                    /\b(?:MI\s*\d{3,7}|P\s*A?\s*\d{4,7})\b/gi
                )
            ].map(match => match[0].replace(/\s/g, '')
                .replace(/^PA/i, 'P').toUpperCase());

            if (new Set(detectedIds).size > 1) {
                throw new Error(
                    'Multiple batch labels detected. ' +
                    'Select only one label with the OCR rectangle.'
                );
            }

            window.pdiIntakeApplyBoxLabelData(fields);
            if (fields.extended_charge) {
                const input = el('extended_charge');
                const recognized = String(fields.extended_charge).toUpperCase();
                if (!/^[A-Z]{1,3}[0-9]+$/.test(recognized)) {
                    throw new Error('Invalid recognized Extended Charge ID.');
                }
                if (input.value !== recognized) {
                    input.value = recognized;
                    input.dataset.pdiFieldOrigin = 'box';
                }
            }

            rememberImported(fields);
            if (typeof window.updatePreview === 'function') {
                window.updatePreview();
            }

            setText(
                'boxOcrStatus',
                'Recognized data transferred to the form. ' +
                'Please verify all values before saving.'
            );
        } catch (error) {
            console.error('Box OCR:', error);
            status.textContent = 'OCR error: ' + error.message;
        } finally {
            if (worker) await worker.terminate();
            button.disabled = !el('boxPhoto').files.length;
        }
    }


    function setupOcrCrop() {
        const image = el('boxPhotoPreview');
        const stage = document.createElement('div');
        stage.style.cssText =
            'position:relative;display:none;max-width:100%;touch-action:none';
        image.parentNode.insertBefore(stage, image);
        stage.appendChild(image);
        image.style.margin = '0';

        const overlay = document.createElement('canvas');
        overlay.style.cssText =
            'position:absolute;inset:0;width:100%;height:100%;' +
            'cursor:crosshair;touch-action:none';
        stage.appendChild(overlay);

        const clearButton = document.createElement('button');
        clearButton.id = 'resetBoxSelection';
        clearButton.type = 'button';
        clearButton.className = 'secondary';
        clearButton.textContent = 'Reset Selection';
        clearButton.disabled = true;
        el('extractBoxData').insertAdjacentElement('afterend', clearButton);


        const cropPreview = document.createElement('img');
        cropPreview.id = 'boxCropPreview';
        cropPreview.alt = 'OCR image crop';
        cropPreview.style.cssText =
            'display:block;max-width:100%;max-height:320px;' +
            'object-fit:contain;margin:8px 0';
        el('boxOcrResults').insertBefore(
            cropPreview, el('boxOcrResults').firstChild
        );

        let selection = null;
        let start = null;

        function redraw() {
            const width = image.clientWidth;
            const height = image.clientHeight;
            if (!width || !height) return;

            overlay.width = width;
            overlay.height = height;
            const ctx = overlay.getContext('2d');
            ctx.clearRect(0, 0, width, height);

            if (selection) {
                const x = Math.min(selection.x1, selection.x2) * width;
                const y = Math.min(selection.y1, selection.y2) * height;
                const w = Math.abs(selection.x2 - selection.x1) * width;
                const h = Math.abs(selection.y2 - selection.y1) * height;
                ctx.fillStyle = 'rgba(40,110,240,0.16)';
                ctx.strokeStyle = '#1769ff';
                ctx.lineWidth = 3;
                ctx.fillRect(x, y, w, h);
                ctx.strokeRect(x, y, w, h);
            }
        }

        function updateButtons() {
            clearButton.disabled = !selection;
            el('extractBoxData').disabled =
                !el('boxPhoto').files.length || !image.naturalWidth;
        }

        function clear() {
            selection = null;
            start = null;
            cropPreview.removeAttribute('src');
            if (!el('boxPhoto').files.length) stage.style.display = 'none';
            el('boxOcrResults').style.display = 'none';
            redraw();
            updateButtons();
        }

        function point(event) {
            const r = overlay.getBoundingClientRect();
            return {
                x: Math.max(0, Math.min(1, (event.clientX - r.left) / r.width)),
                y: Math.max(0, Math.min(1, (event.clientY - r.top) / r.height))
            };
        }

        overlay.addEventListener('pointerdown', event => {
            if (event.button !== 0 || !image.naturalWidth) return;
            start = point(event);
            selection = {
                x1:start.x, y1:start.y, x2:start.x, y2:start.y
            };
            overlay.setPointerCapture(event.pointerId);
            redraw();
            event.preventDefault();
        });

        overlay.addEventListener('pointermove', event => {
            if (!start) return;
            const p = point(event);
            selection.x2 = p.x;
            selection.y2 = p.y;
            redraw();
        });

        overlay.addEventListener('pointerup', event => {
            if (!start) return;
            const p = point(event);
            selection.x2 = p.x;
            selection.y2 = p.y;
            start = null;
            if (
                Math.abs(selection.x2-selection.x1)*image.clientWidth < 15 ||
                Math.abs(selection.y2-selection.y1)*image.clientHeight < 15
            ) selection = null;
            redraw();
            updateButtons();
        });

        overlay.addEventListener('pointercancel', () => {
            start = null;
            selection = null;
            redraw();
            updateButtons();
        });

        image.addEventListener('load', () => {
            stage.style.display = 'inline-block';
            selection = null;
            redraw();
            updateButtons();
            el('boxOcrStatus').textContent =
                'Select the text area by drawing a rectangle on the image.';
        });

        if (window.ResizeObserver) {
            new ResizeObserver(redraw).observe(image);
        }
        clearButton.addEventListener('click', clear);

        function canvas() {
            if (!selection) {
                throw new Error('Draw a rectangle around the label first.');
            }
            const x = Math.min(selection.x1, selection.x2);
            const y = Math.min(selection.y1, selection.y2);
            const w = Math.abs(selection.x2 - selection.x1);
            const h = Math.abs(selection.y2 - selection.y1);

            const sx = Math.floor(x * image.naturalWidth);
            const sy = Math.floor(y * image.naturalHeight);
            const sw = Math.min(
                image.naturalWidth - sx,
                Math.max(1, Math.round(w * image.naturalWidth))
            );
            const sh = Math.min(
                image.naturalHeight - sy,
                Math.max(1, Math.round(h * image.naturalHeight))
            );

            const factor = Math.max(
                1, Math.min(3, 1600 / Math.max(sw, sh))
            );
            const output = document.createElement('canvas');
            output.width = Math.round(sw * factor);
            output.height = Math.round(sh * factor);
            const ctx = output.getContext('2d');
            ctx.filter = 'grayscale(1) contrast(1.35)';
            ctx.drawImage(
                image, sx, sy, sw, sh,
                0, 0, output.width, output.height
            );
            cropPreview.src = output.toDataURL('image/png');
            return output;
        }

        return {clear, canvas, hasSelection: () => Boolean(selection)};
    }

    const cropper = setupOcrCrop();

    window.pdiIntakeBoxOcrExtract = extract;
    window.pdiIntakeResetBoxOcr = function () {
        previousImported = null;
        reset();
        cropper.clear();
    };

    el('boxPhoto').addEventListener('change', function () { reset(); cropper.clear(); });
    el('extractBoxData').addEventListener('click', run);
    reset();
})();
