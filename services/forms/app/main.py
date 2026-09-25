"""
Biz GPT Dynamic Forms service.

Internal API (bearer FORMS_API_KEY) is used by the Open WebUI tool and the
Biz GPT gateway. Public API is used by the form page the user sees; the
unguessable form id is the capability for that one form.
"""

import hmac
import os
import secrets
import string
from pathlib import Path
from typing import Any

from fastapi.middleware.cors import CORSMiddleware
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .actions import ActionError, run_action
from .registry import Registry
from .store import Store
from .validation import apply_prefill, full_errors, missing_required, with_defaults

API_KEY = os.getenv('FORMS_API_KEY', '')
PUBLIC_URL = os.getenv('FORMS_PUBLIC_URL', 'http://localhost:8090').rstrip('/')
FRAME_ANCESTORS = os.getenv('FORMS_FRAME_ANCESTORS', "'self'")
TTL_HOURS = int(os.getenv('FORMS_TTL_HOURS', '72'))
WEB_DIST = Path(os.getenv('FORMS_WEB_DIST') or Path(__file__).resolve().parent.parent / 'web' / 'dist')
CORS_ORIGINS = [origin.strip() for origin in os.getenv('FORMS_CORS_ORIGINS', 'http://localhost:3000,null').split(',') if origin.strip()]

# Default: bizgpt/config/forms when running from a source checkout.
registry = Registry(os.getenv('FORMS_CONFIG_DIR') or str(Path(__file__).resolve().parents[3] / 'config' / 'forms'))
store = Store(os.getenv('FORMS_DB_PATH', '/data/forms.db'))

