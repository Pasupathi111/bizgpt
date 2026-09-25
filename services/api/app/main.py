import os
import secrets
import json
from pathlib import Path
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from jsonschema import Draft202012Validator
from pydantic import BaseModel, Field

from .registry import WorkflowEntry, WorkflowRegistry
from .store import Store


def default_workflows_config_path() -> str:
    env_value = os.getenv('WORKFLOWS_CONFIG_PATH', '').strip()
    if env_value:
        return env_value
    return str(Path(__file__).resolve().parents[3] / 'config' / 'workflows.yaml')


def default_workflow_studio_dir() -> str:
    env_value = os.getenv('WORKFLOW_STUDIO_DIR', '').strip()
    if env_value:
        return env_value
    resolved = Path(__file__).resolve()
    root = resolved.parents[3] if len(resolved.parents) > 3 else resolved.parents[-1]
    return str(root / 'config' / 'workflow-studio')


WORKFLOWS_CONFIG_PATH = default_workflows_config_path()
API_DB_PATH = os.getenv('API_DB_PATH', '/data/api.db')
API_WEB_DIST = Path(os.getenv('API_WEB_DIST') or Path(__file__).resolve().parent.parent / 'web' / 'dist')
WORKFLOW_STUDIO_DIR = Path(default_workflow_studio_dir())
CORS_ORIGINS = [origin.strip() for origin in os.getenv('API_CORS_ORIGINS', 'http://localhost:3000,http://localhost:8093').split(',') if origin.strip()]
FORMS_API_URL = os.getenv('FORMS_API_URL', 'http://bizgpt-forms:8000').rstrip('/')
FORMS_API_KEY = os.getenv('FORMS_API_KEY', '').strip()
INTEGRATIONS_API_URL = os.getenv('INTEGRATIONS_API_URL', 'http://bizgpt-integrations:8002').rstrip('/')
INTEGRATIONS_API_KEY = os.getenv('INTEGRATIONS_API_KEY', '').strip()
TERMINAL_RUN_STATES = {'succeeded', 'failed', 'stopped', 'cancelled', 'completed'}

registry = WorkflowRegistry(WORKFLOWS_CONFIG_PATH)
store = Store(API_DB_PATH)

app = FastAPI(title='Biz GPT API', version='1.0.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=['*'],
    allow_headers=['*'],
)
if (API_WEB_DIST / 'assets').exists():
    app.mount('/assets', StaticFiles(directory=API_WEB_DIST / 'assets'), name='dashboard-assets')


class RunWorkflowRequest(BaseModel):
    inputs: dict = Field(default_factory=dict)
    confirm: bool = False
    wait: bool = True
    user_id: str = ''
    user_email: str = ''


class StopWorkflowRunRequest(BaseModel):
    reason: str = 'Stopped from Biz GPT dashboard'


async def json_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict | None = None,
    body: dict | None = None,
    timeout: float = 30.0,
):
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(method, url, headers=headers, params=params, json=body)
    if response.status_code >= 400:
        detail = response.text[:400]
        raise HTTPException(response.status_code, detail)
    if not response.content:
        return {}
    return response.json()


async def dify_request(workflow: WorkflowEntry, method: str, path: str, *, body: dict | None = None, timeout: float = 30.0):
    config = workflow.configuration()
    base = str(config['base_url']).rstrip('/')
    key = str(config['api_key'])
    if not base or not key:
        raise HTTPException(424, f'Workflow {workflow.id} is not configured')
    return await json_request(
        method,
        f'{base}{path}',
        headers={'Authorization': f'Bearer {key}'},
        body=body,
        timeout=timeout,
    )


async def forms_request(path: str, *, params: dict | None = None):
    if not FORMS_API_KEY:
        raise HTTPException(503, 'FORMS_API_KEY is not configured')
    return await json_request(
        'GET',
        f'{FORMS_API_URL}{path}',
        headers={'Authorization': f'Bearer {FORMS_API_KEY}'},
        params=params,
    )


