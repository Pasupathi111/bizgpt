"""Fixtures: a SQLite database per test and a fake Meta + Open WebUI upstream.

No test talks to the real Meta or Biz GPT APIs; every outbound HTTP call goes through
FakeUpstream via httpx.MockTransport.
"""

import hashlib
import hmac
import json
import time
from collections.abc import Callable

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

API_KEY = 'test-service-key'
APP_SECRET = 'test-app-secret'
VERIFY_TOKEN = 'test-verify-token'
PHONE_NUMBER_ID = '1111111111'


class FakeUpstream:
    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.sent: list[dict] = []
        self.completions: list[dict] = []
        self.chats: dict[str, dict] = {}
        self.answer = 'Hello from Biz GPT'
        # Hooks tests override: return an httpx.Response or raise to simulate failures.
        self.meta_send_hook: Callable[[httpx.Request], httpx.Response | None] | None = None
        self.completion_hook: Callable[[httpx.Request], httpx.Response | None] | None = None
        self.models_hook: Callable[[httpx.Request], httpx.Response | None] | None = None
        self._n = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        url = request.url
        if url.host == 'graph.facebook.com':
            return self._meta(request)
        return self._owui(request)

    def _meta(self, request: httpx.Request) -> httpx.Response:
        assert request.headers['authorization'] == 'Bearer EAAtesttoken1234567890abcdef'
        path = request.url.path
        if path.endswith('/messages') and request.method == 'POST':
            body = json.loads(request.content)
            if body.get('status') == 'read':
                return httpx.Response(200, json={'success': True})
            if self.meta_send_hook:
                result = self.meta_send_hook(request)
                if result is not None:
                    return result
            self._n += 1
            self.sent.append(body)
            return httpx.Response(200, json={'messaging_product': 'whatsapp', 'messages': [{'id': f'wamid.OUT{self._n}'}]})
        if path.endswith(f'/{PHONE_NUMBER_ID}'):
            return httpx.Response(200, json={'display_phone_number': '+91 98765 00000', 'verified_name': 'DBiz Solutions', 'quality_rating': 'GREEN'})
        if path.endswith('/message_templates'):
            return httpx.Response(200, json={'data': [{'name': 'hello_world', 'language': 'en_US', 'status': 'APPROVED', 'category': 'UTILITY',
                                                       'components': [{'type': 'BODY', 'text': 'Hello {{1}}'}]}]})
        return httpx.Response(404, json={'error': {'message': 'unknown path'}})

    def _owui(self, request: httpx.Request) -> httpx.Response:
        assert request.headers['authorization'] == 'Bearer sk-owuitestkey1234567890'
        path = request.url.path
        if path == '/api/models':
            if self.models_hook:
                result = self.models_hook(request)
                if result is not None:
                    return result
            return httpx.Response(200, json={'data': [{'id': 'bizgpt-whatsapp', 'name': 'Biz GPT WhatsApp'}]})
        if path == '/api/chat/completions':
            body = json.loads(request.content)
            self.completions.append(body)
            if self.completion_hook:
                result = self.completion_hook(request)
                if result is not None:
                    return result
            return httpx.Response(200, json={'choices': [{'message': {'role': 'assistant', 'content': self.answer}}]})
        if path == '/api/v1/chats/new':
            chat_id = f'chat-{len(self.chats) + 1}'
            self.chats[chat_id] = json.loads(request.content)['chat']
            return httpx.Response(200, json={'id': chat_id})
        if path.startswith('/api/v1/chats/'):
            chat_id = path.rsplit('/', 1)[-1]
            self.chats[chat_id] = json.loads(request.content)['chat']
            return httpx.Response(200, json={'id': chat_id})
        return httpx.Response(404, json={'detail': 'not found'})


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        whatsapp_access_token='EAAtesttoken1234567890abcdef',
        whatsapp_phone_number_id=PHONE_NUMBER_ID,
        whatsapp_business_account_id='2222222222',
        whatsapp_verify_token=VERIFY_TOKEN,
        whatsapp_app_secret=APP_SECRET,
        openwebui_base_url='http://owui.test',
        openwebui_api_key='sk-owuitestkey1234567890',
        whatsapp_service_api_key=API_KEY,
        database_url=f'sqlite+aiosqlite:///{tmp_path}/test.db',
        rate_limit_per_minute=100,
        http_retries=3,
    )


@pytest.fixture
def upstream() -> FakeUpstream:
    return FakeUpstream()


@pytest.fixture
def client(settings, upstream):
    app = create_app(settings, transport=httpx.MockTransport(upstream.handle), create_tables=True)
    with TestClient(app) as c:
        yield c


def auth() -> dict:
    return {'Authorization': f'Bearer {API_KEY}'}


def signed(body: dict | bytes, secret: str = APP_SECRET) -> tuple[bytes, dict]:
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return raw, {'X-Hub-Signature-256': f'sha256={sig}', 'Content-Type': 'application/json'}


def inbound_payload(
    wamid: str = 'wamid.IN1',
    sender: str = '919876543210',
    name: str | None = 'Priya',
    mtype: str = 'text',
    text: str = 'Hi, what are your hours?',
    extra: dict | None = None,
    ts: int | None = None,
) -> dict:
    message = {'from': sender, 'id': wamid, 'timestamp': str(ts or int(time.time())), 'type': mtype}
    if mtype == 'text':
        message['text'] = {'body': text}
    if extra:
        message.update(extra)
    value = {
        'messaging_product': 'whatsapp',
        'metadata': {'display_phone_number': '919876500000', 'phone_number_id': PHONE_NUMBER_ID},
        'messages': [message],
    }
    if name:
        value['contacts'] = [{'profile': {'name': name}, 'wa_id': sender}]
    return {'object': 'whatsapp_business_account', 'entry': [{'id': '2222222222', 'changes': [{'field': 'messages', 'value': value}]}]}


def status_payload(wamid: str, status: str, errors: list | None = None) -> dict:
    st = {'id': wamid, 'status': status, 'timestamp': str(int(time.time())), 'recipient_id': '919876543210'}
    if errors:
        st['errors'] = errors
    value = {'messaging_product': 'whatsapp', 'metadata': {'phone_number_id': PHONE_NUMBER_ID}, 'statuses': [st]}
    return {'object': 'whatsapp_business_account', 'entry': [{'id': '2222222222', 'changes': [{'field': 'messages', 'value': value}]}]}


def post_webhook(client: TestClient, payload: dict):
    raw, headers = signed(payload)
    return client.post('/api/whatsapp/webhook', content=raw, headers=headers)


@pytest.fixture(autouse=True)
def _no_swallowed_errors(capsys):
    """process() never raises by design, so fail any test whose logs show a swallowed crash."""
    yield
    out = capsys.readouterr().out
    assert 'whatsapp processing failed' not in out, out[-3000:]
