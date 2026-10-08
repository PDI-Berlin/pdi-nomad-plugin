// FIX: this used to guess the deployment base path by searching
// window.location.pathname for '/gui/' or '/dashboards/'. That breaks when
// the page is loaded in a context where neither substring appears in the
// URL (e.g. embedded inside NOMAD GUI v2), silently sending every API call
// to the wrong, unprefixed URL (404). The backend now injects the real
// base path as window.NOMAD_API_BASE (see new_mbe_experiment/app.py);
// prefer that, and only fall back to the old URL-guessing if missing.
function nomadApiBase() {
    if (window.NOMAD_API_BASE) {
        return window.NOMAD_API_BASE;
    }

    const pathname = window.location.pathname;
    const markers = ['/gui/', '/dashboards/'];

    for (const marker of markers) {
        const index = pathname.indexOf(marker);

        if (index >= 0) {
            return (
                pathname.slice(0, index) +
                '/api/v1'
            );
        }
    }

    return '/api/v1';
}


/*
 * Temporary development holder data.
 *
 * These will be replaced by holder entries loaded
 * dynamically from NOMAD.
 */
const xpsInsertCatalog = [
    {
        id: 'XPS_Insert_1',
        entryId: null
    },
    {
        id: 'XPS_Insert_2',
        entryId: null
    },
    {
        id: 'XPS_Insert_3',
        entryId: null
    }
];


const experimentState = {
    growthRunId: '',
    holder: null,
    positions: {},
    layers: [
        {
            chemicalFormula: '',
            dopantElement: '',
            nominalThicknessNm: ''
        }
    ]
};


const layerCatalogState = {
    elements: [],
    dopants: [],
    compositions: []
};


const blockedFormulaAbbreviations = new Set([
    'STO',
    'DSO',
    'GSO',
    'BSO',
    'LAO',
    'KTO',
    'LSAT',
    'LIO',
    'YSZ'
]);


function emptyNominalLayer() {
    return {
        chemicalFormula: '',
        dopantElement: '',
        nominalThicknessNm: ''
    };
}


function layerDisplayName(layer) {
    const formula =
        String(layer.chemicalFormula || '').trim();

    const dopant =
        String(layer.dopantElement || '').trim();

    if (!formula) return 'Not specified';

    return dopant
        ? dopant + ':' + formula
        : formula;
}


function validateChemicalFormula(value) {
    const formula =
        String(value || '').trim();

    if (!formula) return false;

    if (
        blockedFormulaAbbreviations.has(
            formula.toUpperCase()
        )
    ) {
        return false;
    }

    const elements =
        new Set(layerCatalogState.elements);

    const tokenPattern =
        /([A-Z][a-z]?)([1-9][0-9]*)?/g;

    let position = 0;
    let match;
    let found = false;

    while (
        (match = tokenPattern.exec(formula)) !== null
    ) {
        found = true;

        if (match.index !== position) {
            return false;
        }

        if (!elements.has(match[1])) {
            return false;
        }

        position = tokenPattern.lastIndex;
    }

    return (
        found &&
        position === formula.length
    );
}


function rememberLayerCompositions() {
    const values =
        new Set(layerCatalogState.compositions);

    experimentState.layers.forEach(
        function(layer) {
            const formula =
                String(
                    layer.chemicalFormula || ''
                ).trim();

            if (
                formula &&
                validateChemicalFormula(formula)
            ) {
                values.add(formula);
            }
        }
    );

    layerCatalogState.compositions =
        Array.from(values).sort(
            function(a, b) {
                return a.localeCompare(b);
            }
        );
}


async function loadLayerCatalog() {
    const response =
        await fetch('./api/layer-options');

    if (!response.ok) {
        throw new Error(
            'Could not load layer options: ' +
            response.status
        );
    }

    const options =
        await response.json();

    layerCatalogState.elements =
        Array.isArray(options.elements)
            ? options.elements
            : [];

    layerCatalogState.dopants =
        Array.isArray(options.dopants)
            ? options.dopants
            : [];

    const formulas =
        new Set(
            Array.isArray(options.compositions)
                ? options.compositions
                : []
        );

    try {
        const experiments =
            await queryEntriesBySchema(
                'pdi_nomad_plugin.mbe.processes.ExperimentMbePDI',
                1000,
                ['data.nominal_layers']
            );

        experiments.forEach(function(entry) {
            const layers =
                (entry.data || {}).nominal_layers || [];

            layers.forEach(function(layer) {
                const formula =
                    String(
                        (layer || {}).chemical_formula || ''
                    ).trim();

                if (formula) formulas.add(formula);
            });
        });
    } catch (error) {
        console.warn(
            'Could not load historical experiment layer compositions:',
            error
        );
    }

    try {
        const films =
            await queryEntriesBySchema(
                'pdi_nomad_plugin.mbe.materials.ThinFilmMbe',
                1000,
                ['data.chemical_formula']
            );

        films.forEach(function(entry) {
            const formula =
                String(
                    (entry.data || {}).chemical_formula || ''
                ).trim();

            if (formula) formulas.add(formula);
        });
    } catch (error) {
        console.warn(
            'Could not load historical thin-film compositions:',
            error
        );
    }

    layerCatalogState.compositions =
        Array.from(formulas).sort(
            function(a, b) {
                return a.localeCompare(b);
            }
        );
}


function updateLayerStackPreview() {
    const preview =
        document.getElementById(
            'layerStackPreview'
        );

    if (!preview) return;

    preview.innerHTML = '';

    experimentState.layers.forEach(
        function(layer, index) {
            const row =
                document.createElement('div');

            row.className =
                'layer-preview-row';

            const thickness =
                String(
                    layer.nominalThicknessNm || ''
                ).trim();

            row.textContent =
                'Layer ' +
                String(index + 1) +
                ': ' +
                layerDisplayName(layer) +
                (
                    thickness
                        ? ' · ' + thickness + ' nm'
                        : ''
                );

            preview.appendChild(row);
        }
    );
}


function renderLayerStack() {
    const container =
        document.getElementById(
            'layerStackList'
        );

    if (!container) return;

    container.innerHTML = '';

    experimentState.layers.forEach(
        function(layer, index) {
            const card =
                document.createElement('div');

            card.className = 'layer-card';

            const header =
                document.createElement('div');

            header.className =
                'layer-card-header';

            const title =
                document.createElement('strong');

            title.textContent =
                'Layer ' + String(index + 1);

            header.appendChild(title);

            if (index > 0) {
                const remove =
                    document.createElement('button');

                remove.type = 'button';
                remove.className =
                    'secondary layer-remove-button';
                remove.textContent = 'Remove';

                remove.addEventListener(
                    'click',
                    function() {
                        experimentState.layers.splice(
                            index,
                            1
                        );

                        renderLayerStack();
                        updateStatePreview();
                    }
                );

                header.appendChild(remove);
            }

            card.appendChild(header);

            const compositionLabel =
                document.createElement('label');

            compositionLabel.textContent =
                'Composition';

            card.appendChild(compositionLabel);

            const compositionSelect =
                document.createElement('select');

            const emptyOption =
                document.createElement('option');

            emptyOption.value = '';
            emptyOption.textContent =
                'Select composition...';

            compositionSelect.appendChild(
                emptyOption
            );

            layerCatalogState.compositions.forEach(
                function(formula) {
                    const option =
                        document.createElement('option');

                    option.value = formula;
                    option.textContent = formula;

                    compositionSelect.appendChild(
                        option
                    );
                }
            );

            const otherOption =
                document.createElement('option');

            otherOption.value = '__other__';
            otherOption.textContent = 'Other...';

            compositionSelect.appendChild(
                otherOption
            );

            const known =
                layerCatalogState.compositions.includes(
                    layer.chemicalFormula
                );

            if (known) {
                compositionSelect.value =
                    layer.chemicalFormula;
            } else if (layer.chemicalFormula) {
                compositionSelect.value =
                    '__other__';
            } else {
                compositionSelect.value = '';
            }

            card.appendChild(
                compositionSelect
            );

            const customInput =
                document.createElement('input');

            customInput.type = 'text';
            customInput.className =
                'layer-custom-composition';
            customInput.placeholder =
                'e.g. GdScO3';
            customInput.value =
                known
                    ? ''
                    : layer.chemicalFormula;

            customInput.style.display =
                compositionSelect.value === '__other__'
                    ? 'block'
                    : 'none';

            compositionSelect.addEventListener(
                'change',
                function() {
                    if (
                        compositionSelect.value ===
                        '__other__'
                    ) {
                        layer.chemicalFormula = '';
                        customInput.value = '';
                        customInput.style.display =
                            'block';
                        customInput.focus();
                    } else {
                        layer.chemicalFormula =
                            compositionSelect.value;
                        customInput.value = '';
                        customInput.style.display =
                            'none';
                    }

                    updateLayerStackPreview();
                    updateStatePreview();
                }
            );

            customInput.addEventListener(
                'input',
                function() {
                    layer.chemicalFormula =
                        customInput.value.trim();

                    updateLayerStackPreview();
                    updateStatePreview();
                }
            );

            card.appendChild(customInput);

            const formulaHelp =
                document.createElement('div');

            formulaHelp.className =
                'small layer-help';

            formulaHelp.textContent =
                'Use a full chemical formula with valid element symbols.';

            card.appendChild(formulaHelp);

            const dopantLabel =
                document.createElement('label');

            dopantLabel.textContent =
                'Dopant';

            card.appendChild(dopantLabel);

            const dopantSelect =
                document.createElement('select');

            const noDopant =
                document.createElement('option');

            noDopant.value = '';
            noDopant.textContent = 'None';

            dopantSelect.appendChild(
                noDopant
            );

            layerCatalogState.dopants.forEach(
                function(element) {
                    const option =
                        document.createElement('option');

                    option.value = element;
                    option.textContent = element;

                    dopantSelect.appendChild(option);
                }
            );

            dopantSelect.value =
                layer.dopantElement || '';

            dopantSelect.addEventListener(
                'change',
                function() {
                    layer.dopantElement =
                        dopantSelect.value;

                    updateLayerStackPreview();
                    updateStatePreview();
                }
            );

            card.appendChild(dopantSelect);

            const thicknessLabel =
                document.createElement('label');

            thicknessLabel.textContent =
                'Nominal thickness (nm)';

            card.appendChild(thicknessLabel);

            const thicknessInput =
                document.createElement('input');

            thicknessInput.type = 'number';
            thicknessInput.min = '0';
            thicknessInput.step = '0.01';
            thicknessInput.placeholder = 'e.g. 20';
            thicknessInput.value =
                layer.nominalThicknessNm;

            thicknessInput.addEventListener(
                'input',
                function() {
                    layer.nominalThicknessNm =
                        thicknessInput.value;

                    updateLayerStackPreview();
                    updateStatePreview();
                }
            );

            card.appendChild(
                thicknessInput
            );

            const display =
                document.createElement('div');

            display.className =
                'layer-display-name';

            display.textContent =
                'Display: ' +
                layerDisplayName(layer);

            card.appendChild(display);

            container.appendChild(card);
        }
    );

    updateLayerStackPreview();
}


function addNominalLayer() {
    experimentState.layers.push(
        emptyNominalLayer()
    );

    renderLayerStack();
    updateStatePreview();
}


function resetLayerStack() {
    experimentState.layers = [
        emptyNominalLayer()
    ];

    renderLayerStack();
    updateStatePreview();
}


function nominalLayerArchiveData() {
    if (
        !Array.isArray(experimentState.layers) ||
        !experimentState.layers.length
    ) {
        throw new Error(
            'At least one nominal layer is required.'
        );
    }

    return experimentState.layers.map(
        function(layer, index) {
            const layerNumber =
                index + 1;

            const formula =
                String(
                    layer.chemicalFormula || ''
                ).trim();

            if (!formula) {
                throw new Error(
                    'Layer ' +
                    layerNumber +
                    ': composition is required.'
                );
            }

            if (!validateChemicalFormula(formula)) {
                throw new Error(
                    'Layer ' +
                    layerNumber +
                    ': invalid chemical formula. ' +
                    'Use a full formula such as BaSnO3 with valid element symbols.'
                );
            }

            const dopant =
                String(
                    layer.dopantElement || ''
                ).trim();

            if (
                dopant &&
                !layerCatalogState.dopants.includes(
                    dopant
                )
            ) {
                throw new Error(
                    'Layer ' +
                    layerNumber +
                    ': dopant must be a valid chemical element.'
                );
            }

            const thickness =
                Number(
                    layer.nominalThicknessNm
                );

            if (
                !Number.isFinite(thickness) ||
                thickness <= 0
            ) {
                throw new Error(
                    'Layer ' +
                    layerNumber +
                    ': nominal thickness must be greater than zero.'
                );
            }

            const data = {
                chemical_formula: formula,
                nominal_thickness:
                    thickness * 1e-9
            };

            if (dopant) {
                data.dopant_element = dopant;
            }

            return data;
        }
    );
}


async function initialiseLayerStack() {
    await loadLayerCatalog();

    if (
        !Array.isArray(experimentState.layers) ||
        !experimentState.layers.length
    ) {
        experimentState.layers = [
            emptyNominalLayer()
        ];
    }

    renderLayerStack();
}