async def integrations_request(path: str, *, params: dict | None = None):
    if not INTEGRATIONS_API_KEY:
        raise HTTPException(503, 'INTEGRATIONS_API_KEY is not configured')
    return await json_request(
        'GET',
        f'{INTEGRATIONS_API_URL}{path}',
        headers={'Authorization': f'Bearer {INTEGRATIONS_API_KEY}'},
        params=params,
    )


def first_list(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ('parameters', 'user_input_form', 'inputs', 'data'):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def normalize_parameter_field(field: dict) -> tuple[str, dict, dict]:
    name = str(field.get('name') or field.get('variable') or field.get('field') or '').strip()
    if not name:
        raise ValueError('parameter has no name')
    field_type = str(field.get('type') or field.get('input_type') or 'string').strip().lower()
    title = field.get('label') or field.get('title') or name.replace('_', ' ').title()
    description = field.get('description') or field.get('help') or ''
    required = bool(field.get('required'))
    default = field.get('default')
    options = field.get('options') or field.get('choices') or field.get('enum') or []

    schema: dict[str, Any]
    ui: dict[str, Any] = {}
    if field_type in {'paragraph', 'textarea'}:
        schema = {'type': 'string', 'title': title, 'description': description}
        ui = {'ui:widget': 'textarea', 'ui:options': {'rows': 3}}
    elif field_type in {'number', 'float', 'decimal'}:
        schema = {'type': 'number', 'title': title, 'description': description}
    elif field_type in {'integer', 'int'}:
        schema = {'type': 'integer', 'title': title, 'description': description}
    elif field_type in {'boolean', 'bool', 'switch', 'checkbox'}:
        schema = {'type': 'boolean', 'title': title, 'description': description}
    elif field_type in {'select', 'dropdown', 'radio'} and isinstance(options, list) and options:
        values = []
        for item in options:
            if isinstance(item, dict):
                values.append(item.get('value') or item.get('name') or item.get('label'))
            else:
                values.append(item)
        schema = {'type': 'string', 'title': title, 'description': description, 'enum': [value for value in values if value is not None]}
    elif field_type in {'date'}:
        schema = {'type': 'string', 'title': title, 'description': description, 'format': 'date'}
    elif field_type in {'datetime', 'date-time'}:
        schema = {'type': 'string', 'title': title, 'description': description, 'format': 'date-time'}
    else:
        schema = {'type': 'string', 'title': title, 'description': description}

    if default not in (None, ''):
        schema['default'] = default
    return name, schema, ui | ({'required': required} if required else {})


def normalized_schema_from_parameters(parameters_payload: Any, fallback_schema: dict, fallback_ui_schema: dict):
    items = first_list(parameters_payload)
    if not items:
        return fallback_schema, fallback_ui_schema, 'registry_fallback'

    properties: dict[str, dict] = {}
    ui_schema: dict[str, Any] = {'ui:order': []}
    required: list[str] = []
    for item in items:
        try:
            name, schema, ui = normalize_parameter_field(item)
        except ValueError:
            continue
        properties[name] = schema
        ui_schema['ui:order'].append(name)
        if ui.get('required'):
            required.append(name)
        if 'ui:widget' in ui:
            ui_schema[name] = {key: value for key, value in ui.items() if key != 'required'}

    if not properties:
        return fallback_schema, fallback_ui_schema, 'registry_fallback'

    schema = {'type': 'object', 'properties': properties, 'required': required}
    return schema, ui_schema, 'dify_parameters'


async def workflow_detail(workflow: WorkflowEntry) -> dict:
    config = workflow.configuration()
    info = {}
    parameters = {}
    provider_error = ''
    if config['configured']:
        try:
            info = await dify_request(workflow, 'GET', '/v1/info')
        except HTTPException as exc:
            provider_error = exc.detail
        try:
            parameters = await dify_request(workflow, 'GET', '/v1/parameters')
        except HTTPException as exc:
            provider_error = provider_error or exc.detail
    schema, ui_schema, input_source = normalized_schema_from_parameters(
        parameters,
        workflow.input.json_schema,
        workflow.input.ui_schema,
    )
    Draft202012Validator.check_schema(schema)
    return {
        'id': workflow.id,
        'name': info.get('name') or workflow.name,
        'description': info.get('description') or workflow.description,
        'tags': workflow.tags,
        'provider': workflow.provider,
        'configured': config['configured'],
        'config_source': config['source'],
        'config_missing': config['missing'],
        'config_sources': {
            'base_url': config['base_url_source'],
            'api_key': config['api_key_source'],
        },
        'matched_app': config['matched_app'],
        'requires_confirmation': workflow.execution.requires_confirmation,
        'supports_form': workflow.execution.expose_as_form,
        'supports_tool': workflow.execution.expose_as_tool,
        'input_schema': schema,
        'ui_schema': ui_schema,
        'input_source': input_source,
        'provider_info': info,
        'provider_error': provider_error,
    }


def validator_errors(schema: dict, values: dict) -> list[dict]:
    validator = Draft202012Validator(schema)
    errors = []
    for error in sorted(validator.iter_errors(values), key=lambda item: list(item.path)):
        path = '.'.join(str(part) for part in error.path)
        errors.append({'field': path, 'message': error.message})
    return errors


def scalarize_inputs(values: dict) -> dict:
    out = {}
    for key, value in values.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
        else:
            out[key] = str(value)
    return out


def workflow_status_for_ui(workflow: WorkflowEntry, recent_runs: list[dict]) -> str:
    if recent_runs:
        latest = recent_runs[0].get('status') or ''
        if latest in {'running', 'queued', 'pending'}:
            return 'running'
        if latest in {'failed', 'stopped', 'cancelled'}:
            return 'attention'
    return 'live' if workflow.configured() else 'needs_setup'


def fallback_studio_config(workflow: WorkflowEntry, detail: dict) -> dict:
    accent = {
        'sales': 'violet',
        'hr': 'emerald',
        'it': 'amber',
    }
    accent_color = 'blue'
    for tag in workflow.tags:
        if tag in accent:
            accent_color = accent[tag]
            break

    node_titles = [
        ('start', 'Start', 'Capture workflow request'),
        ('schema', 'Input Schema', f"Validate {len((detail.get('input_schema') or {}).get('properties', {}))} workflow fields"),
        ('execute', workflow.name, 'Execute live Dify workflow'),
        ('result', 'Result', 'Format final response and outputs'),
    ]
    nodes = []
    x = 48
    for index, (node_id, title, subtitle) in enumerate(node_titles):
        nodes.append(
            {
                'id': node_id,
                'type': 'default' if index not in {0, len(node_titles) - 1} else ('start' if index == 0 else 'result'),
                'title': title,
                'subtitle': subtitle,
                'description': subtitle,
                'position': {'x': x, 'y': 118 if index % 2 == 0 else 300},
                'size': {'width': 220, 'height': 132},
                'inputs': [] if index == 0 else ['payload'],
                'outputs': [] if index == len(node_titles) - 1 else ['payload'],
                'config': {
                    'workflow_id': workflow.id,
                    'mode': workflow.dify.app_mode,
                    'response_mode': workflow.dify.response_mode,
                },
            }
        )
        x += 250
    edges = [{'source': nodes[index]['id'], 'target': nodes[index + 1]['id']} for index in range(len(nodes) - 1)]
    return {
        'meta': {
            'status': workflow_status_for_ui(workflow, []),
            'version': 'v1.0',
            'environment': 'Production',
            'accent_color': accent_color,
        },
        'nodes': nodes,
        'edges': edges,
    }


def load_studio_config(workflow: WorkflowEntry, detail: dict, recent_runs: list[dict]) -> dict:
    path = WORKFLOW_STUDIO_DIR / f'{workflow.id}.json'
    raw = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text())
        except json.JSONDecodeError:
            raw = {}
    studio = raw if isinstance(raw, dict) else {}
    if not studio.get('nodes'):
        studio = fallback_studio_config(workflow, detail)

    meta = studio.get('meta') if isinstance(studio.get('meta'), dict) else {}
    meta.setdefault('status', workflow_status_for_ui(workflow, recent_runs))
    meta.setdefault('version', 'v1.0')
    meta.setdefault('environment', 'Production')
    meta.setdefault('accent_color', 'blue')
    studio['meta'] = meta
    studio['nodes'] = [node for node in studio.get('nodes', []) if isinstance(node, dict)]
    studio['edges'] = [edge for edge in studio.get('edges', []) if isinstance(edge, dict)]
    return studio


