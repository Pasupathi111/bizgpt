"""
Biz GPT → Monthly Report POC.

Thin pass-through from /api/v1/bizgpt/monthly-report/* to the separate Monthly Report
service (services/monthly-report). The user's own Biz GPT session is forwarded; the
service verifies it again and uses it to call its own model. Mounted by dashboard.py.
"""

import asyncio
import logging
import os

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from open_webui.utils.auth import get_verified_user

log = logging.getLogger(__name__)
router = APIRouter(prefix='/monthly-report')

MONTHLY_REPORT_API_URL = os.getenv('MONTHLY_REPORT_API_URL', 'http://bizgpt-monthly-report:8000').rstrip('/')
TIMEOUT = aiohttp.ClientTimeout(total=300)
PASS_HEADERS = ('content-type', 'content-disposition', 'cache-control')


@router.api_route('/{path:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
async def proxy(path: str, request: Request, user=Depends(get_verified_user)):
    # Plain links (e.g. "Download PDF" in chat) carry only the session cookie.
    auth = request.headers.get('authorization') or (f'Bearer {request.cookies["token"]}' if request.cookies.get('token') else '')
    headers = {'Authorization': auth}
    if request.headers.get('content-type'):
        headers['Content-Type'] = request.headers['content-type']
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.request(
                request.method,
                f'{MONTHLY_REPORT_API_URL}/api/{path}',
                params=list(request.query_params.multi_items()),
                data=await request.body(),
                headers=headers,
            ) as resp:
                body = await resp.read()
                out = {k: v for k, v in resp.headers.items() if k.lower() in PASS_HEADERS}
                return Response(content=body, status_code=resp.status, headers=out)
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.info('monthly report service unreachable: %s', type(e).__name__)
        raise HTTPException(502, 'Monthly Report service is not reachable')
