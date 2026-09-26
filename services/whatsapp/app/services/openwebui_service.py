"""Biz GPT (Open WebUI) through its public HTTP API only. No access to its database.

- get_agent_response(): POST /api/chat/completions against a workspace model (the agent).
- create_or_get_conversation(): POST /api/v1/chats/new, so the WhatsApp conversation shows up
  as a normal Biz GPT chat owned by the API-key user.
- mirror_conversation(): POST /api/v1/chats/{id} with the full message history.
"""

import logging
import time
from typing import Any

import httpx

from app.config import Settings
from app.logging_setup import log_extra
from app.services.http import request_with_retry

log = logging.getLogger(__name__)


class OpenWebUIError(Exception):
    pass


class OpenWebUIAuthError(OpenWebUIError):
    pass


class OpenWebUIService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient, backoff: float = 0.5):
        self.settings = settings
        self.client = client
        self.backoff = backoff

    def _headers(self) -> dict[str, str]:
        key = self.settings.openwebui_api_key.get_secret_value()
        if not key:
            raise OpenWebUIAuthError('OPENWEBUI_API_KEY is not set')
        return {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}

    async def _call(self, method: str, path: str, timeout: float | None = None, retries: int | None = None, **kwargs) -> Any:
        url = self.settings.openwebui_base_url.rstrip('/') + path
        try:
            response = await request_with_retry(
                self.client,
                method,
                url,
                headers=self._headers(),
                timeout=timeout or 15.0,
                retries=self.settings.http_retries if retries is None else retries,
                backoff=self.backoff,
                service='openwebui',
                **kwargs,
            )
        except httpx.TimeoutException as exc:
            raise OpenWebUIError('Biz GPT timed out') from exc
        except httpx.TransportError as exc:
            raise OpenWebUIError(f'Biz GPT unreachable ({type(exc).__name__})') from exc

        if response.status_code in (401, 403):
            raise OpenWebUIAuthError(f'Biz GPT rejected the API key (HTTP {response.status_code})')
        if response.status_code >= 400:
            try:
                detail = response.json().get('detail')
            except ValueError:
                detail = None
            raise OpenWebUIError(f'Biz GPT error HTTP {response.status_code}{f": {detail}" if detail else ""}')
        try:
            return response.json()
        except ValueError as exc:
            raise OpenWebUIError('Biz GPT returned a non-JSON response') from exc

    # ---------- health / models ----------

    async def list_models(self) -> list[dict[str, str]]:
        data = await self._call('GET', '/api/models', retries=1)
        items = data.get('data', []) if isinstance(data, dict) else data or []
        return [{'id': m.get('id'), 'name': m.get('name') or m.get('id')} for m in items if m.get('id')]

    async def check_connection(self, model: str | None = None) -> dict[str, Any]:
        models = await self.list_models()
        ids = {m['id'] for m in models}
        return {'ok': True, 'models': len(models), 'agent_model_found': (model in ids) if model else None}

    # ---------- AI ----------

    async def get_agent_response(self, model: str, messages: list[dict[str, str]]) -> str:
        """One non-streaming completion from the Biz GPT agent model."""
        # Not retried: a timed-out completion may still finish server side, and a retry
        # would double the LLM cost. The caller sends a fallback reply instead.
        body = {'model': model, 'messages': messages, 'stream': False}
        timeout = self.settings.openwebui_timeout_seconds
        try:
            data = await self._call('POST', '/api/chat/completions', timeout=timeout, retries=1, json=body)
        except OpenWebUIError as exc:
            # Biz GPT caches its model list; a model created since (e.g. by sync.py) is
            # "not found" until the list is reloaded. GET /api/models reloads it.
            if 'model not found' not in str(exc).lower():
                raise
            await self.list_models()
            data = await self._call('POST', '/api/chat/completions', timeout=timeout, retries=1, json=body)
        try:
            content = data['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenWebUIError('Biz GPT returned no answer') from exc
        if isinstance(content, list):  # OpenAI content parts
            content = ''.join(p.get('text', '') for p in content if isinstance(p, dict))
        content = (content or '').strip()
        if not content:
            raise OpenWebUIError('Biz GPT returned an empty answer')
        return content

    # ---------- chat mirror ----------

    @staticmethod
    def _chat_body(title: str, model: str, history: list[dict[str, Any]]) -> dict[str, Any]:
        nodes: dict[str, dict[str, Any]] = {}
        linear: list[dict[str, Any]] = []
        parent: str | None = None
        for item in history:
            node = {
                'id': item['id'],
                'parentId': parent,
                'childrenIds': [],
                'role': item['role'],
                'content': item['content'],
                'timestamp': int(item.get('timestamp') or time.time()),
                'done': True,
            }
            if item['role'] == 'assistant':
                node['model'] = model
                node['modelName'] = model
            else:
                node['models'] = [model]
            if parent:
                nodes[parent]['childrenIds'].append(item['id'])
            nodes[item['id']] = node
            linear.append(node)
            parent = item['id']
        return {
            'chat': {
                'title': title,
                'models': [model],
                'tags': ['whatsapp'],
                'history': {'messages': nodes, 'currentId': parent},
                'messages': linear,
            }
        }

    async def create_or_get_conversation(self, existing_chat_id: str | None, title: str, model: str) -> str:
        if existing_chat_id:
            return existing_chat_id
        data = await self._call('POST', '/api/v1/chats/new', json=self._chat_body(title, model, []))
        chat_id = (data or {}).get('id')
        if not chat_id:
            raise OpenWebUIError('Biz GPT did not return a chat id')
        log.info('biz gpt chat created', **log_extra(chat_id=chat_id))
        return chat_id

    async def mirror_conversation(self, chat_id: str, title: str, model: str, history: list[dict[str, Any]]) -> None:
        await self._call('POST', f'/api/v1/chats/{chat_id}', json=self._chat_body(title, model, history))

    async def send_message_to_openwebui(self, model: str, prompt_messages: list[dict[str, str]]) -> str:
        """Forward the customer's conversation to the Biz GPT agent and return its answer."""
        return await self.get_agent_response(model, prompt_messages)

    async def sync_conversation(self, chat_id: str | None, title: str, model: str, history: list[dict[str, Any]]) -> str | None:
        """Create the Biz GPT chat if needed and write the full history into it.

        Best effort: returns the chat id (new or unchanged) and never raises, so a mirror
        problem can't block a customer reply.
        """
        if not self.settings.openwebui_mirror_chats:
            return chat_id
        try:
            chat_id = await self.create_or_get_conversation(chat_id, title, model)
            await self.mirror_conversation(chat_id, title, model, history)
        except OpenWebUIError as exc:
            log.warning('biz gpt chat mirror failed', **log_extra(error=str(exc)))
        return chat_id