async def studio_payload(workflow: WorkflowEntry) -> dict:
    detail = await workflow_detail(workflow)
    recent_runs = store.runs_for_workflow(workflow.id, 8)
    studio = load_studio_config(workflow, detail, recent_runs)
    return {
        'workflow': {
            'id': detail['id'],
            'name': detail['name'],
            'description': detail['description'],
            'tags': detail['tags'],
            'configured': detail['configured'],
            'config_source': detail['config_source'],
            'config_missing': detail['config_missing'],
            'matched_app': detail['matched_app'],
            'requires_confirmation': detail['requires_confirmation'],
            'supports_form': detail['supports_form'],
            'supports_tool': detail['supports_tool'],
            'status': studio['meta'].get('status', 'live'),
            'version': studio['meta'].get('version', 'v1.0'),
            'environment': studio['meta'].get('environment', 'Production'),
            'accent_color': studio['meta'].get('accent_color', 'blue'),
            'provider_error': detail['provider_error'],
        },
        'graph': {
            'nodes': studio['nodes'],
            'edges': studio['edges'],
        },
        'test_form': {
            'schema': detail['input_schema'],
            'ui_schema': detail['ui_schema'],
            'input_source': detail['input_source'],
        },
        'recent_runs': recent_runs,
    }


async def execute_provider_workflow(workflow: WorkflowEntry, inputs: dict, user_label: str) -> dict:
    payload = await dify_request(
        workflow,
        'POST',
        '/v1/workflows/run',
        body={
            'inputs': scalarize_inputs(inputs),
            'response_mode': workflow.dify.response_mode,
            'user': user_label or 'bizgpt-dashboard',
        },
        timeout=300.0,
    )
    return payload.get('data') if isinstance(payload, dict) and isinstance(payload.get('data'), dict) else payload


