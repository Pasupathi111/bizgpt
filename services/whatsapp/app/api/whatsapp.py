"""Internal API used by the Biz GPT WhatsApp tool and the Integrations page (bearer key)."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api import deps
from app.config import Settings
from app.db import session_factory
from app.logging_setup import log_extra, mask_phone
from app.schemas.message import MessageOut
from app.schemas.whatsapp import SendTemplateRequest, SendTextRequest, SettingsUpdate
from app.services.meta_api_service import MetaAPIError, MetaAPIService, MetaNotConfigured
from app.services.openwebui_service import OpenWebUIError, OpenWebUIService
from app.services.whatsapp_service import OutsideServiceWindow, WhatsAppService

log = logging.getLogger(__name__)
router = APIRouter(prefix='/api/whatsapp', tags=['whatsapp'], dependencies=[Depends(deps.require_api_key)])


def _meta_http_error(exc: MetaAPIError) -> HTTPException:
    if isinstance(exc, MetaNotConfigured):
        return HTTPException(503, str(exc))
    if exc.outside_service_window:
        return HTTPException(409, 'Outside the 24-hour window: send an approved template instead.')
    return HTTPException(502, f'WhatsApp API: {exc}')


@router.post('/messages/send', response_model=MessageOut)
async def send_message(body: SendTextRequest, service: WhatsAppService = Depends(deps.whatsapp)):
    try:
        message = await service.send_text(body.to, body.text, body.preview_url)
    except OutsideServiceWindow as exc:
        raise HTTPException(409, str(exc))
    except MetaAPIError as exc:
        raise _meta_http_error(exc)
    log.info('staff message sent', **log_extra(to=mask_phone(body.to)))
    return message


@router.post('/messages/template', response_model=MessageOut)
async def send_template(body: SendTemplateRequest, service: WhatsAppService = Depends(deps.whatsapp)):
    components = body.components
    if components is None and body.body_params:
        components = [{'type': 'body', 'parameters': [{'type': 'text', 'text': p} for p in body.body_params]}]
    try:
        return await service.send_template(body.to, body.template_name, body.language, components)
    except MetaAPIError as exc:
        raise _meta_http_error(exc)


@router.get('/templates')
async def list_templates(meta: MetaAPIService = Depends(deps.meta)):
    try:
        templates = await meta.list_templates()
    except MetaAPIError as exc:
        raise _meta_http_error(exc)
    return [
        {'name': t.get('name'), 'language': t.get('language'), 'status': t.get('status'), 'category': t.get('category'),
         'body': next((c.get('text') for c in t.get('components') or [] if c.get('type') == 'BODY'), None)}
        for t in templates
    ]


async def _account_payload(service: WhatsAppService) -> dict:
    async with session_factory()() as session:
        account = await service.conversations.get_or_create_account(session)
        stats = await service.conversations.stats(session, account.id)
    return {
        'phone_number_id': account.phone_number_id,
        'business_account_id': account.business_account_id,
        'display_phone_number': account.display_phone_number,
        'verified_name': account.verified_name,
        'agent_model': account.agent_model,
        'auto_reply': account.auto_reply,
        'is_active': account.is_active,
        'stats': stats,
    }


@router.get('/settings')
async def get_account_settings(service: WhatsAppService = Depends(deps.whatsapp)):
    return await _account_payload(service)


@router.put('/settings')
async def update_account_settings(body: SettingsUpdate, service: WhatsAppService = Depends(deps.whatsapp)):
    async with session_factory()() as session:
        account = await service.conversations.get_or_create_account(session)
        for field, value in body.model_dump(exclude_none=True).items():
            setattr(account, field, value)
        await session.commit()
    log.info('whatsapp settings updated', **log_extra(fields=','.join(body.model_dump(exclude_none=True))))
    return await _account_payload(service)


@router.get('/models')
async def list_agent_models(openwebui: OpenWebUIService = Depends(deps.openwebui)):
    """Biz GPT models the WhatsApp channel can use as its agent."""
    try:
        return await openwebui.list_models()
    except OpenWebUIError as exc:
        raise HTTPException(502, str(exc))


@router.post('/test-connection')
async def test_connection(
    settings: Settings = Depends(deps.settings),
    service: WhatsAppService = Depends(deps.whatsapp),
    meta: MetaAPIService = Depends(deps.meta),
    openwebui: OpenWebUIService = Depends(deps.openwebui),
):
    """Live check of Meta and Biz GPT. Also refreshes the phone number's display name."""
    result: dict = {}
    try:
        phone = await meta.get_phone_number()
        async with session_factory()() as session:
            account = await service.conversations.get_or_create_account(session)
            account.display_phone_number = phone.get('display_phone_number') or account.display_phone_number
            account.verified_name = phone.get('verified_name') or account.verified_name
            await session.commit()
            agent_model = account.agent_model
        result['whatsapp'] = {'ok': True, 'display_phone_number': phone.get('display_phone_number'),
                              'verified_name': phone.get('verified_name'), 'quality_rating': phone.get('quality_rating')}
    except MetaAPIError as exc:
        agent_model = settings.whatsapp_agent_model
        result['whatsapp'] = {'ok': False, 'detail': str(exc)}
    try:
        result['openwebui'] = await openwebui.check_connection(agent_model)
        if result['openwebui'].get('agent_model_found') is False:
            result['openwebui'].update(ok=False, detail=f'Model "{agent_model}" not found in Biz GPT')
    except OpenWebUIError as exc:
        result['openwebui'] = {'ok': False, 'detail': str(exc)}
    result['ok'] = all(v.get('ok') for v in result.values() if isinstance(v, dict))
    return result
