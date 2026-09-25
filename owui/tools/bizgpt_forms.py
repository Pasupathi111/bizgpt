"""
title: Biz GPT Dynamic Forms
author: Biz GPT
description: Shows prefilled, validated business forms (cab booking, leave, IT tickets…) inside the chat. Forms are served by the Biz GPT forms service.
"""

import json
from datetime import datetime
from typing import Optional

import aiohttp
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        FORMS_API_URL: str = Field(
            default='http://bizgpt-forms:8000',
            description='Forms service URL as seen from the Open WebUI server',
        )
        FORMS_PUBLIC_URL: str = Field(
            default='http://localhost:8090',
            description="Forms service URL as seen from the user's browser (used for the embedded form)",
        )
        FORMS_API_KEY: str = Field(default='', description='Bearer key for the forms service internal API')
        SIDE_PANEL_LINK: bool = Field(default=True, description='Also attach the form as a source, so it can be opened in the right-side panel')

    def __init__(self):
        self.valves = self.Valves()

    async def list_form_types(self) -> str:
        """
        List the business forms Biz GPT can open, with their fields. Call this first whenever the user
        wants to request, book, apply for, report or submit something, to pick the right form and
        extract field values from the user's message.
        """
        types = await self._api('GET', '/api/form-types')
        return json.dumps(
            {
                'now': datetime.now().strftime('%Y-%m-%d %H:%M (%A)'),
                'instructions': 'Pick the best form_type, extract every field value the user already gave '
                '(resolve relative dates like "tomorrow" using "now"; dates YYYY-MM-DD, times HH:MM 24h), '
                'then call open_form. Do not ask for missing fields in text; the form collects them.',
                'form_types': types,
            }
        )

    async def open_form(
        self,
        form_type: str,
        prefill: Optional[dict] = None,
        __user__: Optional[dict] = None,
        __metadata__: Optional[dict] = None,
        __event_emitter__=None,
    ):
        """
        Show a form to the user inside the chat, prefilled with the values extracted from their message.
        The user completes, reviews and confirms it themselves.
        :param form_type: The form type id from list_form_types, e.g. "cab_booking".
        :param prefill: Field values already known, keyed by field name, e.g. {"pickup_date": "2026-09-26", "pickup_time": "10:00"}.
        """
        if isinstance(prefill, str):
            try:
                prefill = json.loads(prefill)
            except json.JSONDecodeError:
                prefill = {}
        context = {
            'user_id': (__user__ or {}).get('id'),
            'user_email': (__user__ or {}).get('email'),
            'chat_id': (__metadata__ or {}).get('chat_id'),
        }
        form = await self._api('POST', '/api/forms', {'form_type': form_type, 'prefill': prefill or {}, 'context': context})
        public_url = f'{self.valves.FORMS_PUBLIC_URL.rstrip("/")}/f/{form["form_id"]}'

        if __event_emitter__:
            # Attach the form directly to the assistant message so it is visible
            # in chat immediately instead of being hidden inside the tool trace.
            await __event_emitter__(
                {
                    'type': 'embeds',
                    'data': {
                        'embeds': [public_url],
                    },
                }
            )

        if self.valves.SIDE_PANEL_LINK and __event_emitter__:
            # A source with embed_url shows as a chip under the reply; clicking it opens
            # the same live form in Open WebUI's right-side panel.
            await __event_emitter__(
                {
                    'type': 'source',
                    'data': {
                        'source': {'name': f'📝 {form_type.replace("_", " ").title()} form', 'embed_url': public_url},
                        'document': ['Interactive form. Open it to complete and submit.'],
                        'metadata': [{'source': public_url}],
                    },
                }
            )

        context_for_llm = {
            'status': 'form_displayed',
            'form_id': form['form_id'],
            'prefilled': form['prefill'],
            'missing_fields': form['missing_fields'],
            'rejected_prefill': form.get('prefill_rejected', []),
            'instructions': 'The form is visible to the user now. In one or two short sentences, say what you '
            'prefilled and which fields they still need to fill in, then stop. Do not repeat the form as text. '
            'When the user reports it was submitted, confirm using the reference number.',
        }
        return HTMLResponse(content=public_url, headers={'Content-Disposition': 'inline'}), context_for_llm

    async def get_form_status(self, form_id: str) -> str:
        """
        Check a form's status (draft, submitted, executed, expired) and its submitted values and result.
        :param form_id: The form_id returned by open_form.
        """
        return json.dumps(await self._api('GET', f'/api/forms/{form_id}'))

    async def _api(self, method: str, path: str, body: Optional[dict] = None):
        url = self.valves.FORMS_API_URL.rstrip('/') + path
        headers = {'Authorization': f'Bearer {self.valves.FORMS_API_KEY}'}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.request(method, url, json=body, headers=headers) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RuntimeError(f'Forms service error {resp.status}: {data}')
                return data
