import importlib
from copy import deepcopy
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from nomad.config import config

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / 'templates'
STATIC_DIR = BASE_DIR / 'static'

app = FastAPI()

LIBRARY_TYPES = {
    'processing_recipe': {
        'label': 'Processing Recipes',
        'kind': 'processing_recipe',
        'schemas': {
            'cleaning': {
                'label': 'Chemical treatment',
                'schema': 'pdi_nomad_plugin.general.schema.CleaningRecipePDI',
                'id_prefix': 'CLEAN',
                'usage_schemas': [
                    'pdi_nomad_plugin.general.schema.CleaningPDI',
                ],
            },
            'annealing': {
                'label': 'Annealing',
                'schema': 'pdi_nomad_plugin.general.schema.AnnealingRecipePDI',
                'id_prefix': 'ANNEAL',
                'usage_schemas': [
                    'pdi_nomad_plugin.general.schema.AnnealingPDI',
                ],
            },
            'back_side_coating': {
                'label': 'Back-side coating',
                'schema': 'pdi_nomad_plugin.general.schema.BackSideCoatingRecipePDI',
                'id_prefix': 'BACKCOAT',
                'usage_schemas': [
                    'pdi_nomad_plugin.general.schema.BackSideCoatingPDI',
                ],
            },
        },
    },
    'sample_cut_recipe': {
        'label': 'Sample Cut Recipes',
        'schema': 'pdi_nomad_plugin.general.schema.SampleCutRecipePDI',
        'kind': 'sample_cut_recipe',
        'usage_schemas': [],
        'usage_note': (
            'Sample Cut execution copies recipe parameters into SampleCutPDI; '
            'the recipe is not referenced by the historical cut entry.'
        ),
    },
    'holder': {
        'label': 'Holders',
        'schema': 'pdi_nomad_plugin.mbe.instrument.SubstrateHolderPDI',
        'kind': 'holder',
        'usage_schemas': [
            'pdi_nomad_plugin.mbe.instrument.FilledSubstrateHolderPDI',
        ],
    },
    'insert': {
        'label': 'Inserts',
        'schema': 'pdi_nomad_plugin.mbe.instrument.InsertReductionPDI',
        'kind': 'insert',
        'usage_schemas': [
            'pdi_nomad_plugin.mbe.instrument.FilledSubstrateHolderPDI',
        ],
    },
}


def _recipe_scalar_fields(schema_path):
    module_name, class_name = schema_path.rsplit('.', 1)
    cls = getattr(importlib.import_module(module_name), class_name)

    skip = {
        'm_def',
        'name',
        'lab_id',
        'datetime',
        'samples',
        'recipe',
        'starting_time',
        'ending_time',
        'end_time',
        'location',
        'tags',
    }

    fields = []

    for name, quantity in cls.m_def.all_quantities.items():
        if name in skip:
            continue

        # Only scalar quantities here; arrays such as tags are excluded.
        if getattr(quantity, 'shape', None):
            continue

        quantity_type = repr(getattr(quantity, 'type', None))

        if 'Reference object' in quantity_type:
            continue
        if 'Datetime' in quantity_type:
            continue

        fields.append(name)

    return sorted(fields)


@app.get('/library-types')
async def library_types():
    result = deepcopy(LIBRARY_TYPES)

    for definition in result['processing_recipe']['schemas'].values():
        definition['fields'] = _recipe_scalar_fields(definition['schema'])

    return result


@app.get('/', response_class=HTMLResponse)
async def index():
    html = (TEMPLATE_DIR / 'index.html').read_text(encoding='utf-8')
    api_base = config.services.api_base_path.rstrip('/') + '/api/v1'
    injection = f'<script>window.NOMAD_API_BASE = {api_base!r};</script>'
    return html.replace(
        '<script src="static/app.js"></script>',
        injection + '<script src="static/app.js"></script>',
        1,
    )


@app.get('/static/styles.css')
async def styles():
    return FileResponse(STATIC_DIR / 'styles.css', media_type='text/css')


@app.get('/static/app.js')
async def javascript():
    return FileResponse(
        STATIC_DIR / 'app.js',
        media_type='application/javascript',
    )
