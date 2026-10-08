from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from nomad.config import config

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / 'templates'
STATIC_DIR = BASE_DIR / 'static'

app = FastAPI()


PROCESS_TYPES = {
    'cleaning': {
        'label': 'Cleaning',
        'schema': 'pdi_nomad_plugin.general.schema.CleaningRecipePDI',
        'processSchema': 'pdi_nomad_plugin.general.schema.CleaningPDI',
    },
    'annealing': {
        'label': 'Annealing',
        'schema': 'pdi_nomad_plugin.general.schema.AnnealingRecipePDI',
        'processSchema': 'pdi_nomad_plugin.general.schema.AnnealingPDI',
    },
    'etching': {
        'label': 'Etching',
        'schema': 'pdi_nomad_plugin.general.schema.EtchingRecipePDI',
        'processSchema': 'pdi_nomad_plugin.general.schema.EtchingPDI',
    },
    'back_side_coating': {
        'label': 'Back-side coating',
        'schema': 'pdi_nomad_plugin.general.schema.BackSideCoatingRecipePDI',
        'processSchema': 'pdi_nomad_plugin.general.schema.BackSideCoatingPDI',
    },
    'sample_cut': {
        'label': 'Sample Cut',
        'schema': 'pdi_nomad_plugin.general.schema.SampleCutRecipePDI',
        'processSchema': 'pdi_nomad_plugin.general.schema.SampleCutPDI',
        'kind': 'sample_cut',
    },
}


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
