"""
title: Biz GPT Form Builder
author: Biz GPT
description: Admins create, preview, update and delete dynamic forms from chat. Saved forms appear immediately in every model that uses Biz GPT Dynamic Forms.
"""

import json
import re
from typing import Optional

import aiohttp
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# Simple field types the model can use -> (JSON schema, ui schema)
FIELD_TYPES = {
    'text': ({'type': 'string'}, {}),
    'textarea': ({'type': 'string'}, {'ui:widget': 'textarea', 'ui:options': {'rows': 3}}),
    'email': ({'type': 'string', 'format': 'email'}, {}),
    'phone': ({'type': 'string', 'pattern': '^[+0-9 ()-]{7,20}$'}, {}),
    'number': ({'type': 'number'}, {}),
    'integer': ({'type': 'integer'}, {}),
    'date': ({'type': 'string', 'format': 'date'}, {}),
    'time': ({'type': 'string', 'pattern': '^([01][0-9]|2[0-3]):[0-5][0-9]$', 'description': '24h HH:MM'}, {'ui:widget': 'time'}),
    'select': ({'type': 'string'}, {}),
    'checkbox': ({'type': 'boolean'}, {}),
}


def build_definition(form_id, title, description, fields, keywords, reference_prefix, success_message, submit_label):
    if isinstance(fields, str):
        fields = json.loads(fields)
    if not isinstance(fields, list) or not fields:
        raise ValueError('fields must be a non-empty list')
    properties, required, ui = {}, [], {'ui:order': []}
    for field in fields:
        name = re.sub(r'[^a-z0-9_]+', '_', str(field.get('name') or field.get('title') or '').strip().lower()).strip('_')
        if not name:
            raise ValueError(f'field without a name: {field}')
        kind = field.get('type', 'text')
        if kind not in FIELD_TYPES:
            raise ValueError(f'field {name!r}: type must be one of {sorted(FIELD_TYPES)}')
        schema, ui_field = (dict(part) for part in FIELD_TYPES[kind])
        schema['title'] = field.get('title') or name.replace('_', ' ').capitalize()
        if field.get('description'):
            schema['description'] = field['description']
        if kind == 'select':
            options = [str(o) for o in field.get('options') or []]
            if len(options) < 2:
                raise ValueError(f'select field {name!r} needs at least 2 options')
            schema['enum'] = options
        for key in ('minimum', 'maximum'):
            if field.get(key) is not None and kind in ('number', 'integer'):
                schema[key] = field[key]
        if field.get('max_length') and schema['type'] == 'string':
            schema['maxLength'] = int(field['max_length'])
        if field.get('default') is not None:
            schema['default'] = field['default']
        if field.get('placeholder'):
            ui_field['ui:placeholder'] = field['placeholder']
        properties[name] = schema
        ui['ui:order'].append(name)
        if ui_field:
            ui[name] = ui_field
        if field.get('required'):
            required.append(name)
    prefix = re.sub(r'[^A-Z0-9]', '', (reference_prefix or form_id[:3]).upper())[:6] or 'REF'
    return {
        'id': form_id,
        'title': title,
        'description': description,
        'keywords': keywords or [],
        'schema': {'type': 'object', 'required': required, 'properties': properties},
        'ui_schema': ui,
        'action': {'type': 'record', 'reference_prefix': prefix},
        'submit_label': submit_label or 'Submit',
        'success_message': success_message or f'{title} submitted. Reference {{reference}}.',
    }


