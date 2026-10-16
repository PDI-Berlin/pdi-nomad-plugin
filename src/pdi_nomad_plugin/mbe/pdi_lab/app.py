from pathlib import Path
import json

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from nomad.config import config

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / 'templates'
STATIC_DIR = BASE_DIR / 'static'

app = FastAPI()


@app.get('/', response_class=HTMLResponse)
async def index():
    html = (TEMPLATE_DIR / 'index.html').read_text(encoding='utf-8')
    base = config.services.api_base_path.rstrip('/')
    injected = '<script>window.PDI_LAB_BASE = ' + json.dumps(base) + ';</script>'
    return html.replace('<script src="static/app.js"></script>',
                        injected + '<script src="static/app.js"></script>', 1)


@app.get('/static/styles.css')
async def styles():
    return FileResponse(STATIC_DIR / 'styles.css', media_type='text/css')


@app.get('/static/app.js')
async def javascript():
    return FileResponse(
        STATIC_DIR / 'app.js',
        media_type='application/javascript',
    )
