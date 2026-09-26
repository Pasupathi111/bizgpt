import json

import httpx

from tests.conftest import VERIFY_TOKEN, auth, inbound_payload, post_webhook, signed, status_payload


def _messages(client, phone='919876543210'):
    return client.get('/api/whatsapp/messages', params={'phone': phone}, headers=auth()).json()


# ---------- GET verification ----------


def test_verification_returns_challenge(client):
    r = client.get('/api/whatsapp/webhook', params={'hub.mode': 'subscribe', 'hub.verify_token': VERIFY_TOKEN, 'hub.challenge': '12345'})
    assert r.status_code == 200
    assert r.text == '12345'


def test_verification_rejects_wrong_token(client):
    r = client.get('/api/whatsapp/webhook', params={'hub.mode': 'subscribe', 'hub.verify_token': 'nope', 'hub.challenge': '1'})
    assert r.status_code == 403


def test_verification_rejects_wrong_mode(client):
    r = client.get('/api/whatsapp/webhook', params={'hub.mode': 'unsubscribe', 'hub.verify_token': VERIFY_TOKEN, 'hub.challenge': '1'})
    assert r.status_code == 403


# ---------- POST incoming message: full flow ----------


def test_incoming_text_is_answered_end_to_end(client, upstream):
    r = post_webhook(client, inbound_payload(text='What are your office hours?'))
    assert r.status_code == 200
    assert r.json()['queued'] == 1

    # Biz GPT got the customer's message with the agent model.
    assert len(upstream.completions) == 1
    completion = upstream.completions[0]
    assert completion['model'] == 'bizgpt-whatsapp'
    assert completion['stream'] is False
    assert completion['messages'][0]['role'] == 'system'
    assert completion['messages'][-1] == {'role': 'user', 'content': 'What are your office hours?'}

    # The answer went back through Meta to the sender.
    assert upstream.sent == [
        {'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': '919876543210', 'type': 'text',
         'text': {'body': 'Hello from Biz GPT', 'preview_url': False}}
    ]

    # Both directions are stored; inbound is processed, outbound sent.
    msgs = _messages(client)
    assert [(m['direction'], m['status'], m['content']) for m in msgs] == [
        ('inbound', 'processed', 'What are your office hours?'),
        ('outbound', 'sent', 'Hello from Biz GPT'),
    ]
    assert msgs[0]['whatsapp_message_id'] == 'wamid.IN1'
    assert msgs[0]['sender_phone'] == '919876543210'
    assert msgs[1]['whatsapp_message_id'] == 'wamid.OUT1'

    # The exchange is mirrored into a Biz GPT chat and linked to the conversation.
    conv = client.get('/api/whatsapp/conversations', headers=auth()).json()[0]
    assert conv['openwebui_chat_id'] == 'chat-1'
    assert conv['contact']['profile_name'] == 'Priya'
    chat = upstream.chats['chat-1']
    assert chat['title'].startswith('WhatsApp · Priya')
    assert [m['role'] for m in chat['messages']] == ['user', 'assistant']


def test_second_message_uses_history_and_same_chat(client, upstream):
    post_webhook(client, inbound_payload(wamid='wamid.A', text='Hi'))
    upstream.answer = 'Sure, happy to help'
    post_webhook(client, inbound_payload(wamid='wamid.B', text='Can you help with pricing?'))
    last = upstream.completions[-1]['messages']
    assert [m['role'] for m in last] == ['system', 'user', 'assistant', 'user']
    assert last[-1]['content'] == 'Can you help with pricing?'
    assert list(upstream.chats) == ['chat-1']
    assert len(upstream.chats['chat-1']['messages']) == 4


# ---------- invalid webhooks ----------


def test_invalid_signature_rejected(client, upstream):
    raw, headers = signed(inbound_payload(), secret='wrong-secret')
    r = client.post('/api/whatsapp/webhook', content=raw, headers=headers)
    assert r.status_code == 401
    assert upstream.completions == []


