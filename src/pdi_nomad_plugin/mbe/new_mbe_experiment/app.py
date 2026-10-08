from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from nomad.config import config
from nomad.utils import hash as nomad_hash

from pdi_nomad_plugin.mbe.materials import ELEMENT_SYMBOLS, MBE_DOPANT_ELEMENTS

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / 'templates'
STATIC_DIR = BASE_DIR / 'static'


DEFAULT_LAYER_COMPOSITIONS = (
    'BaSnO3',
    'LaInO3',
    'SnO2',
    'SnO',
    'GeO2',
    'Al2O3',
    'In2O3',
    'GeO',
    'Ge',
    'Al',
    'Sn',
    'Ba',
    'BaO',
)


@app.get('/api/layer-options')
async def layer_options():
    return {
        'elements': list(ELEMENT_SYMBOLS),
        'dopants': list(MBE_DOPANT_ELEMENTS),
        'compositions': list(DEFAULT_LAYER_COMPOSITIONS),
    }


@app.get('/api/entry-id')
async def calculate_entry_id(
    upload_id: str,
    filename: str,
):
    return {
        'entry_id': nomad_hash(
            upload_id,
            filename,
        )
    }


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
        '<script src="./static/app.js"></script>',
        injection + '<script src="./static/app.js"></script>',
        1,
    )


@app.get('/static/styles.css')
async def styles():
    return FileResponse(
        STATIC_DIR / 'styles.css',
        media_type='text/css',
    )


@app.get('/static/app.js')
async def javascript():
    return FileResponse(
        STATIC_DIR / 'app.js',
        media_type='application/javascript',
    )
