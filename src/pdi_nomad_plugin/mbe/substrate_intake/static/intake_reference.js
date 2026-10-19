(function () {
    'use strict';

    let references = [];
    const el = id => document.getElementById(id);
    const status = message => { el('samplePropStatus').textContent = message; };
    const num = (id, label) => {
        const raw = el(id).value.trim();
        if (raw === '') return null;
        const value = Number(raw);
        if (!Number.isFinite(value) || value < 0) {
            throw new Error(label + ' must be a finite, non-negative number.');
        }
        return value;
    };
    const scalar = (section, name) =>
        section && Object.prototype.hasOwnProperty.call(section, name)
            ? section[name] : null;

    function setNum(id, value) {
        el(id).value = value === undefined || value === null ? '' : String(value);
    }
    function selectValue(id, value) {
        const select = el(id);
        const v = value == null ? '' : String(value);
        if (v && !Array.from(select.options).some(opt => opt.value === v)) {
            const opt = document.createElement('option');
            opt.value = v;
            opt.textContent = v + ' (imported; validate in NOMAD)';
            select.appendChild(opt);
        }
        select.value = v;
    }

    // Explicit source precedence for this intake form only:
    //   box label / user's Batch data > imported reference > empty/default.
    // A later OCR importer can call pdiIntakeApplyBoxLabelData without
    // modifying the saved reference entry in NOMAD.
    const ownedFields = [
        'supplier', 'supplier_id', 'material', 'other_material', 'crystal_id',
        'charge', 'polishing', 'delivery_date',
        'h_index', 'k_index', 'l_index', 'offcut_angle',
        'u_index', 'v_index', 'w_index',
        'geometry_shape', 'width_mm', 'length_mm', 'radius_mm',
        'sector_angle_deg', 'thickness_mm', 'count', 'notes',
        'phys_bravais', 'phys_conductivity',
        'phys_carrier_density', 'phys_carrier_deviation', 'phys_resistivity'
    ];
    const hasValue = node => String(node.value ?? '').trim() !== '';
    const defaultOnly = node => !node.dataset.pdiFieldOrigin &&
        (node.id === 'geometry_shape' && node.value === 'rectangle' ||
         node.id === 'radius_mm' && node.value === '25.4' ||
         node.id === 'sector_angle_deg' && node.value === '90');

    ownedFields.forEach(id => {
        const node = el(id);
        if (!node) throw new Error('Missing original intake field: ' + id);
        // Assignment to .value does not dispatch input/change. Thus only
        // real user edits become 'box', and imported values stay 'reference'.
        const userEdit = () => { node.dataset.pdiFieldOrigin = 'box'; };
        node.addEventListener('input', userEdit);
        node.addEventListener('change', userEdit);
    });
    const dopantRows = el('pdiDopantRows');
    dopantRows.addEventListener('input', () => {
        dopantRows.dataset.pdiFieldOrigin = 'box';
    });
    dopantRows.addEventListener('change', () => {
        dopantRows.dataset.pdiFieldOrigin = 'box';
    });

    function canApplyReference(id) {
        const node = el(id);
        if (node.dataset.pdiFieldOrigin === 'box') return false;
        return !hasValue(node) || node.dataset.pdiFieldOrigin === 'reference' ||
            defaultOnly(node);
    }
    function referenceField(id, value) {
        if (value === undefined || value === null || value === '' ||
            !canApplyReference(id)) return false;
        el(id).value = String(value);
        el(id).dataset.pdiFieldOrigin = 'reference';
        return true;
    }
    function referenceSelect(id, value) {
        if (value === undefined || value === null || value === '' ||
            !canApplyReference(id)) return false;
        selectValue(id, value);
        el(id).dataset.pdiFieldOrigin = 'reference';
        return true;
    }
    function boxField(id, value) {
        if (value === null || value === undefined || value === '') return false;
        const node = el(id);
        if (!node) return false;
        if (node.tagName === 'SELECT' && id !== 'material' && id !== 'geometry_shape') {
            selectValue(id, value);
        } else {
            node.value = String(value);
        }
        node.dataset.pdiFieldOrigin = 'box';
        return true;
    }
    function setTriplet(ids, source, isBox) {
        if (!source) return false;
        const keys = ['h_index', 'k_index', 'l_index'];
        const values = keys.map(k => source[k]);
        if (values.some(x => !Number.isInteger(x))) return false;
        if (!isBox && ids.some(id => !canApplyReference(id))) return false;
        ids.forEach((id,i) => {
            if (isBox) boxField(id, values[i]);
            else referenceField(id, values[i]);
        });
        return true;
    }
    function parseBoxIndices(value) {
        if (Array.isArray(value) && value.length === 3) {
            const result = value.map(Number);
            return result.every(Number.isInteger) ? Object.fromEntries(
                ['h_index', 'k_index', 'l_index'].map((key,i) => [key,result[i]])
            ) : null;
        }
        if (typeof value === 'string') {
            const parts = value.trim().replace(/[()[\],]/g, ' ').split(/\s+/);
            if (parts.length !== 3 || parts.some(v => !/^[+-]?\d+$/.test(v)))
                return null;
            return Object.fromEntries(['h_index','k_index','l_index'].map(
                (key,i) => [key,Number(parts[i])]
            ));
        }
        return value && typeof value === 'object' ? value : null;
    }
    window.pdiIntakeResetImportOrigins = function () {
        ownedFields.forEach(id => delete el(id).dataset.pdiFieldOrigin);
        delete dopantRows.dataset.pdiFieldOrigin;
    };
    window.pdiIntakeApplyBoxLabelData = function (metadata) {
        if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata))
            throw new Error('Box-label metadata must be an object.');
        // Existing user corrections can be revised later, but here a newly
        // recognized physical box label always overrides imported references.
        const aliases = {supplierId: 'supplier_id', crystalId: 'crystal_id',
            charge_id: 'charge', chemical_formula: 'material',
            batch_id: 'charge', thickness: 'thickness_mm'};
        for (const [key,value] of Object.entries(metadata)) {
            const id = aliases[key] || key;
            if (id === 'orientation' || id === 'offcut_direction' ||
                id === 'hkl_reciprocal' || id === 'hkl_direct') {
                const parsed = parseBoxIndices(value);
                if (!parsed) throw new Error('Invalid ' + key + ' indices from box label.');
                setTriplet(id === 'orientation' || id === 'hkl_reciprocal'
                    ? ['h_index','k_index','l_index'] : ['u_index','v_index','w_index'],
                    parsed, true);
            } else if (id === 'material') {
                const material = String(value);
                const found = Array.from(el('material').options).some(o => o.value === material);
                boxField('material', found ? material : 'other');
                boxField('other_material', found ? '' : material);
                if (found) el('other_material').value = '';
                updateMaterialFields();
            } else if (id === 'delivery_date') {
                boxField(id, String(value).slice(0,10));
            } else if (ownedFields.includes(id)) {
                boxField(id, value);
            }
        }
        updateGeometryFields();
        updatePreview();
    };

    function addDopant(data) {
        const row = document.createElement('div');
        row.className = 'pdi-dopant-row';
        row.style.cssText = 'display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:12px;margin:8px 0;border:1px solid #d9dde3;border-radius:6px';
        const fields = [
            ['element', 'Element symbol', 'text', ''],
            ['doping_level', 'Dopant concentration [cm⁻³]', 'number', ''],
            ['doping_deviation', 'Concentration uncertainty [cm⁻³]', 'number', ''],
            ['atomic_fraction', 'Atomic fraction [0–1]', 'number', ''],
            ['mass_fraction', 'Mass fraction [0–1]', 'number', '']
        ];
        fields.forEach(function ([key, label, kind]) {
            const wrapper = document.createElement('label');
            wrapper.textContent = label;
            const inp = document.createElement('input');
            inp.dataset.key = key;
            inp.type = kind;
            if (kind === 'number') { inp.step = 'any'; inp.min = '0'; }
            if (data && data[key] != null) {
                inp.value = String((key === 'doping_level' || key === 'doping_deviation')
                    ? data[key] / 1e6 : data[key]);
            }
            wrapper.appendChild(inp);
            row.appendChild(wrapper);
        });
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'secondary';
        remove.textContent = 'Remove dopant';
        remove.addEventListener('click', () => row.remove());
        row.appendChild(remove);
        el('pdiDopantRows').appendChild(row);
    }
    window.pdiIntakeAddDopant = () => {
        addDopant(null);
        dopantRows.dataset.pdiFieldOrigin = 'box';
    };
    window.pdiIntakeResetPhysicalProperties = function () {
        ['phys_carrier_density', 'phys_carrier_deviation', 'phys_resistivity']
            .forEach(id => setNum(id, null));
        ['phys_bravais', 'phys_conductivity'].forEach(id => { el(id).value = ''; });
        el('pdiDopantRows').replaceChildren();
        delete dopantRows.dataset.pdiFieldOrigin;
    };

    window.pdiIntakeReadSubsections = function () {
        const result = {};
        const bravais = el('phys_bravais').value;
        if (bravais) result.crystal_properties = {bravais_lattices: bravais};

        const ep = {};
        const conductivity = el('phys_conductivity').value;
        if (conductivity) ep.conductivity_type = conductivity;
        const numbers = [
            ['phys_carrier_density', 'carrier_density', 'Carrier density'],
            ['phys_carrier_deviation', 'carrier_density_deviation', 'Carrier-density uncertainty'],
            ['phys_resistivity', 'electrical_resistivity', 'Electrical resistivity']
        ];
        numbers.forEach(([id, key, label]) => {
            const v = num(id, label);
            if (v !== null) ep[key] = v;
        });
        if (Object.keys(ep).length) result.electronic_properties = ep;

        const dopants = [];
        el('pdiDopantRows').querySelectorAll('.pdi-dopant-row').forEach(row => {
            const dopant = {};
            row.querySelectorAll('input').forEach(inp => {
                const raw = inp.value.trim();
                if (!raw) return;
                const key = inp.dataset.key;
                if (!key) return; // UI-only YSZ concentration control
                if (key === 'element') {
                    if (!/^[A-Z][a-z]?$/.test(raw))
                        throw new Error('Dopant element must be a chemical symbol.');
                    dopant.element = raw;
                } else {
                    let value = Number(raw);
                    if (!Number.isFinite(value) || value < 0)
                        throw new Error('Invalid dopant ' + key + '.');
                    if (key.endsWith('_fraction') && value > 1)
                        throw new Error('Dopant fractions must be ≤ 1.');
                    if (key === 'doping_level' || key === 'doping_deviation')
                        value *= 1e6;  // Original NOMAD MEnum quantity is in m⁻³.
                    dopant[key] = value;
                }
            });
            if (!dopant.element) throw new Error('Each dopant needs an element symbol.');
            dopants.push(dopant);
        });
        if (dopants.length) result.dopants = dopants;
        return result;
    };

    function applyData(source) {
        const data = source && source.data ? source.data : source;
        if (!data || typeof data !== 'object') throw new Error('Missing archive.data');
        // No identity, charge, supplier or batch lifecycle information is
        // imported. Only physical properties are copied to the CURRENT form.
        let copied = 0;
        let kept = 0;
        function apply(id, value, select=false) {
            if (value === undefined || value === null || value === '') return;
            if ((select ? referenceSelect : referenceField)(id, value)) copied++;
            else kept++;
        }
        const component = (data.components || [])[0] || {};
        const formula = component.pure_substance && component.pure_substance.molecular_formula;
        if (formula) {
            const canUse = canApplyReference('material') &&
                (el('material').value !== 'other' || canApplyReference('other_material'));
            if (canUse) {
                const isKnown = Array.from(el('material').options)
                    .some(opt => opt.value === formula);
                apply('material', isKnown ? formula : 'other');
                if (!isKnown) apply('other_material', formula);
                else if (el('other_material').dataset.pdiFieldOrigin === 'reference') {
                    el('other_material').value = '';
                    delete el('other_material').dataset.pdiFieldOrigin;
                }
                updateMaterialFields();
            } else kept++;
        }
        apply('polishing', data.polishing, true); // original SubstrateMbe quantity
        const cp = data.crystal_properties || {};
        const hkl = cp.surface_orientation && cp.surface_orientation.hkl_reciprocal;
        if (hkl) {
            if (setTriplet(['h_index','k_index','l_index'],hkl,false)) copied++;
            else kept++;
        }
        apply('phys_bravais', cp.bravais_lattices, true);
        const miscut = cp.miscut && cp.miscut.cartesian_miscut &&
            cp.miscut.cartesian_miscut.reference_orientation;
        if (miscut) {
            if (miscut.hkl_direct) {
                if (setTriplet(['u_index','v_index','w_index'],
                    miscut.hkl_direct,false)) copied++;
                else kept++;
            }
            apply('offcut_angle', miscut.angle);
        }
        const geo = data.geometry || {};
        const geometryType = String(geo.m_def || '').split('.').pop();
        if (geometryType) {
            const desired = geometryType === 'Cylinder' ? 'circle'
                : geometryType === 'CylinderSector' ? 'circular_sector' : 'rectangle';
            const shapeSet = referenceField('geometry_shape', desired);
            if (shapeSet) copied++;
            else kept++;
            // Never silently mix round and rectangular dimensions after the
            // user/box label selected a different geometry family.
            if (el('geometry_shape').value === desired) {
                if (desired === 'rectangle') {
                    const width = geo.width == null ? null : geo.width * 1000;
                    apply('width_mm',width);
                    apply('length_mm',geo.length == null ?
                        (geometryType === 'SquareCuboid' ? width : null) :
                        geo.length * 1000);
                } else {
                    apply('radius_mm',geo.radius == null ? null : geo.radius * 1000);
                    if (desired === 'circular_sector') apply('sector_angle_deg',geo.central_angle);
                }
                apply('thickness_mm',geo.height == null ? null : geo.height * 1000);
            }
            updateGeometryFields();
        }
        const ep = data.electronic_properties || {};
        apply('phys_conductivity', ep.conductivity_type, true);
        apply('phys_carrier_density', scalar(ep, 'carrier_density'));
        apply('phys_carrier_deviation', scalar(ep, 'carrier_density_deviation'));
        apply('phys_resistivity', scalar(ep, 'electrical_resistivity'));
        if (dopantRows.dataset.pdiFieldOrigin !== 'box' &&
            (!dopantRows.children.length ||
              dopantRows.dataset.pdiFieldOrigin === 'reference')) {
            dopantRows.replaceChildren();
            (data.dopants || []).forEach(dopant => addDopant(dopant));
            dopantRows.dataset.pdiFieldOrigin = 'reference';
            copied++;
        } else kept++;
        updatePreview();
        status('Reference properties applied (' + copied + ' fields/groups). ' +
            kept + ' existing box-label/user values retained. ' +
            'Polishing is included when available. Reference entry unchanged.');
    }

    window.pdiIntakeApplyReference = function () {
        const index = Number(el('samplePropReference').value);
        if (!el('samplePropReference').value || !Number.isInteger(index) || !references[index]) {
            status('Select a Sample Prop Reference first.'); return;
        }
        try { applyData(references[index].data); }
        catch (e) { status('Reference error: ' + e.message); }
    };

    window.pdiIntakeLoadReferences = async function () {
        const select = el('samplePropReference');
        const previous = references[Number(select.value)];
        select.innerHTML = '<option value="">Loading...</option>';
        status('Searching visible NOMAD entries...');
        references = [];
        let after = null;
        try {
            for (let page = 0; page < 10; page++) {
                const pagination = {page_size: 100};
                if (after) pagination.page_after_value = after;
                const response = await fetch(nomadApiBase() + '/entries/archive/query', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        owner: 'visible', query: {entry_type: 'SubstrateMbe'},
                        pagination: pagination, required: {data: '*', metadata: '*'}
                    })
                });
                if (!response.ok) throw new Error('HTTP ' + response.status);
                const payload = await response.json();
                for (const record of (payload.data || [])) {
                    const archive = record.archive || record;
                    const data = archive.data || {};
                    const name = String(data.lab_id || data.name ||
                        archive.metadata && archive.metadata.entry_name || '');
                    if (/reference/i.test(name) || /reference/i.test(String(data.charge_id || '')))
                        references.push({name: name, data: data});
                }
                after = payload.pagination && payload.pagination.next_page_after_value;
                if (!after) break;
            }
            select.innerHTML = '<option value="">Select Sample Prop Reference...</option>';
            references.forEach((ref, index) => {
                const opt = document.createElement('option');
                opt.value = String(index);
                opt.textContent = ref.name;
                select.appendChild(opt);
            });
            if (previous) {
                const selected = references.findIndex(r => r.name === previous.name);
                if (selected >= 0) select.value = String(selected);
            }
            status(references.length + ' reference entries available. ' +
                'Select one to apply its properties automatically.');
        } catch (e) {
            select.innerHTML = '<option value="">Reference search unavailable</option>';
            status('Reference query failed (' + e.message + ').');
        }
    };

    async function loadNativeChoices() {
        try {
            const response = await fetch('api/property-options');
            if (!response.ok) throw new Error('HTTP ' + response.status);
            const data = await response.json();
            [['bravais_lattices','phys_bravais'], ['conductivity_type','phys_conductivity']]
                .forEach(([key, id]) => {
                    const select = el(id);
                    const current = select.value;
                    (data[key] || []).forEach(v => {
                        if (!Array.from(select.options).some(o => o.value === v)) {
                            const option = document.createElement('option');
                            option.value = v; option.textContent = v;
                            select.appendChild(option);
                        }
                    });
                    select.value = current;
                });
        } catch (e) {
            status('NOMAD schema enum lookup failed: ' + e.message);
        }
    }
    // Loading the reference list is automatic on entry to the check-in page.
    // The small refresh control is only for references created afterwards.
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            loadNativeChoices();
            window.pdiIntakeLoadReferences();
        });
    } else {
        loadNativeChoices();
        window.pdiIntakeLoadReferences();
    }
})();
