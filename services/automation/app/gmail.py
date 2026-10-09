"""Send-only MCP (streamable HTTP) client for the Google Workspace MCP server that holds the mailbox's OAuth."""

import itertools
import json
import os
import re

import httpx

MCP_URL = os.getenv('GMAIL_MCP_URL', 'http://gmail_mcp:8010/mcp')
MAILBOX = os.getenv('AUTOMATION_MAILBOX', 'dbizgpt.assistant@gmail.com')


class GmailError(RuntimeError):
    pass


class Gmail:
    def __init__(self):
        self._session_id: str | None = None
        self._ids = itertools.count(1)

    async def _rpc(self, client: httpx.AsyncClient, body: dict) -> dict | None:
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
        if self._session_id:
            headers['mcp-session-id'] = self._session_id
        resp = await client.post(MCP_URL, json=body, headers=headers)
        if resp.status_code in (400, 404) and self._session_id:
            raise _SessionExpired()
        resp.raise_for_status()
        self._session_id = resp.headers.get('mcp-session-id', self._session_id)
        raw = resp.text
        for line in raw.splitlines():
            if line.startswith('data:'):
                raw = line[5:]
        return json.loads(raw) if raw.strip() else None

    async def _ensure_session(self, client: httpx.AsyncClient) -> None:
        if self._session_id:
            return
        await self._rpc(client, {'jsonrpc': '2.0', 'id': next(self._ids), 'method': 'initialize', 'params': {
            'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'bizgpt-automation', 'version': '1'}}})
        await self._rpc(client, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})

    async def send(self, *, to: str, subject: str, body: str) -> str:
        """Send a plain-text email; returns the Gmail message id."""
        arguments = {'user_google_email': MAILBOX, 'to': to, 'subject': subject, 'body': body, 'body_format': 'plain'}
        async with httpx.AsyncClient(timeout=90) as client:
            for attempt in range(2):
                try:
                    await self._ensure_session(client)
                    data = await self._rpc(client, {'jsonrpc': '2.0', 'id': next(self._ids), 'method': 'tools/call',
                                                    'params': {'name': 'send_gmail_message', 'arguments': arguments}})
                    break
                except _SessionExpired:
                    self._session_id = None
                    if attempt:
                        raise GmailError('Gmail MCP session could not be re-established')
        if not data or 'error' in data:
            raise GmailError(f'send_gmail_message failed: {(data or {}).get("error")}')
        result = data['result']
        text = '\n'.join(c.get('text', '') for c in result.get('content', []) if c.get('type') == 'text')
        if result.get('isError'):
            raise GmailError(f'send_gmail_message failed: {text[:300]}')
        match = re.search(r'Message ID:\s*([0-9a-f]+)', text)
        if not match:
            raise GmailError(f'send did not return a message id: {text[:200]}')
        return match.group(1)


class _SessionExpired(Exception):
    pass
