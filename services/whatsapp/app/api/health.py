from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.api import deps
from app.config import Settings
from app.db import get_engine
from app.services.meta_api_service import MetaAPIError, MetaAPIService
from app.services.openwebui_service import OpenWebUIError, OpenWebUIService

router = APIRouter(tags=['health'])


async def _database_ok() -> bool:
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text('SELECT 1'))
        return True
    except Exception:
        return False


@router.get('/health')
async def health():
    """Liveness + database. Public, no details."""
    ok = await _database_ok()
    return {'status': 'ok' if ok else 'degraded', 'database': ok}


@router.get('/api/whatsapp/status', dependencies=[Depends(deps.require_api_key)])
async def status(
    settings: Settings = Depends(deps.settings),
    meta: MetaAPIService = Depends(deps.meta),
    openwebui: OpenWebUIService = Depends(deps.openwebui),
):
    """Component status for monitoring and the Integrations page. Never includes credentials."""
    database = {'ok': await _database_ok()}

    if not settings.meta_configured:
        whatsapp = {'ok': False, 'status': 'not_configured', 'detail': 'WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID missing'}
    else:
        try:
            phone = await meta.get_phone_number()
            whatsapp = {'ok': True, 'status': 'ok', 'display_phone_number': phone.get('display_phone_number'),
                        'verified_name': phone.get('verified_name')}
        except MetaAPIError as exc:
            whatsapp = {'ok': False, 'status': 'error', 'detail': str(exc)}

    if not settings.openwebui_api_key.get_secret_value():
        owui = {'ok': False, 'status': 'not_configured', 'detail': 'OPENWEBUI_API_KEY missing'}
    else:
        try:
            owui = {'status': 'ok', **(await openwebui.check_connection(settings.whatsapp_agent_model))}
        except OpenWebUIError as exc:
            owui = {'ok': False, 'status': 'error', 'detail': str(exc)}

    webhook = {
        'ok': bool(settings.whatsapp_verify_token.get_secret_value()),
        'verify_token_set': bool(settings.whatsapp_verify_token.get_secret_value()),
        'signature_verification': bool(settings.whatsapp_app_secret.get_secret_value()),
        'path': '/api/whatsapp/webhook',
    }
    components = {'whatsapp_api': whatsapp, 'openwebui': owui, 'database': database, 'webhook': webhook}
    return {'status': 'ok' if all(c['ok'] for c in components.values()) else 'degraded', **components}
