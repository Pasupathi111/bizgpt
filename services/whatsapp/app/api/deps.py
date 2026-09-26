import hmac

from fastapi import Header, HTTPException, Request

from app.config import Settings
from app.services.meta_api_service import MetaAPIService
from app.services.openwebui_service import OpenWebUIService
from app.services.whatsapp_service import WhatsAppService


def settings(request: Request) -> Settings:
    return request.app.state.settings


def whatsapp(request: Request) -> WhatsAppService:
    return request.app.state.whatsapp


def meta(request: Request) -> MetaAPIService:
    return request.app.state.meta


def openwebui(request: Request) -> OpenWebUIService:
    return request.app.state.openwebui


def require_api_key(request: Request, authorization: str = Header(default='')) -> None:
    """Internal API guard (Biz GPT tool and Integrations page). Constant-time compare."""
    expected = request.app.state.settings.whatsapp_service_api_key.get_secret_value()
    if not expected:
        raise HTTPException(503, 'WHATSAPP_SERVICE_API_KEY is not set')
    token = authorization.removeprefix('Bearer ').strip()
    if not token or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(401, 'Invalid API key')
