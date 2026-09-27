"""Minimal MCP (streamable HTTP) client for the Google Workspace MCP server that holds the mailbox's OAuth."""

import itertools
import json
import os
import re

import httpx

MCP_URL = os.getenv('GMAIL_MCP_URL', 'http://gmail_mcp:8010/mcp')
MAILBOX = os.getenv('ORDERS_MAILBOX', 'dbizgpt.assistant@gmail.com')


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
            'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'bizgpt-orders', 'version': '1'}}})
        await self._rpc(client, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})

    async def call(self, tool: str, arguments: dict) -> str:
        arguments = {'user_google_email': MAILBOX, **arguments}
        async with httpx.AsyncClient(timeout=90) as client:
            for attempt in range(2):
                try:
                    await self._ensure_session(client)
                    data = await self._rpc(client, {'jsonrpc': '2.0', 'id': next(self._ids), 'method': 'tools/call',
                                                    'params': {'name': tool, 'arguments': arguments}})
                    break
                except _SessionExpired:
                    self._session_id = None
                    if attempt:
                        raise GmailError('Gmail MCP session could not be re-established')
        if not data or 'error' in data:
            raise GmailError(f'{tool} failed: {(data or {}).get("error")}')
        result = data['result']
        text = '\n'.join(c.get('text', '') for c in result.get('content', []) if c.get('type') == 'text')
        if result.get('isError'):
            raise GmailError(f'{tool} failed: {text[:300]}')
        return text

    async def search(self, query: str, page_size: int = 25) -> list[dict]:
        """[{message_id, thread_id}] newest first."""
        text = await self.call('search_gmail_messages', {'query': query, 'page_size': page_size})
        ids = re.findall(r'Message ID:\s*([0-9a-f]+)\s*\n.*?Thread ID:\s*([0-9a-f]+)', text, re.S)
        return [{'message_id': m, 'thread_id': t} for m, t in ids]

    async def read(self, message_id: str) -> dict:
        text = await self.call('get_gmail_message_content', {'message_id': message_id})
        head, _, body = text.partition('--- BODY ---')
        headers = {}
        for line in head.splitlines():
            key, sep, value = line.partition(':')
            if sep and key.strip() in ('Subject', 'From', 'Date', 'Message-ID', 'To', 'Cc'):
                headers[key.strip().lower()] = value.strip()
        return {
            'message_id': message_id,
            'subject': headers.get('subject', ''),
            'from': headers.get('from', ''),
            'from_email': _address(headers.get('from', '')),
            'date': headers.get('date', ''),
            'rfc_message_id': headers.get('message-id', ''),
            'body': _strip_quoted(body.strip())[:8000],
        }

    async def send(self, *, to: str, subject: str, body: str, thread_id: str | None = None,
                   in_reply_to: str | None = None) -> str:
        """Send a plain-text email; returns the Gmail message id. Threads it when thread_id/in_reply_to are given."""
        args = {'to': to, 'subject': subject, 'body': body, 'body_format': 'plain'}
        if thread_id:
            args['thread_id'] = thread_id
        if in_reply_to:
            args['in_reply_to'] = in_reply_to
            args['references'] = in_reply_to
        text = await self.call('send_gmail_message', args)
        match = re.search(r'Message ID:\s*([0-9a-f]+)', text)
        if not match:
            raise GmailError(f'send did not return a message id: {text[:200]}')
        return match.group(1)


class _SessionExpired(Exception):
    pass


def _address(value: str) -> str:
    match = re.search(r'<([^>]+)>', value)
    return (match.group(1) if match else value).strip().lower()


def _strip_quoted(body: str) -> str:
    """Drop the quoted history under a reply so only the customer's new text is analysed."""
    lines = []
    for line in body.splitlines():
        if re.match(r'^On .+ wrote:$', line.strip()) or line.strip().startswith('-----Original Message'):
            break
        if line.startswith('>'):
            continue
        lines.append(line)
    return '\n'.join(lines).strip()