class Tools:
    class Valves(BaseModel):
        FORMS_API_URL: str = Field(default='http://bizgpt-forms:8000', description='Forms service URL as seen from the Biz GPT server')
        FORMS_PUBLIC_URL: str = Field(default='http://localhost:8090', description="Forms service URL as seen from the user's browser")
        FORMS_API_KEY: str = Field(default='', description='Bearer key for the forms service internal API')
        ADMIN_ONLY: bool = Field(default=True, description='Only Biz GPT admins may create, change or delete forms')

    def __init__(self):
        self.valves = self.Valves()

    async def list_forms(self) -> str:
        """
        List every dynamic form (built-in and custom) with its id, title and fields.
        """
        types = await self._api('GET', '/api/form-types')
        return json.dumps(
            [{'id': t['id'], 'title': t['title'], 'source': t.get('source'), 'fields': [f['name'] for f in t['fields']]} for t in types]
        )

    async def get_form(self, form_id: str) -> str:
        """
        Get the full definition of one form.
        :param form_id: Form id, e.g. "gym_membership".
        """
        return json.dumps(await self._api('GET', f'/api/form-types/{form_id}'))

    async def save_form(
        self,
        form_id: str,
        title: str,
        description: str,
        fields: list[dict],
        keywords: Optional[list[str]] = None,
        reference_prefix: Optional[str] = None,
        success_message: Optional[str] = None,
        submit_label: Optional[str] = None,
        __user__: Optional[dict] = None,
    ) -> str:
        """
        Create a new custom form, or replace an existing custom form with the same id. Only call this after
        the user has confirmed the field list. Built-in forms cannot be changed.
        :param form_id: Lowercase id with underscores, 3-50 chars, e.g. "gym_membership".
        :param title: Form title shown to users, e.g. "Gym membership".
        :param description: One sentence on what the form is for; the assistant uses it to pick the form.
        :param fields: Ordered list of fields. Each field: {"name": "start_date", "title": "Start date", "type": one of text|textarea|email|phone|number|integer|date|time|select|checkbox, "required": true/false, "options": ["A","B"] (select only), "default": value, "minimum"/"maximum" (numbers), "max_length", "placeholder", "description"}.
        :param keywords: Words users might say that should open this form, e.g. ["gym", "fitness", "membership"].
        :param reference_prefix: 2-6 uppercase letters for reference numbers, e.g. "GYM".
        :param success_message: Message after submit; may use {field_name} and {reference} placeholders.
        :param submit_label: Submit button text, default "Submit".
        """
        self._require_admin(__user__)
        definition = build_definition(form_id, title, description, fields, keywords, reference_prefix, success_message, submit_label)
        saved = await self._api('PUT', f'/api/form-types/{form_id}', definition)
        return json.dumps(
            {
                'status': 'saved',
                'form_id': saved['id'],
                'fields': list(saved['schema']['properties']),
                'required': saved['schema'].get('required', []),
                'instructions': 'Tell the user the form is live for every model with Biz GPT Dynamic Forms. '
                'Offer to preview it with preview_form.',
            }
        )

    async def preview_form(
        self,
        form_id: str,
        prefill: Optional[dict] = None,
        __user__: Optional[dict] = None,
        __metadata__: Optional[dict] = None,
        __event_emitter__=None,
    ):
        """
        Show a form in the chat exactly as users will see it.
        :param form_id: Form id to preview.
        :param prefill: Optional sample values keyed by field name.
        """
        context = {'user_id': (__user__ or {}).get('id'), 'chat_id': (__metadata__ or {}).get('chat_id'), 'preview': True}
        form = await self._api('POST', '/api/forms', {'form_type': form_id, 'prefill': prefill or {}, 'context': context})
        public_url = f'{self.valves.FORMS_PUBLIC_URL.rstrip("/")}/f/{form["form_id"]}'
        context_for_llm = {
            'status': 'preview_displayed',
            'instructions': 'The preview is visible. Ask if any field should change; if so call save_form again.',
        }
        if __event_emitter__:
            # Embedded in the message; an inline tool result would render it a second time.
            await __event_emitter__({'type': 'embeds', 'data': {'embeds': [public_url]}})
            return json.dumps(context_for_llm)
        return HTMLResponse(content=public_url, headers={'Content-Disposition': 'inline'}), context_for_llm

    async def delete_form(self, form_id: str, confirm: bool = False, __user__: Optional[dict] = None) -> str:
        """
        Delete a custom form. Built-in forms cannot be deleted.
        :param form_id: Form id to delete.
        :param confirm: Must be true, and only after the user explicitly confirmed the deletion.
        """
        self._require_admin(__user__)
        if not confirm:
            return json.dumps({'status': 'needs_confirmation', 'message': f'Ask the user to confirm deleting {form_id!r}.'})
        return json.dumps(await self._api('DELETE', f'/api/form-types/{form_id}'))

    def _require_admin(self, user: Optional[dict]):
        if self.valves.ADMIN_ONLY and (user or {}).get('role') != 'admin':
            raise PermissionError('Only Biz GPT admins can create, change or delete forms.')

    async def _api(self, method: str, path: str, body: Optional[dict] = None):
        url = self.valves.FORMS_API_URL.rstrip('/') + path
        headers = {'Authorization': f'Bearer {self.valves.FORMS_API_KEY}'}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.request(method, url, json=body, headers=headers) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RuntimeError(f'Forms service error {resp.status}: {data}')
                return data
