"""MetaAPIService and OpenWebUIService against mocked HTTP."""

import json

import httpx
import pytest

from app.services.meta_api_service import MetaAPIError, MetaAPIService, MetaNotConfigured
from app.services.openwebui_service import OpenWebUIAuthError, OpenWebUIError, OpenWebUIService


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _ok_send(request):
    return httpx.Response(200, json={'messages': [{'id': 'wamid.X'}]})


# ---------- Meta: send ----------


async def test_send_text(settings):
    seen = {}

    def handler(request):
        seen['url'] = str(request.url)
        seen['body'] = json.loads(request.content)
        seen['auth'] = request.headers['authorization']
        return _ok_send(request)

    async with _client(handler) as client:
        wamid = await MetaAPIService(settings, client, backoff=0).send_text('919876543210', 'hi')
    assert wamid == 'wamid.X'
    assert seen['url'] == f'https://graph.facebook.com/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/messages'
    assert seen['body']['text'] == {'body': 'hi', 'preview_url': False}
    assert seen['auth'] == 'Bearer ' + settings.whatsapp_access_token.get_secret_value()


async def test_send_template(settings):
    seen = {}

    def handler(request):
        seen['body'] = json.loads(request.content)
        return _ok_send(request)

    components = [{'type': 'body', 'parameters': [{'type': 'text', 'text': 'Priya'}]}]
    async with _client(handler) as client:
        await MetaAPIService(settings, client, backoff=0).send_template('919876543210', 'order_update', 'en_US', components)
    assert seen['body']['type'] == 'template'
    assert seen['body']['template'] == {'name': 'order_update', 'language': {'code': 'en_US'}, 'components': components}


async def test_api_failure_raises_with_meta_message(settings):
    handler = lambda r: httpx.Response(400, json={'error': {'message': 'Invalid OAuth access token', 'code': 190}})  # noqa: E731
    async with _client(handler) as client:
        with pytest.raises(MetaAPIError) as err:
            await MetaAPIService(settings, client, backoff=0).send_text('919876543210', 'hi')
    assert err.value.status == 400
    assert err.value.code == 190
    assert 'Invalid OAuth access token' in str(err.value)


async def test_outside_service_window_error(settings):
    handler = lambda r: httpx.Response(400, json={'error': {'message': 'Re-engagement message', 'code': 131047}})  # noqa: E731
    async with _client(handler) as client:
        with pytest.raises(MetaAPIError) as err:
            await MetaAPIService(settings, client, backoff=0).send_text('919876543210', 'hi')
    assert err.value.outside_service_window


async def test_send_timeout_is_not_retried(settings):
    """A read timeout on a send may mean Meta already delivered it: never resend."""
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout('slow', request=request)

    async with _client(handler) as client:
        with pytest.raises(MetaAPIError, match='timed out'):
            await MetaAPIService(settings, client, backoff=0).send_text('919876543210', 'hi')
    assert len(calls) == 1


async def test_send_retries_connect_errors_and_429(settings):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError('refused', request=request)
        if len(calls) == 2:
            return httpx.Response(429, json={'error': {'message': 'rate'}})
        return _ok_send(request)

    async with _client(handler) as client:
        assert await MetaAPIService(settings, client, backoff=0).send_text('919876543210', 'hi') == 'wamid.X'
    assert len(calls) == 3


async def test_read_calls_retry_on_5xx_and_timeout(settings):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout('slow', request=request)
        if len(calls) == 2:
            return httpx.Response(503)
        return httpx.Response(200, json={'display_phone_number': '+91 1'})

    async with _client(handler) as client:
        phone = await MetaAPIService(settings, client, backoff=0).get_phone_number()
    assert phone['display_phone_number'] == '+91 1'
    assert len(calls) == 3


async def test_retries_give_up(settings):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(500, json={'error': {'message': 'boom'}})

    async with _client(handler) as client:
        with pytest.raises(MetaAPIError):
            await MetaAPIService(settings, client, backoff=0).get_phone_number()
    assert len(calls) == settings.http_retries


