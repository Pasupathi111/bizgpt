"""Internal API (tool / Integrations page), health, status and log redaction."""

import logging
from datetime import timedelta

import httpx

from app.logging_setup import RedactingFilter, mask_phone
from tests.conftest import auth, inbound_payload, post_webhook


def test_health_is_public(client):
    r = client.get('/health')
    assert r.status_code == 200
    assert r.json() == {'status': 'ok', 'database': True}


def test_internal_api_requires_key(client):
    assert client.get('/api/whatsapp/status').status_code == 401
    assert client.get('/api/whatsapp/status', headers={'Authorization': 'Bearer wrong'}).status_code == 401
    assert client.post('/api/whatsapp/messages/send', json={'to': '+919876543210', 'text': 'x'}).status_code == 401


def test_status_reports_components_without_secrets(client, settings):
    r = client.get('/api/whatsapp/status', headers=auth())
    assert r.status_code == 200
    body = r.json()
    assert body['status'] == 'ok'
    assert body['whatsapp_api']['display_phone_number'] == '+91 98765 00000'
    assert body['openwebui']['agent_model_found'] is True
    assert body['database']['ok'] is True
    assert body['webhook'] == {'ok': True, 'verify_token_set': True, 'signature_verification': True, 'path': '/api/whatsapp/webhook'}
    for secret in settings.secret_values():
        assert secret not in r.text


def test_status_degraded_when_openwebui_rejects_key(client, upstream):
    upstream.models_hook = lambda req: httpx.Response(401, json={'detail': 'bad key'})
    body = client.get('/api/whatsapp/status', headers=auth()).json()
    assert body['status'] == 'degraded'
    assert body['openwebui']['ok'] is False


def test_send_message_inside_window(client, upstream):
    post_webhook(client, inbound_payload())
    r = client.post('/api/whatsapp/messages/send', json={'to': '+91 98765 43210', 'text': 'Your order shipped'}, headers=auth())
    assert r.status_code == 200, r.text
    assert r.json()['content'] == 'Your order shipped'
    assert upstream.sent[-1]['to'] == '919876543210'


def test_send_message_outside_window_needs_template(client, upstream):
    r = client.post('/api/whatsapp/messages/send', json={'to': '+919999999999', 'text': 'Hello'}, headers=auth())
    assert r.status_code == 409
    assert 'template' in r.json()['detail']
    assert upstream.sent == []


def test_send_message_validates_phone(client):
    r = client.post('/api/whatsapp/messages/send', json={'to': 'abc', 'text': 'Hello'}, headers=auth())
    assert r.status_code == 422


def test_send_template(client, upstream):
    r = client.post(
        '/api/whatsapp/messages/template',
        json={'to': '+919999999999', 'template_name': 'hello_world', 'language': 'en_US', 'body_params': ['Priya']},
        headers=auth(),
    )
    assert r.status_code == 200, r.text
    assert r.json()['message_type'] == 'template'
    assert upstream.sent[-1]['template']['components'] == [{'type': 'body', 'parameters': [{'type': 'text', 'text': 'Priya'}]}]


def test_list_templates(client):
    r = client.get('/api/whatsapp/templates', headers=auth())
    assert r.json() == [{'name': 'hello_world', 'language': 'en_US', 'status': 'APPROVED', 'category': 'UTILITY', 'body': 'Hello {{1}}'}]


def test_contact_conversation_and_messages(client):
    post_webhook(client, inbound_payload())
    contact = client.get('/api/whatsapp/contacts/+919876543210', headers=auth())
    assert contact.status_code == 200
    assert contact.json()['profile_name'] == 'Priya'
    assert client.get('/api/whatsapp/contacts/919000000000', headers=auth()).status_code == 404

    convs = client.get('/api/whatsapp/conversations', params={'phone': '+919876543210'}, headers=auth()).json()
    assert len(convs) == 1 and convs[0]['within_service_window'] is True
    detail = client.get(f"/api/whatsapp/conversations/{convs[0]['id']}", headers=auth()).json()
    assert [m['direction'] for m in detail['messages']] == ['inbound', 'outbound']


def test_settings_and_agent_selection(client, upstream):
    r = client.put('/api/whatsapp/settings', json={'agent_model': 'bizgpt-assistant'}, headers=auth())
    assert r.json()['agent_model'] == 'bizgpt-assistant'
    post_webhook(client, inbound_payload())
    assert upstream.completions[-1]['model'] == 'bizgpt-assistant'
    stats = client.get('/api/whatsapp/settings', headers=auth()).json()['stats']
    assert stats['messages_inbound'] == 1 and stats['messages_outbound'] == 1 and stats['contacts'] == 1


def test_test_connection(client):
    r = client.post('/api/whatsapp/test-connection', headers=auth()).json()
    assert r['ok'] is True
    assert r['whatsapp']['verified_name'] == 'DBiz Solutions'
    settings = client.get('/api/whatsapp/settings', headers=auth()).json()
    assert settings['display_phone_number'] == '+91 98765 00000'


def test_models_list(client):
    assert client.get('/api/whatsapp/models', headers=auth()).json() == [{'id': 'bizgpt-whatsapp', 'name': 'Biz GPT WhatsApp'}]


# ---------- logging ----------


def test_redacting_filter_removes_secrets():
    f = RedactingFilter(['super-secret-value'])
    record = logging.LogRecord('x', logging.INFO, __file__, 1, 'token %s and Bearer abc.def and EAAabcdefghijklmnopqrstuvwxyz1234 and super-secret-value', ('sk-abcdefghijklmnopqrstuv',), None)
    f.filter(record)
    msg = record.getMessage()
    assert 'super-secret-value' not in msg
    assert 'abc.def' not in msg
    assert 'EAAabcdefghijklmnopqrstuvwxyz1234' not in msg
    assert 'sk-abcdefghijklmnopqrstuv' not in msg


def test_logs_never_contain_tokens(client, settings, capsys):
    post_webhook(client, inbound_payload())
    client.post('/api/whatsapp/test-connection', headers=auth())
    out = capsys.readouterr().out
    assert out  # structured logs were written
    for secret in settings.secret_values():
        assert secret not in out
    assert '919876543210' not in out  # phone numbers are masked


def test_mask_phone():
    assert mask_phone('919876543210') == '919******210'
    assert mask_phone('') == ''


def test_service_window_helper():
    from app.models import Conversation
    from app.models.base import utcnow
    from app.services.conversation_service import within_service_window

    assert within_service_window(Conversation(last_inbound_at=utcnow() - timedelta(hours=1)))
    assert not within_service_window(Conversation(last_inbound_at=utcnow() - timedelta(hours=25)))
    assert not within_service_window(Conversation())


def test_access_log_redacts_verify_token():
    f = RedactingFilter([])
    record = logging.LogRecord('uvicorn.access', logging.INFO, __file__, 1, '%s - "%s %s HTTP/1.1" %d',
                               ('1.2.3.4', 'GET', '/api/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=abc123secret&hub.challenge=1', 200), None)
    f.filter(record)
    assert 'abc123secret' not in record.getMessage()


def test_uvicorn_access_formatter_still_works_after_redaction():
    from uvicorn.logging import AccessFormatter

    f = RedactingFilter([])
    record = logging.LogRecord('uvicorn.access', logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                               ('1.2.3.4:1', 'GET', '/api/whatsapp/webhook?hub.verify_token=abc123secret', '1.1', 200), None)
    f.filter(record)
    line = AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False).format(record)
    assert 'abc123secret' not in line and '/api/whatsapp/webhook' in line
