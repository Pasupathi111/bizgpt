"""What happens after a form is submitted. Each action returns a result dict."""

import json
import os
import re
import secrets

import httpx

from .registry import FormType


class ActionError(Exception):
    pass


async def run_action(form_type: FormType, form_id: str, values: dict, context: dict) -> dict:
    action = form_type.action
    reference = f'{action.reference_prefix}-{secrets.token_hex(3).upper()}'

    if action.type == 'record':
        return {'reference': reference}

    if action.type == 'webhook':
        if not action.url:
            raise ActionError('webhook action has no url')
        payload = {'form_type': form_type.id, 'form_id': form_id, 'reference': reference, 'values': values, 'context': context}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(action.url, json=payload, headers=action.headers)
        if resp.status_code >= 400:
            raise ActionError(f'webhook returned {resp.status_code}')
        body = _json_or_text(resp)
        return {'reference': reference, 'response': body}

    if action.type == 'dify_workflow':
        config = resolve_dify_config(
            form_id=form_type.id,
            form_title=form_type.title,
            app_id=action.dify_app_id,
            base_url_env=action.dify_base_url_env,
            api_key_env=action.dify_api_key_env,
        )
        base = config['base_url']
        key = config['api_key']
        if not base or not key:
            raise ActionError(f"Dify not configured ({', '.join(config['missing'])})")
        inputs = {k: v if isinstance(v, (str, int, float, bool)) else str(v) for k, v in values.items()}
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f'{base}/v1/workflows/run',
                headers={'Authorization': f'Bearer {key}'},
                json={'inputs': inputs, 'response_mode': 'blocking', 'user': context.get('user_email') or 'bizgpt-forms'},
            )
        if resp.status_code >= 400:
            raise ActionError(f'Dify returned {resp.status_code}: {resp.text[:200]}')
        data = resp.json().get('data', {})
        if data.get('status') != 'succeeded':
            raise ActionError(f'Dify workflow {data.get("status")}: {data.get("error")}')
        result = {
            'reference': reference,
            'workflow_run_id': data.get('id'),
            'task_id': data.get('task_id'),
            'elapsed_time': data.get('elapsed_time'),
            'outputs': data.get('outputs', {}),
        }
        if action.url:
            payload = {
                'form_type': form_type.id,
                'form_id': form_id,
                'reference': reference,
                'workflow_run_id': data.get('id'),
                'task_id': data.get('task_id'),
                'values': values,
                'context': context,
                'outputs': data.get('outputs', {}),
            }
            async with httpx.AsyncClient(timeout=30) as client:
                delivery = await client.post(action.url, json=payload, headers=action.headers)
            if delivery.status_code >= 400:
                raise ActionError(f'workflow handoff returned {delivery.status_code}')
            result['delivery'] = _json_or_text(delivery)
        return result

    raise ActionError(f'unknown action type {action.type!r}')


def _json_or_text(resp: httpx.Response):
    try:
        return resp.json()
    except ValueError:
        return resp.text[:1000]


def resolve_dify_config(*, form_id: str, form_title: str, app_id: str | None, base_url_env: str, api_key_env: str | None) -> dict:
    matched_app = _matched_dify_app(form_id=form_id, form_title=form_title, app_id=app_id)
    env_base_url = os.getenv(base_url_env, '').strip()
    env_api_key = os.getenv(api_key_env or '', '').strip() if api_key_env else ''
    app_base_url = str(matched_app.get('base_url') or '').strip() if matched_app else ''
    app_api_key = str(matched_app.get('api_key') or '').strip() if matched_app else ''

    base_url = (env_base_url or app_base_url).rstrip('/')
    api_key = env_api_key or app_api_key

    missing: list[str] = []
    if not base_url:
        missing.append(base_url_env or 'DIFY_BASE_URL')
    if not api_key:
        lookup = app_id or form_id or form_title
        if api_key_env:
            missing.append(f'{api_key_env} or DIFY_APPS[{lookup}].api_key')
        else:
            missing.append(f'DIFY_APPS[{lookup}].api_key')

    return {'base_url': base_url, 'api_key': api_key, 'missing': missing}


def _matched_dify_app(*, form_id: str, form_title: str, app_id: str | None) -> dict | None:
    candidates = {_canonical_id(value) for value in (app_id or '', form_id, form_title) if value}
    for app in _dify_apps():
        app_type = _canonical_id(str(app.get('type') or ''))
        if app_type and app_type != 'workflow':
            continue
        app_candidates = {
            value for value in (_canonical_id(str(app.get('id') or '')), _canonical_id(str(app.get('name') or ''))) if value
        }
        if candidates & app_candidates:
            return app
    return None


def _dify_apps() -> list[dict]:
    raw = os.getenv('DIFY_APPS', '').strip()
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _canonical_id(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', value.lower())
