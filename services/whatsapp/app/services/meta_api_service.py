"""Official Meta WhatsApp Cloud API (Graph API). The only place that holds the access token."""

import logging
from typing import Any

import httpx

from app.config import Settings
from app.logging_setup import log_extra, mask_phone
from app.services.http import request_with_retry

log = logging.getLogger(__name__)


class MetaAPIError(Exception):
    def __init__(self, message: str, status: int | None = None, code: int | None = None):
        super().__init__(message)
        self.status = status
        self.code = code

    @property
    def outside_service_window(self) -> bool:
        # 131047: "Re-engagement message" - more than 24h since the customer last wrote.
        return self.code == 131047


class MetaNotConfigured(MetaAPIError):
    pass


class MetaAPIService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient, backoff: float = 0.5):
        self.settings = settings
        self.client = client
        self.backoff = backoff

    @property
    def _base(self) -> str:
        return f'{self.settings.whatsapp_graph_url.rstrip("/")}/{self.settings.whatsapp_api_version}'

    def _headers(self) -> dict[str, str]:
        token = self.settings.whatsapp_access_token.get_secret_value()
        if not token or not self.settings.whatsapp_phone_number_id:
            raise MetaNotConfigured('WhatsApp is not configured: set WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID')
        return {'Authorization': f'Bearer {token}'}

    async def _call(self, method: str, path: str, idempotent: bool = True, retries: int | None = None, **kwargs) -> dict[str, Any]:
        headers = self._headers()
        try:
            response = await request_with_retry(
                self.client,
                method,
                f'{self._base}/{path.lstrip("/")}',
                headers=headers,
                timeout=self.settings.meta_timeout_seconds,
                retries=self.settings.http_retries if retries is None else retries,
                backoff=self.backoff,
                service='meta',
                idempotent=idempotent,
                **kwargs,
            )
        except httpx.TimeoutException as exc:
            raise MetaAPIError('WhatsApp API timed out') from exc
        except httpx.TransportError as exc:
            raise MetaAPIError(f'WhatsApp API unreachable ({type(exc).__name__})') from exc

        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code >= 400:
            err = (data or {}).get('error') or {}
            detail = (err.get('error_data') or {}).get('details')
            message = err.get('message') or f'HTTP {response.status_code}'
            raise MetaAPIError(f'{message}{f" ({detail})" if detail else ""}', response.status_code, err.get('code'))
        return data

    async def _send(self, payload: dict[str, Any]) -> str:
        body = {'messaging_product': 'whatsapp', 'recipient_type': 'individual', **payload}
        data = await self._call('POST', f'{self.settings.whatsapp_phone_number_id}/messages', idempotent=False, json=body)
        wamid = ((data.get('messages') or [{}])[0]).get('id')
        if not wamid:
            raise MetaAPIError('WhatsApp API returned no message id')
        log.info('whatsapp message sent', **log_extra(to=mask_phone(payload.get('to')), type=payload.get('type')))
        return wamid

    async def send_text(self, to: str, text: str, preview_url: bool = False) -> str:
        return await self._send({'to': to, 'type': 'text', 'text': {'body': text, 'preview_url': preview_url}})

    async def send_template(self, to: str, name: str, language: str, components: list[dict] | None = None) -> str:
        template: dict[str, Any] = {'name': name, 'language': {'code': language}}
        if components:
            template['components'] = components
        return await self._send({'to': to, 'type': 'template', 'template': template})

    async def mark_read(self, whatsapp_message_id: str) -> None:
        # Cosmetic (blue ticks): one attempt, never worth delaying a reply for.
        await self._call(
            'POST',
            f'{self.settings.whatsapp_phone_number_id}/messages',
            retries=1,
            json={'messaging_product': 'whatsapp', 'status': 'read', 'message_id': whatsapp_message_id},
        )

    async def get_phone_number(self) -> dict[str, Any]:
        return await self._call(
            'GET',
            self.settings.whatsapp_phone_number_id,
            params={'fields': 'display_phone_number,verified_name,quality_rating,code_verification_status'},
        )

    async def list_templates(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.settings.whatsapp_business_account_id:
            raise MetaNotConfigured('Set WHATSAPP_BUSINESS_ACCOUNT_ID to list templates')
        data = await self._call(
            'GET',
            f'{self.settings.whatsapp_business_account_id}/message_templates',
            params={'fields': 'name,status,language,category,components', 'limit': limit},
        )
        return data.get('data') or []
