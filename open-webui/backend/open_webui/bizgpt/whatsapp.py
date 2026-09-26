"""
Biz GPT Integrations → WhatsApp.

Admin-only proxy from the Integrations page to the separate WhatsApp service
(services/whatsapp). The service key stays on the server; the Meta token never
leaves the WhatsApp service. Mounted under /api/v1/bizgpt/whatsapp by dashboard.py.
"""

import asyncio
import logging
import os
from typing import Any, Optional

import aiohttp
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from open_webui.utils.auth import get_admin_user

log = logging.getLogger(__name__)
router = APIRouter(prefix='/whatsapp')

WHATSAPP_API_URL = os.getenv('WHATSAPP_API_URL', 'http://bizgpt-whatsapp:8001').rstrip('/')
WHATSAPP_API_KEY = os.getenv('WHATSAPP_SERVICE_API_KEY', '')
TIMEOUT = aiohttp.ClientTimeout(total=20)


async def call(method: str, path: str, body: Optional[dict] = None, params: Optional[dict] = None, timeout=TIMEOUT) -> Any:
    if not WHATSAPP_API_KEY:
        raise HTTPException(503, 'WHATSAPP_SERVICE_API_KEY is not set for Biz GPT')
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method,
                f'{WHATSAPP_API_URL}{path}',
                json=body,
                params=params,
                headers={'Authorization': f'Bearer {WHATSAPP_API_KEY}'},
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise HTTPException(resp.status, (data or {}).get('detail') if isinstance(data, dict) else 'WhatsApp service error')
                return data
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.info('whatsapp service unreachable: %s', type(e).__name__)
        raise HTTPException(502, 'WhatsApp service is not reachable')


async def summary() -> Optional[dict]:
    """Cheap DB-only summary for the dashboard card (no Meta call). None if unavailable."""
    if not WHATSAPP_API_KEY:
        return None
    try:
        return await call('GET', '/api/whatsapp/settings', timeout=aiohttp.ClientTimeout(total=4))
    except HTTPException:
        return None


@router.get('')
async def get_whatsapp(user=Depends(get_admin_user)):
    """Account settings, stats and live component status in one payload."""
    settings, status = await asyncio.gather(
        call('GET', '/api/whatsapp/settings'),
        call('GET', '/api/whatsapp/status'),
        return_exceptions=True,
    )
    if isinstance(settings, Exception):
        return {'reachable': False, 'detail': getattr(settings, 'detail', 'WhatsApp service is not reachable')}
    return {'reachable': True, 'account': settings, 'status': None if isinstance(status, Exception) else status}


@router.put('/settings')
async def update_whatsapp_settings(form: dict = Body(...), user=Depends(get_admin_user)):
    allowed = {k: v for k, v in form.items() if k in ('agent_model', 'auto_reply', 'is_active')}
    return await call('PUT', '/api/whatsapp/settings', allowed)


@router.post('/test')
async def test_whatsapp(user=Depends(get_admin_user)):
    return await call('POST', '/api/whatsapp/test-connection', timeout=aiohttp.ClientTimeout(total=45))


@router.get('/conversations')
async def whatsapp_conversations(limit: int = Query(10, ge=1, le=50), user=Depends(get_admin_user)):
    return await call('GET', '/api/whatsapp/conversations', params={'limit': limit})