async def test_not_configured(settings):
    settings.whatsapp_access_token = settings.whatsapp_access_token.__class__('')
    async with _client(_ok_send) as client:
        with pytest.raises(MetaNotConfigured):
            await MetaAPIService(settings, client).send_text('919876543210', 'hi')


# ---------- Open WebUI ----------


async def test_openwebui_connection(settings):
    def handler(request):
        assert request.url.path == '/api/models'
        return httpx.Response(200, json={'data': [{'id': 'bizgpt-whatsapp'}, {'id': 'other'}]})

    async with _client(handler) as client:
        result = await OpenWebUIService(settings, client, backoff=0).check_connection('bizgpt-whatsapp')
    assert result == {'ok': True, 'models': 2, 'agent_model_found': True}


async def test_openwebui_auth_failure(settings):
    async with _client(lambda r: httpx.Response(401, json={'detail': 'Not authenticated'})) as client:
        with pytest.raises(OpenWebUIAuthError):
            await OpenWebUIService(settings, client, backoff=0).check_connection()


async def test_openwebui_missing_key(settings):
    settings.openwebui_api_key = settings.openwebui_api_key.__class__('')
    async with _client(lambda r: httpx.Response(200, json={})) as client:
        with pytest.raises(OpenWebUIAuthError):
            await OpenWebUIService(settings, client).list_models()


async def test_openwebui_ai_response(settings):
    seen = {}

    def handler(request):
        seen['body'] = json.loads(request.content)
        return httpx.Response(200, json={'choices': [{'message': {'content': '  We open at 9am.  '}}]})

    async with _client(handler) as client:
        answer = await OpenWebUIService(settings, client).get_agent_response('bizgpt-whatsapp', [{'role': 'user', 'content': 'hours?'}])
    assert answer == 'We open at 9am.'
    assert seen['body'] == {'model': 'bizgpt-whatsapp', 'messages': [{'role': 'user', 'content': 'hours?'}], 'stream': False}


async def test_openwebui_empty_answer(settings):
    async with _client(lambda r: httpx.Response(200, json={'choices': [{'message': {'content': ''}}]})) as client:
        with pytest.raises(OpenWebUIError, match='empty'):
            await OpenWebUIService(settings, client).get_agent_response('m', [])


async def test_openwebui_timeout_not_retried(settings):
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout('slow', request=request)

    async with _client(handler) as client:
        with pytest.raises(OpenWebUIError, match='timed out'):
            await OpenWebUIService(settings, client, backoff=0).get_agent_response('m', [{'role': 'user', 'content': 'x'}])
    assert len(calls) == 1


async def test_openwebui_create_or_get_conversation(settings):
    created = []

    def handler(request):
        created.append(json.loads(request.content))
        return httpx.Response(200, json={'id': 'chat-42'})

    async with _client(handler) as client:
        service = OpenWebUIService(settings, client)
        assert await service.create_or_get_conversation(None, 'WhatsApp · Priya', 'bizgpt-whatsapp') == 'chat-42'
        assert await service.create_or_get_conversation('chat-42', 'WhatsApp · Priya', 'bizgpt-whatsapp') == 'chat-42'
    assert len(created) == 1
    assert created[0]['chat']['tags'] == ['whatsapp']


async def test_mirror_failure_is_swallowed(settings):
    async with _client(lambda r: httpx.Response(500)) as client:
        chat_id = await OpenWebUIService(settings, client, backoff=0).sync_conversation(None, 't', 'm', [])
    assert chat_id is None


async def test_openwebui_model_not_found_reloads_models_and_retries(settings):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == '/api/chat/completions' and calls.count('/api/chat/completions') == 1:
            return httpx.Response(400, json={'detail': 'Model not found'})
        if request.url.path == '/api/models':
            return httpx.Response(200, json={'data': [{'id': 'bizgpt-whatsapp'}]})
        return httpx.Response(200, json={'choices': [{'message': {'content': 'ok'}}]})

    async with _client(handler) as client:
        assert await OpenWebUIService(settings, client).get_agent_response('bizgpt-whatsapp', [{'role': 'user', 'content': 'x'}]) == 'ok'
    assert calls == ['/api/chat/completions', '/api/models', '/api/chat/completions']
