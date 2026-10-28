import importlib
from copy import deepcopy
from pathlib import Path

from fastapi import FastAPI, HTTPException
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
                'schema': 'nomad_material_processing.general.CleaningRecipe',
                'id_prefix': 'CLEAN',
                'write_supported': True,
                'usage_schemas': [
                    'nomad_material_processing.general.Cleaning',
                ],
            },
            'annealing': {
                'label': 'Annealing',
                'schema': 'nomad_material_processing.general.AnnealingRecipe',
                'id_prefix': 'ANNEAL',
                'write_supported': True,
                'usage_schemas': [
                    'nomad_material_processing.general.Annealing',
                ],
            },
            'backside_coating': {
                'label': 'Backside Coating',
                'schema': 'pdi_nomad_plugin.general.schema.BackSideCoatingRecipePDI',
                'id_prefix': 'BACKCOAT',
                'write_supported': True,
                'usage_schemas': [
                    'pdi_nomad_plugin.general.schema.BackSideCoatingPDI',
                ],
            },
        },
    },
    'holder': {
        'label': 'Holders',
        'schema': 'pdi_nomad_plugin.mbe.instrument.SubstrateHolderPDI',
        'kind': 'holder',
        'write_supported': True,
        'write_block_reason': '',
        'usage_schemas': [
            'nomad_material_processing.vapor_deposition.general.FilledSubstrateHolder',
        ],
    },
    'insert': {
        'label': 'Inserts',
        'schema': 'pdi_nomad_plugin.mbe.instrument.InsertReductionPDI',
        'kind': 'insert',
        'write_supported': True,
        'write_block_reason': '',
        'usage_schemas': [
            'nomad_material_processing.vapor_deposition.general.FilledSubstrateHolder',
        ],
    },
}


def _recipe_schema_details(schema_path):
    """Describe fields from the *installed* NOMAD schema, read-only.

    This metadata is only used to render GUI controls. It neither defines
    schemas nor duplicates NOMAD normalization logic.
    """
    module_name, class_name = schema_path.rsplit('.', 1)
    cls = getattr(importlib.import_module(module_name), class_name)
    reserved = {
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
        'instruments',
        'description',
    }
    fields = []
    for name, quantity in cls.m_def.all_quantities.items():
        if name in reserved or getattr(quantity, 'shape', None):
            continue
        type_text = repr(getattr(quantity, 'type', '')).lower()
        if any(
            word in type_text
            for word in (
                'reference object',
                'datetime',
                'sectionproxy',
            )
        ):
            continue
        if 'bool' in type_text:
            kind = 'boolean'
        elif (
            any(
                word in type_text
                for word in (
                    'int',
                    'float',
                    'number',
                    'm_double',
                )
            )
            and 'm_enum' not in type_text
        ):
            kind = 'number'
        else:
            kind = 'text'
        unit = getattr(quantity, 'unit', None)
        fields.append(
            {
                'name': name,
                'kind': kind,
                'unit': str(unit) if unit is not None else None,
            }
        )

    subsections = []
    for name, subsection in cls.m_def.all_sub_sections.items():
        # Runtime sample references and instrument associations are not
        # reusable recipe parameters; never copy them into new recipes.
        if name in {'samples', 'instruments'}:
            continue
        try:
            child = subsection.sub_section.section_cls
        except (AttributeError, ValueError):
            continue
        subsections.append(
            {
                'name': name,
                'repeats': bool(subsection.repeats),
                'schema': f'{child.__module__}.{child.__name__}',
            }
        )
    return {'field_specs': fields, 'subsection_specs': subsections}


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


@app.post('/validate-recipe')
async def validate_recipe(payload: dict):
    """Read-only original NOMAD metainfo preflight before any upload."""
    from .original_preflight import (
        OriginalSchemaValidationError,
        validate_original_recipe,
    )

    allowed = {
        definition['schema']
        for definition in LIBRARY_TYPES['processing_recipe']['schemas'].values()
        if definition['write_supported'] is True
    }
    try:
        return validate_original_recipe(payload.get('data'), allowed)
    except OriginalSchemaValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get('/library-types')
async def library_types():
    result = deepcopy(LIBRARY_TYPES)

    for definition in result['processing_recipe']['schemas'].values():
        schema_path = definition['schema']
        details = _recipe_schema_details(schema_path)
        definition['fields'] = _recipe_scalar_fields(schema_path)
        definition.update(details)

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