def test_missing_signature_rejected(client):
    r = client.post('/api/whatsapp/webhook', content=json.dumps(inbound_payload()), headers={'Content-Type': 'application/json'})
    assert r.status_code == 401


def test_invalid_json_rejected(client):
    raw, headers = signed(b'{not json')
    assert client.post('/api/whatsapp/webhook', content=raw, headers=headers).status_code == 400


def test_wrong_object_rejected(client):
    assert post_webhook(client, {'object': 'page', 'entry': []}).status_code == 400


def test_malformed_entries_are_ignored(client, upstream):
    payload = {'object': 'whatsapp_business_account', 'entry': [{'changes': [{'field': 'messages', 'value': {'messages': [{'type': 'text'}]}}]}, {}]}
    r = post_webhook(client, payload)
    assert r.status_code == 200
    assert r.json()['received'] == 0


# ---------- duplicates ----------


def test_duplicate_message_processed_once(client, upstream):
    payload = inbound_payload(wamid='wamid.DUP')
    assert post_webhook(client, payload).json()['queued'] == 1
    r = post_webhook(client, payload)
    assert r.status_code == 200
    assert r.json()['queued'] == 0
    assert len(upstream.completions) == 1
    assert len(upstream.sent) == 1
    assert len([m for m in _messages(client) if m['direction'] == 'inbound']) == 1


# ---------- unsupported and media ----------


def test_unsupported_type_gets_fixed_reply_without_ai(client, upstream, settings):
    payload = inbound_payload(mtype='unsupported', extra={'errors': [{'code': 131051, 'title': 'Message type unknown'}]})
    assert post_webhook(client, payload).status_code == 200
    assert upstream.completions == []
    assert upstream.sent[0]['text']['body'] == settings.unsupported_reply
    inbound = _messages(client)[0]
    assert inbound['message_type'] == 'unsupported'
    assert inbound['status'] == 'processed'
    assert inbound['meta'] == {'errors': [{'code': 131051, 'title': 'Message type unknown'}]}


def test_audio_is_not_sent_to_ai(client, upstream, settings):
    payload = inbound_payload(mtype='audio', extra={'audio': {'id': 'media-1', 'mime_type': 'audio/ogg'}})
    post_webhook(client, payload)
    assert upstream.completions == []
    assert upstream.sent[0]['text']['body'] == settings.unsupported_reply


def test_image_metadata_stored_and_caption_sent_to_ai(client, upstream):
    payload = inbound_payload(mtype='image', extra={'image': {'id': 'media-9', 'mime_type': 'image/jpeg', 'sha256': 'abc', 'caption': 'Is this damaged?'}})
    post_webhook(client, payload)
    inbound = _messages(client)[0]
    assert inbound['message_type'] == 'image'
    assert inbound['meta'] == {'id': 'media-9', 'mime_type': 'image/jpeg', 'sha256': 'abc', 'caption': 'Is this damaged?'}
    assert upstream.completions[0]['messages'][-1]['content'] == '[Customer sent image] Is this damaged?'


def test_document_metadata(client, upstream):
    payload = inbound_payload(mtype='document', extra={'document': {'id': 'doc-1', 'mime_type': 'application/pdf', 'filename': 'invoice.pdf'}})
    post_webhook(client, payload)
    inbound = _messages(client)[0]
    assert inbound['meta']['filename'] == 'invoice.pdf'
    assert inbound['content'] == '[Customer sent document invoice.pdf]'
    assert len(upstream.completions) == 1


def test_interactive_button_reply_is_text(client, upstream):
    payload = inbound_payload(mtype='interactive', extra={'interactive': {'type': 'button_reply', 'button_reply': {'id': 'yes', 'title': 'Yes please'}}})
    post_webhook(client, payload)
    assert upstream.completions[0]['messages'][-1]['content'] == 'Yes please'


