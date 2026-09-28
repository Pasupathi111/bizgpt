"""Gmail intake for the Monthly Report POC: find site-photo emails and download their image attachments.

Talks MCP (streamable HTTP) to the Google Workspace MCP server that holds the mailbox's OAuth
(github.com/taylorwilsdon/google_workspace_mcp). Settings are this project's own; nothing is shared
with other Biz GPT workflows.
"""

import base64
import itertools
import json
import os
import re

import httpx

MCP_URL = os.getenv('MONTHLY_REPORT_GMAIL_MCP_URL') or 'http://gmail_mcp:8010/mcp'
MAILBOX = os.getenv('MONTHLY_REPORT_MAILBOX') or 'dbizgpt.assistant@gmail.com'
# Emails with image attachments; narrow it (e.g. add subject:report) if the mailbox is shared.
QUERY = os.getenv('MONTHLY_REPORT_GMAIL_QUERY') or 'has:attachment (filename:jpg OR filename:jpeg OR filename:png OR filename:webp) newer_than:60d'
IMAGE_EXT = re.compile(r'\.(jpe?g|png|webp)$', re.I)


class GmailError(RuntimeError):
    pass


class _SessionExpired(Exception):
    pass


class Gmail:
    def __init__(self, url: str = MCP_URL, mailbox: str = MAILBOX):
        self.url, self.mailbox = url, mailbox
        self._session_id: str | None = None
        self._ids = itertools.count(1)
        self._tool_params: dict[str, set[str]] | None = None

    async def _rpc(self, client: httpx.AsyncClient, body: dict) -> dict | None:
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
        if self._session_id:
            headers['mcp-session-id'] = self._session_id
        resp = await client.post(self.url, json=body, headers=headers)
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
            'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'bizgpt-monthly-report', 'version': '1'}}})
        await self._rpc(client, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})

    async def call(self, tool: str, arguments: dict) -> str:
        arguments = {'user_google_email': self.mailbox, **arguments}
        data = None
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                for attempt in range(2):
                    try:
                        await self._ensure_session(client)
                        data = await self._rpc(client, {'jsonrpc': '2.0', 'id': next(self._ids), 'method': 'tools/call',
                                                        'params': {'name': tool, 'arguments': arguments}})
                        break
                    except _SessionExpired:
                        self._session_id = None
                        if attempt:
                            raise GmailError('Gmail connection could not be re-established')
        except httpx.HTTPError as e:
            raise GmailError(f'Gmail is not reachable ({type(e).__name__})') from e
        if not data or 'error' in data:
            raise GmailError(f'Gmail {tool} failed: {(data or {}).get("error")}')
        result = data['result']
        text = '\n'.join(c.get('text', '') for c in result.get('content', []) if c.get('type') == 'text')
        if result.get('isError'):
            raise GmailError(f'Gmail {tool} failed: {text[:300]}')
        return text

    async def search(self, query: str, page_size: int = 25) -> list[str]:
        """Message ids, newest first."""
        text = await self.call('search_gmail_messages', {'query': query, 'page_size': page_size})
        return re.findall(r'Message ID:\s*([0-9a-f]+)', text)

    async def read(self, message_id: str) -> dict:
        text = await self.call('get_gmail_message_content', {'message_id': message_id})
        return parse_message(message_id, text)

    async def params_of(self, tool: str) -> set[str]:
        """Argument names the server accepts for a tool (Google Workspace MCP versions differ)."""
        if self._tool_params is None:
            async with httpx.AsyncClient(timeout=30) as client:
                await self._ensure_session(client)
                data = await self._rpc(client, {'jsonrpc': '2.0', 'id': next(self._ids), 'method': 'tools/list', 'params': {}})
            self._tool_params = {t['name']: set((t.get('inputSchema') or {}).get('properties') or {})
                                 for t in ((data or {}).get('result') or {}).get('tools', [])}
        return self._tool_params.get(tool, set())

    async def download(self, message_id: str, attachment: dict) -> bytes:
        args = {'message_id': message_id, 'attachment_id': attachment['attachment_id'], 'return_base64': True}
        if attachment.get('index') is not None and 'attachment_index' in await self.params_of('get_gmail_attachment_content'):
            args['attachment_index'] = attachment['index']
        text = await self.call('get_gmail_attachment_content', args)
        data = parse_attachment(text)
        if data is not None:
            return data
        url = re.search(r'Download URL:\s*(\S+)', text)
        if url:  # older servers: a temporary link instead of inline data
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(url.group(1))
            if resp.status_code == 200 and resp.content:
                return resp.content
        raise GmailError(f'could not download {attachment["filename"]}')


def parse_message(message_id: str, text: str) -> dict:
    head, _, rest = text.partition('--- BODY ---')
    body, _, att_block = rest.partition('--- ATTACHMENTS ---')
    headers = {}
    for line in head.splitlines():
        key, sep, value = line.partition(':')
        if sep and key.strip() in ('Subject', 'From', 'Date'):
            headers[key.strip().lower()] = value.strip()
    attachments = []
    for m in re.finditer(r'^\s*(\d+)\.\s+(.+?)\s+\(([^,()]+),[^)]*\)[^\n]*\n\s*Attachment ID:\s*(\S+)', att_block, re.M):
        attachments.append({'index': int(m.group(1)) - 1, 'filename': m.group(2).strip(), 'mime': m.group(3).strip(),
                            'attachment_id': m.group(4).strip()})
    sender = headers.get('from', '')
    addr = re.search(r'<([^>]+)>', sender)
    return {
        'message_id': message_id,
        'subject': headers.get('subject', ''),
        'from': sender,
        'from_email': (addr.group(1) if addr else sender).strip().lower(),
        'date': headers.get('date', ''),
        'body': body.strip()[:4000],
        'attachments': attachments,
        'images': [a for a in attachments if a['mime'].lower().startswith('image/') or IMAGE_EXT.search(a['filename'])],
    }


def parse_attachment(text: str) -> bytes | None:
    m = re.search(r'Base64 content \(\d+ chars, standard base64\):\s*\n([A-Za-z0-9+/=\s]+)', text)
    if not m:
        return None
    try:
        return base64.b64decode(re.sub(r'\s+', '', m.group(1)), validate=True)
    except ValueError:
        return None