async def execute_background_run(local_run_id: str, workflow_id: str, inputs: dict, user_label: str):
    workflow = registry.get(workflow_id)
    if not workflow:
        store.finish_run(local_run_id, status='failed', error=f'Unknown workflow {workflow_id}')
        return
    if not workflow.configured():
        store.finish_run(local_run_id, status='failed', error=f'Workflow {workflow_id} is not configured')
        return
    store.set_run_status(local_run_id, status='running')
    try:
        data = await execute_provider_workflow(workflow, inputs, user_label)
    except HTTPException as exc:
        store.finish_run(local_run_id, status='failed', error=str(exc.detail))
        return
    except Exception as exc:
        store.finish_run(local_run_id, status='failed', error=str(exc))
        return

    store.finish_run(
        local_run_id,
        status=data.get('status') or 'succeeded',
        provider_run_id=data.get('id') or data.get('workflow_run_id'),
        provider_task_id=data.get('task_id'),
        outputs=data.get('outputs') or {},
        error=data.get('error'),
    )


async def refresh_run(run: dict) -> dict:
    workflow = registry.get(run['workflow_id'])
    if not workflow or not workflow.configured() or not run.get('provider_run_id'):
        return run
    try:
        payload = await dify_request(workflow, 'GET', f"/v1/workflows/run/{run['provider_run_id']}")
    except HTTPException:
        return run
    data = payload.get('data') if isinstance(payload, dict) and isinstance(payload.get('data'), dict) else payload
    status = data.get('status') or run['status']
    outputs = data.get('outputs') or run['outputs']
    error = data.get('error') or run['error']
    return store.finish_run(
        run['id'],
        status=status,
        provider_run_id=run.get('provider_run_id'),
        provider_task_id=run.get('provider_task_id') or data.get('task_id'),
        outputs=outputs,
        error=error,
    )