async function loadTreatmentHistoryEntries() {

    const treatmentSchemas = [
        {
            type: 'cleaning',
            label: 'Cleaning',
            processSchema:
                'pdi_nomad_plugin.general.schema.CleaningPDI',
            recipeSchema:
                'pdi_nomad_plugin.general.schema.CleaningRecipePDI'
        },
        {
            type: 'annealing',
            label: 'Annealing',
            processSchema:
                'pdi_nomad_plugin.general.schema.AnnealingPDI',
            recipeSchema:
                'pdi_nomad_plugin.general.schema.AnnealingRecipePDI'
        },
        {
            type: 'back_side_coating',
            label: 'Back-side coating',
            processSchema:
                'pdi_nomad_plugin.general.schema.BackSideCoatingPDI',
            recipeSchema:
                'pdi_nomad_plugin.general.schema.BackSideCoatingRecipePDI'
        }
    ];

    const treatments = [];

    for (const treatmentSchema of treatmentSchemas) {

        /*
         * Load the recipes of this process type first.
         * The history should show the RECIPE name, not the
         * generic process-entry name such as
         * "Annealing - 4 substrates".
         */
        const recipeEntries =
            await queryEntriesBySchema(
                treatmentSchema.recipeSchema,
                500,
                [
                    'entry_id',
                    'upload_id',
                    'entry_name',
                    'data.name',
                    'data.lab_id'
                ]
            );

        const recipeNames =
            new Map();

        recipeEntries.forEach(
            function(recipe) {
                const data =
                    recipe.data || {};

                recipeNames.set(
                    recipe.entry_id,
                    data.name ||
                    data.lab_id ||
                    recipe.entry_name ||
                    recipe.entry_id
                );
            }
        );

        const entries =
            await queryEntriesBySchema(
                treatmentSchema.processSchema,
                500,
                [
                    'entry_id',
                    'upload_id',
                    'entry_name',
                    'data'
                ]
            );

        entries.forEach(
            function(entry) {
                const data =
                    entry.data || {};

                const recipeReference =
                    referenceValue(
                        data.recipe
                    );

                const recipeEntryId =
                    entryIdFromReference(
                        recipeReference
                    );

                let recipeName =
                    recipeEntryId
                        ? recipeNames.get(
                            recipeEntryId
                        )
                        : '';

                /*
                 * Some NOMAD references may already contain
                 * resolved display information.
                 */
                if (
                    !recipeName &&
                    data.recipe &&
                    typeof data.recipe === 'object'
                ) {
                    recipeName =
                        data.recipe.name ||
                        data.recipe.lab_id ||
                        '';
                }

                treatments.push({
                    entryId:
                        entry.entry_id,

                    uploadId:
                        entry.upload_id,

                    entryName:
                        entry.entry_name ||
                        entry.entry_id,

                    type:
                        treatmentSchema.type,

                    label:
                        treatmentSchema.label,

                    recipeName:
                        recipeName,

                    data:
                        data
                });
            }
        );
    }

    console.log(
        'Treatment history entries:',
        treatments
    );

    return treatments;
}

function treatmentReferencesSubstrate(
    treatment,
    substrateEntryId
) {

    if (
        !treatment ||
        !treatment.data ||
        !substrateEntryId
    ) {
        return false;
    }


    const samples =
        treatment.data.samples || [];


    return samples.some(
        function(sample) {

            if (!sample) {
                return false;
            }


            const reference =
                sample.reference;


            if (!reference) {
                return false;
            }


            if (
                typeof reference ===
                'string'
            ) {
                return reference.includes(
                    substrateEntryId
                );
            }


            if (
                typeof reference ===
                'object'
            ) {

                const serialized =
                    JSON.stringify(
                        reference
                    );

                return serialized.includes(
                    substrateEntryId
                );
            }


            return false;
        }
    );
}



function nomadArchiveReference(
    uploadId,
    entryId
) {

    if (!uploadId || !entryId) {
        throw new Error(
            'uploadId and entryId are required ' +
            'for a NOMAD archive reference.'
        );
    }

    return (
        '../uploads/' +
        uploadId +
        '/archive/' +
        entryId +
        '#data'
    );
}


function treatmentDate(
    treatment
) {

    const data =
        treatment.data || {};

    return (
        data.datetime ||
        data.starting_time ||
        data.start_time ||
        data.ending_time ||
        ''
    );
}


async function loadTreatmentRecipes() {

    const recipeSchemas = [
        {
            type: 'cleaning',
            schema:
                'pdi_nomad_plugin.general.schema.CleaningRecipePDI'
        },
        {
            type: 'annealing',
            schema:
                'pdi_nomad_plugin.general.schema.AnnealingRecipePDI'
        },
        {
            type: 'etching',
            schema:
                'pdi_nomad_plugin.general.schema.EtchingRecipePDI'
        },
        {
            type: 'back_side_coating',
            schema:
                'pdi_nomad_plugin.general.schema.BackSideCoatingRecipePDI'
        }
    ];

    const recipes = [];

    for (const recipeSchema of recipeSchemas) {

        const response = await fetch(
            nomadApiBase() + '/entries/query',
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    // FIX: without an explicit owner NOMAD defaults to owner="public",
                    // which only returns PUBLISHED entries. Lab data lives in unpublished
                    // uploads, so every query came back empty. "visible" = public + everything
                    // the logged-in user can see (login is sent automatically via cookie).
                    owner: 'visible',
                    query: {
                        'section_defs.definition_qualified_name':
                            recipeSchema.schema
                    },
                    pagination: {
                        page_size: 100
                    },
                    required: {
                        include: [
                            'entry_id',
                            'entry_name'
                        ]
                    }
                })
            }
        );

        if (!response.ok) {
            throw new Error(
                'Treatment recipe query failed for ' +
                recipeSchema.type +
                ': ' +
                response.status
            );
        }

        const result =
            await response.json();

        (result.data || []).forEach(
            function(recipe) {

                recipes.push({
                    entryId:
                        recipe.entry_id,
                    name:
                        recipe.entry_name ||
                        recipe.entry_id,
                    type:
                        recipeSchema.type,
                    schema:
                        recipeSchema.schema
                });
            }
        );
    }

    console.log(
        'Treatment recipes:',
        recipes
    );

    return recipes;
}


// FIX: was POSTing to /entries/query with required.include containing
// data.* paths (e.g. 'data.lab_id'), which /entries/query rejects with a
// 422 (it only serves indexed doc quantities, not archive content). Reuses
// the already-fixed queryEntriesBySchema(), which talks to
// /entries/archive/query instead and returns the same entry shape.
async function loadSubstrates() {
    const entries = await queryEntriesBySchema(
        'pdi_nomad_plugin.mbe.materials.SubstrateMbe',
        500,
        [
            'entry_id',
            'upload_id',
            'entry_name',
            'data.m_def',
            'data.lab_id',
            'data.parent_sample',
            'data.material_designation',
            'data.chemical_formula',
            'data.supplier_id',
            'data.crystal_id',
            'data.charge_id',
            'data.polishing',
            'data.surface_orientation_label',
            'data.offcut_label',
            'data.offcut_direction',
            'data.as_delivered',
            'data.processed',
            'data.grown',
            'data.geometry'
        ]
    );

    const substrates = entries.filter(
        function(entry) {
            return (
                (entry.data || {}).m_def ===
                'pdi_nomad_plugin.mbe.materials.SubstrateMbe'
            );
        }
    );

    console.log(
        'SubstrateMbe query result:',
        substrates
    );

    return substrates;
}


async function loadHolders() {

    const response = await fetch(
        nomadApiBase() + '/entries/query',
        {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                query: {
                    'section_defs.definition_qualified_name':
                        'pdi_nomad_plugin.mbe.instrument.SubstrateHolderPDI'
                },
                pagination: {
                    page_size: 100
                },
                required: {
                    include: [
                        'entry_id',
                        'entry_name',
                        'upload_id'
                    ]
                }
            })
        }
    );

    if (!response.ok) {
        throw new Error(
            'Holder query failed: ' +
            response.status
        );
    }

    const result = await response.json();

    console.log(
        'SubstrateHolderPDI query result:',
        result
    );

    return result.data || [];
}


let substrateCatalogState = [];
let treatmentHistoryState = [];


function substrateStatus(substrate) {

    if (substrate.grown) {
        return 'grown';
    }

    if (substrate.processed) {
        return 'processed';
    }

    if (substrate.asDelivered) {
        return 'as_delivered';
    }

    return '';
}


function uniqueSorted(values) {

    return Array.from(
        new Set(
            values.filter(Boolean)
        )
    ).sort(
        function(a, b) {
            return a.localeCompare(b);
        }
    );
}


function fillFilterSelect(
    elementId,
    values
) {

    const select =
        document.getElementById(
            elementId
        );

    const previousValue =
        select.value;

    select.innerHTML =
        '<option value="">All</option>';

    uniqueSorted(values).forEach(
        function(value) {

            const option =
                document.createElement(
                    'option'
                );

            option.value = value;
            option.textContent = value;

            select.appendChild(option);
        }
    );

    if (
        Array.from(select.options).some(
            function(option) {
                return (
                    option.value ===
                    previousValue
                );
            }
        )
    ) {
        select.value =
            previousValue;
    }
}


function updateSubstrateFilters() {

    fillFilterSelect(
        'filterMaterial',
        substrateCatalogState.map(
            function(substrate) {
                return substrate.material;
            }
        )
    );

    fillFilterSelect(
        'filterBatch',
        substrateCatalogState
            .flatMap(function(substrate) {
                return [
                    substrate.crystalId,
                    substrate.chargeId
                ];
            })
    );

    fillFilterSelect(
        'filterOrientation',
        substrateCatalogState.map(
            function(substrate) {
                return substrate.orientation;
            }
        )
    );

    fillFilterSelect(
        'filterOffcut',
        substrateCatalogState.map(
            function(substrate) {
                return substrate.offcut;
            }
        )
    );

    fillFilterSelect(
        'filterDirection',
        substrateCatalogState.map(
            function(substrate) {
                return substrate.offcutDirection;
            }
        )
    );
}


function cutParentEntryIds() {
    const parentIds = new Set();

    substrateCatalogState.forEach(
        function(substrate) {
            const parentEntryId =
                referenceEntryId(
                    substrate.parentSample
                );

            if (parentEntryId) {
                parentIds.add(
                    parentEntryId
                );
            }
        }
    );

    return parentIds;
}


function substrateHasBeenCut(substrate) {
    if (
        !substrate ||
        !substrate.entryId
    ) {
        return false;
    }

    return cutParentEntryIds().has(
        substrate.entryId
    );
}


function filteredSubstrates() {

    const cutParents =
        cutParentEntryIds();

    const search =
        document.getElementById(
            'substrateSearch'
        ).value
            .trim()
            .toLowerCase();

    const material =
        document.getElementById(
            'filterMaterial'
        ).value;

    const batch =
        document.getElementById(
            'filterBatch'
        ).value;

    const orientation =
        document.getElementById(
            'filterOrientation'
        ).value;

    const offcut =
        document.getElementById(
            'filterOffcut'
        ).value;

    const direction =
        document.getElementById(
            'filterDirection'
        ).value;

    const status =
        document.getElementById(
            'filterStatus'
        ).value;


    return substrateCatalogState.filter(
        function(substrate) {

            /*
             * Once child samples reference this substrate as their
             * parent, the original physical piece no longer exists.
             */
            if (
                cutParents.has(
                    substrate.entryId
                )
            ) {
                return false;
            }

            const searchable = [
                substrate.labId,
                substrate.entryName,
                substrate.material,
                substrate.supplierId,
                substrate.crystalId,
                substrate.chargeId,
                substrate.orientation,
                substrate.offcut,
                substrate.offcutDirection
            ]
                .filter(Boolean)
                .join(' ')
                .toLowerCase();


            if (
                search &&
                !searchable.includes(search)
            ) {
                return false;
            }

            if (
                material &&
                substrate.material !==
                material
            ) {
                return false;
            }

            if (
                batch &&
                substrate.crystalId !== batch &&
                substrate.chargeId !== batch
            ) {
                return false;
            }

            if (
                orientation &&
                substrate.orientation !==
                orientation
            ) {
                return false;
            }

            if (
                offcut &&
                substrate.offcut !==
                offcut
            ) {
                return false;
            }

            if (
                direction &&
                substrate.offcutDirection !==
                direction
            ) {
                return false;
            }

            if (
                status &&
                substrateStatus(
                    substrate
                ) !== status
            ) {
                return false;
            }

            return true;
        }
    );
}


function selectSubstrate(
    substrate
) {

    const position =
        getActivePosition();

    if (
        !position ||
        position.position_usage !==
        'substrate'
    ) {
        return;
    }


    const oldEntryId =
        position.substrate
            ? position.substrate.entryId
            : null;


    /*
     * Treatments already queued for another
     * substrate must not follow a replacement
     * substrate accidentally.
     */
    if (
        oldEntryId &&
        oldEntryId !== substrate.entryId
    ) {
        position.pendingTreatments = [];
    }


    position.substrate = {
        entryId:
            substrate.entryId,
        uploadId:
            substrate.uploadId,
        entryName:
            substrate.entryName,
        labId:
            substrate.labId,
        parentSample:
            substrate.parentSample,
        material:
            substrate.material,
        supplierId:
            substrate.supplierId,
        crystalId:
            substrate.crystalId,
        chargeId:
            substrate.chargeId,
        polishing:
            substrate.polishing,
        orientation:
            substrate.orientation,
        offcut:
            substrate.offcut,
        offcutDirection:
            substrate.offcutDirection,
        geometry:
            substrate.geometry || null,
        asDelivered:
            substrate.asDelivered,
        processed:
            substrate.processed,
        grown:
            substrate.grown
    };


    renderHolder();
    renderSubstrateResults();
    renderTreatmentQueue();
    updateStatePreview();
}


