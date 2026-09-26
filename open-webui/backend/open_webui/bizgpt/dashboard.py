"""
Biz GPT dashboard API.

GET /api/v1/bizgpt/dashboard aggregates the Biz GPT services (workflows API, dynamic
forms, integrations, Nango, Dify, the Gmail MCP server) and Open WebUI's own message
data into one payload for the dashboard page. Every source is fetched in parallel
with a short timeout and fails soft: a broken service marks its own card unavailable
instead of failing the page.

Admins see workspace-wide numbers; other users see their own forms and messages.
"""

import asyncio
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional

import aiohttp
from fastapi import APIRouter, Depends, Query
from open_webui.models.chat_messages import ChatMessage
from open_webui.models.config import Config
from open_webui.internal.db import get_async_db_context
from open_webui.utils.access_control import has_connection_access
from open_webui.utils.auth import get_verified_user
from open_webui.utils.mcp.client import MCPClient
from sqlalchemy import select

log = logging.getLogger(__name__)
router = APIRouter()

BIZGPT_API_URL = os.getenv('BIZGPT_API_URL', 'http://bizgpt-api:8003').rstrip('/')
FORMS_API_URL = os.getenv('FORMS_API_URL', 'http://bizgpt-forms:8000').rstrip('/')
FORMS_API_KEY = os.getenv('FORMS_API_KEY', '')
INTEGRATIONS_API_URL = os.getenv('INTEGRATIONS_API_URL', 'http://bizgpt-integrations:8002').rstrip('/')
INTEGRATIONS_API_KEY = os.getenv('INTEGRATIONS_API_KEY', '')
NANGO_INTERNAL_URL = os.getenv('BIZGPT_NANGO_INTERNAL_URL', 'http://nango-server:3003').rstrip('/')
NANGO_DASHBOARD_URL = os.getenv('NANGO_PUBLIC_SERVER_URL', '')
DIFY_BASE_URL = os.getenv('DIFY_BASE_URL', '').rstrip('/')
DIFY_CONSOLE_URL = os.getenv('DIFY_CONSOLE_URL', '')
GMAIL_MAILBOX = os.getenv('BIZGPT_GMAIL_MAILBOX', 'dbizgpt.assistant@gmail.com')

TIMEOUT = aiohttp.ClientTimeout(total=6)
INBOX_CACHE_SECONDS = 60
_inbox_cache: dict[str, Any] = {'at': 0.0, 'data': None}
_inbox_lock = asyncio.Lock()


# ---------- helpers ----------


async def _get_json(url: str, headers: Optional[dict] = None, params: Optional[dict] = None) -> Any:
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.get(url, headers=headers or {}, params=params) as resp:
            if resp.status >= 400:
                raise RuntimeError(f'{url} -> HTTP {resp.status}')
            return await resp.json(content_type=None)


async def _probe(url: str, ok_statuses: tuple[int, ...] = (200,)) -> bool:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4)) as session:
            async with session.get(url) as resp:
                return resp.status in ok_statuses
    except Exception:
        return False


