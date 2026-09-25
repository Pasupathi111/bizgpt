"""
BizGPT Integrations service.

Stable contracts over Nango so Open WebUI and future MCP/gateway layers can ask:
- get_integration_status
- connect_integration
- disconnect_integration

This service keeps the Nango API details out of the chat/tool layer.
"""

import asyncio
import base64
import hmac
import html
import os
import re
from email.message import EmailMessage
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

API_KEY = os.getenv('INTEGRATIONS_API_KEY', '')
NANGO_SERVER_URL = os.getenv('NANGO_SERVER_URL', 'http://nango-server:3003').rstrip('/')
NANGO_PUBLIC_SERVER_URL = os.getenv('NANGO_PUBLIC_SERVER_URL', NANGO_SERVER_URL).rstrip('/')
NANGO_PUBLIC_CONNECT_URL = os.getenv('NANGO_PUBLIC_CONNECT_URL', 'http://localhost:3009').rstrip('/')
INTEGRATIONS_PUBLIC_URL = os.getenv('INTEGRATIONS_PUBLIC_URL', 'http://localhost:8092').rstrip('/')
NANGO_SECRET_KEY = os.getenv('NANGO_SECRET_KEY', '').strip()
NANGO_ENV = os.getenv('NANGO_ENV', 'dev').strip() or 'dev'
GOOGLE_CLOUD_PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT_ID', '').strip()
GOOGLE_OAUTH_CLIENT_ID = os.getenv('GOOGLE_OAUTH_CLIENT_ID', '').strip()
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET', '').strip()
SUPPORTED_INTEGRATIONS = {
    'gmail': os.getenv('NANGO_GMAIL_CONFIG_KEY', 'gmail').strip() or 'gmail',
    'outlook': os.getenv('NANGO_OUTLOOK_CONFIG_KEY', 'outlook').strip() or 'outlook',
}
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

app = FastAPI(title='BizGPT Integrations', version='1.0.0')


class ConnectRequest(BaseModel):
    integration: str
    user_id: str
    user_email: str = ''
    user_name: str = ''


class DisconnectRequest(BaseModel):
    integration: str
    user_id: str


class SearchEmailsRequest(BaseModel):
    user_id: str
    integration: str = 'gmail'
    query: str = ''
    limit: int = 10
    unread_only: bool = False


class MarkEmailRequest(BaseModel):
    user_id: str
    integration: str = 'gmail'
    email_ids: list[str]
    read: bool


class ArchiveEmailRequest(BaseModel):
    user_id: str
    integration: str = 'gmail'
    email_ids: list[str]


class ReplyEmailRequest(BaseModel):
    user_id: str
    integration: str = 'gmail'
    email_id: str
    body: str
    user_email: str = ''
    reply_all: bool = False
    confirm: bool = True


class InboxSummaryRequest(BaseModel):
    user_id: str
    integration: str = 'gmail'
    query: str = ''
    limit: int = 25
    unread_only: bool = False


class TriageInboxRequest(BaseModel):
    user_id: str
    integration: str = 'gmail'
    query: str = ''
    limit: int = 25
    unread_only: bool = False
    apply: bool = False
    confirm: bool = False


def require_api_key(authorization: str = Header(default='')):
    if not API_KEY:
        raise HTTPException(503, 'INTEGRATIONS_API_KEY is not configured')
    token = authorization.removeprefix('Bearer ').strip()
    if not hmac.compare_digest(token.encode(), API_KEY.encode()):
        raise HTTPException(401, 'invalid api key')


def provider_config_key(integration: str) -> str:
    key = SUPPORTED_INTEGRATIONS.get(integration.strip().lower())
    if not key:
        raise HTTPException(404, f'unknown integration {integration!r}. Known: {sorted(SUPPORTED_INTEGRATIONS)}')
    return key


def connect_hint(integration: str) -> str:
    return f'{NANGO_PUBLIC_SERVER_URL}/integrations/{provider_config_key(integration)}'


def gmail_oauth_callback_url() -> str:
    return f'{NANGO_PUBLIC_SERVER_URL}/oauth/callback'


def gmail_api_console_url() -> str:
    if GOOGLE_CLOUD_PROJECT_ID:
        return (
            'https://console.developers.google.com/apis/api/'
            f'gmail.googleapis.com/overview?project={GOOGLE_CLOUD_PROJECT_ID}'
        )
    return 'https://console.developers.google.com/apis/api/gmail.googleapis.com/overview'