function renderSubstrateResults() {

    const container =
        document.getElementById(
            'substrateResults'
        );

    container.innerHTML = '';


    const position =
        getActivePosition();

    if (
        !position ||
        position.position_usage !==
        'substrate'
    ) {

        const message =
            document.createElement('p');

        message.className = 'small';

        message.style.padding = '10px';

        message.textContent =
            'Select a substrate holder position first.';

        container.appendChild(
            message
        );

        return;
    }


    const substrateNameCollator =
        new Intl.Collator(
            undefined,
            {
                numeric: true,
                sensitivity: 'base'
            }
        );

    const substrates =
        filteredSubstrates()
            .filter(
                function(substrate) {
                    return substrateFitsPosition(
                        substrate,
                        position
                    );
                }
            )
            .sort(
                function(a, b) {
                    const aName =
                        a.labId ||
                        a.entryName ||
                        a.entryId ||
                        '';

                    const bName =
                        b.labId ||
                        b.entryName ||
                        b.entryId ||
                        '';

                    return substrateNameCollator.compare(
                        aName,
                        bName
                    );
                }
            );


    if (substrates.length === 0) {

        const message =
            document.createElement('p');

        message.className = 'small';

        message.style.padding = '10px';

        message.textContent =
            'No matching substrates found.';

        container.appendChild(
            message
        );

        return;
    }


    substrates.forEach(
        function(substrate) {

            const row =
                document.createElement(
                    'div'
                );

            row.className =
                'substrate-result';


            if (
                position.substrate &&
                position.substrate.entryId ===
                substrate.entryId
            ) {
                row.style.background =
                    '#eef4fb';
            }


            const title =
                document.createElement(
                    'div'
                );

            title.style.fontWeight =
                'bold';

            title.textContent =
                substrate.labId ||
                substrate.entryName ||
                substrate.entryId;

            row.appendChild(title);


            const details =
                document.createElement(
                    'div'
                );

            details.className =
                'small';

            const parts = [
                substrate.material,
                substrate.orientation,
                substrate.offcut,
                substrate.offcutDirection,
                substrateStatus(
                    substrate
                )
            ].filter(Boolean);

            details.textContent =
                parts.join(' | ');

            row.appendChild(details);


            row.addEventListener(
                'click',
                function() {
                    selectSubstrate(
                        substrate
                    );
                }
            );


            container.appendChild(
                row
            );
        }
    );
}


async function initialiseSubstrates() {

    const container =
        document.getElementById(
            'substrateResults'
        );

    container.innerHTML =
        '<p class="small" style="padding:10px;">' +
        'Loading substrates...' +
        '</p>';


    try {

        const entries =
            await loadSubstrates();


        substrateCatalogState =
            entries.map(
                function(entry) {

                    const data =
                        entry.data || {};

                    return {
                        entryId:
                            entry.entry_id,
                        uploadId:
                            entry.upload_id,
                        entryName:
                            entry.entry_name ||
                            entry.entry_id,
                        labId:
                            data.lab_id ||
                            entry.entry_name ||
                            entry.entry_id,

                        parentSample:

                            data.parent_sample || null,
                        material:
                            data.material_designation ||
                            data.chemical_formula ||
                            '',
                        formula:
                            data.chemical_formula ||
                            '',
                        supplierId:
                            data.supplier_id ||
                            '',
                        crystalId:
                            data.crystal_id ||
                            '',
                        chargeId:
                            data.charge_id ||
                            '',
                        polishing:
                            data.polishing ||
                            '',
                        orientation:
                            data.surface_orientation_label ||
                            '',
                        offcut:
                            data.offcut_label ||
                            '',
                        offcutDirection:
                            data.offcut_direction ||
                            '',
                        asDelivered:
                            Boolean(
                                data.as_delivered
                            ),
                        processed:
                            Boolean(
                                data.processed
                            ),
                        grown:
                            Boolean(
                                data.grown
                            ),
                        geometry:
                            data.geometry || null
                    };
                }
            );


        updateSubstrateFilters();
        renderSubstrateResults();

    } catch (error) {

        console.error(error);

        container.innerHTML =
            '<p class="small" style="padding:10px;">' +
            'Could not load substrates.' +
            '</p>';
    }
}


function initialiseSubstrateFilterEvents() {

    document.getElementById(
        'substrateSearch'
    ).addEventListener(
        'input',
        renderSubstrateResults
    );


    [
        'filterMaterial',
        'filterBatch',
        'filterOrientation',
        'filterOffcut',
        'filterDirection',
        'filterStatus'
    ].forEach(
        function(elementId) {

            document.getElementById(
                elementId
            ).addEventListener(
                'change',
                renderSubstrateResults
            );
        }
    );
}


function treatmentProcessSchema(type) {

    const schemas = {
        cleaning:
            'pdi_nomad_plugin.general.schema.CleaningPDI',
        annealing:
            'pdi_nomad_plugin.general.schema.AnnealingPDI',
        etching:
            'pdi_nomad_plugin.general.schema.EtchingPDI',
        back_side_coating:
            'pdi_nomad_plugin.general.schema.BackSideCoatingPDI'
    };

    return schemas[type] || null;
}


function safeTreatmentPart(value) {

    return String(value || '')
        .trim()
        .replace(/\s+/g, '_')
        .replace(/[^A-Za-z0-9._-]/g, '');
}


function treatmentArchiveData(
    substrate,
    treatment
) {

    const processSchema =
        treatmentProcessSchema(
            treatment.type
        );

    if (!processSchema) {
        throw new Error(
            'Unsupported treatment type: ' +
            treatment.type
        );
    }

    if (
        !substrate.uploadId ||
        !substrate.entryId
    ) {
        throw new Error(
            'Selected substrate has no complete ' +
            'NOMAD reference.'
        );
    }

    if (
        !treatment.recipeUploadId ||
        !treatment.entryId
    ) {
        throw new Error(
            'Treatment recipe has no complete ' +
            'NOMAD reference: ' +
            treatment.name
        );
    }


    let datetime;

    if (treatment.datetime) {
        datetime =
            new Date(
                treatment.datetime
            ).toISOString();
    } else {
        datetime =
            new Date().toISOString();
    }


    const data = {
        m_def:
            processSchema,

        name:
            (
                substrate.labId ||
                substrate.entryName ||
                substrate.entryId
            ) +
            ' - ' +
            treatment.name,

        datetime:
            datetime,

        samples: [
            {
                name:
                    substrate.labId ||
                    substrate.entryName ||
                    substrate.entryId,

                reference:
                    nomadArchiveReference(
                        substrate.uploadId,
                        substrate.entryId
                    )
            }
        ],

        recipe:
            nomadArchiveReference(
                treatment.recipeUploadId,
                treatment.entryId
            )
    };


    if (treatment.notes) {
        data.description =
            treatment.notes;
    }


    return data;
}


function treatmentFilename(
    substrate,
    treatment,
    index
) {

    const substrateName =
        safeTreatmentPart(
            substrate.labId ||
            substrate.entryName ||
            substrate.entryId
        );

    const type =
        safeTreatmentPart(
            treatment.type
        );

    const time =
        new Date()
            .toISOString()
            .replace(/[-:TZ.]/g, '')
            .slice(0, 14);


    return (
        substrateName +
        '_' +
        type +
        '_' +
        time +
        '_' +
        String(index + 1) +
        '.archive.yaml'
    );
}


async function uploadTreatmentArchive(
    uploadId,
    filename,
    data
) {

    const params =
        new URLSearchParams();

    params.append(
        'file_name',
        filename
    );

    params.append(
        'overwrite_if_exists',
        'false'
    );

    params.append(
        'trigger_processing',
        'true'
    );


    const response =
        await fetch(
            nomadApiBase() +
            '/uploads/' +
            encodeURIComponent(
                uploadId
            ) +
            '/raw/?' +
            params.toString(),
            {
                method: 'PUT',
                headers: {
                    'Content-Type':
                        'application/json'
                },
                body: JSON.stringify(
                    {
                        data: data
                    },
                    null,
                    2
                )
            }
        );


    if (!response.ok) {

        let detail = '';

        try {

            const errorData =
                await response.json();

            if (errorData.detail) {
                detail =
                    ': ' +
                    errorData.detail;
            }

        } catch (_) {
        }


        throw new Error(
            'Treatment upload failed (' +
            response.status +
            ')' +
            detail
        );
    }
}


async function savePendingTreatments() {

    const position =
        getActivePosition();

    const status =
        document.getElementById(
            'treatmentSaveStatus'
        );

    const button =
        document.getElementById(
            'saveTreatmentsButton'
        );


    if (
        !position ||
        position.position_usage !==
        'substrate' ||
        !position.substrate
    ) {
        status.textContent =
            'Select a substrate first.';
        return;
    }


    const treatments =
        position.pendingTreatments || [];


    if (treatments.length === 0) {
        status.textContent =
            'No pending treatments to save.';
        return;
    }


    const substrate =
        position.substrate;

    const uploadId =
        document.getElementById(
            'targetUpload'
        ).value;


    if (!uploadId) {
        status.textContent =
            'Select a target upload first.';
        return;
    }


    button.disabled = true;

    const savedTreatments = [];


    try {

        for (
            let index = 0;
            index < treatments.length;
            index++
        ) {

            const treatment =
                treatments[index];

            status.textContent =
                'Saving treatment ' +
                String(index + 1) +
                ' of ' +
                String(treatments.length) +
                ': ' +
                treatment.name +
                '...';


            const data =
                treatmentArchiveData(
                    substrate,
                    treatment
                );

            const filename =
                treatmentFilename(
                    substrate,
                    treatment,
                    index
                );


            await uploadTreatmentArchive(
                uploadId,
                filename,
                data
            );


            savedTreatments.push(
                treatment
            );
        }


        position.pendingTreatments =
            treatments.filter(
                function(treatment) {
                    return (
                        !savedTreatments.includes(
                            treatment
                        )
                    );
                }
            );


        renderTreatmentQueue();
        updateStatePreview();


        status.textContent =
            String(savedTreatments.length) +
            ' treatment(s) saved. ' +
            'NOMAD processing was triggered.';


        /*
         * Reload the history query. Depending on NOMAD
         * processing time, newly written entries may not
         * be indexed immediately.
         */
        try {

            treatmentHistoryState =
                await loadTreatmentHistoryEntries();

            renderTreatmentHistory();

        } catch (historyError) {

            console.warn(
                'Treatment history refresh failed:',
                historyError
            );
        }

    } catch (error) {

        /*
         * Keep treatments that were not saved.
         * Treatments already uploaded are removed from
         * the pending queue to avoid duplicate writes.
         */
        position.pendingTreatments =
            treatments.filter(
                function(treatment) {
                    return (
                        !savedTreatments.includes(
                            treatment
                        )
                    );
                }
            );

        renderTreatmentQueue();
        updateStatePreview();

        status.textContent =
            'Error after saving ' +
            String(savedTreatments.length) +
            ' treatment(s): ' +
            error.message;

    } finally {

        button.disabled =
            false;
    }
}


function initialiseTreatmentSaveControls() {

    if (
        document.getElementById(
            'saveTreatmentsButton'
        )
    ) {
        return;
    }


    const editor =
        document.querySelector(
            '.treatment-editor'
        );

    if (!editor) {
        console.warn(
            'Treatment editor not found.'
        );
        return;
    }


    const button =
        document.createElement(
            'button'
        );

    button.id =
        'saveTreatmentsButton';

    button.type =
        'button';

    button.className =
        'primary';

    button.style.marginTop =
        '12px';

    button.style.width =
        '100%';

    button.textContent =
        'Save treatments to NOMAD';

    button.addEventListener(
        'click',
        savePendingTreatments
    );


    const status =
        document.createElement(
            'p'
        );

    status.id =
        'treatmentSaveStatus';

    status.className =
        'small';

    status.textContent =
        'Treatments will be saved to the ' +
        'selected target upload.';


    editor.appendChild(
        button
    );

    editor.appendChild(
        status
    );
}


