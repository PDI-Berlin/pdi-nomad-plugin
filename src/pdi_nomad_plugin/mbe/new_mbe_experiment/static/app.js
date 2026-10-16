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


const experimentState = {
    growthRunId: '',
    holder: null,
    positions: {}
};


// Nominal composition/dopant/thickness inputs are disabled until original NOMAD
// definitions can represent them. No substitute m_def is introduced.

async function loadTreatmentHistoryEntries() {
    const definitions = [
        {type:'cleaning', label:'Cleaning', processSchema:'nomad_material_processing.general.Cleaning', recipeSchema:'nomad_material_processing.general.CleaningRecipe'},
        {type:'annealing', label:'Annealing', processSchema:'nomad_material_processing.general.Annealing', recipeSchema:'nomad_material_processing.general.AnnealingRecipe'},
        {type:'etching', label:'Etching', processSchema:'nomad_material_processing.general.Etching', recipeSchema:'nomad_material_processing.general.EtchingRecipe'}
    ];
    const treatments = [];
    for (const definition of definitions) {
        const recipes = await queryEntriesBySchema(definition.recipeSchema, 500, ['entry_id','entry_name','data']);
        const recipeNames = new Map(recipes.map(function(recipe) {
            const d = recipe.data || {};
            return [recipe.entry_id, d.name || d.lab_id || recipe.entry_name || recipe.entry_id];
        }));
        const entries = await queryEntriesBySchema(definition.processSchema, 500, ['entry_id','upload_id','entry_name','data']);
        for (const entry of entries) {
            const data = entry.data || {};
            const recipeRef = referenceValue(data.recipe);
            const recipeId = entryIdFromReference(recipeRef);
            treatments.push({
                entryId:entry.entry_id, uploadId:entry.upload_id,
                entryName:entry.entry_name || entry.entry_id,
                type:definition.type, label:definition.label,
                recipeName:recipeNames.get(recipeId) || '', data:data
            });
        }
    }
    return treatments;
}

function treatmentReferencesSubstrate(treatment, substrateEntryId) {
    if (!treatment || !treatment.data || !substrateEntryId) {
        return false;
    }

    // Only the original Process.samples[].reference relationship is verified.
    const samples = treatment.data.samples || [];
    return samples.some(function(sample) {
        return referenceEntryId(sample && sample.reference) === substrateEntryId;
    });
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
    // Existing NOMAD recipes; unsupported local coating/cutting schemas are not queried.
    const types = [
        {type:'cleaning', schema:'nomad_material_processing.general.CleaningRecipe'},
        {type:'annealing', schema:'nomad_material_processing.general.AnnealingRecipe'},
        {type:'etching', schema:'nomad_material_processing.general.EtchingRecipe'}
    ];
    const recipes = [];
    for (const type of types) {
        const entries = await queryEntriesBySchema(type.schema, 500, ['entry_id','entry_name','data']);
        entries.forEach(function(entry) {
            const data = entry.data || {};
            recipes.push({
                entryId: entry.entry_id, name:data.name || entry.entry_name || entry.entry_id,
                type:type.type, schema:type.schema
            });
        });
    }
    return recipes;
}


// FIX: was POSTing to /entries/query with required.include containing
// data.* paths (e.g. 'data.lab_id'), which /entries/query rejects with a
// 422 (it only serves indexed doc quantities, not archive content). Reuses
// the already-fixed queryEntriesBySchema(), which talks to
// /entries/archive/query instead and returns the same entry shape.
async function loadSubstrates() {
    const schema = 'nomad_material_processing.general.CrystallineSubstrate';
    const entries = await queryEntriesBySchema(schema, 1000, ['entry_id','upload_id','entry_name','data']);
    return entries.filter(function(entry) { return entry.data && entry.data.m_def === schema; });
}


