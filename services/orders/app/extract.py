"""AI extraction of T-shirt orders from customer emails, plus rule-based validation."""

import json
import os
import re

import httpx

OPENWEBUI_URL = os.getenv('OPENWEBUI_BASE_URL', 'http://open-webui:8080').rstrip('/')
OPENWEBUI_API_KEY = os.getenv('OPENWEBUI_API_KEY', '')
MODEL = os.getenv('ORDERS_MODEL', 'gpt-4.1-mini')

SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL']
COLOURS = ['White', 'Black', 'Navy', 'Grey', 'Red', 'Royal blue', 'Green']
PAYMENT_METHODS = ['Bank transfer', 'UPI', 'Card', 'Cash on delivery', 'Invoice']

# (field, label) in the order the checklist shows them.
REQUIRED = [
    ('customer_name', 'Customer name'),
    ('customer_email', 'Customer email'),
    ('customer_phone', 'Customer phone'),
    ('delivery_address', 'Delivery address'),
    ('items', 'Order items (size and colour)'),
    ('quantity', 'Quantity'),
    ('payment_method', 'Payment method'),
    ('preferred_delivery_time', 'Preferred delivery time'),
]

FIELDS_SPEC = f"""{{
  "customer_name": string or null,
  "customer_email": string or null,
  "customer_phone": string or null,
  "delivery_address": string or null (full address with city and PIN code),
  "items": [ {{ "size": one of {SIZES} or null, "color": one of {COLOURS} or null, "quantity": integer or null, "print_text": string or null }} ],
  "payment_method": one of {PAYMENT_METHODS} or null,
  "preferred_delivery_time": string or null (date and/or time window as the customer wrote it, e.g. "2026-10-09 morning"),
  "notes": string or null
}}"""


class ExtractionError(RuntimeError):
    pass


async def _complete(system: str, user: str) -> dict:
    body = {
        'model': MODEL,
        'stream': False,
        'temperature': 0,
        'response_format': {'type': 'json_object'},
        'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f'{OPENWEBUI_URL}/api/chat/completions', json=body,
                                 headers={'Authorization': f'Bearer {OPENWEBUI_API_KEY}'})
    if resp.status_code >= 400:
        raise ExtractionError(f'model call failed: {resp.status_code} {resp.text[:200]}')
    try:
        return json.loads(resp.json()['choices'][0]['message']['content'])
    except (KeyError, ValueError, TypeError) as e:
        raise ExtractionError(f'model returned no JSON: {e}') from e


async def extract_new(email: dict, today: str) -> dict:
    """{is_order: bool, reason: str, fields: {...}} for a message that starts a new conversation."""
    system = (
        'You read emails sent to a custom T-shirt printing business and extract orders. '
        'Decide if the email is a customer placing (or trying to place) a T-shirt order. Newsletters, notifications, '
        'security alerts, spam, delivery failures and general questions are NOT orders. '
        f'Today is {today}. Return JSON: {{"is_order": boolean, "reason": short string, "fields": {FIELDS_SPEC}}}. '
        'Only use information written in the email; never invent values. Use null for anything not given. '
        'Map sizes like "large" to "L", colours to the closest allowed colour, payment like "GPay"/"PhonePe" to "UPI", '
        '"COD" to "Cash on delivery". One entry in items per size/colour combination.'
    )
    user = f'From: {email["from"]}\nSubject: {email["subject"]}\nDate: {email["date"]}\n\n{email["body"]}'
    result = await _complete(system, user)
    fields = _clean(result.get('fields') or {})
    if not fields.get('customer_email') and email.get('from_email'):
        fields['customer_email'] = email['from_email']
    return {'is_order': bool(result.get('is_order')), 'reason': str(result.get('reason') or '')[:300], 'fields': fields}


async def merge_reply(current: dict, email: dict, today: str) -> dict:
    """Apply the customer's reply to an existing order; returns the updated fields."""
    system = (
        'You update an existing T-shirt order with information from the customer\'s reply email. '
        f'Today is {today}. Return JSON: {{"fields": {FIELDS_SPEC}}} with the full updated order. '
        'Keep every existing value unless the reply clearly changes it. Fill fields the reply provides. '
        'If the reply gives a size, colour or quantity for an existing item, update that item instead of adding a new one. '
        'Never invent values; use null for anything still unknown.'
    )
    user = f'Current order JSON:\n{json.dumps(current)}\n\nCustomer reply:\nFrom: {email["from"]}\nSubject: {email["subject"]}\n\n{email["body"]}'
    result = await _complete(system, user)
    merged = _clean(result.get('fields') or {})
    # The model may drop values; never lose something we already had.
    for key, value in current.items():
        if key != 'items' and value not in (None, '', []) and merged.get(key) in (None, '', []):
            merged[key] = value
    if not merged.get('items') and current.get('items'):
        merged['items'] = current['items']
    return merged


def validate(fields: dict) -> dict:
    """{checks: [{field, label, ok}], missing: [labels], complete: bool}"""
    items = fields.get('items') or []
    ok = {
        'customer_name': bool(fields.get('customer_name')),
        'customer_email': bool(re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', fields.get('customer_email') or '')),
        'customer_phone': len(re.sub(r'\D', '', fields.get('customer_phone') or '')) >= 8,
        'delivery_address': len((fields.get('delivery_address') or '').strip()) >= 10,
        'items': bool(items) and all(i.get('size') and i.get('color') for i in items),
        'quantity': bool(items) and all(isinstance(i.get('quantity'), int) and i['quantity'] > 0 for i in items),
        'payment_method': bool(fields.get('payment_method')),
        'preferred_delivery_time': bool(fields.get('preferred_delivery_time')),
    }
    checks = [{'field': f, 'label': label, 'ok': ok[f]} for f, label in REQUIRED]
    missing = [c['label'] for c in checks if not c['ok']]
    return {'checks': checks, 'missing': missing, 'complete': not missing}


def _clean(fields: dict) -> dict:
    out = {}
    for key in ('customer_name', 'customer_email', 'customer_phone', 'delivery_address', 'payment_method',
                'preferred_delivery_time', 'notes'):
        value = fields.get(key)
        out[key] = str(value).strip()[:500] if value not in (None, '') else None
    if out['customer_email']:
        out['customer_email'] = out['customer_email'].lower()
    if out['payment_method'] not in PAYMENT_METHODS:
        out['payment_method'] = None if not out['payment_method'] else out['payment_method']
    items = []
    for item in (fields.get('items') or [])[:20]:
        if not isinstance(item, dict):
            continue
        qty = item.get('quantity')
        try:
            qty = int(qty) if qty not in (None, '') else None
        except (TypeError, ValueError):
            qty = None
        items.append({
            'size': item.get('size') if item.get('size') in SIZES else None,
            'color': item.get('color') if item.get('color') in COLOURS else None,
            'quantity': qty,
            'print_text': (str(item['print_text']).strip()[:200] if item.get('print_text') else None),
        })
    out['items'] = items
    return out
