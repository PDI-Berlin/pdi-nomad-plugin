/* Stage 12: 8YSZ is a material PRESET, not a chemical formula or NOMAD Quantity. */
(function (root) {
    'use strict';
    const doc = root.document;
    if (!doc || !doc.getElementById) return;
    const material = doc.getElementById('material');
    const container = doc.getElementById('pdiDopantRows');
    if (!material || !container) return;
    function setEightYSZ() {
        if (material.value !== '8ysz') return;
        let rows = Array.from(container.querySelectorAll('.pdi-dopant-row'));
        if (rows.length > 1) {
            root.alert('8YSZ preset supports exactly one Y dopant. Remove other dopants first.');
            material.value = 'ZrO2';
            return;
        }
        if (!rows.length) {
            if (typeof root.pdiIntakeAddDopant !== 'function') {
                root.alert('Dopant editor is not available.');
                material.value = 'ZrO2';
                return;
            }
            root.pdiIntakeAddDopant();
            rows = Array.from(container.querySelectorAll('.pdi-dopant-row'));
        }
        const row = rows[0];
        const element = row && row.querySelector('input[data-key="element"]');
        const basis = row && row.querySelector('.pdi-ysz-basis');
        const value = row && row.querySelector('.pdi-ysz-input');
        if (!element || !basis || !value) {
            root.alert('8YSZ dopant controls missing. No automatic values were applied.');
            material.value = 'ZrO2';
            return;
        }
        element.value = 'Y';
        element.dispatchEvent(new Event('input', {bubbles: true}));
        basis.value = 'ysz_oxide';
        basis.dispatchEvent(new Event('change', {bubbles: true}));
        value.value = '8';
        value.dispatchEvent(new Event('input', {bubbles: true}));
        if (typeof root.updatePreview === 'function') root.updatePreview();
    }
    material.addEventListener('change', setEightYSZ);
})(typeof window !== 'undefined' ? window : globalThis);
