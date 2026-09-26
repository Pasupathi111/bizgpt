"""Meta webhook: GET = subscription verification, POST = messages and status events."""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.api import deps
from app.config import Settings
from app.logging_setup import log_extra
from app.schemas.whatsapp import parse_webhook
from app.services.whatsapp_service import WhatsAppService

log = logging.getLogger(__name__)
router = APIRouter(prefix='/api/whatsapp', tags=['webhook'])

MAX_BODY_BYTES = 1_000_000


def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    if not header or not header.startswith('sha256='):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix('sha256='))


@router.get('/webhook', response_class=PlainTextResponse)
async def verify_webhook(
    mode: str = Query('', alias='hub.mode'),
    token: str = Query('', alias='hub.verify_token'),
    challenge: str = Query('', alias='hub.challenge'),
    settings: Settings = Depends(deps.settings),
):
    expected = settings.whatsapp_verify_token.get_secret_value()
    if mode == 'subscribe' and expected and hmac.compare_digest(token.encode(), expected.encode()):
        log.info('webhook verified by meta')
        return PlainTextResponse(challenge)
    log.warning('webhook verification rejected', **log_extra(mode=mode))
    raise HTTPException(403, 'Verification failed')


@router.post('/webhook')
async def receive_webhook(
    request: Request,
    background: BackgroundTasks,
    settings: Settings = Depends(deps.settings),
    service: WhatsAppService = Depends(deps.whatsapp),
):
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(413, 'Payload too large')

    secret = settings.whatsapp_app_secret.get_secret_value()
    if secret and not verify_signature(secret, body, request.headers.get('x-hub-signature-256')):
        log.warning('webhook signature rejected')
        raise HTTPException(401, 'Invalid signature')

    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(400, 'Invalid JSON')
    if not isinstance(payload, dict) or payload.get('object') != 'whatsapp_business_account':
        raise HTTPException(400, 'Not a WhatsApp Business webhook')

    parsed = parse_webhook(payload)
    # Storage is fast and synchronous so a crash can't lose a message; the AI reply runs
    # after Meta has its 200 (Meta retries slow or failed deliveries, which the dedupe absorbs).
    to_process = await service.ingest(parsed)
    if to_process:
        background.add_task(service.process_many, to_process)
    return {'status': 'ok', 'received': len(parsed.messages), 'statuses': len(parsed.statuses), 'queued': len(to_process)}