async function loadHolders() {
    return await queryEntriesBySchema(
        'nomad_material_processing.vapor_deposition.general.SubstrateHolder',
        500, ['entry_id','upload_id','entry_name','data']);
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


function filteredSubstrates() {

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



// Original CrystallineSubstrate payloads from Substrate Intake, without local quantities.
function originalMbeSubstrateFields(data) {
    const components = Array.isArray(data.components) ? data.components : [];
    const first = components[0] || {};
    const formula = String(((first.pure_substance || {}).molecular_formula) || '').trim();
    const crystal = data.crystal_properties || {};
    const direction = ((crystal.surface_orientation || {}).hkl_reciprocal) || {};
    const indices = ['h_index','k_index','l_index'];
    const orientation = indices.every(function(k) {return direction[k] !== undefined && direction[k] !== null;})
        ? indices.map(function(k) {return direction[k];}).join(' ') : '';
    const miscut = (crystal.miscut || {}).cartesian_miscut || {};
    const ref = (miscut.reference_orientation || {});
    const tilt = Number(ref.angle);
    const direct = ref.hkl_direct || {};
    const offcut = ref.angle !== undefined && Number.isFinite(tilt) ? String(tilt) + '°' : '';
    const offcutDirection = indices.every(function(k) {return direct[k] !== undefined && direct[k] !== null;})
        ? indices.map(function(k) {return direct[k];}).join(' ') : '';
    const description = String(data.description || '');
    const crystalMatch = description.match(/^Crystal ID:\s*(.*)$/m);
    const chargeMatch = description.match(/^Charge ID:\s*(.*)$/m);
    return {
        formula:formula, material:formula, orientation:orientation, offcut:offcut,
        offcutDirection:offcutDirection,
        crystalId:crystalMatch ? crystalMatch[1].trim() : '',
        chargeId:chargeMatch ? chargeMatch[1].trim() : ''
    };
}

async function initialiseSubstrates() {
    const container = document.getElementById('substrateResults');
    container.innerHTML = '<p class="small" style="padding:10px;">Loading substrates...</p>';
    try {
        const entries = await loadSubstrates();
        substrateCatalogState = entries.map(function(entry) {
            const data = entry.data || {};
            const fields = originalMbeSubstrateFields(data);
            return {
                entryId:entry.entry_id, uploadId:entry.upload_id,
                entryName:entry.entry_name || entry.entry_id,
                labId:data.lab_id || data.name || entry.entry_name || entry.entry_id,
                parentSample:null, material:fields.material, formula:fields.formula,
                supplierId:data.supplier_id || '', crystalId:fields.crystalId, chargeId:fields.chargeId,
                polishing:'', orientation:fields.orientation, offcut:fields.offcut,
                offcutDirection:fields.offcutDirection, asDelivered:false,
                processed:false, grown:false, geometry:data.geometry || null
            };
        });
        updateSubstrateFilters();
        renderSubstrateResults();
    } catch (error) {
        console.error(error);
        container.innerHTML = '<p class="small" style="padding:10px;">Could not load original NOMAD substrates.</p>';
        throw error;
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
            'nomad_material_processing.general.Cleaning',
        annealing:
            'nomad_material_processing.general.Annealing',
        etching:
            'nomad_material_processing.general.Etching',
        // Back-side coating is disabled: no verified original schema exists.
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


async function uploadTreatmentArchive() {
    throw new Error(
        'Treatment uploads from New MBE Experiment are disabled. ' +
        'Use the dedicated Substrate Processing app and original NOMAD process schemas.'
    );
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
            etching: 'Etching'
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


        if (select.dataset.refreshHandlersInstalled !== '1') {
            select.addEventListener('change', function() {
                button.disabled = !select.value;
            });

            button.addEventListener('click', addTreatmentToQueue);
            select.dataset.refreshHandlersInstalled = '1';
        }

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


function updateEmptyHolderButton() {
    const button = document.getElementById('emptyHolderButton');
    if (button) button.textContent = 'Clear local assignments';
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
        !experimentState.holder ||
        !position ||
        position.position_usage !== 'substrate' ||
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


async function uploadArchiveData() {
    throw new Error(
        'New MBE Experiment saving is disabled: the original MolecularBeamEpitaxy ' +
        'section is not an EntryData root. No NOMAD archive has been uploaded.'
    );
}


function experimentArchiveData(filledHolderReference) {
    throw new Error('Cannot serialize an MBE growth experiment until its original NOMAD fields and references have been verified.');
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
 * - physical holder geometry: SubstrateHolder archive
 * - current loadout: unreferenced FilledSubstrateHolder
 * - historical loadout: FilledSubstrateHolder referenced by MolecularBeamEpitaxy
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


function holderWorkflowStatus() {
    // Original SubstrateHolder has no lifecycle/status quantity.
    return 'not recorded';
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

            const hasRecordedSnapshot =
                currentByPhysical.has(
                    candidate.entry_id
                );

            let value =
                positions.length;

            // Prefer the physical holder that a recorded original
            // FilledSubstrateHolder explicitly references. No lifecycle
            // status can be inferred from this relationship.
            if (hasRecordedSnapshot) value += 100000;

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
                'nomad_material_processing.vapor_deposition.general.SubstrateHolder',
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
                'nomad_material_processing.vapor_deposition.general.FilledSubstrateHolder',
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
                 * FilledSubstrateHolder inherits from
                 * SubstrateHolder, therefore guard both
                 * by m_def and by substrate_holder reference.
                 */
                return (
                    mDef !== 'nomad_material_processing.vapor_deposition.general.FilledSubstrateHolder' &&
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
                    mDef === 'nomad_material_processing.vapor_deposition.general.FilledSubstrateHolder'
                );
            }
        );

    /*
     * Associate recorded loadouts with their exact physical holder reference.
     * Never infer the physical holder's current occupancy from these entries.
     */
    // Most recent recorded snapshot per physical holder. This is NOT proof
    // that the holder is currently occupied; NOMAD has no original status field.
    const currentByPhysical =
        new Map();

    filled.forEach(function(entry) {
        const data =
            entry.data || {};

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
     * Keep the most recent recorded snapshot for each canonical holder.
     * A snapshot may be historical, not a live holder status.
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

        // Retained for read-only catalog compatibility.
        empty: holders,

        filled: filled,
        experiments: [],
        current: current,
        currentByPhysical:
            canonicalCurrentByPhysical
    };

    return holderCatalogState;
}

// Insert selection intentionally unavailable: the original geometry contract
// has not been validated. No synthetic dimensions or substitute m_def.
async function loadInsertCatalogV2() {
    insertCatalogState = [];
}


function holderDisplayStatus(workflowStatus, hasFilledHolder) {
    return hasFilledHolder
        ? 'recorded loadout (current occupancy unverified)'
        : 'no recorded loadout (occupancy unverified)';
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

        let recordedLoadoutCount = 0;

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

                const currentFilled =
                    catalog.currentByPhysical.get(
                        entry.entry_id
                    );

                if (currentFilled) recordedLoadoutCount += 1;

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
                 * PHYSICAL SubstrateHolder.
                 */
                option.value =
                    entry.entry_id;

                option.dataset.kind =
                    'physical';

                option.dataset.status =
                    workflowStatus;

                option.dataset.uploadId =
                    entry.upload_id || '';

                option.dataset.filledEntryId = currentFilled
                    ? currentFilled.entry_id : '';

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
                recordedLoadoutCount +
                ' with recorded loadout. Current occupancy cannot be inferred ' +
                'from original NOMAD holder fields.';
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
        // An insert alone is not evidence of a substrate or dummy.
        target.position_usage = item.substrate ? 'substrate' : null;
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

    // The old history belongs to the previous holder.
    document.getElementById('treatmentHistory').textContent = '';

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
         * from the physical SubstrateHolder.
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
         * The FilledSubstrateHolder is loaded only
         * as the current occupancy snapshot.
         */
        const filledEntryId =
            option.dataset.filledEntryId ||
            '';

        if (filledEntryId) {
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
            applyFilledOverlay(filledHolder.data);
            const info = document.getElementById('filledHolderSaveStatus');
            if (info) info.textContent =
                'Showing the most recent recorded NOMAD loadout as a historical ' +
                'reference. Current physical occupancy is NOT verified. ' +
                'Any changes are local only.';
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
        renderTreatmentHistory();

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


function substrateFootprint(geometry) {
    if (!geometry || typeof geometry !== 'object') return null;

    const num = geometryNumber;
    const type = String(geometry.m_def || '').split('.').pop();

    if (type === 'Cylinder' || type === 'CylinderSector') {
        const radius = num(geometry.radius);
        const angle = type === 'Cylinder'
            ? 360 : num(geometry.central_angle);

        return radius > 0 && angle > 0 && angle <= 360
            ? {
                shape: type === 'Cylinder' ? 'circle' : 'circular_sector',
                radius: radius,
                central_angle: angle
            }
            : null;
    }

    if (type === 'SquareCuboid' || type === 'RectangleCuboid') {
        const width = num(geometry.width);
        const length = num(geometry.length) ??
            (type === 'SquareCuboid' ? width : null);

        return width > 0 && length > 0
            ? {shape: 'rectangle', width: width, length: length}
            : null;
    }

    return null;
}
function geometryFits(candidate, opening) {
    const a = substrateFootprint(candidate);
    const b = substrateFootprint(opening);
    if (!a || !b) return false;
    const tolerance = 0.00005; // 0.05 mm
    if (a.shape === 'rectangle' && b.shape === 'rectangle') {
        return (a.width <= b.width + tolerance &&
                a.length <= b.length + tolerance) ||
               (a.length <= b.width + tolerance &&
                a.width <= b.length + tolerance);
    }
    if (b.shape === 'circle') {
        if (a.shape === 'rectangle') {
            return Math.hypot(a.width, a.length) / 2 <= b.radius + tolerance;
        }
        return a.radius <= b.radius + tolerance;
    }
    if (b.shape === 'rectangle' && a.shape === 'circle') {
        return 2 * a.radius <= Math.min(b.width, b.length) + tolerance;
    }
    if (b.shape === 'circular_sector' && a.shape === 'circular_sector') {
        return a.radius <= b.radius + tolerance &&
            a.central_angle <= b.central_angle + 1e-6;
    }
    // Unverified cross-shape/sector fit is unsafe.
    return false;
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

    if (holderId.endsWith('_1/4')) {
        return {shape: 'circular_sector', radius: 0.0254, central_angle: 90};
    }
    if (holderId.endsWith('_2')) {
        return {shape: 'circle', radius: 0.0254, central_angle: 360};
    }
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


function substrateFitsPosition(substrate, position) {
    if (!substrate || !position) {
        return false;
    }

    const target =
        effectivePositionGeometry(position);

    if (!substrateFootprint(target)) {
        return false;
    }

    if (!substrateFootprint(substrate.geometry)) {
        return false;
    }

    return geometryFits(
        substrate.geometry,
        target
    );
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
    }
    renderTreatmentHistory();
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
    }
    renderTreatmentHistory();
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


function isInsidePdiLab() {
    if (window.parent === window) {
        return false;
    }

    try {
        return (
            window.parent.location.origin === window.location.origin &&
            window.parent.location.pathname.includes(
                '/dashboards/pdi-lab/'
            )
        );
    } catch (_) {
        return (
            new URLSearchParams(
                window.location.search
            ).get('pdi_lab') === '1'
        );
    }
}


function openSelectedSubstrateInProcessing() {
    const position = getActivePosition();
    if (!position || !position.substrate) return;

    if (isInsidePdiLab()) {
        window.parent.postMessage(
            {
                type: 'pdi-lab:navigate',
                target: 'processing',
                payload: {
                    type: 'pdi-lab:activate-processing',
                    substrateEntryId: position.substrate.entryId
                }
            },
            window.location.origin
        );
        return;
    }

    const params = new URLSearchParams();
    params.set('substrate_entry_id', position.substrate.entryId);
    params.set('return_url', window.location.href);
    window.location.href = processingDashboardUrl() + '?' + params.toString();
}


window.addEventListener('message', function(event) {
    if (
        event.origin !== window.location.origin ||
        event.source !== window.parent
    ) {
        return;
    }

    const data = event.data || {};

    if (data.type !== 'pdi-lab:resume') {
        return;
    }

    refreshExperimentCatalogs().catch(function(error) {
        console.error('Could not refresh MBE catalogs:', error);
    });
});


let experimentCatalogRefreshPromise = null;

function refreshExperimentCatalogs() {
    if (experimentCatalogRefreshPromise) {
        return experimentCatalogRefreshPromise;
    }

    experimentCatalogRefreshPromise = (async function() {
        const holder = document.getElementById('holderSelect');
        const upload = document.getElementById('targetUpload');
        const recipe = document.getElementById('treatmentRecipeSelect');

        const oldHolder = holder.value;
        const oldUpload = upload.value;
        const oldRecipe = recipe ? recipe.value : '';

        await refreshSubstrateData();

        await Promise.all([
            initialiseHolderSelect(),
            loadUploads(),
            recipe ? initialiseTreatmentRecipes() : Promise.resolve()
        ]);


        function restore(select, value) {
            if (value && Array.from(select.options).some(function(opt) {
                return opt.value === value;
            })) {
                select.value = value;
            }
        }

        restore(holder, oldHolder);
        restore(upload, oldUpload);

        if (!upload.value) {
            restoreTargetUploadSelection();
        }

        if (recipe) {
            restore(recipe, oldRecipe);
            document.getElementById('addTreatmentButton').disabled =
                !recipe.value;
        }

        // Keep unsaved holder positions and layer fields unchanged.
    })().finally(function() {
        experimentCatalogRefreshPromise = null;
    });

    return experimentCatalogRefreshPromise;
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

        if (refreshed) {
            position.substrate = Object.assign({}, refreshed);
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


/*
 * Do not serialize RectangleCuboid/SquareCuboid as FilledHolder slot_geometry:
 * these original classes are not Geometry subclasses in NOMAD 1.4.3.
 * The local draft exporter omits unsupported geometries explicitly.
 */

function xyForFilledHolderPosition(position, positionName) {
    const present = function(value) {
        return value !== null && value !== undefined && value !== '';
    };
    if (present(position.rho) && present(position.theta)) {
        const rho = Number(position.rho);
        const theta = Number(position.theta);
        if (!Number.isFinite(rho) || rho < 0 ||
            !Number.isFinite(theta)) {
            throw new Error(
                'Invalid rho/theta for position ' + positionName + '.'
            );
        }
        const radians = theta * Math.PI / 180;
        return {
            x_position: rho * Math.cos(radians),
            y_position: rho * Math.sin(radians)
        };
    }
    if (present(position.x_position) && present(position.y_position)) {
        const x = Number(position.x_position);
        const y = Number(position.y_position);
        if (!Number.isFinite(x) || !Number.isFinite(y)) {
            throw new Error(
                'Invalid x/y coordinates for position ' + positionName + '.'
            );
        }
        return {x_position: x, y_position: y};
    }
    throw new Error(
        'Position ' + positionName +
        ' has no complete physical-holder coordinates.'
    );
}

function filledHolderArchiveData() {
    throw new Error('Cannot save a filled holder until position usage, dummy inserts and lifecycle have been mapped to original FilledSubstrateHolder quantities.');
}


/*
 * A successful HTTP PUT only confirms that NOMAD accepted the upload.
 * A Filled Holder / Experiment must not advance the physical holder's
 * lifecycle until the API also confirms its entry processing.
 *
 * Use NOMAD's existing processing result; do not run or replace normalizers.
 */
async function uploadArchiveDataV2() {
    throw new Error(
        'New MBE Experiment saving is disabled: no verified original EntryData root ' +
        'is available for the MBE and filled-holder sections.'
    );
}


function loadoutTimestamp() {
    return new Date().toISOString().replace(/[-:TZ.]/g, '');
}



// Original SubstrateHolder has no tags or grown/ungrown status.
// Never construct synthetic holder lifecycle quantities.


async function setPhysicalHolderWorkflowStatus(nextStatus) {
    throw new Error('Original SubstrateHolder has no tags/status quantities; cannot persist ' + nextStatus + ' as invented metainfo.');
}


async function saveFilledHolderToNomad() {
    throw new Error(
        'A FilledSubstrateHolder is an original NOMAD section, not a verified ' +
        'EntryArchive.data root. Export a local draft instead; nothing was saved to NOMAD.'
    );
}


async function saveExperimentToNomad() {
    throw new Error(
        'MolecularBeamEpitaxy is not an EntryData root in the installed original schema. ' +
        'Export a local draft instead; nothing was saved to NOMAD.'
    );
}


async function emptyCurrentHolder() {
    // Clear only local assignments. The original holder schema has no persisted
    // empty/grown lifecycle status, and historical loadouts must not be edited.
    const status = document.getElementById('filledHolderSaveStatus');
    if (!experimentState.holder) {
        if (status) status.textContent = 'Select a holder first.';
        return;
    }
    const physicalPositions = Array.isArray(experimentState.holder.archiveData.positions)
        ? experimentState.holder.archiveData.positions : [];
    experimentState.positions = {};
    physicalPositions.forEach(function(position) {
        if (position.name) experimentState.positions[position.name] = makePositionState(position);
    });
    experimentState.activePositionName = null;
    experimentState.currentFilledDirty = true;
    renderHolder();
    renderTreatmentHistory();
    updateStatePreview();
    if (status) {
        status.textContent = 'Local assignments cleared. No NOMAD holder or historical loadout was changed.';
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
    renderTreatmentHistory();
}


async function startNewExperiment() {
    const targetUpload = document.getElementById('targetUpload').value;
    experimentState.growthRunId = '';
    experimentState.experimentSaved = false;
    document.getElementById('growthRunId').value = '';
    document.getElementById('experimentSaveStatus').textContent = 'Configure the next experiment.';
    document.getElementById('filledHolderSaveStatus').textContent =
        'Local holder assignments only; NOMAD writes remain disabled.';
    document.getElementById('startNewExperimentButton').style.display = 'none';
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


function downloadLocalMbeDraft() {
    const status = document.getElementById('experimentSaveStatus');
    try {
        const draft = window.NomadMbeDrafts.build(
            experimentState, [], nomadArchiveReference,
            xyForFilledHolderPosition
        );
        const filename = experimentSafePart(experimentState.growthRunId || 'MBE') +
            '_LOCAL_DRAFT_NOT_NOMAD_ENTRY.json';
        const blob = new Blob([JSON.stringify(draft, null, 2)],
            {type: 'application/json'});
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
        if (status) status.textContent =
            'Local draft exported. This is NOT a NOMAD archive and nothing was uploaded.';
    } catch (error) {
        if (status) status.textContent = 'Draft export failed: ' + error.message;
    }
}

function hideUnmappedNominalLayerControls() {
    // The nominal-layer UI was backed exclusively by the removed custom schema.
    const list = document.getElementById('layerStackList');
    if (list) {
        const panel = list.closest('section, .card, .panel');
        const sharedPanel = panel && (
            panel.querySelector('#holderGrid') ||
            panel.querySelector('#growthRunId')
        );
        if (panel && !sharedPanel) panel.hidden = true;
        else list.hidden = true;
    }
    ['layerStackPreview', 'addLayerButton', 'resetLayerButton'].forEach(function(id) {
        const element = document.getElementById(id);
        if (element) element.hidden = true;
    });
}

function configureOriginalSchemaWriteSafety() {
    const disabled = [
        ['saveFilledHolderButton', 'filledHolderSaveStatus'],
        ['saveExperimentButton', 'experimentSaveStatus']
    ];
    disabled.forEach(function(ids) {
        const button = document.getElementById(ids[0]);
        const status = document.getElementById(ids[1]);
        if (button) {
            button.disabled = true;
            button.title = 'Original NOMAD section has no verified EntryData root';
        }
        if (status) status.textContent =
            'NOMAD write disabled: the original section is not an EntryData root. ' +
            'Use Export local draft; this does not create a NOMAD entry.';
    });
}

async function initialiseWorkflowV2() {
    configureOriginalSchemaWriteSafety();
    hideUnmappedNominalLayerControls();
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
    ]);

    updateCombinedId();
    updateStatePreview();
}

initialiseWorkflowV2().then(function() {
    if (isInsidePdiLab()) {
        window.parent.postMessage(
            {
                type: 'pdi-lab:ready',
                app: 'experiment'
            },
            window.location.origin
        );
    }
});
