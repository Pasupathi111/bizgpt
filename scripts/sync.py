#!/usr/bin/env python3
"""
Push everything in bizgpt/owui/ into a running Open WebUI instance.

Run after every Open WebUI upgrade (or after editing a function/tool):
    python3 scripts/sync.py

Reads bizgpt/.env: OWUI_URL, OWUI_API_KEY, DIFY_BASE_URL, DIFY_APPS.
Stdlib only, so it runs anywhere without installing anything.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env():
    env_file = ROOT / '.env'
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


def api(method, path, body=None):
    url = os.environ['OWUI_URL'].rstrip('/') + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Authorization', f'Bearer {os.environ["OWUI_API_KEY"]}')
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        if e.code == 404 and method == 'GET':
            return None
        raise SystemExit(f'{method} {path} failed: {e.code} {e.read().decode()[:300]}')


def frontmatter(content):
    match = re.search(r'"""(.*?)"""', content, re.S)
    meta = {}
    for line in (match.group(1) if match else '').splitlines():
        if ':' in line:
            key, value = line.split(':', 1)
            meta[key.strip()] = value.strip()
    return meta


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

        valves = function_valves(fid)
        if valves:
            api('POST', f'/api/v1/functions/id/{fid}/valves/update', valves)
            print(f'valves   function {fid}: {", ".join(valves)}')


def function_valves(fid):
    if fid == 'dify_pipe':
        valves = {}
        if os.environ.get('DIFY_BASE_URL'):
            valves['DIFY_BASE_URL'] = os.environ['DIFY_BASE_URL']
        if os.environ.get('DIFY_APPS'):
            json.loads(os.environ['DIFY_APPS'])  # fail fast on bad JSON
            valves['DIFY_APPS'] = os.environ['DIFY_APPS']
        return valves
    return {}


def sync_tools():
    tools_dir = ROOT / 'owui' / 'tools'
    for path in sorted(tools_dir.glob('*.py')) if tools_dir.exists() else []:
        tid = path.stem
        content = path.read_text()
        meta = frontmatter(content)
        form = {
            'id': tid,
            'name': meta.get('title', tid),
            'content': content,
            'meta': {'description': meta.get('description', ''), 'manifest': meta},
        }
        if api('GET', f'/api/v1/tools/id/{tid}'):
            api('POST', f'/api/v1/tools/id/{tid}/update', form)
            print(f'updated  tool {tid}')
        else:
            api('POST', '/api/v1/tools/create', form)
            print(f'created  tool {tid}')


if __name__ == '__main__':
    load_env()
    for key in ('OWUI_URL', 'OWUI_API_KEY'):
        if not os.environ.get(key):
            sys.exit(f'Missing {key} in bizgpt/.env')
    sync_functions()
    sync_tools()
    print('done')