def test_reaction_is_stored_not_answered(client, upstream):
    payload = inbound_payload(mtype='reaction', extra={'reaction': {'emoji': '👍', 'message_id': 'wamid.OUT1'}})
    post_webhook(client, payload)
    assert upstream.completions == []
    assert upstream.sent == []
    assert _messages(client)[0]['status'] == 'processed'


# ---------- status events ----------


def test_status_events_update_outbound_message(client, upstream):
    post_webhook(client, inbound_payload())
    post_webhook(client, status_payload('wamid.OUT1', 'delivered'))
    assert _messages(client)[1]['status'] == 'delivered'
    post_webhook(client, status_payload('wamid.OUT1', 'read'))
    assert _messages(client)[1]['status'] == 'read'
    # A late "sent" never moves it backwards.
    post_webhook(client, status_payload('wamid.OUT1', 'sent'))
    assert _messages(client)[1]['status'] == 'read'


def test_failed_status_records_error(client, upstream):
    post_webhook(client, inbound_payload())
    post_webhook(client, status_payload('wamid.OUT1', 'failed', [{'code': 131026, 'title': 'Message undeliverable'}]))
    out = _messages(client)[1]
    assert out['status'] == 'failed'
    assert out['error'] == '131026: Message undeliverable'


def test_status_for_unknown_message_is_ignored(client):
    r = post_webhook(client, status_payload('wamid.UNKNOWN', 'read'))
    assert r.status_code == 200


# ---------- failure handling ----------


def test_openwebui_failure_sends_fallback(client, upstream, settings):
    upstream.completion_hook = lambda req: httpx.Response(500, json={'detail': 'model crashed'})
    assert post_webhook(client, inbound_payload()).status_code == 200
    assert upstream.sent[0]['text']['body'] == settings.fallback_reply
    inbound = _messages(client)[0]
    assert inbound['status'] == 'processed'
    assert 'HTTP 500' in inbound['error']


def test_meta_send_failure_is_stored_not_raised(client, upstream):
    upstream.meta_send_hook = lambda req: httpx.Response(400, json={'error': {'message': 'Invalid parameter', 'code': 100}})
    assert post_webhook(client, inbound_payload()).status_code == 200
    msgs = _messages(client)
    assert msgs[1]['direction'] == 'outbound'
    assert msgs[1]['status'] == 'failed'
    assert 'Invalid parameter' in msgs[1]['error']


def test_disconnected_account_stores_but_does_not_answer(client, upstream):
    client.put('/api/whatsapp/settings', json={'is_active': False}, headers=auth())
    post_webhook(client, inbound_payload())
    assert upstream.completions == []
    assert upstream.sent == []
    inbound = _messages(client)[0]
    assert inbound['status'] == 'processed'
    assert inbound['error'] == 'auto reply off'


def test_rate_limit_per_contact(settings, upstream):
    from fastapi.testclient import TestClient

    from app.main import create_app

    settings.rate_limit_per_minute = 2
    app = create_app(settings, transport=httpx.MockTransport(upstream.handle), create_tables=True)
    with TestClient(app) as c:
        for i in range(3):
            post_webhook(c, inbound_payload(wamid=f'wamid.R{i}', text=f'msg {i}'))
        assert len(upstream.completions) == 2
        inbound = [m for m in _messages(c) if m['direction'] == 'inbound']
        assert inbound[-1]['error'] == 'rate limited'


def test_outbound_with_clashing_wamid_is_still_recorded(client, upstream, capsys):
    upstream.meta_send_hook = lambda req: httpx.Response(200, json={'messages': [{'id': 'wamid.SAME'}]})
    post_webhook(client, inbound_payload(wamid='wamid.X1', text='one'))
    post_webhook(client, inbound_payload(wamid='wamid.X2', text='two'))
    msgs = _messages(client)
    assert [m['status'] for m in msgs] == ['processed', 'sent', 'processed', 'sent']
    assert msgs[3]['whatsapp_message_id'] is None and 'duplicate wamid' in msgs[3]['error']
    assert 'processing failed' not in capsys.readouterr().out