def gmail_setup_checklist() -> list[dict]:
    return [
        {
            'key': 'GOOGLE_CLOUD_PROJECT_ID',
            'required': True,
            'configured': bool(GOOGLE_CLOUD_PROJECT_ID),
            'value': GOOGLE_CLOUD_PROJECT_ID or '',
            'description': 'Google Cloud project id used by the Gmail OAuth app.',
        },
        {
            'key': 'GOOGLE_OAUTH_CLIENT_ID',
            'required': True,
            'configured': bool(GOOGLE_OAUTH_CLIENT_ID),
            'value': GOOGLE_OAUTH_CLIENT_ID or '',
            'description': 'OAuth client id for the Google app connected to Nango.',
        },
        {
            'key': 'GOOGLE_OAUTH_CLIENT_SECRET',
            'required': True,
            'configured': bool(GOOGLE_OAUTH_CLIENT_SECRET),
            'value': 'configured' if GOOGLE_OAUTH_CLIENT_SECRET else '',
            'description': 'OAuth client secret for the Google app connected to Nango.',
        },
        {
            'key': 'NANGO_GMAIL_CONFIG_KEY',
            'required': True,
            'configured': bool(SUPPORTED_INTEGRATIONS.get('gmail')),
            'value': SUPPORTED_INTEGRATIONS.get('gmail') or '',
            'description': 'Nango provider config key used for Gmail.',
        },
        {
            'key': 'NANGO_PUBLIC_SERVER_URL',
            'required': True,
            'configured': bool(NANGO_PUBLIC_SERVER_URL),
            'value': NANGO_PUBLIC_SERVER_URL,
            'description': 'Public Nango server URL. Gmail redirect URI must use this host.',
        },
        {
            'key': 'GOOGLE_REDIRECT_URI',
            'required': True,
            'configured': True,
            'value': gmail_oauth_callback_url(),
            'description': 'Authorized redirect URI that must be added in Google Cloud Console.',
        },
        {
            'key': 'GMAIL_API_CONSOLE_URL',
            'required': True,
            'configured': bool(GOOGLE_CLOUD_PROJECT_ID),
            'value': gmail_api_console_url(),
            'description': 'Enable gmail.googleapis.com in this project before mailbox actions will work.',
        },
    ]


def normalize_end_user_email(value: str) -> Optional[str]:
    email = (value or '').strip()
    if not email or not EMAIL_RE.match(email):
        return None
    return email


