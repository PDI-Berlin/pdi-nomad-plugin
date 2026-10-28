from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from nomad.config import config

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / 'templates'
STATIC_DIR = BASE_DIR / 'static'

app = FastAPI()


PROCESS_TYPES = {
    'cleaning': {
        'label': 'Cleaning',
        'schema': 'nomad_material_processing.general.CleaningRecipe',
        'processSchema': 'nomad_material_processing.general.Cleaning',
    },
    'annealing': {
        'label': 'Annealing',
        'schema': 'nomad_material_processing.general.AnnealingRecipe',
        'processSchema': 'nomad_material_processing.general.Annealing',
    },
    'backside_coating': {
        'label': 'Backside Coating',
        'schema': 'pdi_nomad_plugin.general.schema.BackSideCoatingRecipePDI',
        'processSchema': 'pdi_nomad_plugin.general.schema.BackSideCoatingPDI',
    },
    'sample_cut': {
        'label': 'Sample Cut',
        'schema': None,
        'processSchema': 'pdi_nomad_plugin.general.schema.SampleCutPDI',
        'kind': 'sample_cut',
    },
}

# No verified upstream SampleCut or BackSideCoating process in the
# canonical modules. Do not register those actions until upstream m_def
# classes are found and runtime-validated. No PDI fallback is permitted.


@app.post('/validate-process')
async def validate_process(payload: dict):
    """Validate the *exact* proposed process against installed upstream metainfo.

    This endpoint is read-only. The browser must require success before any
    upload; neither this endpoint nor its helper executes a normalizer.
    """
    from .original_process_preflight import (
        OriginalProcessValidationError,
        validate_original_process,
    )

    allowed = {
        definition['processSchema']
        for definition in PROCESS_TYPES.values()
        if definition.get('kind') != 'sample_cut'
    }
    try:
        return validate_original_process(payload.get('data'), allowed)
    except OriginalProcessValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get('/process-types')
async def process_types():
    return PROCESS_TYPES


@app.get('/', response_class=HTMLResponse)
async def index():
    # FIX: app.js used to guess its own deployment base path (/nomad-oasis)
    # by searching window.location.pathname for '/gui/' or '/dashboards/'.
    # That breaks whenever this page is loaded in a context where neither
    # substring is present in the URL (e.g. embedded inside NOMAD GUI v2),
    # causing every API call to 404. The backend always knows the real
    # base path, so inject it directly instead of guessing client-side.
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
