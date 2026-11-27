import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from nomad.config import config

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / 'templates'
STATIC_DIR = BASE_DIR / 'static'

app = FastAPI()


@app.get('/', response_class=HTMLResponse)
async def index():
    shell = (TEMPLATE_DIR / 'index.html').read_text(encoding='utf-8')
    inventory = (TEMPLATE_DIR / 'inventory.html').read_text(encoding='utf-8')
    script = (STATIC_DIR / 'inventory.js').read_text(encoding='utf-8')

    marker = '<script src="static/inventory.js"></script>'
    if inventory.count(marker) != 1:
        raise RuntimeError('Inventory script marker missing')

    inventory = inventory.replace(marker, '<script>' + script + '</script>', 1)
    api = config.services.api_base_path.rstrip('/') + '/api/v1'
    inventory = inventory.replace(
        '</head>',
        '<script>window.NOMAD_API_BASE = ' + json.dumps(api) + ';</script></head>',
        1,
    )

    base = config.services.api_base_path.rstrip('/')
    injected = (
        '<script>window.PDI_LAB_BASE = '
        + json.dumps(base)
        + ';window.PDI_LAB_INVENTORY_SRCDOC = '
        + json.dumps(inventory).replace('</', '<\\/')
        + ';</script>'
    )
    marker = '<script src="static/app.js"></script>'
    if shell.count(marker) != 1:
        raise RuntimeError('Workspace script marker missing')
    return shell.replace(marker, injected + marker, 1)


@app.get('/inventory', response_class=HTMLResponse)
async def inventory():
    html = (TEMPLATE_DIR / 'inventory.html').read_text()
    api = config.services.api_base_path.rstrip('/') + '/api/v1'
    injection = '<script>window.NOMAD_API_BASE = ' + json.dumps(api) + ';</script>'
    return html.replace('</head>', injection + '</head>', 1)


@app.get('/static/pdi-lab-logo-420.png')
async def sidebar_logo():
    return FileResponse(
        STATIC_DIR / 'pdi-lab-logo-420.png',
        media_type='image/png',
    )


@app.get('/static/inventory.js')
async def inventory_js():
    return FileResponse(
        STATIC_DIR / 'inventory.js', media_type='application/javascript'
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
