#!/usr/bin/env python3
"""Fake Meta Graph API + fake Biz GPT API for trying the service without real accounts.

    python dev/mock_upstream.py            # listens on :5056
    WHATSAPP_GRAPH_URL=http://localhost:5056 OPENWEBUI_BASE_URL=http://localhost:5056 ...

GET /_sent lists the WhatsApp messages the service "sent". Any token/key is accepted.
"""

import os
import uuid

import uvicorn
from fastapi import FastAPI, Request

app = FastAPI()
sent: list[dict] = []
chats: dict[str, dict] = {}


@app.post('/{version}/{phone_number_id}/messages')
async def send(version: str, phone_number_id: str, request: Request):
    body = await request.json()
    if body.get('status') == 'read':
        return {'success': True}
    sent.append(body)
    return {'messaging_product': 'whatsapp', 'messages': [{'id': f'wamid.MOCK{uuid.uuid4().hex}'}]}


@app.get('/{version}/{node_id}/message_templates')
async def templates(version: str, node_id: str):
    return {'data': [{'name': 'hello_world', 'language': 'en_US', 'status': 'APPROVED', 'category': 'UTILITY',
                      'components': [{'type': 'BODY', 'text': 'Hello World'}]}]}


@app.get('/api/models')
async def models():
    return {'data': [{'id': 'bizgpt-whatsapp', 'name': 'Biz GPT WhatsApp (mock)'}]}


@app.post('/api/chat/completions')
async def completions(request: Request):
    body = await request.json()
    question = body['messages'][-1]['content']
    return {'choices': [{'message': {'role': 'assistant', 'content': f'(mock Biz GPT) You asked: {question}'}}]}


@app.post('/api/v1/chats/new')
async def new_chat(request: Request):
    chat_id = f'mock-chat-{len(chats) + 1}'
    chats[chat_id] = (await request.json())['chat']
    return {'id': chat_id}


@app.post('/api/v1/chats/{chat_id}')
async def update_chat(chat_id: str, request: Request):
    chats[chat_id] = (await request.json())['chat']
    return {'id': chat_id}


# OpenAI-compatible LLM, so a real Biz GPT can use "mock-gpt" as the base model.
@app.get('/v1/models')
async def openai_models():
    return {'object': 'list', 'data': [{'id': 'mock-gpt', 'object': 'model', 'owned_by': 'mock'}]}


@app.post('/v1/chat/completions')
async def openai_completions(request: Request):
    body = await request.json()
    msgs = body['messages']
    has_system = any(m['role'] == 'system' for m in msgs)
    answer = f"(mock LLM, system prompt: {'yes' if has_system else 'no'}, turns: {len(msgs)}) You said: {msgs[-1]['content']}"
    return {'id': 'cmpl-mock', 'object': 'chat.completion', 'model': body.get('model'),
            'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': answer}}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}


@app.get('/_sent')
async def list_sent():
    return {'sent': sent, 'chats': chats}


@app.get('/{version}/{phone_number_id}')
async def phone(version: str, phone_number_id: str):
    return {'display_phone_number': '+91 90000 00000', 'verified_name': 'DBiz (mock)', 'quality_rating': 'GREEN', 'id': phone_number_id}


if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=int(os.getenv('PORT', '5056')))