@app.get('/health')
async def health():
    forms_ok = False
    integrations_ok = False
    try:
        forms = await forms_request('/health')
        forms_ok = forms.get('status') == 'ok'
    except HTTPException:
        pass
    try:
        integrations = await integrations_request('/health')
        integrations_ok = integrations.get('status') == 'ok'
    except HTTPException:
        pass
    return {
        'status': 'ok',
        'workflow_count': len(registry.list()),
        'configured_workflow_count': len([workflow for workflow in registry.list() if workflow.configured()]),
        'forms_service': forms_ok,
        'integrations_service': integrations_ok,
    }


@app.get('/api/overview')
async def overview():
    forms_recent = []
    integrations_health = {}
    try:
        forms_recent = await forms_request('/api/forms', params={'limit': 5})
    except HTTPException:
        forms_recent = []
    try:
        integrations_health = await integrations_request('/health')
    except HTTPException:
        integrations_health = {'status': 'unreachable'}
    runs = store.recent_runs(10)
    workflows = registry.list()
    return {
        'workflow_count': len(workflows),
        'configured_workflow_count': len([workflow for workflow in workflows if workflow.configured()]),
        'recent_runs': runs,
        'recent_forms': forms_recent,
        'integrations': integrations_health,
    }


@app.get('/api/workflows')
def list_workflows():
    items = []
    for workflow in registry.list():
        config = workflow.configuration()
        recent_runs = store.runs_for_workflow(workflow.id, 1)
        items.append(
            {
                'id': workflow.id,
                'name': workflow.name,
                'description': workflow.description,
                'tags': workflow.tags,
                'configured': config['configured'],
                'config_source': config['source'],
                'config_missing': config['missing'],
                'matched_app': config['matched_app'],
                'requires_confirmation': workflow.execution.requires_confirmation,
                'supports_form': workflow.execution.expose_as_form,
                'supports_tool': workflow.execution.expose_as_tool,
                'status': workflow_status_for_ui(workflow, recent_runs),
                'latest_run': recent_runs[0] if recent_runs else None,
            }
        )
    return items


@app.post('/api/workflows/reload')
def reload_workflows():
    registry.reload()
    return {'status': 'reloaded', 'workflow_count': len(registry.list())}


@app.get('/api/workflows/{workflow_id}')
async def get_workflow(workflow_id: str):
    workflow = registry.get(workflow_id)
    if not workflow:
        raise HTTPException(404, f'Unknown workflow {workflow_id}')
    return await workflow_detail(workflow)


@app.get('/api/workflows/{workflow_id}/studio')
async def get_workflow_studio(workflow_id: str):
    workflow = registry.get(workflow_id)
    if not workflow:
        raise HTTPException(404, f'Unknown workflow {workflow_id}')
    return await studio_payload(workflow)


@app.get('/api/workflows/{workflow_id}/runs')
def workflow_runs(workflow_id: str, limit: int = 20):
    workflow = registry.get(workflow_id)
    if not workflow:
        raise HTTPException(404, f'Unknown workflow {workflow_id}')
    return store.runs_for_workflow(workflow_id, min(limit, 100))


