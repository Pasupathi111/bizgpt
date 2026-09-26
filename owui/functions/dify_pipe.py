"""
title: Dify Apps
author: BizGPT
version: 1.0.0
description: Exposes self-hosted Dify apps (chatflow, agent, chat, workflow, completion) as models in Biz GPT, streaming answers, live node progress and knowledge citations.
"""

import json
import time
from typing import AsyncGenerator, Optional

import aiohttp
from pydantic import BaseModel, Field

# Biz GPT chat_id -> Dify conversation_id (per app). In-memory: a restart
# simply starts a fresh Dify conversation for existing chats.
_CONVERSATIONS: dict[str, str] = {}

CHAT_TYPES = ('chat', 'chatflow', 'agent', 'advanced-chat')


class Pipe:
    class Valves(BaseModel):
        DIFY_BASE_URL: str = Field(
            default='http://dify-api:5001',
            description='Dify API base URL, without /v1 (e.g. https://dify.yourcompany.com)',
        )
        DIFY_APPS: str = Field(
            default='[]',
            description=(
                'JSON list of apps: [{"id": "lead-qualifier", "name": "Lead Qualifier", '
                '"type": "workflow", "api_key": "app-xxx", "input_key": "query"}]. '
                'type = chatflow | agent | chat | workflow | completion'
            ),
        )
        SHOW_NODE_PROGRESS: bool = Field(default=True, description='Show each Dify node as a live status line')
        SHOW_CITATIONS: bool = Field(default=True, description='Show Dify knowledge-base sources as citations')
        TIMEOUT_SECONDS: int = Field(default=300)

    def __init__(self):
        self.type = 'manifold'
        self.name = 'Dify / '
        self.valves = self.Valves()

    def _apps(self) -> list[dict]:
        try:
            apps = json.loads(self.valves.DIFY_APPS or '[]')
            return [a for a in apps if a.get('id') and a.get('api_key')]
        except json.JSONDecodeError:
            return []

    def pipes(self) -> list[dict]:
        apps = self._apps()
        if not apps:
            return [{'id': 'not-configured', 'name': 'Not configured (set DIFY_APPS valve)'}]
        return [{'id': a['id'], 'name': a.get('name', a['id'])} for a in apps]

    async def pipe(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__=None,
        __chat_id__: Optional[str] = None,
        __task__: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        # Title / tag / follow-up generation should not run a business workflow.
        if __task__:
            yield ''
            return

        app_id = body.get('model', '').split('.', 1)[-1]
        app = next((a for a in self._apps() if a['id'] == app_id), None)
        if not app:
            yield 'Dify app is not configured. Admin → Functions → Dify Apps → Valves → DIFY_APPS.'
            return

        query = _last_user_text(body.get('messages', []))
        user = (__user__ or {}).get('email') or (__user__ or {}).get('id') or 'bizgpt'
        app_type = app.get('type', 'chatflow')
        base = self.valves.DIFY_BASE_URL.rstrip('/') + '/v1'
        headers = {'Authorization': f'Bearer {app["api_key"]}', 'Content-Type': 'application/json'}

        inputs = dict(app.get('inputs', {}))
        if app_type in CHAT_TYPES:
            url = f'{base}/chat-messages'
            conv_key = f'{app_id}:{__chat_id__}'
            payload = {
                'inputs': inputs,
                'query': query,
                'response_mode': 'streaming',
                'user': user,
                'conversation_id': _CONVERSATIONS.get(conv_key, '') if __chat_id__ else '',
            }
        else:
            # Workflow / completion apps take named inputs. A JSON object message
            # maps onto inputs directly; plain text goes into input_key.
            parsed = _try_json_object(query)
            if parsed is not None:
                inputs.update(parsed)
            else:
                inputs[app.get('input_key', 'query')] = query
            url = f'{base}/workflows/run' if app_type == 'workflow' else f'{base}/completion-messages'
            payload = {'inputs': inputs, 'response_mode': 'streaming', 'user': user}
            conv_key = None

        emit = __event_emitter__ or _noop
        streamed_text = False
        started = time.monotonic()

        await emit({'type': 'status', 'data': {'description': f'Running Dify app: {app.get("name", app_id)}', 'done': False}})
        try:
            timeout = aiohttp.ClientTimeout(total=self.valves.TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        detail = await resp.text()
                        await emit({'type': 'status', 'data': {'description': 'Dify request failed', 'done': True}})
                        yield f'**Dify error {resp.status}:** {detail[:500]}'
                        return

                    async for event in _sse_events(resp):
                        name = event.get('event')

                        if name in ('message', 'agent_message', 'text_chunk'):
                            chunk = event.get('answer') if name != 'text_chunk' else event.get('data', {}).get('text')
                            if chunk:
                                streamed_text = True
                                yield chunk

                        elif name == 'node_started' and self.valves.SHOW_NODE_PROGRESS:
                            title = event.get('data', {}).get('title') or event.get('data', {}).get('node_type')
                            await emit({'type': 'status', 'data': {'description': f'▶ {title}', 'done': False}})

                        elif name == 'agent_thought' and self.valves.SHOW_NODE_PROGRESS:
                            tool = event.get('tool')
                            if tool:
                                await emit({'type': 'status', 'data': {'description': f'🔧 Using tool: {tool}', 'done': False}})

                        elif name == 'message_end':
                            if conv_key and __chat_id__ and event.get('conversation_id'):
                                _CONVERSATIONS[conv_key] = event['conversation_id']
                            if self.valves.SHOW_CITATIONS:
                                for res in (event.get('metadata') or {}).get('retriever_resources') or []:
                                    await emit(_citation(res))

                        elif name == 'workflow_finished':
                            data = event.get('data', {})
                            if data.get('status') not in (None, 'succeeded'):
                                yield f'\n\n**Workflow {data.get("status")}:** {data.get("error") or ""}'
                            elif not streamed_text:
                                yield _format_outputs(data.get('outputs') or {})

                        elif name == 'error':
                            yield f'\n\n**Dify error:** {event.get("message", event)}'
                            break
        except Exception as e:
            await emit({'type': 'status', 'data': {'description': 'Dify request failed', 'done': True}})
            yield f'**Could not reach Dify at {self.valves.DIFY_BASE_URL}:** {e}'
            return

        await emit(
            {
                'type': 'status',
                'data': {'description': f'Dify finished in {time.monotonic() - started:.1f}s', 'done': True},
            }
        )


async def _noop(_event):
    return None


async def _sse_events(resp) -> AsyncGenerator[dict, None]:
    buffer = b''
    async for chunk in resp.content.iter_any():
        buffer += chunk
        while b'\n' in buffer:
            line, buffer = buffer.split(b'\n', 1)
            line = line.strip()
            if not line.startswith(b'data:'):
                continue
            try:
                yield json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue


def _last_user_text(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get('role') == 'user':
            content = m.get('content', '')
            if isinstance(content, list):
                return '\n'.join(p.get('text', '') for p in content if p.get('type') == 'text')
            return content
    return ''


def _try_json_object(text: str) -> Optional[dict]:
    text = text.strip()
    if not text.startswith('{'):
        return None
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def _format_outputs(outputs: dict) -> str:
    if not outputs:
        return '_Workflow finished with no outputs._'
    if len(outputs) == 1:
        value = next(iter(outputs.values()))
        return value if isinstance(value, str) else f'```json\n{json.dumps(value, indent=2)}\n```'
    lines = []
    for key, value in outputs.items():
        if isinstance(value, (dict, list)):
            value = f'\n```json\n{json.dumps(value, indent=2)}\n```'
        lines.append(f'**{key}:** {value}')
    return '\n\n'.join(lines)


def _citation(res: dict) -> dict:
    name = res.get('document_name') or res.get('dataset_name') or 'Dify knowledge'
    return {
        'type': 'source',
        'data': {
            'source': {'name': name},
            'document': [res.get('content', '')],
            'metadata': [{'source': name, 'score': res.get('score')}],
        },
    }