def with_connect_api_url(connect_url: str) -> str:
    if not connect_url:
        return connect_url
    parsed = urlparse(connect_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    # Self-hosted Connect UI defaults to Nango cloud unless apiURL is supplied.
    query.setdefault('apiURL', NANGO_PUBLIC_SERVER_URL)
    return urlunparse(parsed._replace(query=urlencode(query)))


def connect_embed_url(integration: str, token: str) -> str:
    if not token:
        return ''
    return f'{INTEGRATIONS_PUBLIC_URL}/public/connect/{integration}?session_token={token}'


def connect_page_html(integration: str, connect_url: str) -> str:
    integration_name = integration.replace('_', ' ').title()
    safe_connect_url = html.escape(connect_url, quote=True)
    safe_title = html.escape(f'Connect {integration_name}', quote=False)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{safe_title}</title>
    <style>
      :root {{
        color-scheme: light dark;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }}
      body {{
        margin: 0;
        background: #0b1220;
        color: #e5e7eb;
      }}
      .shell {{
        min-height: 100vh;
        box-sizing: border-box;
        padding: 16px;
      }}
      .card {{
        max-width: 980px;
        margin: 0 auto;
        background: rgba(15, 23, 42, 0.92);
        border: 1px solid rgba(148, 163, 184, 0.25);
        border-radius: 20px;
        overflow: hidden;
        box-shadow: 0 20px 40px rgba(15, 23, 42, 0.35);
      }}
      .header {{
        padding: 18px 20px 12px;
        border-bottom: 1px solid rgba(148, 163, 184, 0.18);
      }}
      .eyebrow {{
        font-size: 12px;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #93c5fd;
        margin: 0 0 6px;
      }}
      h1 {{
        font-size: 20px;
        line-height: 1.3;
        margin: 0;
      }}
      p {{
        margin: 8px 0 0;
        color: #cbd5e1;
        font-size: 14px;
        line-height: 1.5;
      }}
      .frame-wrap {{
        padding: 16px;
      }}
      iframe {{
        width: 100%;
        min-height: 760px;
        border: 0;
        border-radius: 16px;
        background: #fff;
      }}
      @media (max-width: 768px) {{
        .shell {{
          padding: 8px;
        }}
        .frame-wrap {{
          padding: 10px;
        }}
        iframe {{
          min-height: 680px;
          border-radius: 12px;
        }}
      }}
    </style>
  </head>
  <body>
    <div class="shell">
      <div class="card">
        <div class="header">
          <div class="eyebrow">BizGPT Integration</div>
          <h1>{safe_title}</h1>
          <p>Finish authorization in this panel, then return to chat. The connection window stays inside BizGPT so you do not need to open a raw URL.</p>
        </div>
        <div class="frame-wrap">
          <iframe src="{safe_connect_url}" title="{safe_title}" allow="clipboard-read; clipboard-write"></iframe>
        </div>
      </div>
    </div>
    <script>
      const reportHeight = () => {{
        const height = Math.max(
          document.documentElement.scrollHeight || 0,
          document.body.scrollHeight || 0,
          840
        );
        window.parent?.postMessage({{ type: 'iframe:height', height }}, '*');
      }};
      window.addEventListener('load', reportHeight);
      window.addEventListener('resize', reportHeight);
      new ResizeObserver(reportHeight).observe(document.body);
    </script>
  </body>
</html>
"""


def nango_headers() -> dict[str, str]:
    if not NANGO_SECRET_KEY:
        raise HTTPException(
            503,
            'NANGO_SECRET_KEY is not configured. Set it in bizgpt/.env so BizGPT can create connect sessions.',
        )
    return {'Authorization': f'Bearer {NANGO_SECRET_KEY}'}


async def nango_request(method: str, path: str, *, params: Optional[dict] = None, body: Optional[dict] = None) -> httpx.Response:
    async with httpx.AsyncClient(timeout=20) as client:
        return await client.request(
            method,
            f'{NANGO_SERVER_URL}{path}',
            params=params,
            json=body,
            headers=nango_headers(),
        )


async def nango_proxy_request(
    method: str,
    path: str,
    *,
    connection_id: str,
    provider_config_key: str,
    params: Optional[dict] = None,
    body: Optional[dict] = None,
    headers: Optional[dict] = None,
) -> httpx.Response:
    proxy_headers = {
        **nango_headers(),
        'Connection-Id': connection_id,
        'Provider-Config-Key': provider_config_key,
    }
    if headers:
        proxy_headers.update(headers)
    async with httpx.AsyncClient(timeout=30) as client:
        return await client.request(
            method,
            f'{NANGO_SERVER_URL}/proxy/{path.lstrip("/")}',
            params=params,
            json=body,
            headers=proxy_headers,
        )


async def list_connections(integration: str) -> list[dict]:
    response = await nango_request('GET', '/connections', params={'integrationId': provider_config_key(integration)})
    if response.status_code >= 400:
        detail = response.text[:400]
        raise HTTPException(502, f'Nango connections lookup failed ({response.status_code}): {detail}')
    return response.json().get('connections') or response.json().get('data') or []


def match_end_user_connection(connections: list[dict], *, user_id: str) -> Optional[dict]:
    matches = [
        item
        for item in connections
        if ((item.get('end_user') or {}).get('id') == user_id or (item.get('tags') or {}).get('end_user_id') == user_id)
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: item.get('created') or item.get('updated_at') or '')
    return matches[-1]


def gmail_header_map(message: dict) -> dict[str, str]:
    payload = message.get('payload') or {}
    headers = payload.get('headers') or []
    return {str(item.get('name') or '').lower(): str(item.get('value') or '') for item in headers}


def decode_gmail_data(value: str) -> str:
    if not value:
        return ''
    padding = '=' * (-len(value) % 4)
    return base64.urlsafe_b64decode(f'{value}{padding}'.encode()).decode('utf-8', errors='replace')


def extract_gmail_bodies(payload: dict) -> tuple[str, str]:
    mime_type = payload.get('mimeType') or ''
    body_data = ((payload.get('body') or {}).get('data')) or ''
    text_parts: list[str] = []
    html_parts: list[str] = []

    if body_data:
        decoded = decode_gmail_data(body_data)
        if mime_type == 'text/html':
            html_parts.append(decoded)
        else:
            text_parts.append(decoded)

    for part in payload.get('parts') or []:
        child_text, child_html = extract_gmail_bodies(part)
        if child_text:
            text_parts.append(child_text)
        if child_html:
            html_parts.append(child_html)

    return '\n'.join([part for part in text_parts if part]).strip(), '\n'.join([part for part in html_parts if part]).strip()


def summarize_gmail_message(message: dict, *, include_bodies: bool = False) -> dict:
    headers = gmail_header_map(message)
    label_ids = message.get('labelIds') or []
    summary = {
        'id': message.get('id'),
        'thread_id': message.get('threadId'),
        'snippet': message.get('snippet') or '',
        'subject': headers.get('subject') or '(no subject)',
        'from': headers.get('from') or '',
        'to': headers.get('to') or '',
        'cc': headers.get('cc') or '',
        'date': headers.get('date') or '',
        'labels': label_ids,
        'unread': 'UNREAD' in label_ids,
    }
    if include_bodies:
        text_body, html_body = extract_gmail_bodies(message.get('payload') or {})
        summary['body_text'] = text_body
        summary['body_html'] = html_body
    return summary


def normalize_reply_subject(subject: str) -> str:
    value = (subject or '').strip()
    if not value:
        return 'Re:'
    return value if value.lower().startswith('re:') else f'Re: {value}'


def extract_email_address(value: str) -> str:
    text = (value or '').strip()
    if not text:
        return ''
    match = re.search(r'<([^>]+)>', text)
    if match:
        return match.group(1).strip().lower()
    if '@' in text:
        cleaned = text.replace('"', '').strip()
        return cleaned.split()[-1].strip('<>').lower()
    return ''


def inbox_zero_profile(message: dict) -> dict:
    subject = str(message.get('subject') or '')
    snippet = str(message.get('snippet') or '')
    labels = [str(label) for label in (message.get('labels') or [])]
    sender = str(message.get('from') or '')
    sender_email = extract_email_address(sender)
    sender_lower = sender.lower()
    sender_local = sender_email.split('@', 1)[0] if sender_email else ''
    subject_lower = subject.lower()
    snippet_lower = snippet.lower()
    body = f'{subject_lower} {snippet_lower}'

    category_promotional = any(label in labels for label in ('CATEGORY_PROMOTIONS', 'CATEGORY_FORUMS', 'CATEGORY_SOCIAL'))
    machine_sender = any(token in sender_lower or token in sender_local for token in ('noreply', 'no-reply', 'newsletter', 'updates', 'notification', 'alerts'))
    digest_like = any(token in body for token in ('unsubscribe', 'newsletter', 'digest', 'daily update', 'weekly update', 'promotions'))
    finance_like = any(token in body for token in ('invoice', 'receipt', 'payment', 'statement'))
    security_like = any(token in body for token in ('security alert', 'sign-in', 'signin', 'password', 'verification', 'verify', 'otp', 'fraud', 'scam'))
    action_language = any(
        token in body
        for token in (
            '?',
            'please review',
            'please approve',
            'approval',
            'can you',
            'could you',
            'need your',
            'let me know',
            'follow up',
            'request',
            'action required',
            'reply',
        )
    )
    urgent = any(token in body for token in ('urgent', 'asap', 'today', 'by eod', 'immediately'))
    finance_actionable = finance_like and action_language

    bulk = (category_promotional or digest_like or machine_sender) and not security_like and not finance_actionable
    notification = (finance_like or 'CATEGORY_UPDATES' in labels) and not action_language and not security_like
    needs_reply = bool(message.get('unread')) and not bulk and (action_language or urgent)
    if needs_reply:
        category = 'needs_reply'
        recommended_action = 'reply'
        reason = 'Unread message with human-style wording that likely needs a response.'
    elif security_like or finance_actionable:
        category = 'review'
        recommended_action = 'review'
        reason = 'Contains security or account-related details that should be reviewed before taking action.'
    elif bulk:
        category = 'bulk'
        recommended_action = 'archive'
        reason = 'Looks like a newsletter, promotion, or automated sender.'
    elif notification:
        category = 'fyi'
        recommended_action = 'mark_read' if message.get('unread') else 'keep'
        reason = 'Looks informational rather than conversational.'
    else:
        category = 'review'
        recommended_action = 'review'
        reason = 'Needs a quick review before deciding what to do.'

    return {
        'id': message.get('id'),
        'thread_id': message.get('thread_id'),
        'subject': subject,
        'from': sender,
        'date': message.get('date') or '',
        'snippet': snippet,
        'labels': labels,
        'unread': bool(message.get('unread')),
        'category': category,
        'recommended_action': recommended_action,
        'reason': reason,
        'signals': {
            'bulk': bulk,
            'notification': notification,
            'needs_reply': needs_reply,
            'urgent': urgent,
        },
    }


def inbox_zero_summary_payload(*, integration: str, query: str, unread_only: bool, messages: list[dict]) -> dict:
    analyzed = [inbox_zero_profile(message) for message in messages]
    buckets = {
        'needs_reply': [item for item in analyzed if item['category'] == 'needs_reply'],
        'bulk': [item for item in analyzed if item['category'] == 'bulk'],
        'fyi': [item for item in analyzed if item['category'] == 'fyi'],
        'review': [item for item in analyzed if item['category'] == 'review'],
    }
    return {
        'integration': integration,
        'query': query,
        'unread_only': unread_only,
        'analyzed_count': len(analyzed),
        'summary': {
            'needs_reply': len(buckets['needs_reply']),
            'clearable': len(buckets['bulk']) + len(buckets['fyi']),
            'fyi': len(buckets['fyi']),
            'review': len(buckets['review']),
            'unread': len([item for item in analyzed if item['unread']]),
        },
        'priority': {
            'needs_reply': buckets['needs_reply'][:5],
            'review': buckets['review'][:5],
            'clearable': (buckets['bulk'] + buckets['fyi'])[:10],
        },
        'messages': analyzed,
    }


async def gmail_inbox_summary(
    integration: str,
    *,
    user_id: str,
    query: str = '',
    limit: int = 25,
    unread_only: bool = False,
) -> dict:
    inbox = await gmail_search_messages(
        integration,
        user_id=user_id,
        query=query,
        limit=limit,
        unread_only=unread_only,
    )
    return inbox_zero_summary_payload(
        integration=integration,
        query=query,
        unread_only=unread_only,
        messages=inbox.get('messages') or [],
    )


async def gmail_triage_inbox(
    integration: str,
    *,
    user_id: str,
    query: str = '',
    limit: int = 25,
    unread_only: bool = False,
    apply: bool = False,
    confirm: bool = False,
) -> dict:
    summary = await gmail_inbox_summary(
        integration,
        user_id=user_id,
        query=query,
        limit=limit,
        unread_only=unread_only,
    )
    messages = summary.get('messages') or []
    archive_ids = [item['id'] for item in messages if item['recommended_action'] == 'archive' and item.get('id')]
    mark_read_ids = [item['id'] for item in messages if item['recommended_action'] == 'mark_read' and item.get('id')]

    plan = {
        'archive': archive_ids,
        'mark_read': mark_read_ids,
        'reply_first': [item['id'] for item in messages if item['recommended_action'] == 'reply' and item.get('id')],
        'review_first': [item['id'] for item in messages if item['recommended_action'] == 'review' and item.get('id')],
    }

    if apply and not confirm:
        return {
            'integration': integration,
            'status': 'confirmation_required',
            'message': 'Inbox triage found actions to apply, but confirm=false so nothing changed.',
            'plan': plan,
            'summary': summary.get('summary') or {},
        }

    applied: list[dict] = []
    if apply:
        if archive_ids:
            archived = await gmail_modify_messages(
                integration,
                user_id=user_id,
                email_ids=archive_ids,
                add_labels=[],
                remove_labels=['INBOX'],
            )
            applied.append({'action': 'archive', 'count': archived['updated_count'], 'email_ids': archive_ids})
        if mark_read_ids:
            updated = await gmail_modify_messages(
                integration,
                user_id=user_id,
                email_ids=mark_read_ids,
                add_labels=[],
                remove_labels=['UNREAD'],
            )
            applied.append({'action': 'mark_read', 'count': updated['updated_count'], 'email_ids': mark_read_ids})

    return {
        'integration': integration,
        'status': 'applied' if apply else 'planned',
        'message': 'Inbox Zero triage created a plan for reply, archive, and mark-read actions.'
        if not apply
        else 'Inbox Zero triage applied the low-risk archive and mark-read actions.',
        'plan': plan,
        'applied': applied,
        'summary': summary.get('summary') or {},
        'messages': messages,
    }


def proxy_error_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except Exception:
        data = {'message': response.text[:500]}

    error = data.get('error') if isinstance(data, dict) else None
    message = ''
    if isinstance(error, dict):
        message = str(error.get('message') or '')
        reasons = {
            str(item.get('reason') or '').lower()
            for item in (error.get('errors') or [])
            if isinstance(item, dict)
        }
        if 'accessnotconfigured' in reasons or 'service_disabled' in message.lower():
            return (
                'Gmail API is disabled for the Google Cloud project behind this OAuth app. '
                f'Enable gmail.googleapis.com in Google Cloud Console for the same project used by your Nango Gmail integration: {gmail_api_console_url()}. '
                f'The authorized redirect URI should be {gmail_oauth_callback_url()}. '
                'After enabling it, wait a minute, then retry. Do not reconnect unless you changed the OAuth app.'
            )
        if message:
            return message
    return response.text[:500] or f'Proxy request failed with status {response.status_code}'


def ensure_proxy_ok(response: httpx.Response):
    if response.status_code < 400:
        return
    detail = proxy_error_detail(response)
    status = 424 if response.status_code in (401, 403, 404) else 502
    raise HTTPException(status, detail)


def summarize_connection(integration: str, data: dict, *, user_id: str) -> dict:
    connection = (data.get('data') or {}).get('connection') or {}
    refresh_exhausted = bool(connection.get('refresh_exhausted'))
    last_refresh_failure = connection.get('last_refresh_failure')
    status = 'expired' if refresh_exhausted else 'connected'
    return {
        'integration': integration,
        'status': status,
        'connected': status == 'connected',
        'action': 'retry' if refresh_exhausted else None,
        'connection_id': connection.get('connection_id') or user_id,
        'provider_config_key': connection.get('provider_config_key') or provider_config_key(integration),
        'created_at': connection.get('created_at'),
        'updated_at': connection.get('updated_at'),
        'credentials_expires_at': connection.get('credentials_expires_at'),
        'last_refresh_failure': last_refresh_failure,
        'message': 'Connection is ready.' if status == 'connected' else 'Connection needs to be refreshed.',
    }


async def fetch_status(integration: str, *, user_id: str, user_email: str = '') -> dict:
    _ = user_email  # reserved for future connection matching / richer status messaging
    if not NANGO_SECRET_KEY:
        return {
            'integration': integration,
            'status': 'not_configured',
            'connected': False,
            'action': 'connect_integration',
            'message': 'Nango API key is not configured yet. BizGPT wiring is ready, but OAuth setup is still pending.',
            'connect_url': connect_hint(integration),
        }

    match = match_end_user_connection(await list_connections(integration), user_id=user_id)
    if not match:
        return {
            'integration': integration,
            'status': 'missing',
            'connected': False,
            'action': 'connect_integration',
            'message': 'No connection found for this user yet.',
            'connect_url': connect_hint(integration),
        }
    return summarize_connection(integration, {'data': {'connection': match}}, user_id=user_id)


async def require_connected_email(integration: str, *, user_id: str) -> tuple[str, str]:
    match = match_end_user_connection(await list_connections(integration), user_id=user_id)
    if not match:
        raise HTTPException(
            409,
            f'No {integration} connection exists for this user yet. Connect the integration first.',
        )
    return str(match.get('connection_id') or ''), provider_config_key(integration)


async def gmail_get_message(connection_id: str, provider_config_key: str, email_id: str, *, include_bodies: bool) -> dict:
    response = await nango_proxy_request(
        'GET',
        f'gmail/v1/users/me/messages/{email_id}',
        connection_id=connection_id,
        provider_config_key=provider_config_key,
        params={'format': 'full' if include_bodies else 'metadata'},
    )
    ensure_proxy_ok(response)
    return summarize_gmail_message(response.json(), include_bodies=include_bodies)


async def gmail_search_messages(
    integration: str,
    *,
    user_id: str,
    query: str = '',
    limit: int = 10,
    unread_only: bool = False,
) -> dict:
    connection_id, provider_key = await require_connected_email(integration, user_id=user_id)
    q_parts = [part.strip() for part in [query] if part and part.strip()]
    if unread_only:
        q_parts.append('is:unread')
    response = await nango_proxy_request(
        'GET',
        'gmail/v1/users/me/messages',
        connection_id=connection_id,
        provider_config_key=provider_key,
        params={
            'maxResults': max(1, min(limit, 20)),
            'labelIds': 'INBOX',
            **({'q': ' '.join(q_parts)} if q_parts else {}),
        },
    )
    ensure_proxy_ok(response)
    data = response.json()
    raw_messages = data.get('messages') or []
    details = await asyncio.gather(
        *[
            gmail_get_message(connection_id, provider_key, str(item.get('id') or ''), include_bodies=False)
            for item in raw_messages
            if item.get('id')
        ]
    )
    return {
        'integration': integration,
        'connected': True,
        'query': query,
        'unread_only': unread_only,
        'count': len(details),
        'messages': details,
    }


async def gmail_modify_messages(integration: str, *, user_id: str, email_ids: list[str], add_labels: list[str], remove_labels: list[str]) -> dict:
    connection_id, provider_key = await require_connected_email(integration, user_id=user_id)
    clean_ids = [email_id for email_id in email_ids if email_id]
    if not clean_ids:
        raise HTTPException(400, 'email_ids must contain at least one message id')
    response = await nango_proxy_request(
        'POST',
        'gmail/v1/users/me/messages/batchModify',
        connection_id=connection_id,
        provider_config_key=provider_key,
        body={
            'ids': clean_ids,
            'addLabelIds': add_labels,
            'removeLabelIds': remove_labels,
        },
    )
    ensure_proxy_ok(response)
    return {'integration': integration, 'updated_count': len(clean_ids), 'email_ids': clean_ids}


async def gmail_reply_to_message(
    integration: str,
    *,
    user_id: str,
    email_id: str,
    body: str,
    user_email: str = '',
    reply_all: bool = False,
) -> dict:
    connection_id, provider_key = await require_connected_email(integration, user_id=user_id)
    source_response = await nango_proxy_request(
        'GET',
        f'gmail/v1/users/me/messages/{email_id}',
        connection_id=connection_id,
        provider_config_key=provider_key,
        params={'format': 'metadata', 'metadataHeaders': ['From', 'To', 'Cc', 'Subject', 'Message-ID', 'References']},
    )
    ensure_proxy_ok(source_response)
    source = source_response.json()
    headers = gmail_header_map(source)

    recipient_to = headers.get('reply-to') or headers.get('from') or ''
    if not recipient_to:
        raise HTTPException(400, 'Could not determine the recipient for this reply.')

    message = EmailMessage()
    if user_email:
        message['From'] = user_email
    message['To'] = recipient_to
    if reply_all and headers.get('cc'):
        message['Cc'] = headers.get('cc')
    message['Subject'] = normalize_reply_subject(headers.get('subject') or '')
    if headers.get('message-id'):
        message['In-Reply-To'] = headers['message-id']
        refs = ' '.join(part for part in [headers.get('references') or '', headers['message-id']] if part).strip()
        if refs:
            message['References'] = refs
    message.set_content(body.strip())

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip('=')
    send_response = await nango_proxy_request(
        'POST',
        'gmail/v1/users/me/messages/send',
        connection_id=connection_id,
        provider_config_key=provider_key,
        body={'raw': raw, 'threadId': source.get('threadId')},
    )
    ensure_proxy_ok(send_response)
    sent = send_response.json()
    return {
        'integration': integration,
        'status': 'sent',
        'message_id': sent.get('id'),
        'thread_id': sent.get('threadId') or source.get('threadId'),
        'replied_to': email_id,
    }


@app.get('/health')
def health():
    return {
        'status': 'ok',
        'nango_server_url': NANGO_SERVER_URL,
        'nango_env': NANGO_ENV,
        'nango_api_ready': bool(NANGO_SECRET_KEY),
        'supported_integrations': sorted(SUPPORTED_INTEGRATIONS),
        'gmail_setup': gmail_setup_checklist(),
    }


@app.get('/api/integrations/setup', dependencies=[Depends(require_api_key)])
async def get_integration_setup(integration: str = 'gmail'):
    name = integration.strip().lower()
    provider_config_key(name)
    if name != 'gmail':
        raise HTTPException(400, 'Only Gmail setup guidance is available right now.')
    return {
        'integration': name,
        'message': 'These are the required Gmail setup details BizGPT expects in env-backed configuration.',
        'items': gmail_setup_checklist(),
    }


@app.get('/api/integrations/status', dependencies=[Depends(require_api_key)])
async def get_integration_status(integration: Optional[str] = None, user_id: str = '', user_email: str = ''):
    if not user_id:
        raise HTTPException(400, 'user_id is required')
    if integration:
        return await fetch_status(integration, user_id=user_id, user_email=user_email)
    return {
        'items': [await fetch_status(name, user_id=user_id, user_email=user_email) for name in sorted(SUPPORTED_INTEGRATIONS)],
    }


@app.post('/api/emails/search', dependencies=[Depends(require_api_key)])
async def search_emails(req: SearchEmailsRequest):
    integration = req.integration.strip().lower()
    if integration != 'gmail':
        raise HTTPException(400, 'Only Gmail is supported right now.')
    return await gmail_search_messages(
        integration,
        user_id=req.user_id,
        query=req.query,
        limit=req.limit,
        unread_only=req.unread_only,
    )


@app.post('/api/inbox/summary', dependencies=[Depends(require_api_key)])
async def get_inbox_summary(req: InboxSummaryRequest):
    integration = req.integration.strip().lower()
    if integration != 'gmail':
        raise HTTPException(400, 'Only Gmail is supported right now.')
    return await gmail_inbox_summary(
        integration,
        user_id=req.user_id,
        query=req.query,
        limit=req.limit,
        unread_only=req.unread_only,
    )


@app.post('/api/inbox/triage', dependencies=[Depends(require_api_key)])
async def triage_inbox(req: TriageInboxRequest):
    integration = req.integration.strip().lower()
    if integration != 'gmail':
        raise HTTPException(400, 'Only Gmail is supported right now.')
    return await gmail_triage_inbox(
        integration,
        user_id=req.user_id,
        query=req.query,
        limit=req.limit,
        unread_only=req.unread_only,
        apply=req.apply,
        confirm=req.confirm,
    )


@app.get('/api/emails/{email_id}', dependencies=[Depends(require_api_key)])
async def get_email(email_id: str, user_id: str = '', integration: str = 'gmail'):
    if not user_id:
        raise HTTPException(400, 'user_id is required')
    integration = integration.strip().lower()
    if integration != 'gmail':
        raise HTTPException(400, 'Only Gmail is supported right now.')
    connection_id, provider_key = await require_connected_email(integration, user_id=user_id)
    return await gmail_get_message(connection_id, provider_key, email_id, include_bodies=True)


@app.post('/api/emails/mark', dependencies=[Depends(require_api_key)])
async def mark_emails(req: MarkEmailRequest):
    integration = req.integration.strip().lower()
    if integration != 'gmail':
        raise HTTPException(400, 'Only Gmail is supported right now.')
    result = await gmail_modify_messages(
        integration,
        user_id=req.user_id,
        email_ids=req.email_ids,
        add_labels=[] if req.read else ['UNREAD'],
        remove_labels=['UNREAD'] if req.read else [],
    )
    return {
        **result,
        'status': 'updated',
        'read': req.read,
        'message': f'Marked {result["updated_count"]} email(s) as {"read" if req.read else "unread"}.',
    }


@app.post('/api/emails/archive', dependencies=[Depends(require_api_key)])
async def archive_emails(req: ArchiveEmailRequest):
    integration = req.integration.strip().lower()
    if integration != 'gmail':
        raise HTTPException(400, 'Only Gmail is supported right now.')
    result = await gmail_modify_messages(
        integration,
        user_id=req.user_id,
        email_ids=req.email_ids,
        add_labels=[],
        remove_labels=['INBOX'],
    )
    return {
        **result,
        'status': 'archived',
        'message': f'Archived {result["updated_count"]} email(s).',
    }


@app.post('/api/emails/reply', dependencies=[Depends(require_api_key)])
async def reply_email(req: ReplyEmailRequest):
    integration = req.integration.strip().lower()
    if integration != 'gmail':
        raise HTTPException(400, 'Only Gmail is supported right now.')
    if not req.confirm:
        return {
            'integration': integration,
            'status': 'confirmation_required',
            'message': 'Reply was not sent because confirm=false.',
        }
    return await gmail_reply_to_message(
        integration,
        user_id=req.user_id,
        email_id=req.email_id,
        body=req.body,
        user_email=req.user_email,
        reply_all=req.reply_all,
    )


@app.post('/api/integrations/connect', dependencies=[Depends(require_api_key)])
async def connect_integration(req: ConnectRequest):
    integration = req.integration.strip().lower()
    key = provider_config_key(integration)
    if not NANGO_SECRET_KEY:
        return {
            'integration': integration,
            'status': 'not_configured',
            'connect_url': connect_hint(integration),
            'message': 'Nango API key is not configured yet. Open Nango and finish the integration setup first.',
        }

    response = await nango_request(
        'POST',
        '/connect/sessions',
        body={
            'end_user': {
                'id': req.user_id,
                **({'email': normalize_end_user_email(req.user_email)} if normalize_end_user_email(req.user_email) else {}),
            },
            'allowed_integrations': [key],
        },
    )
    payload = response.json()
    if response.status_code == 400:
        return {
            'integration': integration,
            'status': 'needs_setup',
            'connect_url': connect_hint(integration),
            'message': 'Nango could not create a connect session yet. Create the integration config in Nango first.',
            'details': payload,
        }
    if response.status_code >= 400:
        raise HTTPException(502, f'Nango connect session failed ({response.status_code}): {payload}')

    data = payload.get('data') or {}
    token = data.get('token')
    return {
        'integration': integration,
        'status': 'connect_ready',
        'token': token,
        'connect_url': with_connect_api_url(data.get('connect_link') or f'{NANGO_PUBLIC_CONNECT_URL}/'),
        'connect_embed_url': connect_embed_url(integration, token),
        'expires_at': data.get('expires_at'),
        'message': 'Open the connect URL to finish authorization.',
    }


@app.get('/public/connect/{integration}', response_class=HTMLResponse)
async def public_connect_page(integration: str, session_token: str = ''):
    integration = integration.strip().lower()
    provider_config_key(integration)
    token = session_token.strip()
    if not token:
        raise HTTPException(400, 'session_token is required')
    connect_url = with_connect_api_url(f'{NANGO_PUBLIC_CONNECT_URL}/?session_token={token}')
    return HTMLResponse(connect_page_html(integration, connect_url))


@app.delete('/api/integrations/disconnect', dependencies=[Depends(require_api_key)])
async def disconnect_integration(req: DisconnectRequest):
    integration = req.integration.strip().lower()
    match = match_end_user_connection(await list_connections(integration), user_id=req.user_id)
    if not match:
        return {'integration': integration, 'status': 'missing', 'message': 'No connection existed for this user.'}
    response = await nango_request('DELETE', f"/connections/{match.get('connection_id')}")
    if response.status_code >= 400:
        raise HTTPException(502, f'Nango disconnect failed ({response.status_code}): {response.text[:400]}')
    return {'integration': integration, 'status': 'disconnected', 'message': 'Connection removed.'}
