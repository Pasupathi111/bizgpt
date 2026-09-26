"""
title: Biz GPT Integrations
author: Biz GPT
description: Checks integration status, opens embedded OAuth flows, and performs Gmail mailbox actions through Biz GPT-managed integrations.
"""

import json
from typing import Optional

import aiohttp
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        INTEGRATIONS_API_URL: str = Field(
            default='http://bizgpt-integrations:8002',
            description='Integrations service URL as seen from the Biz GPT server',
        )
        INTEGRATIONS_PUBLIC_URL: str = Field(
            default='http://localhost:8092',
            description='Integrations service URL as seen from the user browser for embedded OAuth flows',
        )
        INTEGRATIONS_API_KEY: str = Field(default='', description='Bearer key for the integrations service internal API')
        FORMS_API_URL: str = Field(
            default='http://bizgpt-forms:8000',
            description='Forms service URL as seen from the Biz GPT server',
        )
        FORMS_PUBLIC_URL: str = Field(
            default='http://localhost:8090',
            description='Forms service URL as seen from the user browser for rendered JSON views',
        )
        FORMS_API_KEY: str = Field(default='', description='Bearer key for the forms service internal API')

    def __init__(self):
        self.valves = self.Valves()

    async def get_integration_status(self, integration: Optional[str] = None, __user__: Optional[dict] = None) -> str:
        """
        Check whether the current user has connected an integration such as Gmail.
        :param integration: Optional integration id such as "gmail". If omitted, returns all supported integrations.
        """
        user = __user__ or {}
        query = {'user_id': user.get('id') or '', 'user_email': user.get('email') or ''}
        if integration:
            query['integration'] = integration
        data = await self._api('GET', '/api/integrations/status', query=query)
        return json.dumps(data)

    async def get_integration_setup(self, integration: str = 'gmail') -> str:
        """
        Show the env-backed setup checklist for an integration.
        Use this when configuration is incomplete or an external provider reports a setup error.
        :param integration: Integration id such as "gmail".
        """
        data = await self._api('GET', '/api/integrations/setup', query={'integration': integration})
        return json.dumps(data)

    async def connect_integration(
        self,
        integration: str,
        __user__: Optional[dict] = None,
        __event_emitter__=None,
    ) -> str:
        """
        Create a Nango connect link for the current user so they can authorize an integration.
        :param integration: Integration id such as "gmail".
        """
        user = __user__ or {}
        data = await self._api(
            'POST',
            '/api/integrations/connect',
            body={
                'integration': integration,
                'user_id': user.get('id') or '',
                'user_email': user.get('email') or '',
                'user_name': user.get('name') or '',
            },
        )

        embed_url = data.get('connect_embed_url')
        connect_url = data.get('connect_url')

        if embed_url and __event_emitter__:
            await __event_emitter__(
                {
                    'type': 'embeds',
                    'data': {
                        'embeds': [embed_url],
                    },
                }
            )

        if embed_url and __event_emitter__:
            # Optional right-side panel access without exposing the raw Nango URL in chat.
            await __event_emitter__(
                {
                    'type': 'source',
                    'data': {
                        'source': {'name': f'Connect {integration.title()}', 'embed_url': embed_url},
                        'document': [data.get('message') or 'Finish authorization in the embedded panel.'],
                        'metadata': [{'source': f'bizgpt://integrations/{integration}/connect'}],
                    },
                }
            )

        if embed_url:
            context = {
                'integration': integration,
                'status': data.get('status'),
                'embedded': True,
                'expires_at': data.get('expires_at'),
                'message': f'The {integration.title()} authorization panel is displayed in chat.',
                'instructions': 'The OAuth panel is already visible to the user in chat. Tell them to complete authorization in that panel. Do not mention any URL, browser address, or link text, and do not repeat any raw URL.',
            }
            return HTMLResponse(content=embed_url, headers={'Content-Disposition': 'inline'}), context

        fallback = {
            'integration': integration,
            'status': data.get('status'),
            'embedded': False,
            'message': data.get('message') or 'Open the connection flow to continue.',
            'instructions': 'Ask the user to use the connection flow, but do not expose internal URLs unless absolutely necessary.',
        }
        if connect_url:
            fallback['open_in_browser'] = self.valves.INTEGRATIONS_PUBLIC_URL.rstrip('/')
        return json.dumps(fallback)

    async def search_emails(
        self,
        query: str = '',
        limit: int = 10,
        unread_only: bool = False,
        account: str = 'gmail',
        __user__: Optional[dict] = None,
        __event_emitter__=None,
    ) -> str:
        """
        Search or list emails for the current user.
        Use this for requests like "show my latest Gmail messages" or "show unread emails".
        :param query: Optional Gmail-style search text.
        :param limit: Maximum number of messages to return, up to 20.
        :param unread_only: If true, only return unread emails.
        :param account: Email integration id. Use "gmail".
        """
        user = __user__ or {}
        return await self._email_api_or_setup(
            'POST',
            '/api/emails/search',
            account=account,
            __event_emitter__=__event_emitter__,
            body={
                'integration': account,
                'user_id': user.get('id') or '',
                'query': query or '',
                'limit': limit,
                'unread_only': unread_only,
            },
        )

    async def get_inbox_summary(
        self,
        query: str = '',
        limit: int = 25,
        unread_only: bool = False,
        account: str = 'gmail',
        __user__: Optional[dict] = None,
        __event_emitter__=None,
    ) -> str:
        """
        Summarize the current inbox using Biz GPT-native Inbox Zero heuristics.
        Use this for requests like "summarize my inbox" or "what needs a reply?"
        :param query: Optional Gmail-style search text.
        :param limit: Maximum number of inbox messages to analyze, up to 25.
        :param unread_only: If true, only analyze unread inbox messages.
        :param account: Email integration id. Use "gmail".
        """
        user = __user__ or {}
        return await self._email_api_or_setup(
            'POST',
            '/api/inbox/summary',
            account=account,
            __event_emitter__=__event_emitter__,
            body={
                'integration': account,
                'user_id': user.get('id') or '',
                'query': query or '',
                'limit': limit,
                'unread_only': unread_only,
            },
        )

    async def triage_inbox(
        self,
        query: str = '',
        limit: int = 25,
        unread_only: bool = False,
        apply: bool = False,
        confirm: bool = False,
        account: str = 'gmail',
        __user__: Optional[dict] = None,
        __event_emitter__=None,
    ) -> str:
        """
        Create or apply an Inbox Zero triage plan for the current inbox.
        Use apply=true only when the user explicitly asked to archive or mark-read the suggested low-risk emails.
        :param query: Optional Gmail-style search text.
        :param limit: Maximum number of inbox messages to analyze, up to 25.
        :param unread_only: If true, only analyze unread inbox messages.
        :param apply: If true, apply the low-risk archive and mark-read actions.
        :param confirm: Safety flag for apply actions. Keep true only when the user explicitly confirmed the change.
        :param account: Email integration id. Use "gmail".
        """
        user = __user__ or {}
        return await self._email_api_or_setup(
            'POST',
            '/api/inbox/triage',
            account=account,
            __event_emitter__=__event_emitter__,
            body={
                'integration': account,
                'user_id': user.get('id') or '',
                'query': query or '',
                'limit': limit,
                'unread_only': unread_only,
                'apply': apply,
                'confirm': confirm,
            },
        )

    async def get_email(
        self,
        email_id: str,
        account: str = 'gmail',
        __user__: Optional[dict] = None,
        __event_emitter__=None,
    ) -> str:
        """
        Get one email with its subject, sender, date, snippet, and body.
        :param email_id: Gmail message id returned by search_emails.
        :param account: Email integration id. Use "gmail".
        """
        user = __user__ or {}
        return await self._email_api_or_setup(
            'GET',
            f'/api/emails/{email_id}',
            account=account,
            __event_emitter__=__event_emitter__,
            query={'integration': account, 'user_id': user.get('id') or ''},
        )

    async def mark_email(
        self,
        email_ids: list[str],
        read: bool,
        account: str = 'gmail',
        __user__: Optional[dict] = None,
        __event_emitter__=None,
    ) -> str:
        """
        Mark one or more emails as read or unread.
        :param email_ids: Message ids returned by search_emails.
        :param read: True marks as read, false marks as unread.
        :param account: Email integration id. Use "gmail".
        """
        user = __user__ or {}
        return await self._email_api_or_setup(
            'POST',
            '/api/emails/mark',
            account=account,
            __event_emitter__=__event_emitter__,
            body={
                'integration': account,
                'user_id': user.get('id') or '',
                'email_ids': email_ids,
                'read': read,
            },
        )

    async def archive_email(
        self,
        email_ids: list[str],
        account: str = 'gmail',
        __user__: Optional[dict] = None,
        __event_emitter__=None,
    ) -> str:
        """
        Archive one or more emails by removing the Inbox label.
        :param email_ids: Message ids returned by search_emails.
        :param account: Email integration id. Use "gmail".
        """
        user = __user__ or {}
        return await self._email_api_or_setup(
            'POST',
            '/api/emails/archive',
            account=account,
            __event_emitter__=__event_emitter__,
            body={
                'integration': account,
                'user_id': user.get('id') or '',
                'email_ids': email_ids,
            },
        )

    async def reply_email(
        self,
        email_id: str,
        body: str,
        reply_all: bool = False,
        confirm: bool = True,
        account: str = 'gmail',
        __user__: Optional[dict] = None,
        __event_emitter__=None,
    ) -> str:
        """
        Reply to an existing email thread.
        :param email_id: Message id returned by search_emails.
        :param body: Plain text reply body.
        :param reply_all: If true, keep the original CC recipients.
        :param confirm: Safety flag for send actions. Keep true when the user explicitly asked to reply.
        :param account: Email integration id. Use "gmail".
        """
        user = __user__ or {}
        return await self._email_api_or_setup(
            'POST',
            '/api/emails/reply',
            account=account,
            __event_emitter__=__event_emitter__,
            body={
                'integration': account,
                'user_id': user.get('id') or '',
                'user_email': user.get('email') or '',
                'email_id': email_id,
                'body': body,
                'reply_all': reply_all,
                'confirm': confirm,
            },
        )

    async def _email_api_or_setup(
        self,
        method: str,
        path: str,
        *,
        account: str,
        __event_emitter__=None,
        body: Optional[dict] = None,
        query: Optional[dict] = None,
    ) -> str:
        try:
            data = await self._api(method, path, body=body, query=query)
            view = await self._create_json_view(
                __event_emitter__,
                title=f'{account.title()} output',
                description='Structured integration data rendered as a dynamic JSON view.',
                data=data if isinstance(data, dict) else {'result': data},
            )
            if view:
                return (
                    HTMLResponse(
                        content=self._json_view_embed_html(view['public_url'], f'{account.title()} output'),
                        headers={'Content-Disposition': 'inline'},
                    ),
                    {
                        'integration': account,
                        'status': 'json_view_displayed',
                        'count': data.get('count') if isinstance(data, dict) else None,
                        'instructions': 'The dynamic JSON panel is already visible in chat. Use it as the primary output and give only a short human summary.',
                    },
                )
            return json.dumps(data)
        except RuntimeError as exc:
            detail = str(exc)
            setup_markers = (
                'Gmail API is disabled',
                'Google Cloud Console',
                'connect the integration first',
                'not configured',
                'confirmation_required',
            )
            if account == 'gmail' and any(marker in detail for marker in setup_markers):
                try:
                    setup = await self._api('GET', '/api/integrations/setup', query={'integration': account})
                except Exception:
                    setup = None
                setup_payload = {
                    'integration': account,
                    'status': 'setup_required',
                    'message': detail,
                    'required_setup': setup.get('items') if isinstance(setup, dict) else None,
                    'instructions': 'Show the required setup list clearly. Do not ask the user to reconnect unless they changed the OAuth app or the connection is missing.',
                }
                view = await self._create_json_view(
                    __event_emitter__,
                    title=f'{account.title()} setup required',
                    description='Required configuration rendered as a dynamic JSON view.',
                    data=setup_payload,
                )
                if view:
                    return (
                        HTMLResponse(
                            content=self._json_view_embed_html(view['public_url'], f'{account.title()} setup required'),
                            headers={'Content-Disposition': 'inline'},
                        ),
                        {
                            'integration': account,
                            'status': 'setup_required',
                            'instructions': 'The setup checklist is already visible in chat. Explain the blocker briefly and do not ask the user to reconnect unless the OAuth app changed.',
                        },
                    )
                return json.dumps(
                    setup_payload
                )
            raise

    async def _create_json_view(self, event_emitter, *, title: str, description: str, data: dict) -> Optional[dict]:
        try:
            view = await self._forms_api(
                'POST',
                '/api/views',
                body={'title': title, 'description': description, 'data': data},
            )
        except Exception:
            return None
        public_url = f'{self.valves.FORMS_PUBLIC_URL.rstrip("/")}/v/{view["view_id"]}'
        if event_emitter:
            await event_emitter(
                {
                    'type': 'source',
                    'data': {
                        'source': {'name': title, 'embed_url': public_url},
                        'document': [description],
                        'metadata': [{'source': public_url}],
                    },
                }
            )
        return {'view_id': view['view_id'], 'public_url': public_url}

    def _json_view_embed_html(self, public_url: str, title: str) -> str:
        safe_url = public_url.replace('&', '&amp;').replace('"', '&quot;')
        safe_title = title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        return f"""
<!doctype html>
<html>
  <body style="margin:0;background:#f8fafc;font-family:Inter,Arial,sans-serif;">
    <div style="border:1px solid #e2e8f0;border-radius:16px;overflow:hidden;background:#fff;">
      <div style="padding:12px 16px;border-bottom:1px solid #e2e8f0;background:#f8fafc;">
        <div style="font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#475569;">Dynamic JSON Output</div>
        <div style="margin-top:4px;font-size:16px;font-weight:600;color:#0f172a;">{safe_title}</div>
      </div>
      <iframe
        src="{safe_url}"
        title="{safe_title}"
        style="display:block;width:100%;height:920px;border:0;background:#fff;"
        referrerpolicy="strict-origin-when-cross-origin"
      ></iframe>
    </div>
    <script>
      const reportHeight = () => {{
        const h = Math.max(document.documentElement.scrollHeight || 0, document.body.scrollHeight || 0, 980);
        window.parent?.postMessage({{ type: 'iframe:height', height: h }}, '*');
      }};
      window.addEventListener('load', reportHeight);
      new ResizeObserver(reportHeight).observe(document.body);
    </script>
  </body>
</html>
        """

    async def _api(self, method: str, path: str, body: Optional[dict] = None, query: Optional[dict] = None):
        url = self.valves.INTEGRATIONS_API_URL.rstrip('/') + path
        headers = {'Authorization': f'Bearer {self.valves.INTEGRATIONS_API_KEY}'}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.request(method, url, params=query, json=body, headers=headers) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RuntimeError(f'Integrations service error {resp.status}: {data}')
                return data

    async def _forms_api(self, method: str, path: str, body: Optional[dict] = None):
        url = self.valves.FORMS_API_URL.rstrip('/') + path
        headers = {'Authorization': f'Bearer {self.valves.FORMS_API_KEY}'}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.request(method, url, json=body, headers=headers) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RuntimeError(f'Forms service error {resp.status}: {data}')
                return data
