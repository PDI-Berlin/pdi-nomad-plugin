/*
 * Local-only MBE draft exporter. This file does not call NOMAD APIs and
 * does not create EntryArchive.data. Every m_def below uses an unchanged
 * original PDI or NOMAD section; UI-only metadata is deliberately outside them.
 * The result is NOT a valid NOMAD archive and MUST NOT be uploaded as one.
 */
(function (root, factory) {
    const api = factory();
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    if (root) root.NomadMbeDrafts = api;
})(typeof window !== 'undefined' ? window : null, function () {
    'use strict';
    const MBE = 'pdi_nomad_plugin.mbe.processes.ExperimentMbePDI';
    const FILM = 'pdi_nomad_plugin.mbe.materials.ThinFilmMbe';
    const STACK = 'pdi_nomad_plugin.mbe.materials.ThinFilmStackMbePDI';
    const FILM_REF = 'nomad_material_processing.general.ThinFilmReference';
    const FILLED = 'pdi_nomad_plugin.mbe.instrument.FilledSubstrateHolderPDI';
    const POSITION = 'pdi_nomad_plugin.mbe.instrument.FilledSubstrateHolderPositionPDI';
    const SAMPLE_REF = 'nomad.datamodel.metainfo.basesections.v1.CompositeSystemReference';
    const INSERT_REF = 'nomad_material_processing.vapor_deposition.general.InsertReductionReference';
    const SUPPORTED_GEOMETRIES = new Set([
        'nomad_material_processing.general.SquareCuboid',
        'nomad_material_processing.general.RectangleCuboid',
        'nomad_material_processing.general.Cylinder',
        'nomad_material_processing.general.CylinderSector'
    ]);

    function asReference(entity, makeRef) {
        if (!entity) return null;
        if (entity.reference) return entity.reference;
        if (!entity.uploadId || !entity.entryId) return null;
        return makeRef(entity.uploadId, entity.entryId);
    }

    function build(state, layers, makeRef, xyFromPosition) {
        if (!state || !state.holder || !state.holder.entryId) {
            throw new Error('Select an original NOMAD physical holder.');
        }
        if (!state.growthRunId || !String(state.growthRunId).trim()) {
            throw new Error('Enter a Growth Run ID.');
        }
        if (!Array.isArray(layers) || !layers.length) {
            throw new Error('Enter at least one valid nominal layer.');
        }
        const holder = state.holder;
        const holderRef = makeRef(holder.uploadId, holder.entryId);
        const warnings = [];
        const filledPositions = [];
        const localPositions = [];

        Object.keys(state.positions || {}).sort().forEach(function (name) {
            const position = state.positions[name];
            const positionData = {
                m_def: POSITION,
                name: name
            };
            if (['substrate', 'si_dummy', 'sapphire_dummy']
                    .includes(position.position_usage)) {
                positionData.position_usage = position.position_usage;
            }
            const coords = xyFromPosition(position, name);
            Object.assign(positionData, coords);
            const slot = position.slotGeometry || position.slot_geometry;
            if (slot && SUPPORTED_GEOMETRIES.has(slot.m_def)) {
                const allowed = slot.m_def.endsWith('CylinderSector')
                    ? ['height', 'radius', 'central_angle']
                    : slot.m_def.endsWith('Cylinder')
                    ? ['height', 'radius']
                    : ['height', 'width', 'length'];
                const geometry = {m_def: slot.m_def};
                allowed.forEach(function (field) {
                    if (slot[field] !== undefined && slot[field] !== null) {
                        geometry[field] = slot[field];
                    }
                });
                positionData.slot_geometry = geometry;
            } else if (slot) {
                warnings.push('Position ' + name + ': slot geometry is not a ' +
                    'supported original Geometry subtype; omitted from draft section.');
            }
            const insertRef = asReference(position.insertReduction, makeRef);
            if (insertRef) {
                positionData.insert_reduction = {m_def: INSERT_REF, reference: insertRef};
            } else if (position.insertReduction) {
                warnings.push('Position ' + name + ': insert has no NOMAD reference.');
            }
            if (position.position_usage === 'substrate') {
                const sampleRef = asReference(position.substrate, makeRef);
                if (!sampleRef) {
                    throw new Error('Position ' + name + ': substrate lacks a NOMAD archive reference.');
                }
                positionData.substrate = {m_def: SAMPLE_REF, reference: sampleRef};
            }
            filledPositions.push(positionData);
            localPositions.push({name: name, usage: position.position_usage || 'empty'});
        });
        const filled = {
            m_def: FILLED,
            name: 'Draft loadout for ' + holder.id,
            substrate_holder: holderRef,
            positions: filledPositions
        };
        const mbe = {
            m_def: MBE,
            name: String(state.growthRunId).trim(),
            lab_id: String(state.growthRunId).trim(),
            method: 'Molecular Beam Epitaxy'
            // The original normalizer populates samples and creates _lyr_1.
            // Pre-populating samples would suppress automatic layer creation!
        };
        const postNormalization = [];
        const growthId = String(state.growthRunId).trim();
        for (const p of localPositions) {
            if (p.usage !== 'substrate') continue;
            const stackId = growthId + '_' + p.name;
            const extra = layers.slice(1).map(function(layer, index) {
                const layerId = stackId + '_lyr_' + (index + 2);
                return {
                    layer_number: index + 2,
                    filename: layerId + '.archive.yaml',
                    thin_film: {m_def: FILM, name: layerId, lab_id: layerId},
                    // A reference cannot be assigned until this archive is created.
                    stack_reference_type: FILM_REF,
                    nominal_properties_local_only: layer
                };
            });
            postNormalization.push({
                holder_position: p.name,
                stack_id: stackId,
                expected_stack_type: STACK,
                mandatory_layer_1: stackId + '_lyr_1',
                mandatory_layer_1_properties: layers[0],
                extra_layer_archives: extra
            });
        }
        return {
            format: 'pdi-local-mbe-draft-v2',
            nomad_archive: false,
            notice: 'Local planning export only. Original PDI EntryData roots are used, ' +
                'but this planning preview is not validated for upload. Do not upload.',
            original_sections: {mbe: mbe, filled_holder: filled},
            local_planning_only: {
                combined_id: String(state.growthRunId).trim() + '@' + holder.id,
                nominal_layers: layers,
                position_usage: localPositions
            },
            post_normalization_plan: postNormalization,
            warnings: warnings.concat([
                'Each _lyr_1 is created by the original ExperimentMbePDI normalizer.',
                'Additional layer archives and stack links are PLANNED ONLY, not uploaded.',
                'The original experiment must have samples absent or empty before normalization.'
            ])
        };
    }

    const PRESETS = [
        'SnO','SnO2','Sn','Al','Al2O3','Ge','GeO2',
        'BaSnO3','LaInO3','BaO','InO2','LaO'
    ];
    const ELEMENTS = new Set((
        'H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc ' +
        'Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr ' +
        'Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr ' +
        'Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir ' +
        'Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am ' +
        'Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn ' +
        'Nh Fl Mc Lv Ts Og'
    ).split(' '));
    const FORMULA_PART = /^([A-Z][a-z]?)(\d+(?:\.\d+)?)?/;

    function checkFormula(formula) {
        formula = String(formula || '').trim();
        if (!formula) throw new Error('Chemical formula required.');
        let i=0, depth=0, atoms=0;
        while (i < formula.length) {
            if (formula[i] === '(') {
                depth++;
                i++;
                continue;
            }
            if (formula[i] === ')') {
                if (!depth--) throw new Error('Unmatched closing parenthesis.');
                i++;
                const mult = /^(\d+(?:\.\d+)?)/.exec(formula.slice(i));
                if (mult) {
                    if (+mult[1] <= 0) throw new Error('Invalid factor.');
                    i += mult[1].length;
                }
                continue;
            }
            const m = FORMULA_PART.exec(formula.slice(i));
            if (!m || !ELEMENTS.has(m[1])) {
                throw new Error(
                    'Invalid formula/capitalization near '+formula.slice(i)
                );
            }
            if (m[2] && +m[2] <= 0) {
                throw new Error('Invalid stoichiometric factor.');
            }
            i += m[0].length;
            atoms++;
        }
        if (depth || !atoms) {
            throw new Error('Unclosed group / missing element.');
        }
        return formula;
    }

    function filmData(base, substrateGeometry, layer) {
        if (!substrateGeometry || !substrateGeometry.m_def) {
            throw new Error('Substrate geometry missing.');
        }
        const type = substrateGeometry.m_def;
        const prefix = 'nomad_material_processing.general.';
        const shapes = {
            [prefix+'RectangleCuboid']:
                ['length','width','alpha','beta','gamma'],
            [prefix+'SquareCuboid']:
                ['length','width','alpha','beta','gamma'],
            [prefix+'Cylinder']: ['radius'],
            [prefix+'CylinderSector']: ['radius','central_angle']
        };
        const fields = shapes[type];
        if (!fields) {
            throw new Error('Unsupported substrate geometry: '+type);
        }

        const g = {m_def:type};
        for (const k of fields) {
            if (substrateGeometry[k] != null) {
                if (!Number.isFinite(+substrateGeometry[k])) {
                    throw new Error('Invalid geometry '+k);
                }
                g[k] = +substrateGeometry[k];
            }
        }

        if (
            type.endsWith('RectangleCuboid') &&
                (!(g.length>0) || !(g.width>0)) ||
            type.endsWith('SquareCuboid') && !(g.width>0) ||
            (type.endsWith('Cylinder') ||
                type.endsWith('CylinderSector')) && !(g.radius>0) ||
            type.endsWith('CylinderSector') &&
                !(g.central_angle>0 && g.central_angle<=360)
        ) {
            throw new Error('Substrate lateral dimensions missing or invalid.');
        }

        if (!(+layer.thicknessNm>0) ||
            !Number.isFinite(+layer.thicknessNm)) {
            throw new Error('Layer thickness must be positive (nm).');
        }

        // NOMAD geometry uses meters.
        // Never copy substrate height into the thin film.
        g.height = +layer.thicknessNm * 1e-9;

        const formula = checkFormula(layer.composition);
        const description = [];
        const dopant = String(layer.dopant||'').trim();
        const value = String(layer.dopantValue??'').trim();
        const unit = String(layer.dopantUnit||'').trim();

        if (dopant) {
            if (!ELEMENTS.has(dopant)) {
                throw new Error('Invalid dopant symbol: '+dopant);
            }
            description.push('Nominal dopant: '+dopant);
        }

        if (value) {
            if (
                !dopant ||
                !['cm^-3','at.%','mol.%'].includes(unit) ||
                !Number.isFinite(+value) ||
                +value<=0
            ) {
                throw new Error('Invalid dopant value or unit.');
            }
            description.push(
                'Nominal doping value: '+value+' '+unit
            );
        }

        if (layer.notes) {
            description.push('Growth notes: '+String(layer.notes).trim());
        }

        const data = {
            m_def: base.m_def,
            name: base.name,
            lab_id: base.lab_id,
            geometry: g,
            components: [{
                m_def:
                    'nomad.datamodel.metainfo.basesections.v1.PureSubstanceComponent',
                pure_substance: {molecular_formula:formula}
            }]
        };

        if (description.length) {
            data.description = description.join('\n');
        }
        return data;
    }

    function includesFields(actual,expected) {
        if (typeof expected==='number') {
            return typeof actual==='number' &&
                Math.abs(actual-expected) <=
                Math.max(1e-18,Math.abs(expected)*1e-9);
        }
        if (Array.isArray(expected)) {
            return Array.isArray(actual) &&
                actual.length===expected.length &&
                expected.every((v,i)=>includesFields(actual[i],v));
        }
        if (expected && typeof expected==='object') {
            return actual && typeof actual==='object' &&
                Object.keys(expected).every(
                    k=>includesFields(actual[k],expected[k])
                );
        }
        return actual===expected;
    }

    return {build: build, PRESETS, checkFormula, filmData, includesFields};
});