@app.post('/api/workflows/{workflow_id}/run')
async def run_workflow(workflow_id: str, req: RunWorkflowRequest, background_tasks: BackgroundTasks):
    workflow = registry.get(workflow_id)
    if not workflow:
        raise HTTPException(404, f'Unknown workflow {workflow_id}')
    detail = await workflow_detail(workflow)
    errors = validator_errors(detail['input_schema'], req.inputs)
    if errors:
        return {'status': 'invalid', 'errors': errors}
    if workflow.execution.requires_confirmation and not req.confirm:
        return {
            'status': 'confirmation_required',
            'workflow_id': workflow_id,
            'preview': req.inputs,
            'message': f'{workflow.name} requires confirmation before execution.',
        }
    if not workflow.configured():
        raise HTTPException(424, f'Workflow {workflow_id} is not configured')

    local_run_id = f'run_{secrets.token_hex(6)}'
    store.create_run(local_run_id, workflow_id, req.inputs)
    user_label = req.user_email or req.user_id or 'bizgpt-dashboard'
    if not req.wait:
        queued = store.set_run_status(local_run_id, status='queued')
        background_tasks.add_task(execute_background_run, local_run_id, workflow_id, req.inputs, user_label)
        return {
            'run_id': queued['id'],
            'workflow_id': workflow_id,
            'status': queued['status'],
            'provider_run_id': queued.get('provider_run_id'),
            'provider_task_id': queued.get('provider_task_id'),
            'outputs': queued['outputs'],
            'error': queued.get('error'),
        }

    store.set_run_status(local_run_id, status='running')
    data = await execute_provider_workflow(workflow, req.inputs, user_label)
    finished = store.finish_run(
        local_run_id,
        status=data.get('status') or 'succeeded',
        provider_run_id=data.get('id') or data.get('workflow_run_id'),
        provider_task_id=data.get('task_id'),
        outputs=data.get('outputs') or {},
        error=data.get('error'),
    )
    return {
        'run_id': finished['id'],
        'workflow_id': workflow_id,
        'status': finished['status'],
        'provider_run_id': finished.get('provider_run_id'),
        'provider_task_id': finished.get('provider_task_id'),
        'outputs': finished['outputs'],
        'error': finished.get('error'),
    }


@app.get('/api/workflow-runs')
def recent_workflow_runs(limit: int = 20):
    return store.recent_runs(min(limit, 100))


@app.get('/api/workflow-runs/{run_id}')
async def get_workflow_run(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, f'Unknown run {run_id}')
    return await refresh_run(run)


@app.post('/api/workflow-runs/{run_id}/stop')
async def stop_workflow_run(run_id: str, req: StopWorkflowRunRequest):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, f'Unknown run {run_id}')
    workflow = registry.get(run['workflow_id'])
    if not workflow or not workflow.configured():
        raise HTTPException(424, 'Workflow is not configured')
    if not run.get('provider_task_id'):
        raise HTTPException(409, 'Run has no provider task id')
    payload = await dify_request(
        workflow,
        'POST',
        f"/v1/workflows/tasks/{run['provider_task_id']}/stop",
        body={'reason': req.reason},
    )
    status = payload.get('status') or payload.get('result') or 'stopped'
    return store.finish_run(
        run_id,
        status='stopped' if status else 'stopped',
        provider_run_id=run.get('provider_run_id'),
        provider_task_id=run.get('provider_task_id'),
        outputs=run.get('outputs'),
        error=None,
    )


@app.get('/api/forms/recent')
async def forms_recent(limit: int = 20):
    return await forms_request('/api/forms', params={'limit': min(limit, 100)})


@app.get('/api/integrations/health')
async def integrations_health():
    return await integrations_request('/health')


@app.get('/api/integrations/setup')
async def integrations_setup(integration: str = 'gmail'):
    return await integrations_request('/api/integrations/setup', params={'integration': integration})


@app.get('/{full_path:path}')
def dashboard_app(full_path: str):
    if full_path.startswith('api/') or full_path == 'health':
        raise HTTPException(404, 'Not found')
    index = API_WEB_DIST / 'index.html'
    if not index.exists():
        raise HTTPException(503, 'dashboard UI not built')
    return FileResponse(index, headers={'Cache-Control': 'no-store'})