def _ts(value: Any) -> Optional[float]:
    """Epoch seconds from an ISO string or epoch s/ms/ns number."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        while v > 1e11:  # ms / µs / ns -> s
            v /= 1000
        return v
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except ValueError:
        return None


def _day(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d')


def _title(form_type: str) -> str:
    return form_type.replace('_', ' ').title()


async def _safe(coro, default):
    try:
        return await coro
    except Exception as e:
        log.info('bizgpt dashboard source failed: %s', e)
        return default


# ---------- sources ----------


async def _workflows() -> dict:
    workflows, runs = await asyncio.gather(
        _get_json(f'{BIZGPT_API_URL}/api/workflows'),
        _get_json(f'{BIZGPT_API_URL}/api/workflow-runs'),
    )
    return {'ok': True, 'workflows': workflows or [], 'runs': runs or []}


async def _forms() -> dict:
    headers = {'Authorization': f'Bearer {FORMS_API_KEY}'}
    types, forms = await asyncio.gather(
        _get_json(f'{FORMS_API_URL}/api/form-types', headers),
        _get_json(f'{FORMS_API_URL}/api/forms', headers, {'limit': 200}),
    )
    return {'ok': True, 'types': types or [], 'forms': forms or []}


async def _personal_integrations(user) -> list[dict]:
    data = await _get_json(
        f'{INTEGRATIONS_API_URL}/api/integrations/status',
        {'Authorization': f'Bearer {INTEGRATIONS_API_KEY}'},
        {'user_id': user.id, 'user_email': user.email or ''},
    )
    return data.get('items', []) if isinstance(data, dict) else []


async def _messages(user, since: float) -> list[tuple]:
    async with get_async_db_context() as db:
        stmt = select(ChatMessage.created_at, ChatMessage.role, ChatMessage.output).filter(
            ChatMessage.created_at >= int(since)
        )
        if user.role != 'admin':
            stmt = stmt.filter(ChatMessage.user_id == user.id)
        # created_at may be seconds or ms; a seconds cutoff keeps both, series() re-filters.
        result = await db.execute(stmt)
        return list(result.all())


async def _gmail_connection(user) -> Optional[dict]:
    connections = await Config.get('tool_server.connections', []) or []
    for connection in connections:
        if connection.get('type') == 'mcp' and (
            (connection.get('info') or {}).get('id') == 'gmail' or 'gmail' in connection.get('url', '')
        ):
            if not (connection.get('config') or {}).get('enable', True):
                return None
            return connection if await has_connection_access(user, connection) else None
    return None


def _parse_batch(text: str) -> list[dict]:
    messages = []
    for block in text.split('\n---'):
        fields = dict(re.findall(r'^(Message ID|Subject|From|Date|Web Link): (.*)$', block, flags=re.M))
        if not fields.get('Message ID'):
            continue
        sender = fields.get('From', '')
        name = re.sub(r'\s*<[^>]*>\s*', '', sender).strip().strip('"') or sender
        try:
            at = parsedate_to_datetime(fields.get('Date', '')).timestamp()
        except Exception:
            at = None
        messages.append(
            {
                'id': fields['Message ID'].strip(),
                'from': name,
                'subject': fields.get('Subject', '(no subject)').strip(),
                'at': at,
                'link': fields.get('Web Link', '').strip(),
            }
        )
    return messages


async def _inbox(connection: dict) -> dict:
    async with _inbox_lock:
        if _inbox_cache['data'] and time.time() - _inbox_cache['at'] < INBOX_CACHE_SECONDS:
            return _inbox_cache['data']
        url = connection['url'].rstrip('/')
        client = MCPClient()
        await asyncio.wait_for(client.connect(url), timeout=8)
        try:
            args = {'user_google_email': GMAIL_MAILBOX}

            async def search(query: str, size: int) -> list[str]:
                out = await client.call_tool('search_gmail_messages', {**args, 'query': query, 'page_size': size})
                text = ''.join(part.get('text', '') for part in out or [])
                return re.findall(r'Message ID: (\w+)', text)

            unread_ids, recent_ids = await asyncio.gather(search('in:inbox is:unread', 100), search('in:inbox', 5))
            recent = []
            if recent_ids:
                out = await client.call_tool(
                    'get_gmail_messages_content_batch', {**args, 'message_ids': recent_ids, 'format': 'metadata'}
                )
                recent = _parse_batch(''.join(part.get('text', '') for part in out or []))
                unread = set(unread_ids)
                for message in recent:
                    message['unread'] = message['id'] in unread
            data = {
                'available': True,
                'mailbox': GMAIL_MAILBOX,
                'unread': len(unread_ids),
                'unread_capped': len(unread_ids) >= 100,
                'recent': recent,
            }
        finally:
            await client.disconnect()
        _inbox_cache.update(at=time.time(), data=data)
        return data


# ---------- endpoint ----------


@router.get('/dashboard')
async def get_dashboard(days: int = Query(7, ge=1, le=90), user=Depends(get_verified_user)):
    now = time.time()
    since = now - days * 86400
    is_admin = user.role == 'admin'
    gmail_connection = await _safe(_gmail_connection(user), None)

    workflows, forms, personal, messages, nango_up, dify_up, gmail_up, inbox = await asyncio.gather(
        _safe(_workflows(), {'ok': False, 'workflows': [], 'runs': []}),
        _safe(_forms(), {'ok': False, 'types': [], 'forms': []}),
        _safe(_personal_integrations(user), None),
        _safe(_messages(user, since), []),
        _probe(f'{NANGO_INTERNAL_URL}/health'),
        # Dify's API answers 401 without an app key, which still proves it is up.
        _probe(f'{DIFY_BASE_URL}/v1/info', (200, 401)) if DIFY_BASE_URL else asyncio.sleep(0, False),
        _probe(gmail_connection['url'].rstrip('/').removesuffix('/mcp') + '/health') if gmail_connection else asyncio.sleep(0, False),
        _safe(_inbox(gmail_connection), None) if gmail_connection else asyncio.sleep(0, None),
    )

    # Scope forms to the user unless admin.
    all_forms = forms['forms']
    my_forms = all_forms if is_admin else [f for f in all_forms if f.get('user_id') == user.id]
    submitted = [f for f in my_forms if f.get('status') in ('submitted', 'executed')]

    # ---- activity series ----
    day_keys = [_day(now - (days - 1 - i) * 86400) for i in range(days)]
    index = {d: i for i, d in enumerate(day_keys)}

    def series(items, ts_getter):
        values = [0] * days
        for item in items:
            ts = _ts(ts_getter(item))
            if ts and ts >= since and _day(ts) in index:
                values[index[_day(ts)]] += 1
        return values

    runs = workflows['runs'] if is_admin else []
    user_messages = [m for m in messages if m.role == 'user']
    tool_messages = [
        m for m in messages if m.role == 'assistant' and any(
            (o or {}).get('type') == 'function_call' for o in (m.output or []) if isinstance(o, dict)
        )
    ]
    activity = {
        'days': day_keys,
        'series': {
            'workflow_runs': series(runs, lambda r: r.get('started_at') or r.get('created_at')),
            'form_submissions': series(submitted, lambda f: f.get('updated_at')),
            'messages': series(user_messages, lambda m: m.created_at),
            'tool_calls': series(tool_messages, lambda m: m.created_at),
        },
    }

    # ---- integrations ----
    personal_by_id = {i.get('integration'): i for i in (personal or [])}

    def personal_item(key: str, name: str) -> dict:
        item = personal_by_id.get(key) or {}
        status = 'connected' if item.get('connected') else ('unavailable' if personal is None or not nango_up else 'not_connected')
        return {
            'id': f'{key}_personal',
            'name': f'{name} (personal)',
            'kind': key,
            'status': status,
            'detail': item.get('message') or ('Nango is not reachable' if not nango_up else 'Connect from chat'),
            'account': item.get('email') or item.get('account_email'),
        }

    integrations = [
        {
            'id': 'gmail_mcp',
            'name': 'Gmail & Drive',
            'kind': 'gmail',
            'status': 'connected' if gmail_up else ('restricted' if not gmail_connection else 'down'),
            'detail': GMAIL_MAILBOX if gmail_connection else 'Admin-only shared mailbox',
            'account': GMAIL_MAILBOX if gmail_connection else None,
        },
        {
            'id': 'dify',
            'name': 'Dify',
            'kind': 'dify',
            'status': 'connected' if dify_up else ('not_configured' if not DIFY_BASE_URL else 'down'),
            'detail': 'Workflow engine',
        },
        {
            'id': 'forms',
            'name': 'Dynamic Forms',
            'kind': 'forms',
            'status': 'connected' if forms['ok'] else 'down',
            'detail': f"{len(forms['types'])} form types",
        },
        {
            'id': 'nango',
            'name': 'Nango',
            'kind': 'nango',
            'status': 'connected' if nango_up else 'down',
            'detail': 'OAuth broker for personal Gmail / Outlook',
        },
        personal_item('gmail', 'Gmail'),
        personal_item('outlook', 'Outlook'),
    ]

    # ---- recent activity ----
    recent: list[dict] = []
    for f in my_forms[:20]:
        status = f.get('status')
        reference = (f.get('result') or {}).get('reference')
        recent.append(
            {
                'type': 'form',
                'title': f"{_title(f.get('form_type', 'form'))} {'submitted' if status in ('submitted', 'executed') else 'opened'}",
                'detail': reference or ', '.join(f.get('missing_fields') or []) or '',
                'status': {'executed': 'success', 'submitted': 'success', 'expired': 'expired'}.get(status, 'draft'),
                'at': _ts(f.get('updated_at') or f.get('created_at')),
            }
        )
    for r in runs[:20]:
        recent.append(
            {
                'type': 'workflow',
                'title': f"{r.get('workflow_name') or r.get('workflow_id', 'Workflow')} {r.get('status', '')}".strip(),
                'detail': r.get('id', ''),
                'status': 'success' if r.get('status') in ('succeeded', 'completed', 'success') else r.get('status', 'info'),
                'at': _ts(r.get('started_at') or r.get('created_at')),
            }
        )
    if inbox and inbox.get('recent'):
        for m in inbox['recent'][:3]:
            recent.append(
                {'type': 'email', 'title': f"Email from {m['from']}", 'detail': m['subject'], 'status': 'unread' if m.get('unread') else 'info', 'at': m.get('at')}
            )
    recent = sorted((r for r in recent if r['at']), key=lambda r: r['at'], reverse=True)[:8]

    # ---- cards ----
    wf = workflows['workflows']
    custom_types = [t for t in forms['types'] if t.get('source') == 'custom']
    connected_integrations = [i for i in integrations if i['status'] == 'connected']
    personal_connected = [i for i in integrations if i['id'].endswith('_personal') and i['status'] == 'connected']

    return {
        'generated_at': now,
        'user': {'name': user.name, 'role': user.role},
        'scope': 'workspace' if is_admin else 'personal',
        'cards': {
            'workflows': {
                'total': len(wf),
                'active': len([w for w in wf if w.get('configured')]),
                'available': workflows['ok'],
            },
            'forms': {
                'types': len(forms['types']),
                'custom': len(custom_types),
                'submissions': len(submitted),
                'available': forms['ok'],
            },
            'integrations': {'connected': len(connected_integrations), 'total': len(integrations)},
            'nango': {'up': nango_up, 'connections': len(personal_connected)},
            'inbox': {
                'available': bool(inbox),
                'unread': (inbox or {}).get('unread', 0),
                'unread_capped': (inbox or {}).get('unread_capped', False),
                'reason': None if inbox else ('restricted' if not gmail_connection else 'unavailable'),
            },
        },
        'activity': activity,
        'recent_activity': recent,
        'integrations': integrations,
        'inbox': inbox,
        'workflows': [
            {'id': w['id'], 'name': w['name'], 'status': w.get('status'), 'configured': w.get('configured')} for w in wf
        ],
        'links': {
            'dify_console': DIFY_CONSOLE_URL or None,
            'nango_dashboard': NANGO_DASHBOARD_URL if is_admin and NANGO_DASHBOARD_URL else None,
        },
    }
