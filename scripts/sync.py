#!/usr/bin/env python3
"""
Make a running Biz GPT match bizgpt/owui/ (the source of truth in Git).

    python3 scripts/sync.py

Idempotent: creates what is missing, updates what exists, never duplicates.
Syncs: owui/functions/*.py, owui/tools/*.py (+ valves from .env), owui/models/*.json.

Reads bizgpt/.env: OPEN_WEBUI_URL, OPEN_WEBUI_API_KEY (optional when Biz GPT runs
with WEBUI_AUTH=False locally), plus the per-extension settings below.
Stdlib only, so it runs anywhere without installing anything.
"""

import json
import os
import re
import string
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_READ = [{'principal_type': 'user', 'principal_id': '*', 'permission': 'read'}]
TOKEN = ''


def load_env():
    env_file = ROOT / '.env'
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))
    # Backwards compatibility with the first .env layout.
    for new, old in (('OPEN_WEBUI_URL', 'OWUI_URL'), ('OPEN_WEBUI_API_KEY', 'OWUI_API_KEY')):
        if not os.environ.get(new) and os.environ.get(old):
            os.environ[new] = os.environ[old]


def api(method, path, body=None, auth=True):
    url = os.environ['OPEN_WEBUI_URL'].rstrip('/') + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if auth:
        req.add_header('Authorization', f'Bearer {TOKEN}')
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        if e.code in (401, 404) and method == 'GET':
            return None
        raise SystemExit(f'{method} {path} failed: {e.code} {e.read().decode()[:300]}')


def authenticate():
    global TOKEN
    TOKEN = os.environ.get('OPEN_WEBUI_API_KEY', '')
    if TOKEN:
        return
    # WEBUI_AUTH=False (local single-user mode) issues an admin session without credentials.
    try:
        TOKEN = api('POST', '/api/v1/auths/signin', {'email': '', 'password': ''}, auth=False)['token']
        print('auth     using local single-user session (WEBUI_AUTH=False)')
    except SystemExit:
        sys.exit('Set OPEN_WEBUI_API_KEY in bizgpt/.env (Settings → Account → API Keys)')


def frontmatter(content):
    match = re.search(r'"""(.*?)"""', content, re.S)
    meta = {}
    for line in (match.group(1) if match else '').splitlines():
        if ':' in line:
            key, value = line.split(':', 1)
            meta[key.strip()] = value.strip()
    return meta


def env_valves(mapping):
    """{valve_name: ENV_NAME} -> {valve_name: value} for env vars that are set."""
    return {valve: os.environ[env] for valve, env in mapping.items() if os.environ.get(env)}


# Which .env variables feed which extension's valves.
VALVES = {
    'dify_pipe': {'DIFY_BASE_URL': 'DIFY_BASE_URL', 'DIFY_APPS': 'DIFY_APPS'},
    'bizgpt_forms': {
        'FORMS_API_URL': 'FORMS_API_URL',
        'FORMS_PUBLIC_URL': 'FORMS_PUBLIC_URL',
        'FORMS_API_KEY': 'FORMS_API_KEY',
    },
    'bizgpt_form_builder': {
        'FORMS_API_URL': 'FORMS_API_URL',
        'FORMS_PUBLIC_URL': 'FORMS_PUBLIC_URL',
        'FORMS_API_KEY': 'FORMS_API_KEY',
    },
    'bizgpt_integrations': {
        'INTEGRATIONS_API_URL': 'INTEGRATIONS_API_URL',
        'INTEGRATIONS_PUBLIC_URL': 'INTEGRATIONS_PUBLIC_URL',
        'INTEGRATIONS_API_KEY': 'INTEGRATIONS_API_KEY',
        'FORMS_API_URL': 'FORMS_API_URL',
        'FORMS_PUBLIC_URL': 'FORMS_PUBLIC_URL',
        'FORMS_API_KEY': 'FORMS_API_KEY',
    },
}


def sync_functions():
    for path in sorted((ROOT / 'owui' / 'functions').glob('*.py')):
        fid = path.stem
        content = path.read_text()
        meta = frontmatter(content)
        form = {
            'id': fid,
            'name': meta.get('title', fid),
            'content': content,
            'meta': {'description': meta.get('description', ''), 'manifest': meta},
        }
        existing = api('GET', f'/api/v1/functions/id/{fid}')
        if existing:
            api('POST', f'/api/v1/functions/id/{fid}/update', form)
            print(f'updated  function {fid}')
        else:
            api('POST', '/api/v1/functions/create', form)
            print(f'created  function {fid}')
            existing = api('GET', f'/api/v1/functions/id/{fid}')

        if not existing.get('is_active'):
            api('POST', f'/api/v1/functions/id/{fid}/toggle')
            print(f'enabled  function {fid}')

        valves = env_valves(VALVES.get(fid, {}))
        if 'DIFY_APPS' in valves:
            json.loads(valves['DIFY_APPS'])  # fail fast on bad JSON
        if valves:
            api('POST', f'/api/v1/functions/id/{fid}/valves/update', valves)
            print(f'valves   function {fid}: {", ".join(valves)}')


def sync_tools():
    for path in sorted((ROOT / 'owui' / 'tools').glob('*.py')):
        tid = path.stem
        content = path.read_text()
        meta = frontmatter(content)
        form = {
            'id': tid,
            'name': meta.get('title', tid),
            'content': content,
            'meta': {'description': meta.get('description', ''), 'manifest': meta},
            'access_grants': PUBLIC_READ,
        }
        if api('GET', f'/api/v1/tools/id/{tid}'):
            api('POST', f'/api/v1/tools/id/{tid}/update', form)
            print(f'updated  tool {tid}')
        else:
            api('POST', '/api/v1/tools/create', form)
            print(f'created  tool {tid}')

        valves = env_valves(VALVES.get(tid, {}))
        if valves:
            api('POST', f'/api/v1/tools/id/{tid}/valves/update', valves)
            print(f'valves   tool {tid}: {", ".join(valves)}')


def sync_models():
    for path in sorted((ROOT / 'owui' / 'models').glob('*.json')):
        raw = string.Template(path.read_text()).safe_substitute(os.environ)
        model = json.loads(raw)
        if '${' in model.get('base_model_id', '') or not model.get('base_model_id'):
            print(f'skipped  model {model["id"]}: set BIZGPT_BASE_MODEL in .env')
            continue
        if api('GET', f'/api/v1/models/model?id={model["id"]}'):
            api('POST', '/api/v1/models/model/update', model)
            print(f'updated  model {model["id"]} (base: {model["base_model_id"]})')
        else:
            api('POST', '/api/v1/models/create', model)
            print(f'created  model {model["id"]} (base: {model["base_model_id"]})')


if __name__ == '__main__':
    load_env()
    if not os.environ.get('OPEN_WEBUI_URL'):
        sys.exit('Missing OPEN_WEBUI_URL in bizgpt/.env')
    authenticate()
    sync_functions()
    sync_tools()
    sync_models()
    print('done')
