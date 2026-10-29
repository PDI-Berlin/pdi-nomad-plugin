/* Intake-only YSZ composition control.  Original NOMAD m_defs and normalizers
 * are unchanged. Fractions refer to Y among ALL atoms and total mass.
 * 1-x mol ZrO2 + x mol Y2O3: Zr=1-x, Y=2x, O=2+x.
 */
(function (root) {
    'use strict';

    const M = Object.freeze({Zr: 91.224, Y: 88.90584, O: 15.999});
    const MAX_OXIDE_FRACTION = 1;
    function finiteFraction(value, label) {
        const n = Number(value);
        if (value === '' || value === null || !Number.isFinite(n) ||
            n < 0 || n >= MAX_OXIDE_FRACTION) {
            throw new Error(label + ': expected a finite fraction in [0, 1).');
        }
        return n;
    }
    function yszFromOxideFraction(fraction) {
        const x = finiteFraction(fraction, 'Y2O3 molar fraction');
        const zr = 1 - x;
        const y = 2 * x;
        const o = 2 + x;
        const totalMass = zr * M.Zr + y * M.Y + o * M.O;
        return Object.freeze({
            oxide_mol_percent: x * 100,
            atomic_fraction: y / (zr + y + o),
            mass_fraction: y * M.Y / totalMass,
            cation_fraction: y / (zr + y)
        });
    }
    function oxideFractionFromAtomicFraction(atomic) {
        const a = finiteFraction(atomic, 'Y atomic fraction');
        const x = 3 * a / (2 * (1 - a));
        if (x >= 1) throw new Error('Y atomic fraction is outside the YSZ composition range.');
        return x;
    }
    function oxideFractionFromMassFraction(mass) {
        const w = finiteFraction(mass, 'Y mass fraction');
        // Y mass: 2*x*M.Y; host oxide mixture mass is C + x*D.
        const c = M.Zr + 2 * M.O;
        const d = -M.Zr + 2 * M.Y + M.O;
        const x = w * c / (2 * M.Y - w * d);
        if (!Number.isFinite(x) || x >= 1 || x < 0) {
            throw new Error('Y mass fraction is outside the YSZ composition range.');
        }
        return x;
    }
    const chemistry = Object.freeze({
        yszFromOxideFraction,
        oxideFractionFromAtomicFraction,
        oxideFractionFromMassFraction
    });
    root.pdiIntakeYSZ = chemistry;
    if (typeof module !== 'undefined' && module.exports) module.exports = chemistry;

    if (!root.document || !root.document.getElementById ||
        !root.document.getElementById('pdiDopantRows')) return;

    const doc = root.document;
    const container = doc.getElementById('pdiDopantRows');
    const message = (text) => { throw new Error(text); };
    function materialFormula() {
        const selected = doc.getElementById('material');
        if (!selected) return '';
        if (selected.value === 'other') {
            return (doc.getElementById('other_material') || {}).value || '';
        }
        return selected.value === '8ysz' ? 'ZrO2' : selected.value;
    }
    function field(row, key) {
        return row.querySelector('input[data-key="' + key + '"]');
    }
    function isYSZ(row) {
        return materialFormula().trim() === 'ZrO2' &&
            field(row, 'element') && field(row, 'element').value.trim() === 'Y';
    }
    function createLabel(labelText, child) {
        const wrapper = doc.createElement('label');
        wrapper.textContent = labelText;
        wrapper.appendChild(child);
        return wrapper;
    }
    function numericValue(input, label) {
        if (!input || !input.value.trim()) message(label + ' is required.');
        const value = Number(input.value);
        if (!Number.isFinite(value) || value < 0 || value > 100) {
            message(label + ' must be between 0 and 100.');
        }
        return value;
    }
    function synchronize(row, required) {
        const selector = row.querySelector('.pdi-ysz-basis');
        const driver = row.querySelector('.pdi-ysz-input');
        const details = row.querySelector('.pdi-ysz-info');
        if (!selector || !driver) return;
        const atomic = field(row, 'atomic_fraction');
        const mass = field(row, 'mass_fraction');
        if (!atomic || !mass) return;
        if (selector.value === 'manual') {
            driver.disabled = true;
            driver.value = '';
            atomic.readOnly = false;
            mass.readOnly = false;
            details.textContent = 'Other materials: enter both fractions explicitly, or leave both blank.';
            return;
        }
        driver.disabled = false;
        atomic.readOnly = true;
        mass.readOnly = true;
        if (!isYSZ(row)) {
            atomic.value = '';
            mass.value = '';
            details.textContent = 'YSZ mode requires host formula ZrO2 and dopant element Y.';
            if (required) message(details.textContent);
            return;
        }
        if (!driver.value.trim()) {
            atomic.value = '';
            mass.value = '';
            details.textContent = 'Enter a Y2O3 mol-% or Y fraction to calculate both values.';
            if (required) message(details.textContent);
            return;
        }
        try {
            const entered = numericValue(driver, 'YSZ concentration');
            const x = selector.value === 'ysz_oxide' ? entered / 100
                : selector.value === 'ysz_atomic'
                    ? oxideFractionFromAtomicFraction(entered / 100)
                    : oxideFractionFromMassFraction(entered / 100);
            const values = yszFromOxideFraction(x);
            atomic.value = String(values.atomic_fraction);
            mass.value = String(values.mass_fraction);
            details.textContent = values.oxide_mol_percent.toFixed(4) + ' mol-% Y2O3; ' +
                (100 * values.cation_fraction).toFixed(3) + ' atom-% Y on cation sites. ' +
                'Atomic/mass fractions below are of all atoms/total mass.';
        } catch (err) {
            atomic.value = '';
            mass.value = '';
            details.textContent = err.message;
            if (required) throw err;
        }
    }
    function decorate(row) {
        if (row.dataset.pdiYszDecorated === '1') return;
        row.dataset.pdiYszDecorated = '1';
        const atomic = field(row, 'atomic_fraction');
        const mass = field(row, 'mass_fraction');
        if (!atomic || !mass) return;
        const selector = doc.createElement('select');
        selector.className = 'pdi-ysz-basis';
        [
            ['manual', 'Other material / manual fractions'],
            ['ysz_oxide', 'YSZ: mol-% Y2O3 in ZrO2'],
            ['ysz_atomic', 'YSZ: atom-% Y (all atoms)'],
            ['ysz_mass', 'YSZ: weight-% Y (total mass)']
        ].forEach(function (entry) {
            const option = doc.createElement('option');
            option.value = entry[0];
            option.textContent = entry[1];
            selector.appendChild(option);
        });
        const driver = doc.createElement('input');
        driver.className = 'pdi-ysz-input';
        driver.type = 'number';
        driver.min = '0';
        driver.max = '100';
        driver.step = 'any';
        driver.placeholder = 'e.g. 8';
        driver.disabled = true;
        // No data-key: this UI-only concentration is NOT a NOMAD Quantity.
        const details = doc.createElement('p');
        details.className = 'small pdi-ysz-info';
        details.style.gridColumn = '1 / -1';
        const wrapper = createLabel('Concentration definition', selector);
        const driverWrapper = createLabel('Concentration [%]', driver);
        row.insertBefore(wrapper, row.firstChild);
        row.insertBefore(driverWrapper, wrapper.nextSibling);
        row.appendChild(details);
        const element = field(row, 'element');
        selector.addEventListener('change', function () {
            driver.value = '';
            synchronize(row, false);
        });
        driver.addEventListener('input', function () { synchronize(row, false); });
        if (element) element.addEventListener('input', function () { synchronize(row, false); });

        // Existing references: only infer the basis if BOTH stored fractions
        // agree. Never silently reinterpret inconsistent imported data.
        const a = Number(atomic.value);
        const w = Number(mass.value);
        if (isYSZ(row) && atomic.value.trim() && mass.value.trim() &&
            Number.isFinite(a) && Number.isFinite(w) && a > 0 && w > 0) {
            try {
                const fraction = oxideFractionFromAtomicFraction(a);
                const converted = yszFromOxideFraction(fraction);
                if (Math.abs(converted.mass_fraction - w) < 1e-7) {
                    selector.value = 'ysz_oxide';
                    driver.value = String(100 * fraction);
                }
            } catch (_) { /* keep original reference numbers in manual mode */ }
        }
        synchronize(row, false);
    }
    function decorateAll() {
        container.querySelectorAll('.pdi-dopant-row').forEach(decorate);
    }
    const baseAdd = root.pdiIntakeAddDopant;
    if (typeof baseAdd === 'function') {
        root.pdiIntakeAddDopant = function () {
            const result = baseAdd.apply(this, arguments);
            decorateAll();
            return result;
        };
    }
    const baseRead = root.pdiIntakeReadSubsections;
    if (typeof baseRead === 'function') {
        root.pdiIntakeReadSubsections = function () {
            decorateAll();
            container.querySelectorAll('.pdi-dopant-row').forEach(row => {
                synchronize(row, true);
                const atomic = field(row, 'atomic_fraction');
                const mass = field(row, 'mass_fraction');
                const a = atomic.value.trim();
                const w = mass.value.trim();
                if ((a && !w) || (!a && w)) {
                    message('Dopant: atomic_fraction and mass_fraction must both be provided. ' +
                        'For YSZ select the Y2O3 mol-% mode.');
                }
                for (const input of row.querySelectorAll('input[data-key]')) {
                    if (input.value.trim() && input.dataset.key !== 'element' &&
                        !Number.isFinite(Number(input.value))) {
                        message('Invalid non-finite dopant value: ' + input.dataset.key);
                    }
                }
            });
            return baseRead.apply(this, arguments);
        };
    }
    if (root.MutationObserver) {
        const observer = new root.MutationObserver(decorateAll);
        observer.observe(container, {childList: true});
    }
    decorateAll();
})(typeof window !== 'undefined' ? window : globalThis);