async function initialiseTreatmentRecipes() {

    const select =
        document.getElementById(
            'treatmentRecipeSelect'
        );

    const button =
        document.getElementById(
            'addTreatmentButton'
        );

    select.innerHTML =
        '<option value="">Loading treatment recipes...</option>';

    button.disabled = true;

    try {

        const recipes =
            await loadTreatmentRecipes();

        select.innerHTML =
            '<option value="">Select treatment recipe...</option>';


        const groups = {
            cleaning: 'Cleaning',
            annealing: 'Annealing',
            etching: 'Etching',
            back_side_coating:
                'Back-side coating'
        };


        Object.keys(groups).forEach(
            function(type) {

                const recipesOfType =
                    recipes.filter(
                        function(recipe) {
                            return (
                                recipe.type ===
                                type
                            );
                        }
                    );

                if (
                    recipesOfType.length === 0
                ) {
                    return;
                }


                const group =
                    document.createElement(
                        'optgroup'
                    );

                group.label =
                    groups[type];


                recipesOfType.forEach(
                    function(recipe) {

                        const option =
                            document.createElement(
                                'option'
                            );

                        option.value =
                            recipe.entryId;

                        option.textContent =
                            recipe.name;

                        option.dataset.recipeType =
                            recipe.type;

                        option.dataset.recipeSchema =
                            recipe.schema;
                        option.dataset.recipeUploadId =
                            recipe.uploadId || '';

                        group.appendChild(
                            option
                        );
                    }
                );


                select.appendChild(
                    group
                );
            }
        );


        select.addEventListener(
            'change',
            function() {

                button.disabled =
                    !select.value;
            }
        );


        button.addEventListener(
            'click',
            addTreatmentToQueue
        );

    } catch (error) {

        console.error(error);

        select.innerHTML =
            '<option value="">Could not load treatment recipes</option>';

        button.disabled = true;
    }
}


const TARGET_UPLOAD_STORAGE_KEY =
    'new_mbe_target_upload';


function installTargetUploadPersistence() {
    const select =
        document.getElementById(
            'targetUpload'
        );

    if (
        !select ||
        select.dataset.persistenceInstalled === '1'
    ) {
        return;
    }

    select.dataset.persistenceInstalled = '1';

    select.addEventListener(
        'change',
        function() {
            if (select.value) {
                sessionStorage.setItem(
                    TARGET_UPLOAD_STORAGE_KEY,
                    select.value
                );
            } else {
                sessionStorage.removeItem(
                    TARGET_UPLOAD_STORAGE_KEY
                );
            }
        }
    );
}


function restoreTargetUploadSelection() {
    const select =
        document.getElementById(
            'targetUpload'
        );

    if (!select) {
        return;
    }

    const saved =
        sessionStorage.getItem(
            TARGET_UPLOAD_STORAGE_KEY
        );

    if (
        saved &&
        Array.from(select.options).some(
            function(option) {
                return option.value === saved;
            }
        )
    ) {
        select.value = saved;
    }
}


function updateEmptyHolderButton(workflowStatus) {
    const button =
        document.getElementById(
            'emptyHolderButton'
        );

    if (!button) {
        return;
    }

    if (workflowStatus === 'grown') {
        button.textContent =
            'Take off samples';
    } else {
        button.textContent =
            'Empty filled holder';
    }
}


async function loadUploads() {

    const select =
        document.getElementById(
            'targetUpload'
        );

    const status =
        document.getElementById(
            'uploadStatus'
        );

    select.innerHTML =
        '<option value="">' +
        'Loading uploads...' +
        '</option>';

    status.textContent =
        'Loading writable NOMAD uploads...';


    const params =
        new URLSearchParams();

    params.append(
        'roles',
        'main_author'
    );

    params.append(
        'roles',
        'coauthor'
    );

    params.append(
        'page_size',
        '100'
    );


    try {

        const response =
            await fetch(
                nomadApiBase() +
                '/uploads?' +
                params.toString()
            );

        if (!response.ok) {
            throw new Error(
                'Upload request failed: ' +
                response.status
            );
        }


        const result =
            await response.json();

        const uploads =
            (result.data || []).filter(
                function(upload) {
                    return !upload.published;
                }
            );


        select.innerHTML =
            '<option value="">' +
            'Select target upload...' +
            '</option>';


        uploads.forEach(
            function(upload) {

                const option =
                    document.createElement(
                        'option'
                    );

                option.value =
                    upload.upload_id;

                const name =
                    upload.upload_name ||
                    'Unnamed upload';

                const entries =
                    upload.entries !== undefined
                        ? upload.entries
                        : '?';

                option.textContent =
                    name +
                    ' ? ' +
                    upload.upload_id +
                    ' (' +
                    entries +
                    ' entries)';

                select.appendChild(
                    option
                );
            }
        );


        status.textContent =
            String(uploads.length) +
            ' writable unpublished upload(s) ' +
            'available.';

    } catch (error) {

        select.innerHTML =
            '<option value="">' +
            'Could not load uploads' +
            '</option>';

        status.textContent =
            'Error: ' +
            error.message;
    }
}





function getActivePosition() {

    if (
        !experimentState.activePositionName
    ) {
        return null;
    }

    return experimentState.positions[
        experimentState.activePositionName
    ] || null;
}


function referenceEntryId(reference) {

    if (!reference) {
        return null;
    }


    if (
        typeof reference === 'object' &&
        reference.reference
    ) {
        return referenceEntryId(
            reference.reference
        );
    }


    if (typeof reference !== 'string') {
        return null;
    }


    const match =
        reference.match(
            new RegExp(
                '/archive/([^/#]+)'
            )
        );

    return match
        ? match[1]
        : null;
}


function substrateByEntryId(entryId) {

    if (!entryId) {
        return null;
    }

    return (
        substrateCatalogState.find(
            function(substrate) {
                return (
                    substrate.entryId ===
                    entryId
                );
            }
        ) || null
    );
}


function substrateLineage(substrate) {

    const lineage = [];
    const seen = new Set();

    let current =
        substrate;

    while (
        current &&
        current.entryId &&
        !seen.has(
            current.entryId
        )
    ) {

        seen.add(
            current.entryId
        );

        lineage.push(
            current
        );


        const parentEntryId =
            referenceEntryId(
                current.parentSample
            );

        if (!parentEntryId) {
            break;
        }

        current =
            substrateByEntryId(
                parentEntryId
            );
    }


    return lineage;
}


function treatmentHistoryForSubstrate(
    substrate
) {

    const lineage =
        substrateLineage(
            substrate
        );

    const rows = [];


    lineage.forEach(
        function(lineageSubstrate, index) {

            treatmentHistoryState.forEach(
                function(treatment) {

                    if (
                        treatmentReferencesSubstrate(
                            treatment,
                            lineageSubstrate.entryId
                        )
                    ) {

                        rows.push({
                            treatment:
                                treatment,

                            substrate:
                                lineageSubstrate,

                            inherited:
                                index > 0
                        });
                    }
                }
            );
        }
    );


    rows.sort(
        function(a, b) {

            const dateA =
                treatmentDate(
                    a.treatment
                );

            const dateB =
                treatmentDate(
                    b.treatment
                );

            return String(
                dateA
            ).localeCompare(
                String(dateB)
            );
        }
    );


    return rows;
}


function renderTreatmentHistory() {

    const container =
        document.getElementById(
            'treatmentHistory'
        );

    container.innerHTML = '';

    const position =
        getActivePosition();


    if (
        !position ||
        !position.substrate
    ) {

        const empty =
            document.createElement(
                'p'
            );

        empty.className =
            'small';

        empty.textContent =
            'Select a substrate to view its history.';

        container.appendChild(
            empty
        );

        return;
    }


    const substrate =
        position.substrate;

    const lineage =
        substrateLineage(
            substrate
        );

    const history =
        treatmentHistoryForSubstrate(
            substrate
        );


    if (lineage.length > 1) {

        const lineageInfo =
            document.createElement(
                'p'
            );

        lineageInfo.className =
            'small';

        lineageInfo.textContent =
            'Substrate lineage: ' +
            lineage
                .slice()
                .reverse()
                .map(
                    function(item) {
                        return (
                            item.labId ||
                            item.entryName ||
                            item.entryId
                        );
                    }
                )
                .join(' ? ');

        container.appendChild(
            lineageInfo
        );
    }


    if (history.length === 0) {

        const empty =
            document.createElement(
                'p'
            );

        empty.className =
            'small';

        empty.textContent =
            'No treatment history found.';

        container.appendChild(
            empty
        );

        return;
    }


    history.forEach(
        function(row) {

            const treatment =
                row.treatment;

            const item =
                document.createElement(
                    'div'
                );

            item.className =
                'treatment-history-item';


            const title =
                document.createElement(
                    'div'
                );

            title.textContent =
                treatment.label +
                ': ' +
                (
                    treatment.recipeName ||
                    treatment.entryName
                );

            item.appendChild(
                title
            );


            if (row.inherited) {

                const inherited =
                    document.createElement(
                        'div'
                    );

                inherited.className =
                    'small';

                inherited.textContent =
                    'Inherited from ' +
                    (
                        row.substrate.labId ||
                        row.substrate.entryName ||
                        row.substrate.entryId
                    );

                item.appendChild(
                    inherited
                );
            }


            const date =
                treatmentDate(
                    treatment
                );

            if (date) {

                const dateElement =
                    document.createElement(
                        'div'
                    );

                dateElement.className =
                    'treatment-history-date';

                dateElement.textContent =
                    date;

                item.appendChild(
                    dateElement
                );
            }


            container.appendChild(
                item
            );
        }
    );
}


async function initialiseTreatmentHistory() {

    try {

        treatmentHistoryState =
            await loadTreatmentHistoryEntries();

        renderTreatmentHistory();

    } catch (error) {

        console.error(error);

        const container =
            document.getElementById(
                'treatmentHistory'
            );

        container.innerHTML =
            '<p class="small">' +
            'Could not load treatment history.' +
            '</p>';
    }
}





function setDefaultTreatmentDateTime() {

    const input =
        document.getElementById(
            'treatmentDateTime'
        );

    if (!input || input.value) {
        return;
    }

    const now = new Date();

    const local =
        new Date(
            now.getTime() -
            now.getTimezoneOffset() * 60000
        )
            .toISOString()
            .slice(0, 16);

    input.value = local;
}


function addTreatmentToQueue() {

    const position =
        getActivePosition();

    if (
        !position ||
        position.position_usage !==
        'substrate'
    ) {
        return;
    }


    const select =
        document.getElementById(
            'treatmentRecipeSelect'
        );

    if (!select.value) {
        return;
    }


    const option =
        select.options[
            select.selectedIndex
        ];


    const treatmentDateTime =
        document.getElementById(
            'treatmentDateTime'
        ).value;

    const treatmentNotes =
        document.getElementById(
            'treatmentNotes'
        ).value.trim();


    if (!position.pendingTreatments) {
        position.pendingTreatments = [];
    }


    const exists =
        position.pendingTreatments.some(
            function(item) {
                return (
                    item.entryId ===
                    select.value
                );
            }
        );


    if (!exists) {

        position.pendingTreatments.push({
            entryId:
                select.value,
            name:
                option.textContent,
            type:
                option.dataset.recipeType,
            schema:
                option.dataset.recipeSchema,
            recipeUploadId:
                option.dataset.recipeUploadId,
            datetime:
                treatmentDateTime || null,
            notes:
                treatmentNotes || null
        });
    }


    select.value = '';


    document.getElementById(
        'treatmentDateTime'
    ).value = '';

    document.getElementById(
        'treatmentNotes'
    ).value = '';

    document.getElementById(
        'addTreatmentButton'
    ).disabled = true;


    renderTreatmentQueue();
    updateStatePreview();
}


function updateGrowthRunId() {

    experimentState.growthRunId =
        document
            .getElementById('growthRunId')
            .value
            .trim();

    updateCombinedId();
    updateStatePreview();
}


async function loadHolderArchive(entryId) {

    const response = await fetch(
        nomadApiBase() +
        '/entries/' +
        encodeURIComponent(entryId) +
        '/archive/query',
        {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                required: '*'
            })
        }
     );

    if (!response.ok) {
        throw new Error(
            'Holder archive query failed: ' +
            response.status
        );
    }

    const result = await response.json();
    const archive =
        result &&
        result.data &&
        result.data.archive;

    if (!archive || !archive.data) {
        throw new Error(
            'Holder archive response has no archive.data.'
        );
    }

    return archive;
}













function experimentSafePart(value) {

    return String(value || '')
        .trim()
        .replace(/\s+/g, '_')
        .replace(/[^A-Za-z0-9._@-]/g, '');
}


async function archiveEntryId(
    uploadId,
    filename
) {

    const params =
        new URLSearchParams();

    params.append(
        'upload_id',
        uploadId
    );

    params.append(
        'filename',
        filename
    );

    const response =
        await fetch(
            'api/entry-id?' +
            params.toString()
        );

    if (!response.ok) {
        throw new Error(
            'Could not calculate NOMAD entry ID (' +
            response.status +
            ').'
        );
    }

    const result =
        await response.json();

    if (!result.entry_id) {
        throw new Error(
            'NOMAD entry ID is missing.'
        );
    }

    return result.entry_id;
}


async function uploadArchiveData(
    uploadId,
    filename,
    data
) {

    const params =
        new URLSearchParams();

    params.append(
        'file_name',
        filename
    );

    params.append(
        'overwrite_if_exists',
        'false'
    );

    params.append(
        'trigger_processing',
        'true'
    );


    const response =
        await fetch(
            nomadApiBase() +
            '/uploads/' +
            encodeURIComponent(
                uploadId
            ) +
            '/raw/?' +
            params.toString(),
            {
                method: 'PUT',
                headers: {
                    'Content-Type':
                        'application/json'
                },
                body: JSON.stringify(
                    {
                        data: data
                    },
                    null,
                    2
                )
            }
        );


    if (!response.ok) {

        let detail = '';

        try {

            const errorData =
                await response.json();

            if (errorData.detail) {
                detail =
                    ': ' +
                    errorData.detail;
            }

        } catch (_) {
        }

        throw new Error(
            'Archive upload failed (' +
            response.status +
            ')' +
            detail
        );
    }
}





