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
            } else if (position.position_usage === 'si_dummy' ||
                       position.position_usage === 'sapphire_dummy') {
                warnings.push('Position ' + name + ': dummy is GUI-only; no ' +
                    'original CompositeSystem reference is available.');
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
    return {build: build};
});