app = FastAPI(title='Biz GPT Forms', version='1.0.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.middleware('http')
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    # The form page is embedded by Open WebUI; only allow the configured origins to frame it.
    response.headers['Content-Security-Policy'] = f'frame-ancestors {FRAME_ANCESTORS}'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


def require_api_key(authorization: str = Header(default='')):
    if not API_KEY:
        raise HTTPException(503, 'FORMS_API_KEY is not configured')
    token = authorization.removeprefix('Bearer ').strip()
    if not hmac.compare_digest(token.encode(), API_KEY.encode()):
        raise HTTPException(401, 'invalid api key')


# ---------- models ----------


class CreateFormRequest(BaseModel):
    form_type: str
    prefill: dict = Field(default_factory=dict)
    context: dict = Field(default_factory=dict)  # user_id, user_email, chat_id


class SubmitRequest(BaseModel):
    values: dict


class CreateViewRequest(BaseModel):
    title: str
    description: str = ''
    data: dict = Field(default_factory=dict)
    schema: dict | None = None
    ui_schema: dict = Field(default_factory=dict)


# ---------- helpers ----------


def form_url(form_id: str) -> str:
    return f'{PUBLIC_URL}/f/{form_id}'


def view_url(view_id: str) -> str:
    return f'{PUBLIC_URL}/v/{view_id}'


def load_form(form_id: str) -> dict:
    form = store.get(form_id)
    if not form:
        raise HTTPException(404, 'form not found')
    return form


def load_view(view_id: str) -> dict:
    view = store.get_view(view_id)
    if not view:
        raise HTTPException(404, 'view not found')
    if view['expired']:
        raise HTTPException(410, 'this view has expired')
    return view


def internal_view(form: dict) -> dict:
    return {
        'form_id': form['id'],
        'form_type': form['form_type'],
        'status': 'expired' if form['expired'] else form['status'],
        'prefill': form['prefill'],
        'missing_fields': form['missing'],
        'values': form['values'],
        'result': form['result'],
        'url': form_url(form['id']),
        'created_at': form['created_at'],
        'updated_at': form['updated_at'],
    }


def internal_json_view(view: dict) -> dict:
    return {
        'view_id': view['id'],
        'title': view['title'],
        'description': view['description'],
        'schema': view['schema'],
        'ui_schema': view['ui_schema'],
        'data': view['data'],
        'url': view_url(view['id']),
        'created_at': view['created_at'],
        'expires_at': view['expires_at'],
    }


class _SafeDict(dict):
    def __missing__(self, key):
        return '{' + key + '}'


def titleize(key: str) -> str:
    return ' '.join(part.capitalize() for part in key.replace('-', '_').split('_') if part) or 'Value'


def infer_json_schema(value: Any, key: str = 'value') -> dict:
    if isinstance(value, dict):
        properties = {name: infer_json_schema(child, name) for name, child in value.items()}
        return {
            'type': 'object',
            'title': titleize(key),
            'properties': properties,
            'additionalProperties': False,
        }
    if isinstance(value, list):
        item_schema = infer_json_schema(value[0], f'{key}_item') if value else {'type': 'string', 'title': 'Item'}
        return {'type': 'array', 'title': titleize(key), 'items': item_schema}
    if isinstance(value, bool):
        return {'type': 'boolean', 'title': titleize(key)}
    if isinstance(value, int) and not isinstance(value, bool):
        return {'type': 'integer', 'title': titleize(key)}
    if isinstance(value, float):
        return {'type': 'number', 'title': titleize(key)}
    if value is None:
        return {'type': 'string', 'title': titleize(key), 'default': ''}
    return {'type': 'string', 'title': titleize(key), 'default': str(value)}


def normalize_view_data(data: dict) -> dict:
    def convert(value: Any):
        if isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        if isinstance(value, list):
            return [convert(v) for v in value]
        if value is None:
            return ''
        if isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    return convert(data)


async def submit(form: dict, values: dict) -> dict:
    if form['expired']:
        raise HTTPException(410, 'this form has expired')
    if form['status'] != 'draft':
        raise HTTPException(409, f'this form was already {form["status"]}')
    form_type = registry.get(form['form_type'])
    if not form_type:
        raise HTTPException(410, 'form type no longer exists')

    # Prefilled values are part of the submitted form state; the public form only
    # posts user-edited fields, so we always merge them here before validating.
    merged_values = {**form['prefill'], **values}
    errors = full_errors(form_type.json_schema, merged_values)
    if errors:
        return JSONResponse(status_code=422, content={'status': 'invalid', 'errors': errors})
    if not store.claim_for_submit(form['id'], merged_values):
        raise HTTPException(409, 'this form was already submitted')

    try:
        result = await run_action(form_type, form['id'], merged_values, form['context'])
    except Exception as e:  # noqa: BLE001 - any action failure goes back to the user
        # Back to draft so the user can fix the problem and retry.
        detail = str(e) if isinstance(e, ActionError) else 'the action could not be completed'
        store.finish(form['id'], 'draft', {'error': detail})
        return JSONResponse(status_code=502, content={'status': 'failed', 'message': f'Submission failed: {detail}'})

    message = string.Formatter().vformat(form_type.success_message, (), _SafeDict({**merged_values, **result}))
    result['message'] = message
    store.finish(form['id'], 'executed', result)
    return {'status': 'executed', 'message': message, 'result': result}


# ---------- internal API ----------


@app.get('/health')
def health():
    return {'status': 'ok', 'form_types': len(registry.types)}


@app.get('/api/form-types', dependencies=[Depends(require_api_key)])
def list_form_types():
    return [
        {'id': t.id, 'title': t.title, 'description': t.description, 'keywords': t.keywords, 'fields': t.fields()}
        for t in registry.types.values()
    ]


@app.post('/api/form-types/reload', dependencies=[Depends(require_api_key)])
def reload_form_types():
    registry.reload()
    return {'form_types': list(registry.types)}


@app.post('/api/forms', dependencies=[Depends(require_api_key)])
def create_form(req: CreateFormRequest):
    form_type = registry.get(req.form_type)
    if not form_type:
        raise HTTPException(404, f'unknown form_type {req.form_type!r}. Known: {sorted(registry.types)}')
    accepted, rejected = apply_prefill(form_type.json_schema, req.prefill)
    values = with_defaults(form_type.json_schema, accepted)
    missing = missing_required(form_type.json_schema, values)
    context = {**req.context, 'extracted_fields': list(accepted)}
    form = store.create(secrets.token_urlsafe(18), form_type.id, values, missing, context, TTL_HOURS)
    return {**internal_view(form), 'prefill_rejected': rejected}


@app.get('/api/forms', dependencies=[Depends(require_api_key)])
def recent_forms(limit: int = 50):
    return [internal_view(f) for f in store.recent(min(limit, 200))]


@app.get('/api/forms/{form_id}', dependencies=[Depends(require_api_key)])
def get_form(form_id: str):
    return internal_view(load_form(form_id))


@app.post('/api/views', dependencies=[Depends(require_api_key)])
def create_view(req: CreateViewRequest):
    data = normalize_view_data(req.data)
    schema = req.schema or infer_json_schema(data, 'result')
    view = store.create_view(
        secrets.token_urlsafe(18),
        req.title,
        req.description,
        schema,
        req.ui_schema,
        data,
        TTL_HOURS,
    )
    return internal_json_view(view)


@app.post('/api/forms/{form_id}/submit', dependencies=[Depends(require_api_key)])
async def submit_form_internal(form_id: str, req: SubmitRequest):
    form = load_form(form_id)
    return await submit(form, req.values)


# ---------- public API (form page) ----------


@app.get('/api/public/forms/{form_id}')
def get_public_form(form_id: str):
    form = load_form(form_id)
    form_type = registry.get(form['form_type'])
    if not form_type:
        raise HTTPException(410, 'form type no longer exists')
    return {
        'mode': 'form',
        'form_id': form['id'],
        'title': form_type.title,
        'description': form_type.description,
        'schema': form_type.json_schema,
        'ui_schema': form_type.ui_schema,
        'submit_label': form_type.submit_label,
        'form_data': form['values'] or form['prefill'],
        'prefilled_fields': form['context'].get('extracted_fields', []),
        'status': 'expired' if form['expired'] else form['status'],
        'result': form['result'],
    }


@app.get('/api/public/views/{view_id}')
def get_public_view(view_id: str):
    view = load_view(view_id)
    return {
        'mode': 'view',
        'view_id': view['id'],
        'title': view['title'],
        'description': view['description'],
        'schema': view['schema'],
        'ui_schema': view['ui_schema'],
        'form_data': view['data'],
        'status': 'view',
    }


@app.post('/api/public/forms/{form_id}/submit')
async def submit_public_form(form_id: str, req: SubmitRequest):
    return await submit(load_form(form_id), req.values)


# ---------- form page (React build) ----------

if (WEB_DIST / 'assets').exists():
    app.mount('/assets', StaticFiles(directory=WEB_DIST / 'assets'), name='assets')


@app.get('/f/{form_id}')
def form_page(form_id: str):
    index = WEB_DIST / 'index.html'
    if not index.exists():
        raise HTTPException(503, 'form UI not built (run npm run build in services/forms/web)')
    return FileResponse(index, headers={'Cache-Control': 'no-store'})


@app.get('/v/{view_id}')
def view_page(view_id: str):
    index = WEB_DIST / 'index.html'
    if not index.exists():
        raise HTTPException(503, 'form UI not built (run npm run build in services/forms/web)')
    return FileResponse(index, headers={'Cache-Control': 'no-store'})