function experimentArchiveData(
    filledHolderReference
) {

    const growthRunId =
        experimentState.growthRunId;

    return {
        m_def:
            'pdi_nomad_plugin.mbe.processes.' +
            'ExperimentMbePDI',

        name:
            growthRunId,

        lab_id:
            growthRunId,

        nominal_layers:
            nominalLayerArchiveData(),

        substrate_holder: {
            reference:
                filledHolderReference
        }
    };
}





function updateStatePreview() {

    document.getElementById(
        'statePreview'
    ).textContent =
        JSON.stringify(
            experimentState,
            null,
            2
        );
}



/* -------------------------------------------------------------------------
 * MBE holder workflow v2
 *
 * Source of truth:
 * - physical holder geometry: SubstrateHolderPDI archive
 * - current loadout: unreferenced FilledSubstrateHolderPDI
 * - historical loadout: FilledSubstrateHolderPDI referenced by ExperimentMbePDI
 *
 * No holder layout names are hard-coded here. Geometry is rendered from the
 * positions stored in the physical holder archive.
 * ------------------------------------------------------------------------- */

let holderCatalogState = {
    empty: [],
    filled: [],
    experiments: [],
    current: []
};
let insertCatalogState = [];


// FIX: /entries/query (the plain search endpoint) only accepts pre-indexed
// "doc quantities" in required.include (entry_id, upload_id, results.*, ...).
// It cannot return archive content like data.lab_id -- NOMAD rejects that
// with 422 "data.lab_id is not a doc quantity". Archive content (anything
// under "data") has to come from /entries/archive/query instead, which
// takes a nested required shape: {metadata: {...}, data: {...}}.
//
// To avoid touching every call site, this still accepts the same flat
// 'include' list callers already pass (e.g. ['entry_id', 'upload_id',
// 'entry_name', 'data.lab_id', 'mainfile']) and splits it internally:
// entry_id/upload_id are always present on the result already, 'data.x'
// entries go under required.data, everything else (entry_name, mainfile,
// published, ...) goes under required.metadata. The returned objects keep
// the exact same shape callers already expect (entry.data.x, entry.entry_name, ...).
async function queryEntriesBySchema(schema, pageSize, include) {
    const fields = include || ['entry_id', 'upload_id', 'entry_name'];
    const metadataRequired = {};
    const dataRequired = {};

    let wantsFullData = false;
    for (const field of fields) {
        if (field === 'entry_id' || field === 'upload_id') {
            continue;
        }
        if (field === 'data') {
            // Bare 'data' means 'the whole data section'.
            wantsFullData = true;
        } else if (field.startsWith('data.')) {
            dataRequired[field.slice('data.'.length)] = '*';
        } else {
            metadataRequired[field] = '*';
        }
    }

    const required = {};
    if (Object.keys(metadataRequired).length) {
        required.metadata = metadataRequired;
    }
    if (wantsFullData) {
        required.data = '*';
    } else if (Object.keys(dataRequired).length) {
        required.data = dataRequired;
    }

    const response = await fetch(
        nomadApiBase() + '/entries/archive/query',
        {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                // FIX: without an explicit owner NOMAD defaults to owner="public",
                // which only returns PUBLISHED entries. Lab data lives in unpublished
                // uploads, so every query came back empty. "visible" = public + everything
                // the logged-in user can see (login is sent automatically via cookie).
                owner: 'visible',
                query: {
                    'section_defs.definition_qualified_name': schema
                },
                pagination: {page_size: pageSize || 500},
                required: required
            })
        }
    );
    if (!response.ok) {
        throw new Error('NOMAD query failed for ' + schema + ': ' + response.status);
    }
    const result = await response.json();
    return (result.data || []).map(function(entry) {
        const archive = entry.archive || {};
        return Object.assign(
            {
                entry_id: entry.entry_id,
                upload_id: entry.upload_id,
                data: archive.data || {}
            },
            archive.metadata || {}
        );
    });
}


async function queryExperimentHolderReferences() {
    const response = await fetch(
        nomadApiBase() + '/entries/archive/query',
        {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                // FIX: without an explicit owner NOMAD defaults to owner="public",
                // which only returns PUBLISHED entries. Lab data lives in unpublished
                // uploads, so every query came back empty. "visible" = public + everything
                // the logged-in user can see (login is sent automatically via cookie).
                owner: 'visible',
                query: {
                    'section_defs.definition_qualified_name':
                        'pdi_nomad_plugin.mbe.processes.ExperimentMbePDI'
                },
                pagination: {page_size: 1000},
                required: {
                    data: {
                        substrate_holder: {
                            reference: '*'
                        }
                    }
                }
            })
        }
    );

    if (!response.ok) {
        throw new Error(
            'Experiment holder-reference query failed: ' +
            response.status
        );
    }

    const result = await response.json();
    return (result.data || []).map(function(entry) {
        const archive = entry.archive || {};
        return {
            entry_id: entry.entry_id,
            upload_id: entry.upload_id,
            data: archive.data || {}
        };
    });
}


function entryIdFromReference(reference) {
    if (!reference) return null;
    if (typeof reference === 'object') {
        reference = reference.reference || '';
    }
    const match = String(reference).match(/\/archive\/([^/#?]+)(?:#|$)/);
    return match ? match[1] : null;
}


function referenceValue(value) {
    if (!value) return '';
    if (typeof value === 'string') return value;
    return value.reference || '';
}


function filledPhysicalReference(data) {
    return referenceValue(data && data.substrate_holder);
}


function isDiscardedLoadout(data) {
    const tags = data && Array.isArray(data.tags) ? data.tags : [];
    return tags.includes('discarded_loadout');
}


const HOLDER_WORKFLOW_STATES = [
    'empty',
    'ungrown',
    'grown'
];


function holderWorkflowStatus(data) {
    const tags =
        data && Array.isArray(data.tags)
            ? data.tags
            : [];

    if (tags.includes('grown')) {
        return 'grown';
    }

    if (tags.includes('ungrown')) {
        return 'ungrown';
    }

    if (tags.includes('empty')) {
        return 'empty';
    }

    // Legacy physical holders without a workflow tag
    // are treated as available until they enter the
    // new workflow for the first time.
    return 'empty';
}


function filledHolderTimestamp(entry) {
    const data = entry && entry.data
        ? entry.data
        : {};

    const value = Date.parse(
        data.datetime || ''
    );

    return Number.isFinite(value)
        ? value
        : 0;
}


function physicalHolderCatalogKey(entry) {
    const data = entry.data || {};

    return String(
        data.lab_id ||
        data.name ||
        entry.entry_name ||
        entry.entry_id ||
        ''
    ).trim();
}


function canonicalPhysicalHolders(
    holders,
    currentByPhysical
) {
    const byLabId =
        new Map();

    holders.forEach(function(entry) {
        const key =
            physicalHolderCatalogKey(
                entry
            );

        if (!key) {
            return;
        }

        function score(candidate) {
            const data =
                candidate.data || {};

            const positions =
                Array.isArray(
                    data.positions
                )
                    ? data.positions
                    : [];

            const workflowStatus =
                holderWorkflowStatus(
                    data
                );

            const hasCurrentSnapshot =
                currentByPhysical.has(
                    candidate.entry_id
                );

            let value =
                positions.length;

            /*
             * A holder referenced by the current,
             * non-discarded loadout is authoritative.
             */
            if (hasCurrentSnapshot) {
                value += 100000;
            }

            /*
             * A non-empty workflow status without a
             * matching current snapshot is inconsistent.
             * Prefer a clean empty physical definition.
             */
            if (
                workflowStatus === 'empty'
            ) {
                value += 1000;
            } else if (
                !hasCurrentSnapshot
            ) {
                value -= 10000;
            }

            return value;
        }

        const previous =
            byLabId.get(key);

        if (
            !previous ||
            score(entry) >
                score(previous)
        ) {
            byLabId.set(
                key,
                entry
            );
        }
    });

    return Array.from(
        byLabId.values()
    );
}


async function loadHolderCatalogV2() {
    const [holdersRaw, filledRaw] =
        await Promise.all([
            queryEntriesBySchema(
                'pdi_nomad_plugin.mbe.instrument.SubstrateHolderPDI',
                500,
                [
                    'entry_id',
                    'upload_id',
                    'entry_name',
                    'data',
                    'mainfile',
                    'published'
                ]
            ),
            queryEntriesBySchema(
                'pdi_nomad_plugin.mbe.instrument.FilledSubstrateHolderPDI',
                500,
                [
                    'entry_id',
                    'upload_id',
                    'entry_name',
                    'data',
                    'mainfile',
                    'published'
                ]
            )
        ]);

    const physicalCandidates =
        holdersRaw.filter(
            function(entry) {
                const data =
                    entry.data || {};

                const mDef =
                    String(
                        data.m_def || ''
                    );

                /*
                 * FilledSubstrateHolderPDI inherits from
                 * SubstrateHolderPDI, therefore guard both
                 * by m_def and by substrate_holder reference.
                 */
                return (
                    !mDef.includes(
                        'FilledSubstrateHolderPDI'
                    ) &&
                    !data.substrate_holder
                );
            }
        );

    const filled =
        filledRaw.filter(
            function(entry) {
                const mDef =
                    String(
                        (entry.data || {}).m_def ||
                        ''
                    );

                return (
                    !mDef ||
                    mDef.includes(
                        'FilledSubstrateHolderPDI'
                    )
                );
            }
        );

    /*
     * Map only CURRENT, non-discarded loadouts
     * back to their exact physical holder entry.
     */
    const currentByPhysical =
        new Map();

    filled.forEach(function(entry) {
        const data =
            entry.data || {};

        if (
            isDiscardedLoadout(data)
        ) {
            return;
        }

        const physicalId =
            entryIdFromReference(
                filledPhysicalReference(
                    data
                )
            );

        if (!physicalId) {
            return;
        }

        const previous =
            currentByPhysical.get(
                physicalId
            );

        if (
            !previous ||
            filledHolderTimestamp(entry) >
                filledHolderTimestamp(
                    previous
                )
        ) {
            currentByPhysical.set(
                physicalId,
                entry
            );
        }
    });

    /*
     * One physical holder per logical lab_id.
     */
    const holders =
        canonicalPhysicalHolders(
            physicalCandidates,
            currentByPhysical
        );

    const canonicalIds =
        new Set(
            holders.map(
                function(entry) {
                    return entry.entry_id;
                }
            )
        );

    /*
     * Only current snapshots belonging to the selected
     * canonical physical holders remain relevant.
     */
    const canonicalCurrentByPhysical =
        new Map();

    currentByPhysical.forEach(
        function(entry, physicalId) {
            if (
                canonicalIds.has(
                    physicalId
                )
            ) {
                canonicalCurrentByPhysical.set(
                    physicalId,
                    entry
                );
            }
        }
    );

    const current =
        Array.from(
            canonicalCurrentByPhysical.values()
        );

    holderCatalogState = {
        holders: holders,

        // retained for compatibility
        empty: holders,

        filled: filled,
        experiments: [],
        current: current,
        currentByPhysical:
            canonicalCurrentByPhysical
    };

    return holderCatalogState;
}

async function loadInsertCatalogV2() {
    try {
        const entries = await queryEntriesBySchema(
            'pdi_nomad_plugin.mbe.instrument.InsertReductionPDI',
            200,
            [
                'entry_id',
                'upload_id',
                'entry_name',
                'data.lab_id',
                'data.name',
                'data.inner_geometry',
                'data.outer_geometry'
            ]
        );

        insertCatalogState = entries.map(function(entry) {
            const data = entry.data || {};

            return {
                entryId: entry.entry_id,
                uploadId: entry.upload_id,
                name:
                    data.lab_id ||
                    data.name ||
                    entry.entry_name ||
                    entry.entry_id,
                innerGeometry:
                    data.inner_geometry || null,
                outerGeometry:
                    data.outer_geometry || null
            };
        });

    } catch (error) {
        console.warn(
            'InsertReductionPDI catalog could not be loaded.',
            error
        );

        insertCatalogState = [];
    }
}


function holderDisplayStatus(workflowStatus, hasFilledHolder) {
    if (workflowStatus === 'empty') {
        return 'empty';
    }

    if (hasFilledHolder) {
        return 'filled · ' + workflowStatus;
    }

    return workflowStatus;
}


async function initialiseHolderSelect() {
    const select =
        document.getElementById(
            'holderSelect'
        );

    const status =
        document.getElementById(
            'holderCatalogStatus'
        );

    select.innerHTML =
        '<option value="">Loading holders...</option>';

    if (status) {
        status.textContent =
            'Loading physical holders from NOMAD...';
    }

    try {
        const catalog =
            await loadHolderCatalogV2();

        await loadInsertCatalogV2();

        select.innerHTML =
            '<option value="">Select holder...</option>';

        const counts = {
            empty: 0,
            ungrown: 0,
            grown: 0
        };

        catalog.holders
            .slice()
            .sort(function(a, b) {
                const aData = a.data || {};
                const bData = b.data || {};

                const aName =
                    aData.lab_id ||
                    aData.name ||
                    a.entry_name ||
                    a.entry_id;

                const bName =
                    bData.lab_id ||
                    bData.name ||
                    b.entry_name ||
                    b.entry_id;

                return String(aName)
                    .localeCompare(
                        String(bName),
                        undefined,
                        {
                            numeric: true,
                            sensitivity: 'base'
                        }
                    );
            })
            .forEach(function(entry) {
                const data =
                    entry.data || {};

                const workflowStatus =
                    holderWorkflowStatus(
                        data
                    );

                counts[workflowStatus] += 1;

                const currentFilled =
                    catalog.currentByPhysical.get(
                        entry.entry_id
                    );

                const holderName =
                    data.lab_id ||
                    data.name ||
                    entry.entry_name ||
                    entry.entry_id;

                const option =
                    document.createElement(
                        'option'
                    );

                /*
                 * IMPORTANT:
                 * The option always points to the
                 * PHYSICAL SubstrateHolderPDI.
                 */
                option.value =
                    entry.entry_id;

                option.dataset.kind =
                    'physical';

                option.dataset.status =
                    workflowStatus;

                option.dataset.uploadId =
                    entry.upload_id || '';

                option.dataset.filledEntryId =
                    (
                        workflowStatus !== 'empty' &&
                        currentFilled
                    )
                        ? currentFilled.entry_id
                        : '';

                option.textContent =
                    holderName +
                    ' — ' +
                    holderDisplayStatus(
                        workflowStatus,
                        Boolean(currentFilled)
                    );

                select.appendChild(
                    option
                );
            });

        if (status) {
            status.textContent =
                catalog.holders.length +
                ' physical holder(s): ' +
                counts.empty +
                ' empty, ' +
                counts.ungrown +
                ' ungrown, ' +
                counts.grown +
                ' grown.';
        }

    } catch (error) {
        console.error(error);

        select.innerHTML =
            '<option value="">Could not load holders</option>';

        if (status) {
            status.textContent =
                'Error: ' +
                error.message;
        }
    }
}

function makePositionState(position) {
    return {
        position_usage: null,
        substrate: null,
        insertReduction: null,
        pendingTreatments: [],
        rho: position.rho,
        theta: position.theta,
        x_position: position.x_position,
        y_position: position.y_position,
        slot_geometry: position.slot_geometry || null
    };
}


function resolveSubstrateFromFilled(position) {
    const substrateRef = position && position.substrate;
    const reference = referenceValue(substrateRef);
    const entryId = entryIdFromReference(reference);
    if (!entryId) return null;
    const known = substrateCatalogState.find(function(item) {
        return item.entryId === entryId;
    });
    if (known) return Object.assign({}, known);
    return {
        entryId: entryId,
        uploadId: '',
        entryName: substrateRef && substrateRef.name ? substrateRef.name : entryId,
        labId: substrateRef && substrateRef.name ? substrateRef.name : entryId,
        reference: reference
    };
}


function resolveInsertFromFilled(position) {
    const insert = position && position.insert_reduction;
    const reference = referenceValue(insert);
    const entryId = entryIdFromReference(reference);
    if (!entryId) return null;
    const known = insertCatalogState.find(function(item) {
        return item.entryId === entryId;
    });
    if (known) return Object.assign({}, known);
    return {
        entryId: entryId,
        uploadId: '',
        name: insert && insert.name ? insert.name : entryId,
        reference: reference
    };
}


function applyFilledOverlay(filledData) {
    const filledPositions = Array.isArray(filledData.positions) ? filledData.positions : [];
    filledPositions.forEach(function(item) {
        if (!item.name || !experimentState.positions[item.name]) return;
        const target = experimentState.positions[item.name];
        target.position_usage = item.position_usage || (item.substrate ? 'substrate' : null);
        target.substrate = resolveSubstrateFromFilled(item);
        target.insertReduction = resolveInsertFromFilled(item);
    });
}


async function selectHolder() {
    const select =
        document.getElementById(
            'holderSelect'
        );

    const entryId =
        select.value;

    const option =
        select.options[
            select.selectedIndex
        ];

    if (!entryId) {
        resetHolderSelection(false);
        return;
    }

    document
        .getElementById(
            'holderLabel'
        )
        .textContent =
        'Loading holder...';

    document
        .getElementById(
            'holderGrid'
        )
        .innerHTML =
        '<p class="small">Loading holder archive...</p>';

    try {
        /*
         * Holder selection now ALWAYS starts
         * from the physical SubstrateHolderPDI.
         */
        const physicalArchive =
            await loadHolderArchive(
                entryId
            );

        const physicalData =
            physicalArchive.data || {};

        const physicalMetadata =
            physicalArchive.metadata || {};

        const workflowStatus =
            holderWorkflowStatus(
                physicalData
            );

        const holderName =
            physicalData.lab_id ||
            physicalData.name ||
            option.textContent ||
            entryId;

        const positions =
            Array.isArray(
                physicalData.positions
            )
                ? physicalData.positions
                : [];

        let filledHolder = null;

        /*
         * For occupied holders the physical holder
         * remains the selectable object.
         *
         * The FilledSubstrateHolderPDI is loaded only
         * as the current occupancy snapshot.
         */
        const filledEntryId =
            option.dataset.filledEntryId ||
            '';

        if (
            workflowStatus !== 'empty' &&
            filledEntryId
        ) {
            const filledArchive =
                await loadHolderArchive(
                    filledEntryId
                );

            const filledData =
                filledArchive.data || {};

            const filledMetadata =
                filledArchive.metadata || {};

            filledHolder = {
                entryId:
                    filledEntryId,

                uploadId:
                    filledMetadata.upload_id ||
                    '',

                name:
                    filledData.name ||
                    filledEntryId,

                mainfile:
                    filledMetadata.mainfile ||
                    '',

                published:
                    filledMetadata.published ===
                    true,

                data:
                    filledData,

                metadata:
                    filledMetadata
            };
        }

        if (
            workflowStatus !== 'empty' &&
            !filledHolder
        ) {
            throw new Error(
                'Holder is marked "' +
                workflowStatus +
                '" but no current filled-holder snapshot could be resolved.'
            );
        }

        experimentState.holder = {
            id:
                holderName,

            entryId:
                entryId,

            uploadId:
                physicalMetadata.upload_id ||
                option.dataset.uploadId ||
                '',

            archiveData:
                physicalData,

            metadata:
                physicalMetadata,

            filledHolder:
                filledHolder,

            selectedKind:
                'physical',

            workflowStatus:
                workflowStatus
        };

        updateEmptyHolderButton(
            workflowStatus
        );

        experimentState.positions = {};

        positions.forEach(
            function(position) {
                if (position.name) {
                    experimentState.positions[
                        position.name
                    ] =
                        makePositionState(
                            position
                        );
                }
            }
        );

        if (filledHolder) {
            applyFilledOverlay(
                filledHolder.data
            );
        }

        experimentState.activePositionName =
            null;

        experimentState.currentFilledDirty =
            false;

        experimentState.experimentSaved =
            false;

        document
            .getElementById(
                'holderLabel'
            )
            .textContent =
            holderName +
            ' · ' +
            holderDisplayStatus(
                workflowStatus,
                Boolean(filledHolder)
            );

        renderHolderImageV2();
        renderHolder();

        document
            .getElementById(
                'substratePicker'
            )
            .style.display =
            'none';

        updateCombinedId();
        updateStatePreview();

    } catch (error) {
        console.error(error);

        resetHolderSelection(false);

        document
            .getElementById(
                'holderLabel'
            )
            .textContent =
            'Could not load holder';

        document
            .getElementById(
                'holderGrid'
            )
            .innerHTML =
            '<div class="warning">' +
            'Could not load holder data from NOMAD: ' +
            escapeHtml(
                String(
                    error.message ||
                    error
                )
            ) +
            '</div>';
    }
}

function escapeHtml(value) {
    return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}


function holderRawFileUrl(imagePath) {
    if (!experimentState.holder || !imagePath) return '';
    let rawPath = String(imagePath).replace(/^\.\//, '');
    const mainfile = String((experimentState.holder.metadata || {}).mainfile || '');
    if (!rawPath.includes('/') && mainfile.includes('/')) {
        rawPath = mainfile.slice(0, mainfile.lastIndexOf('/') + 1) + rawPath;
    }
    const encodedPath = rawPath.split('/').map(encodeURIComponent).join('/');
    return nomadApiBase() + '/uploads/' +
        encodeURIComponent(experimentState.holder.uploadId) + '/raw/' + encodedPath;
}


function renderHolderImageV2() {
    const wrap = document.getElementById('holderImageWrap');
    const image = document.getElementById('holderImage');
    if (!wrap || !image || !experimentState.holder) return;
    const imagePath = experimentState.holder.archiveData && experimentState.holder.archiveData.image;
    if (!imagePath) {
        wrap.style.display = 'none';
        image.removeAttribute('src');
        return;
    }
    image.onload = function() { wrap.style.display = 'block'; };
    image.onerror = function() { wrap.style.display = 'none'; };
    image.src = holderRawFileUrl(imagePath);
}


function positionCoordinates(position) {
    /*
     * Holder positions are defined by polar coordinates.
     * Rho + Theta are authoritative.
     *
     * x_position / y_position are retained only as
     * a legacy fallback for older holder definitions.
     */
    const rho =
        Number(
            position.rho
        );

    const theta =
        Number(
            position.theta
        );

    if (
        Number.isFinite(rho) &&
        Number.isFinite(theta)
    ) {
        const rad =
            theta *
            Math.PI /
            180;

        return {
            x:
                rho *
                Math.cos(rad),

            y:
                rho *
                Math.sin(rad)
        };
    }

    const x =
        Number(
            position.x_position
        );

    const y =
        Number(
            position.y_position
        );

    if (
        Number.isFinite(x) &&
        Number.isFinite(y)
    ) {
        return {
            x:
                x,
            y:
                y
        };
    }

    return {
        x: 0,
        y: 0
    };
}

function geometryNumber(value) {
    if (
        typeof value === 'number' &&
        Number.isFinite(value)
    ) {
        return value;
    }

    if (
        value &&
        typeof value === 'object' &&
        typeof value.magnitude === 'number' &&
        Number.isFinite(value.magnitude)
    ) {
        return value.magnitude;
    }

    const parsed = Number(value);

    return Number.isFinite(parsed)
        ? parsed
        : null;
}


function geometryXY(geometry) {
    if (
        !geometry ||
        typeof geometry !== 'object'
    ) {
        return null;
    }

    const width =
        geometryNumber(geometry.width);

    let length =
        geometryNumber(geometry.length);

    if (!Number.isFinite(width)) {
        return null;
    }

    if (!Number.isFinite(length)) {
        length = width;
    }

    return {
        width: width,
        length: length
    };
}


function geometryMatches(first, second) {
    const a = geometryXY(first);
    const b = geometryXY(second);

    if (!a || !b) {
        return false;
    }

    const tolerance = 0.00005;

    const direct =
        Math.abs(a.width - b.width) <= tolerance &&
        Math.abs(a.length - b.length) <= tolerance;

    const rotated =
        Math.abs(a.width - b.length) <= tolerance &&
        Math.abs(a.length - b.width) <= tolerance;

    return direct || rotated;
}


function fallbackHolderSlotGeometry() {
    const holder =
        experimentState.holder || {};

    const holderId =
        String(
            holder.id ||
            holder.labId ||
            holder.name ||
            ''
        ).trim();

    if (holderId.endsWith('_10')) {
        return {
            width: 0.01,
            length: 0.01
        };
    }

    if (holderId.endsWith('_20')) {
        return {
            width: 0.02,
            length: 0.02
        };
    }

    return null;
}


function positionSlotGeometry(position) {
    const explicitGeometry =
        position
            ? position.slot_geometry
            : null;

    if (geometryXY(explicitGeometry)) {
        return explicitGeometry;
    }

    return fallbackHolderSlotGeometry();
}


function effectivePositionGeometry(position) {
    if (
        position &&
        position.insertReduction &&
        position.insertReduction.innerGeometry
    ) {
        return position.insertReduction.innerGeometry;
    }

    return positionSlotGeometry(position);
}


function insertFitsPosition(insert, position) {
    if (!insert || !position) {
        return false;
    }

    const slotGeometry =
        positionSlotGeometry(position);

    /*
     * Never offer an insert when the physical slot
     * geometry is unknown. Otherwise an oversized
     * insert could be offered for an incompatible
     * holder position.
     */
    if (!geometryXY(slotGeometry)) {
        return false;
    }

    if (!geometryXY(insert.outerGeometry)) {
        return false;
    }

    return geometryMatches(
        insert.outerGeometry,
        slotGeometry
    );
}


function substrateFitsPosition(substrate, position) {
    if (!substrate || !position) {
        return false;
    }

    const target =
        effectivePositionGeometry(position);

    if (!geometryXY(target)) {
        return true;
    }

    if (!geometryXY(substrate.geometry)) {
        return false;
    }

    return geometryMatches(
        substrate.geometry,
        target
    );
}


function insertWindowPercent(position) {
    if (
        !position ||
        !position.insertReduction
    ) {
        return null;
    }

    const inner =
        geometryXY(
            position.insertReduction.innerGeometry
        );

    const outer =
        geometryXY(
            position.insertReduction.outerGeometry
        );

    if (!inner || !outer) {
        return null;
    }

    if (
        outer.width <= 0 ||
        outer.length <= 0
    ) {
        return null;
    }

    return {
        width: Math.max(
            10,
            Math.min(
                100,
                100 * inner.width / outer.width
            )
        ),
        height: Math.max(
            10,
            Math.min(
                100,
                100 * inner.length / outer.length
            )
        )
    };
}


function positionDisplayState(position) {
    if (!position.position_usage) return 'empty';
    if (position.position_usage === 'substrate') {
        return position.substrate ? (position.substrate.labId || position.substrate.entryName || 'Substrate') : 'Select substrate';
    }
    if (position.position_usage === 'si_dummy') return 'Si dummy';
    if (position.position_usage === 'sapphire_dummy') return 'Sapphire / Al₂O₃ dummy';
    return position.position_usage;
}


function selectHolderPosition(positionName) {
    if (!experimentState.positions[positionName]) return;
    experimentState.activePositionName = positionName;
    renderHolder();
    const position = experimentState.positions[positionName];
    const picker = document.getElementById('substratePicker');
    const label = document.getElementById('activePositionLabel');
    if (label) label.textContent = 'Active holder position: ' + positionName;
    picker.style.display = position.position_usage === 'substrate' ? 'block' : 'none';
    if (position.position_usage === 'substrate') {
        renderSubstrateResults();
        renderTreatmentHistory();
    }
    updateProcessingButtonV2();
}


function renderHolder() {
    const grid = document.getElementById('holderGrid');

    const positionControlsPanel =
        document.getElementById('positionControlsPanel');
    grid.innerHTML = '';

    if (positionControlsPanel) {
        positionControlsPanel.innerHTML = '';
    }
    if (!experimentState.holder) return;

    const names = Object.keys(experimentState.positions);
    if (!names.length) {
        grid.innerHTML = '<div class="warning">This physical holder has no positions in NOMAD.</div>';
        return;
    }

    const disc = document.createElement('div');
    disc.className = 'holder-disc holder-disc-generic';
    const coords = names.map(function(name) {
        return {name: name, coord: positionCoordinates(experimentState.positions[name])};
    });
    let maxRadius = 0;
    coords.forEach(function(item) {
        maxRadius = Math.max(maxRadius, Math.hypot(item.coord.x, item.coord.y));
    });
    if (!maxRadius) maxRadius = 1;

    coords.forEach(function(item) {
        const position = experimentState.positions[item.name];
        const slot = document.createElement('button');
        slot.type = 'button';
        slot.className = 'holder-slot generic-slot';
        if (position.position_usage) slot.classList.add('active');
        if (position.position_usage && position.position_usage !== 'substrate') slot.classList.add('si-dummy');
        if (experimentState.activePositionName === item.name) slot.classList.add('selected-position');
        slot.style.left = (50 + 36 * item.coord.x / maxRadius) + '%';
        slot.style.top = (50 + 36 * item.coord.y / maxRadius) + '%';
        slot.innerHTML =
            '<span class="holder-slot-name">' + escapeHtml(item.name) + '</span>' +
            '<span class="holder-slot-state">' + escapeHtml(positionDisplayState(position)) + '</span>';

        const insertSize = insertWindowPercent(position);

        if (insertSize) {
            const insertWindow = document.createElement('span');
            insertWindow.className = 'holder-insert-window';
            insertWindow.style.width = insertSize.width + '%';
            insertWindow.style.height = insertSize.height + '%';
            slot.appendChild(insertWindow);
        }

        slot.addEventListener('click', function() {
            selectHolderPosition(item.name);
        });
        disc.appendChild(slot);
    });

    grid.appendChild(disc);

    if (!experimentState.activePositionName || !experimentState.positions[experimentState.activePositionName]) {
        const help = document.createElement('p');
        help.className = 'small holder-help';
        help.textContent = 'Click a holder position to assign a substrate or dummy.';
        grid.appendChild(help);
        return;
    }

    const positionName = experimentState.activePositionName;
    const position = experimentState.positions[positionName];
    const controls = document.createElement('div');
    controls.className = 'position-controls active-position-controls';
    controls.innerHTML = '<strong>Position ' + escapeHtml(positionName) + '</strong>';

    const row = document.createElement('div');
    row.className = 'assignment-buttons';
    [
        {value: null, label: 'Empty'},
        {value: 'substrate', label: 'Substrate'},
        {value: 'si_dummy', label: 'Si dummy'},
        {value: 'sapphire_dummy', label: 'Sapphire / Al₂O₃ dummy'}
    ].forEach(function(item) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = item.value === position.position_usage ? 'primary' : 'secondary';
        button.textContent = item.label;
        button.addEventListener('click', function() { setPositionUsage(positionName, item.value); });
        row.appendChild(button);
    });
    controls.appendChild(row);

    if (insertCatalogState.length) {
        const insertLabel = document.createElement('label');
        insertLabel.textContent = 'Insert reduction (optional)';
        controls.appendChild(insertLabel);
        const insertSelect = document.createElement('select');
        insertSelect.innerHTML = '<option value="">No insert</option>';
        insertCatalogState
            .filter(function(insert) {
                return insertFitsPosition(
                    insert,
                    position
                );
            })
            .forEach(function(insert) {
            const option = document.createElement('option');
            option.value = insert.entryId;
            option.textContent = insert.name;
            option.selected = position.insertReduction && position.insertReduction.entryId === insert.entryId;
            insertSelect.appendChild(option);
        });
        insertSelect.addEventListener('change', function() {
            position.insertReduction = insertCatalogState.find(function(insert) {
                return insert.entryId === insertSelect.value;
            }) || null;

            if (
                position.substrate &&
                geometryXY(position.substrate.geometry) &&
                !substrateFitsPosition(
                    position.substrate,
                    position
                )
            ) {
                position.substrate = null;
                position.pendingTreatments = [];
            }

            experimentState.currentFilledDirty = true;

            renderHolder();

            if (
                position.position_usage ===
                'substrate'
            ) {
                renderSubstrateResults();
                renderTreatmentHistory();
            }

            updateProcessingButtonV2();
            updateStatePreview();
        });
        controls.appendChild(insertSelect);
    }

    if (positionControlsPanel) {
        positionControlsPanel.appendChild(controls);
    } else {
        grid.appendChild(controls);
    }
}


function setPositionUsage(positionName, usage) {
    const position = experimentState.positions[positionName];
    if (!position) return;
    position.position_usage = usage;
    if (usage !== 'substrate') {
        position.substrate = null;
        position.pendingTreatments = [];
    }
    experimentState.activePositionName = positionName;
    experimentState.currentFilledDirty = true;
    const picker = document.getElementById('substratePicker');
    const label = document.getElementById('activePositionLabel');
    if (label) label.textContent = 'Active holder position: ' + positionName;
    picker.style.display = usage === 'substrate' ? 'block' : 'none';
    renderHolder();
    if (usage === 'substrate') {
        renderSubstrateResults();
        renderTreatmentHistory();
    }
    updateProcessingButtonV2();
    updateStatePreview();
}


const selectSubstrateOriginal = selectSubstrate;
selectSubstrate = function(substrate) {
    const position = getActivePosition();
    if (!position || position.position_usage !== 'substrate') return;
    position.substrate = {
        entryId: substrate.entryId,
        uploadId: substrate.uploadId,
        entryName: substrate.entryName,
        labId: substrate.labId,
        parentSample: substrate.parentSample,
        material: substrate.material,
        formula: substrate.formula,
        supplierId: substrate.supplierId,
        crystalId: substrate.crystalId,
        chargeId: substrate.chargeId,
        polishing: substrate.polishing,
        orientation: substrate.orientation,
        offcut: substrate.offcut,
        offcutDirection: substrate.offcutDirection,
        asDelivered: substrate.asDelivered,
        processed: substrate.processed,
        grown: substrate.grown,
        geometry: substrate.geometry || null
    };
    position.pendingTreatments = [];
    experimentState.currentFilledDirty = true;
    renderHolder();
    renderSubstrateResults();
    renderTreatmentHistory();
    updateProcessingButtonV2();
    updateStatePreview();

    // Re-read the selected substrate and related treatment state from NOMAD
    // without doing a browser reload, which would discard the unsaved holder.
    refreshSubstrateData().catch(function(error) {
        console.error('Could not refresh substrate data after selection:', error);
    });
};


function updateProcessingButtonV2() {
    const button = document.getElementById('openProcessingButton');
    if (!button) return;
    const position = getActivePosition();
    button.disabled = !(position && position.substrate && position.substrate.entryId);
}


function processingDashboardUrl() {
    const pathname = window.location.pathname;
    const marker = '/dashboards/';
    const index = pathname.indexOf(marker);
    const base = index >= 0 ? pathname.slice(0, index) : '';
    return base + '/dashboards/processing/';
}


function openSelectedSubstrateInProcessing() {
    const position = getActivePosition();
    if (!position || !position.substrate) return;
    const params = new URLSearchParams();
    params.set('substrate_entry_id', position.substrate.entryId);
    params.set('return_url', window.location.href);
    window.location.href = processingDashboardUrl() + '?' + params.toString();
}


async function refreshSubstrateData() {
    const position = getActivePosition();
    const selectedId = position && position.substrate ? position.substrate.entryId : null;
    await Promise.all([initialiseSubstrates(), initialiseTreatmentHistory()]);
    if (selectedId && position) {
        const refreshed =
            substrateCatalogState.find(
                function(item) {
                    return (
                        item.entryId ===
                        selectedId
                    );
                }
            );

        if (
            refreshed &&
            substrateHasBeenCut(
                refreshed
            )
        ) {
            position.substrate = null;
            position.pendingTreatments = [];
            experimentState.currentFilledDirty = true;
        } else if (refreshed) {
            position.substrate =
                Object.assign(
                    {},
                    refreshed
                );
        }
    }
    renderSubstrateResults();
    renderTreatmentHistory();
    renderHolder();
    updateProcessingButtonV2();
}


function renderTreatmentQueue() {
    const container = document.getElementById('treatmentQueue');
    if (!container) return;
    container.innerHTML = '<p class="small">Treatments are managed in the Substrate Processing app.</p>';
}


function filledHolderArchiveData() {
    if (!experimentState.holder) throw new Error('Select a holder first.');
    if (!experimentState.holder.uploadId || !experimentState.holder.entryId) {
        throw new Error('Selected physical holder has no complete NOMAD reference.');
    }

    const positions = [];
    Object.entries(experimentState.positions).forEach(function(entry) {
        const positionName = entry[0];
        const position = entry[1];
        if (!position.position_usage) return;
        const item = {name: positionName, position_usage: position.position_usage};
        if (position.position_usage === 'substrate') {
            if (!position.substrate) {
                throw new Error('Position ' + positionName + ' is marked as substrate but no substrate is selected.');
            }

            if (
                substrateHasBeenCut(
                    position.substrate
                )
            ) {
                throw new Error(
                    'Substrate ' +
                    (
                        position.substrate.labId ||
                        position.substrate.entryName ||
                        position.substrate.entryId
                    ) +
                    ' has been cut into child samples and is no longer physically available.'
                );
            }

            let ref = position.substrate.reference || '';
            if (!ref) {
                if (!position.substrate.uploadId || !position.substrate.entryId) {
                    throw new Error('Substrate in position ' + positionName + ' has no complete NOMAD reference.');
                }
                ref = nomadArchiveReference(position.substrate.uploadId, position.substrate.entryId);
            }
            item.substrate = {
                name: position.substrate.labId || position.substrate.entryName || position.substrate.entryId,
                reference: ref
            };
        }
        if (position.insertReduction) {
            let insertRef = position.insertReduction.reference || '';
            if (!insertRef && position.insertReduction.uploadId && position.insertReduction.entryId) {
                insertRef = nomadArchiveReference(position.insertReduction.uploadId, position.insertReduction.entryId);
            }
            if (insertRef) {
                item.insert_reduction = {
                    name: position.insertReduction.name || position.insertReduction.entryId,
                    reference: insertRef
                };
            }
        }
        positions.push(item);
    });

    if (!positions.length) throw new Error('No holder positions are configured.');

    const existing = experimentState.holder.filledHolder;
    const now = new Date();
    const dateLabel = now.toISOString().slice(0, 10);
    const name = existing && existing.data && existing.data.name ?
        existing.data.name : experimentState.holder.id + ' fill ' + dateLabel;
    const existingTags = existing && existing.data && Array.isArray(existing.data.tags) ? existing.data.tags : [];

    return {
        m_def: 'pdi_nomad_plugin.mbe.instrument.FilledSubstrateHolderPDI',
        name: name,
        lab_id: experimentState.holder.id,
        datetime: existing && existing.data ? existing.data.datetime : now.toISOString(),
        tags: existingTags.filter(function(tag) { return tag !== 'discarded_loadout'; }),
        substrate_holder: nomadArchiveReference(experimentState.holder.uploadId, experimentState.holder.entryId),
        positions: positions
    };
}


async function uploadArchiveDataV2(uploadId, filename, data, overwrite) {
    const params = new URLSearchParams();
    params.append('file_name', filename);
    params.append('overwrite_if_exists', overwrite ? 'true' : 'false');
    params.append('trigger_processing', 'true');
    params.append('wait_for_processing', 'true');
    const response = await fetch(
        nomadApiBase() + '/uploads/' + encodeURIComponent(uploadId) + '/raw/?' + params.toString(),
        {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({data: data}, null, 2)
        }
    );
    if (!response.ok) {
        let detail = '';
        try {
            const errorData = await response.json();
            detail = errorData.detail ? ': ' + errorData.detail : '';
        } catch (_) {}
        throw new Error('Archive upload failed (' + response.status + ')' + detail);
    }
}


function loadoutTimestamp() {
    return new Date().toISOString().replace(/[-:TZ.]/g, '');
}



function holderTagsWithWorkflowStatus(tags, nextStatus) {
    const reserved =
        new Set([
            'empty',
            'ungrown',
            'grown'
        ]);

    const result =
        (Array.isArray(tags) ? tags : [])
            .filter(function(tag) {
                return !reserved.has(tag);
            });

    if (nextStatus) {
        result.push(nextStatus);
    }

    return result;
}


async function setPhysicalHolderWorkflowStatus(nextStatus) {
    const holder =
        experimentState.holder;

    if (!holder) {
        throw new Error(
            'No physical holder is selected.'
        );
    }

    if (
        !['empty', 'ungrown', 'grown']
            .includes(nextStatus)
    ) {
        throw new Error(
            'Invalid holder workflow status: ' +
            nextStatus
        );
    }

    const metadata =
        holder.metadata || {};

    const uploadId =
        holder.uploadId ||
        metadata.upload_id ||
        '';

    const mainfile =
        metadata.mainfile ||
        '';

    if (
        metadata.published === true
    ) {
        throw new Error(
            'Published physical holders are read-only.'
        );
    }

    if (
        !uploadId ||
        !mainfile
    ) {
        throw new Error(
            'Physical holder lacks upload or mainfile and cannot be updated safely.'
        );
    }

    /*
     * Work on a complete copy of the existing physical
     * holder archive so no geometry or metadata is lost.
     */
    const data =
        JSON.parse(
            JSON.stringify(
                holder.archiveData || {}
            )
        );

    data.tags =
        holderTagsWithWorkflowStatus(
            data.tags,
            nextStatus
        );

    await uploadArchiveDataV2(
        uploadId,
        mainfile,
        data,
        true
    );

    /*
     * Keep the in-memory holder synchronized with NOMAD.
     */
    holder.archiveData =
        data;

    holder.workflowStatus =
        nextStatus;

    const label =
        document.getElementById(
            'holderLabel'
        );

    if (label) {
        label.textContent =
            holder.id +
            ' · ' +
            nextStatus;
    }
}


async function saveFilledHolderToNomad(options) {
    options = options || {};
    const button = document.getElementById('saveFilledHolderButton');
    const status = document.getElementById('filledHolderSaveStatus');
    const targetUpload = document.getElementById('targetUpload').value;
    if (!experimentState.holder) {
        if (status) status.textContent = 'Select a holder first.';
        throw new Error('Select a holder first.');
    }

    const existing = experimentState.holder.filledHolder;
    let uploadId;
    let filename;
    let entryId;
    let overwrite = false;

    if (existing) {
        if (existing.published) {
            if (status) status.textContent = 'Published filled holders are read-only.';
            throw new Error('Published filled holders are read-only.');
        }
        uploadId = existing.uploadId;
        filename = existing.mainfile;
        entryId = existing.entryId;
        overwrite = true;
        if (!uploadId || !filename || !entryId) {
            throw new Error('Existing filled holder lacks upload, mainfile, or entry ID and cannot be updated safely.');
        }
    } else {
        if (!targetUpload) {
            if (status) status.textContent = 'Select a target upload first.';
            throw new Error('Select a target upload first.');
        }
        uploadId = targetUpload;
        const holderId = experimentSafePart(experimentState.holder.id);
        filename = holderId + '_fill_' + loadoutTimestamp() + '.FilledSubstrateHolder.archive.yaml';
        entryId = await archiveEntryId(uploadId, filename);
    }

    if (button) button.disabled = true;
    try {
        if (status && !options.silent) status.textContent = existing ? 'Updating filled holder...' : 'Saving filled holder...';
        const data = filledHolderArchiveData();
        await uploadArchiveDataV2(uploadId, filename, data, overwrite);

        /*
         * The FilledSubstrateHolderPDI is the occupancy
         * snapshot. The physical SubstrateHolderPDI carries
         * the current workflow state.
         */
        await setPhysicalHolderWorkflowStatus('ungrown');

        experimentState.holder.filledHolder = {
            entryId: entryId,
            uploadId: uploadId,
            name: data.name,
            mainfile: filename,
            published: false,
            data: data,
            metadata: {upload_id: uploadId, mainfile: filename, published: false}
        };
        experimentState.currentFilledDirty = false;
        if (status && !options.silent) status.textContent = 'Filled holder saved. You can close the app and continue later.';
        updateStatePreview();

        await refreshSubstrateData();
        await initialiseHolderSelect();

        const holderSelect =
            document.getElementById('holderSelect');

        const physicalHolderEntryId =
            experimentState.holder
                ? experimentState.holder.entryId
                : '';

        if (
            holderSelect &&
            physicalHolderEntryId &&
            Array.from(holderSelect.options).some(
                function(option) {
                    return (
                        option.value ===
                        physicalHolderEntryId
                    );
                }
            )
        ) {
            holderSelect.value =
                physicalHolderEntryId;
        }

        return nomadArchiveReference(uploadId, entryId);
    } catch (error) {
        if (status && !options.silent) status.textContent = 'Error: ' + error.message;
        throw error;
    } finally {
        if (button) button.disabled = false;
    }
}


async function saveExperimentToNomad() {
    const button =
        document.getElementById(
            'saveExperimentButton'
        );

    const status =
        document.getElementById(
            'experimentSaveStatus'
        );

    const uploadId =
        document.getElementById(
            'targetUpload'
        ).value;

    if (!uploadId) {
        status.textContent =
            'Select a target upload first.';
        return;
    }

    if (!experimentState.growthRunId) {
        status.textContent =
            'Enter a Growth Run ID first.';
        return;
    }

    if (!experimentState.holder) {
        status.textContent =
            'Select a holder first.';
        return;
    }

    try {
        nominalLayerArchiveData();
    } catch (error) {
        status.textContent =
            'Error: ' + error.message;
        return;
    }

    const physicalHolderEntryId =
        experimentState.holder.entryId;

    button.disabled = true;

    let filledSavedThisAttempt = false;

    try {
        let filledReference;

        if (
            !experimentState.holder.filledHolder ||
            experimentState.currentFilledDirty
        ) {
            status.textContent =
                'Saving filled holder...';

            filledReference =
                await saveFilledHolderToNomad({
                    silent: true
                });

            filledSavedThisAttempt =
                true;

        } else {
            const filled =
                experimentState.holder.filledHolder;

            filledReference =
                nomadArchiveReference(
                    filled.uploadId,
                    filled.entryId
                );
        }

        const growthRunId =
            experimentSafePart(
                experimentState.growthRunId
            );

        if (!growthRunId) {
            throw new Error(
                'Growth Run ID is invalid.'
            );
        }

        const experimentFilename =
            growthRunId +
            '.ExperimentMbe.archive.yaml';

        const experimentData =
            experimentArchiveData(
                filledReference
            );

        status.textContent =
            'Saving experiment...';

        await uploadArchiveDataV2(
            uploadId,
            experimentFilename,
            experimentData,
            false
        );

        rememberLayerCompositions();

        /*
         * Experiment exists successfully:
         * the physical holder now contains grown samples.
         */
        await setPhysicalHolderWorkflowStatus(
            'grown'
        );

        experimentState.experimentSaved =
            true;

        /*
         * A Growth Run ID belongs to exactly one
         * experiment. Clear it immediately after save.
         */
        experimentState.growthRunId =
            '';

        const growthInput =
            document.getElementById(
                'growthRunId'
            );

        growthInput.value =
            '';

        updateCombinedId();

        status.textContent =
            'Experiment saved. Holder is now filled · grown. ' +
            'Linked substrates are marked grown by the ExperimentMbePDI normalizer.';

        document.getElementById(
            'startNewExperimentButton'
        ).style.display =
            'block';

        /*
         * Refresh catalogs, but keep the page and target upload.
         */
        await refreshSubstrateData();
        await initialiseHolderSelect();

        const holderSelect =
            document.getElementById(
                'holderSelect'
            );

        if (
            physicalHolderEntryId &&
            Array.from(holderSelect.options).some(
                function(option) {
                    return (
                        option.value ===
                        physicalHolderEntryId
                    );
                }
            )
        ) {
            holderSelect.value =
                physicalHolderEntryId;

            await selectHolder();
        }

        updateStatePreview();

    } catch (error) {
        status.textContent =
            (
                filledSavedThisAttempt
                    ? 'Filled holder was saved, but the experiment failed: '
                    : 'Error: '
            ) +
            error.message;

    } finally {
        button.disabled =
            false;
    }
}

async function emptyCurrentHolder() {
    const status =
        document.getElementById(
            'filledHolderSaveStatus'
        );

    if (!experimentState.holder) {
        status.textContent =
            'Select a holder first.';
        return;
    }

    const holder =
        experimentState.holder;

    const workflowStatus =
        holder.workflowStatus ||
        holderWorkflowStatus(
            holder.archiveData || {}
        );

    const filled =
        holder.filledHolder;

    try {
        /*
         * No saved FilledSubstrateHolder exists:
         * just release the physical holder.
         */
        if (!filled) {
            await setPhysicalHolderWorkflowStatus(
                'empty'
            );

            resetHolderSelection(true);

            await initialiseHolderSelect();

            status.textContent =
                'Holder is empty and available.';

            return;
        }

        if (filled.published) {
            status.textContent =
                'Published filled holders are read-only.';
            return;
        }

        /*
         * A grown loadout is historical experiment data.
         * Never mark it as discarded.
         *
         * Taking samples off only changes the CURRENT
         * physical holder state.
         */
        if (workflowStatus === 'grown') {
            await setPhysicalHolderWorkflowStatus(
                'empty'
            );

            resetHolderSelection(true);

            await initialiseHolderSelect();

            status.textContent =
                'Samples removed. Historical grown loadout retained; holder is now empty.';

            return;
        }

        /*
         * Ungrown holder:
         * this is a prepared loadout that was abandoned
         * before a growth experiment was completed.
         */
        if (
            !filled.uploadId ||
            !filled.mainfile
        ) {
            status.textContent =
                'Filled holder cannot be updated safely because its raw file is unknown.';
            return;
        }

        const data =
            filledHolderArchiveData();

        const tags =
            Array.isArray(data.tags)
                ? data.tags.slice()
                : [];

        if (
            !tags.includes(
                'discarded_loadout'
            )
        ) {
            tags.push(
                'discarded_loadout'
            );
        }

        data.tags =
            tags;

        await uploadArchiveDataV2(
            filled.uploadId,
            filled.mainfile,
            data,
            true
        );

        await setPhysicalHolderWorkflowStatus(
            'empty'
        );

        resetHolderSelection(true);

        await initialiseHolderSelect();

        status.textContent =
            'Unused loadout retained in NOMAD as discarded; holder is now empty.';

    } catch (error) {
        status.textContent =
            'Error: ' +
            error.message;
    }
}

function resetHolderSelection(clearSelect) {
    experimentState.holder = null;
    experimentState.positions = {};
    experimentState.activePositionName = null;
    experimentState.currentFilledDirty = false;
    updateEmptyHolderButton('empty');
    if (clearSelect) document.getElementById('holderSelect').value = '';
    document.getElementById('holderLabel').textContent = 'No holder selected';
    document.getElementById('holderGrid').innerHTML = '';
    document.getElementById('substratePicker').style.display = 'none';
    const wrap = document.getElementById('holderImageWrap');
    if (wrap) wrap.style.display = 'none';
    updateCombinedId();
    updateStatePreview();
}


async function startNewExperiment() {
    const targetUpload = document.getElementById('targetUpload').value;
    experimentState.growthRunId = '';
    experimentState.experimentSaved = false;
    document.getElementById('growthRunId').value = '';
    document.getElementById('experimentSaveStatus').textContent = 'Configure the next experiment.';
    document.getElementById('filledHolderSaveStatus').textContent = 'A holder loadout can be saved without a Growth Run ID.';
    document.getElementById('startNewExperimentButton').style.display = 'none';
    resetLayerStack();
    resetHolderSelection(true);
    await Promise.all([initialiseHolderSelect(), refreshSubstrateData()]);
    if (targetUpload) document.getElementById('targetUpload').value = targetUpload;
}


function updateCombinedId() {
    const element = document.getElementById('combinedId');
    if (experimentState.growthRunId && experimentState.holder) {
        element.textContent = experimentState.growthRunId + '@' + experimentState.holder.id;
    } else {
        element.textContent = '—';
    }
}


async function initialiseWorkflowV2() {
    installTargetUploadPersistence();

    await loadUploads();
    restoreTargetUploadSelection();

    /*
     * Growth Run IDs are never persisted between
     * completed/reloaded experiment sessions.
     */
    experimentState.growthRunId = '';

    const growthInput =
        document.getElementById(
            'growthRunId'
        );

    if (growthInput) {
        growthInput.value = '';
    }

    initialiseSubstrateFilterEvents();

    await Promise.all([
        initialiseSubstrates(),
        initialiseTreatmentHistory(),
        initialiseHolderSelect(),
        initialiseLayerStack()
    ]);

    updateCombinedId();
    updateStatePreview();
}

initialiseWorkflowV2();
