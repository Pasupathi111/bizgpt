"""
title: Biz GPT Dynamic Forms
author: Biz GPT
description: Shows prefilled, validated business forms (cab booking, leave, IT tickets…) inside the chat. Forms are served by the Biz GPT forms service.
"""

import json
import re
from html import escape as html_escape
from datetime import datetime
from typing import Optional

import aiohttp
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        FORMS_API_URL: str = Field(
            default='http://bizgpt-forms:8000',
            description='Forms service URL as seen from the Biz GPT server',
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
            # the same live form in Biz GPT's right-side panel.
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
        if __event_emitter__:
            # Already embedded in the message above; an inline tool result would render it a second time.
            return json.dumps(context_for_llm)
        return HTMLResponse(content=public_url, headers={'Content-Disposition': 'inline'}), context_for_llm

    async def get_form_status(self, form_id: str) -> str:
        """
        Check a form's status (draft, submitted, executed, expired) and its submitted values and result.
        :param form_id: The form_id returned by open_form.
        """
        return json.dumps(await self._api('GET', f'/api/forms/{form_id}'))

    async def list_submitted_forms(self, form_type: str, limit: int = 20) -> str:
        """
        List the most recently submitted forms of one type, newest first, with their reference, values and
        submission time. Use it to find orders or requests waiting for review, e.g. form_type "tshirt_order".
        :param form_type: The form type id, e.g. "tshirt_order".
        :param limit: How many submitted forms to return (1-50).
        """
        limit = max(1, min(int(limit or 20), 50))
        forms = await self._api('GET', '/api/forms?limit=200')
        submitted = [
            {
                'form_id': f['form_id'],
                'reference': (f.get('result') or {}).get('reference'),
                'status': f['status'],
                'values': f['values'],
                'submitted_at': f['updated_at'],
            }
            for f in forms
            if f['form_type'] == form_type and f['status'] == 'executed'
        ]
        return json.dumps(submitted[:limit])

    async def show_approval_card(
        self,
        form_id: str,
        email_subject: str,
        email_body: str,
        __event_emitter__=None,
    ):
        """
        Show a submitted form as an approval card in the chat: every submitted value, the draft email to the
        customer, a green "Approve & send" button and a red "Reject" button. A click posts the approver's
        decision back to the chat as a message; nothing is sent by this tool.
        :param form_id: The form_id of the submitted form (from list_submitted_forms).
        :param email_subject: Subject of the draft confirmation email.
        :param email_body: Plain-text body of the draft confirmation email.
        """
        form = await self._api('GET', f'/api/forms/{form_id}')
        form_type = await self._api('GET', f'/api/form-types/{form["form_type"]}')
        properties = (form_type.get('schema') or {}).get('properties', {})
        values = form.get('values') or {}
        reference = (form.get('result') or {}).get('reference') or form_id
        recipient = next((v for k, v in values.items() if 'email' in k and isinstance(v, str)), '')

        html = _approval_cards_html(
            [
                {
                    'title': form_type.get('title', form['form_type']),
                    'reference': reference,
                    'form_id': form_id,
                    'rows': _rows(values, properties),
                    'recipient': recipient,
                    'subject': email_subject,
                    'body': email_body,
                    'approve_text': f'✅ Approve order {reference}: send the email shown on the card to {recipient}.',
                }
            ]
        )
        context = {
            'status': 'approval_card_displayed',
            'reference': reference,
            'recipient': recipient,
            'instructions': 'The approval card with Approve & send and Reject buttons is visible. Reply with one '
            'short sentence asking the approver to use the buttons, then stop. Do not repeat the draft as text. '
            'Send nothing until a message saying the order was approved arrives.',
        }
        if __event_emitter__:
            await __event_emitter__({'type': 'embeds', 'data': {'embeds': [html]}})
            return json.dumps(context)
        return HTMLResponse(content=html, headers={'Content-Disposition': 'inline'}), context

    async def show_pending_approvals(
        self,
        form_type: str,
        exclude_references: Optional[list] = None,
        __event_emitter__=None,
    ):
        """
        Show every submitted form of one type that still needs a decision, as a list of approval cards in the
        chat. Each card has the submitted values, the standard confirmation email, a green "Approve & send"
        button and a red "Reject" button, so the approver never needs to know a reference. Nothing is sent by
        this tool.
        :param form_type: The form type id, e.g. "tshirt_order".
        :param exclude_references: References already decided (for example already emailed), to leave out.
        """
        if isinstance(exclude_references, str):
            exclude_references = [r.strip() for r in exclude_references.replace(',', ' ').split() if r.strip()]
        excluded = {str(r).upper() for r in (exclude_references or [])}
        form_type_def = await self._api('GET', f'/api/form-types/{form_type}')
        properties = (form_type_def.get('schema') or {}).get('properties', {})
        title = form_type_def.get('title', form_type)
        forms = await self._api('GET', '/api/forms?limit=200')

        items = []
        for f in forms:
            reference = (f.get('result') or {}).get('reference') or f['form_id']
            if f['form_type'] != form_type or f['status'] != 'executed' or reference.upper() in excluded:
                continue
            if (f.get('result') or {}).get('decision'):
                continue
            values = f.get('values') or {}
            email = _standard_email(title, reference, values, properties)
            items.append(
                {
                    'title': title,
                    'reference': reference,
                    'form_id': f['form_id'],
                    'rows': _rows(values, properties),
                    **email,
                    'approve_text': f'✅ Approve order {reference} (form {f["form_id"]}): send its standard '
                    f'confirmation email to {email["recipient"]}.',
                }
            )

        context = {
            'status': 'pending_approvals_displayed',
            'count': len(items),
            'pending': [{'reference': i['reference'], 'form_id': i['form_id'], 'recipient': i['recipient']} for i in items],
            'instructions': 'The pending orders are visible as cards with Approve & send and Reject buttons. '
            'Reply in one short sentence with how many orders are waiting and ask the approver to decide on each '
            'card, then stop. Do not list the orders again as text. Send nothing until an approval message arrives.',
        }
        if not items:
            context['instructions'] = 'Nothing is pending. Say so in one short sentence.'
            return json.dumps(context)
        html = _approval_cards_html(items, heading=f'{len(items)} pending {title.lower()}{"s" if len(items) != 1 else ""}')
        if __event_emitter__:
            await __event_emitter__({'type': 'embeds', 'data': {'embeds': [html]}})
            return json.dumps(context)
        return HTMLResponse(content=html, headers={'Content-Disposition': 'inline'}), context

    async def show_order_summary(self, __event_emitter__=None):
        """
        Show the order dashboard in the chat: total orders till date and how many are Active, Pending,
        Shipping and Done, with the latest orders in each status. Call this whenever the user asks how many
        orders there are, for an order count, order status overview, or order summary.
        """
        counts = {status: n for status, n, _, _ in ORDER_STATUSES}
        total = sum(counts.values())
        context = {
            'status': 'order_summary_displayed',
            'as_of': datetime.now().strftime('%Y-%m-%d'),
            'total_orders': total,
            'by_status': counts,
            'instructions': 'The order summary card is visible in the chat. Reply with one short sentence giving '
            'the total and the status split (for example "You have 248 orders till date: 42 active, 18 pending, '
            '27 shipping and 161 done."). Do not repeat the card as a table.',
        }
        html = _order_summary_html(total)
        if __event_emitter__:
            await __event_emitter__({'type': 'embeds', 'data': {'embeds': [html]}})
            return json.dumps(context)
        return HTMLResponse(content=html, headers={'Content-Disposition': 'inline'}), context

    async def get_approval_email(self, form_id: str) -> str:
        """
        Get the standard confirmation email (to, subject, body) exactly as shown on the pending-approval card
        for a submitted form. Use it to send the approved email word for word.
        :param form_id: The form_id from the approval message or list_submitted_forms.
        """
        form = await self._api('GET', f'/api/forms/{form_id}')
        form_type_def = await self._api('GET', f'/api/form-types/{form["form_type"]}')
        properties = (form_type_def.get('schema') or {}).get('properties', {})
        reference = (form.get('result') or {}).get('reference') or form_id
        decision = (form.get('result') or {}).get('decision')
        if decision:
            return json.dumps(
                {'reference': reference, 'already_decided': decision,
                 'instructions': 'This order already has a decision. Do not send any email; tell the approver.'}
            )
        email = _standard_email(form_type_def.get('title', form['form_type']), reference, form.get('values') or {}, properties)
        return json.dumps({'reference': reference, 'to': email['recipient'], 'subject': email['subject'], 'body': email['body']})

    async def record_decision(
        self,
        form_id: str,
        decision: str,
        gmail_message_id: str = '',
        note: str = '',
        __user__: Optional[dict] = None,
    ) -> str:
        """
        Record the approver's final decision on a submitted form, right after the approved email was sent
        (or when an order is rejected without an email). A decided form leaves the pending list and can't be
        emailed again. Each form can be decided once.
        :param form_id: The form_id of the order.
        :param decision: "approved" or "rejected".
        :param gmail_message_id: The Gmail message id returned by send_gmail_message, if an email was sent.
        :param note: Optional short note, e.g. the rejection reason.
        """
        gmail_message_id = (gmail_message_id or '').strip()
        if gmail_message_id and not re.fullmatch(r'[0-9a-f]{10,24}', gmail_message_id):
            return json.dumps(
                {'status': 'refused', 'reason': f'{gmail_message_id!r} is not a Gmail message id. Only record the id '
                 'returned by send_gmail_message. If send_gmail_message was not called or failed, tell the approver '
                 'the email was NOT sent and do not record a decision.'}
            )
        if decision == 'approved' and not gmail_message_id:
            return json.dumps(
                {'status': 'refused', 'reason': 'An approval needs the Gmail message id of the sent confirmation. '
                 'Call send_gmail_message first; if it is unavailable or fails, tell the approver the email was NOT sent.'}
            )
        body = {'decision': decision, 'by': (__user__ or {}).get('email'), 'gmail_message_id': gmail_message_id or None, 'note': note or None}
        try:
            form = await self._api('POST', f'/api/forms/{form_id}/decision', body)
        except RuntimeError as e:
            if ' 409' in str(e):
                return json.dumps({'status': 'already_decided', 'form_id': form_id})
            raise
        return json.dumps({'status': 'recorded', 'reference': (form.get('result') or {}).get('reference'), 'decision': decision})

    async def _api(self, method: str, path: str, body: Optional[dict] = None):
        url = self.valves.FORMS_API_URL.rstrip('/') + path
        headers = {'Authorization': f'Bearer {self.valves.FORMS_API_KEY}'}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.request(method, url, json=body, headers=headers) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RuntimeError(f'Forms service error {resp.status}: {data}')
                return data



# Static demo figures for the order summary card: (status, count, colour, latest orders).
ORDER_STATUSES = [
    ('Active', 42, '#2563eb', [('ORD-1248', 'Priya Sharma', '25 × Navy L'), ('ORD-1245', 'Arun Kumar', '10 × White M')]),
    ('Pending', 18, '#d97706', [('ORD-1247', 'Meena Iyer', '40 × Black XL'), ('ORD-1244', 'Rahul Verma', '6 × Red S')]),
    ('Shipping', 27, '#7c3aed', [('ORD-1239', 'Kavya Nair', '15 × Grey M'), ('ORD-1236', 'Sanjay Patel', '30 × Green L')]),
    ('Done', 161, '#16a34a', [('ORD-1231', 'Divya Rao', '12 × Royal blue XL'), ('ORD-1228', 'Vikram Singh', '50 × White L')]),
]


def _order_summary_html(total: int) -> str:
    """Order status summary card for the chat. Clicking a status asks Biz GPT about those orders."""
    esc = html_escape
    tiles, bar, lists = '', '', ''
    for status, count, colour, orders in ORDER_STATUSES:
        pct = count * 100 / total if total else 0
        prompt = f'Show me the {status.lower()} orders'
        tiles += (
            f'<button class="tile" style="--c:{colour}" data-prompt="{esc(prompt)}">'
            f'<span class="dot"></span><span class="name">{esc(status)}</span>'
            f'<span class="num">{count}</span><span class="pct">{pct:.0f}%</span></button>'
        )
        bar += f'<span style="width:{pct:.2f}%;background:{colour}" title="{esc(status)}: {count}"></span>'
        rows = ''.join(
            f'<div class="row"><span class="ref">{esc(ref)}</span><span class="who">{esc(who)}</span>'
            f'<span class="what">{esc(what)}</span><span class="pill" style="--c:{colour}">{esc(status)}</span></div>'
            for ref, who, what in orders
        )
        lists += rows
    today = datetime.now().strftime('%d %b %Y')
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: Inter, system-ui, Arial, sans-serif; color: #0f172a; background: transparent; }}
  .card {{ border: 1px solid #e2e8f0; border-radius: 16px; background: #fff; overflow: hidden; }}
  .head {{ display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; padding: 16px 18px 12px; }}
  .eyebrow {{ font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: #64748b; }}
  .total {{ margin-top: 4px; font-size: 30px; font-weight: 700; line-height: 1; }}
  .total small {{ font-size: 13px; font-weight: 500; color: #64748b; margin-left: 6px; }}
  .asof {{ font-size: 12px; color: #64748b; white-space: nowrap; }}
  .bar {{ display: flex; height: 8px; margin: 0 18px; border-radius: 999px; overflow: hidden; gap: 2px; background: #f1f5f9; }}
  .tiles {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; padding: 14px 18px; }}
  .tile {{ display: grid; grid-template-columns: auto 1fr; align-items: center; gap: 2px 8px; padding: 12px; text-align: left;
    border: 1px solid #e2e8f0; border-radius: 12px; background: #f8fafc; font: inherit; color: inherit; cursor: pointer; }}
  .tile:hover {{ border-color: var(--c); }}
  .dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--c); }}
  .name {{ font-size: 12.5px; font-weight: 600; color: #475569; }}
  .num {{ grid-column: 1 / -1; font-size: 22px; font-weight: 700; }}
  .pct {{ grid-column: 1 / -1; font-size: 12px; color: #64748b; }}
  .sec {{ padding: 4px 18px 14px; }}
  .label {{ font-size: 12px; font-weight: 600; color: #64748b; margin: 6px 0 8px; }}
  .row {{ display: grid; grid-template-columns: 82px 1fr 1fr auto; gap: 10px; align-items: center; padding: 8px 0; font-size: 13px; border-top: 1px solid #f1f5f9; }}
  .ref {{ font-weight: 600; }} .who, .what {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }} .what {{ color: #64748b; }}
  .pill {{ padding: 3px 9px; border-radius: 999px; font-size: 11.5px; font-weight: 600; color: var(--c);
    background: color-mix(in srgb, var(--c) 12%, transparent); }}
  @media (max-width: 560px) {{
    .tiles {{ grid-template-columns: repeat(2, 1fr); }}
    .row {{ grid-template-columns: 76px 1fr auto; }} .what {{ display: none; }}
  }}
  @media (prefers-color-scheme: dark) {{
    body {{ color: #e2e8f0; }} .card {{ background: #0f172a; border-color: #1e293b; }}
    .tile {{ background: #111827; border-color: #1e293b; }} .name {{ color: #cbd5e1; }}
    .bar {{ background: #1e293b; }} .row {{ border-color: #1e293b; }}
  }}
</style></head><body>
<div class="card">
  <div class="head">
    <div><div class="eyebrow">Orders till date</div><div class="total">{total}<small>orders</small></div></div>
    <div class="asof">As of {esc(today)}</div>
  </div>
  <div class="bar">{bar}</div>
  <div class="tiles">{tiles}</div>
  <div class="sec"><div class="label">Latest orders</div>{lists}</div>
</div>
<script>
  const post = (m) => window.parent !== window && window.parent.postMessage(m, '*');
  const height = () => post({{ type: 'iframe:height', height: document.documentElement.scrollHeight }});
  new ResizeObserver(height).observe(document.body); height();
  document.querySelectorAll('.tile').forEach((t) =>
    t.addEventListener('click', () => post({{ type: 'input:prompt:submit', text: t.dataset.prompt }})));
</script>
</body></html>"""


def _rows(values: dict, properties: dict) -> list:
    """(title, value) pairs in schema order, skipping empty values."""
    order = [k for k in properties if k in values] + [k for k in values if k not in properties]
    return [(properties.get(k, {}).get('title', k), values[k]) for k in order if values[k] not in (None, '')]


def _standard_email(title: str, reference: str, values: dict, properties: dict) -> dict:
    """The confirmation email shown on a pending-approval card and sent after approval."""
    recipient = next((v for k, v in values.items() if 'email' in k and isinstance(v, str)), '')
    name = next((v for k, v in values.items() if k.endswith('name') and isinstance(v, str) and v.strip()), '')
    details = '\n'.join(
        f'- {k}: {v}' for k, v in _rows(values, properties) if not str(v) == recipient and not str(v) == name
    )
    body = (
        f'Dear {name or "customer"},\n\n'
        f'Thank you for your order. Your {title.lower()} {reference} is confirmed with these details:\n\n'
        f'{details}\n\n'
        'We will keep you posted on delivery. Reply to this email if anything needs to change.\n\n'
        'Best regards,\nBiz GPT Orders team'
    )
    return {'recipient': recipient, 'subject': f'Your {title} {reference} is confirmed', 'body': body}


def _approval_cards_html(items: list, heading: str = '') -> str:
    """Approval cards for the chat. Buttons post the decision back to Biz GPT as a chat message."""
    esc = html_escape
    cards = []
    for i, item in enumerate(items):
        rows_html = ''.join(f'<div class="k">{esc(str(k))}</div><div class="v">{esc(str(v))}</div>' for k, v in item['rows'])
        cards.append(f"""
<div class="card" data-approve="{esc(item['approve_text'])}" data-reject="{esc(f"❌ Reject order {item['reference']} (form {item['form_id']}). Reason: ")}">
  <div class="head">
    <div><div class="eyebrow">{esc(item['title'])} · approval</div><div class="title">{esc(item['reference'])}</div></div>
    <span class="badge">Pending approval</span>
  </div>
  <div class="sec"><div class="label">Order details</div><div class="grid">{rows_html}</div></div>
  <details class="sec" {'open' if len(items) == 1 else ''}><summary class="label">Confirmation email to {esc(item['recipient'])}</summary>
    <div class="mail"><div class="meta"><b>To:</b> {esc(item['recipient'])}<br><b>Subject:</b> {esc(item['subject'])}</div><pre>{esc(item['body'])}</pre></div>
  </details>
  <div class="actions">
    <button class="approve">Approve &amp; send</button>
    <button class="reject">Reject</button>
    <div class="reason"><textarea placeholder="Reason for rejecting (shared with the customer)"></textarea>
      <button class="reject confirm">Confirm reject</button><button class="ghost cancel">Cancel</button></div>
    <div class="note"></div>
  </div>
</div>""")
    heading_html = f'<div class="heading">{esc(heading)}</div>' if heading else ''
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: Inter, system-ui, Arial, sans-serif; color: #0f172a; background: transparent; }}
  .heading {{ margin: 2px 2px 10px; font-size: 13px; font-weight: 650; color: #475569; }}
  .card {{ border: 1px solid #e2e8f0; border-radius: 16px; background: #fff; overflow: hidden; margin-bottom: 14px; }}
  .head {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 18px; border-bottom: 1px solid #e2e8f0; background: #f8fafc; }}
  .eyebrow {{ font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: #64748b; }}
  .title {{ margin-top: 2px; font-size: 16px; font-weight: 650; }}
  .badge {{ padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; background: #fef3c7; color: #92400e; white-space: nowrap; }}
  .badge.ok {{ background: #dcfce7; color: #166534; }} .badge.no {{ background: #fee2e2; color: #991b1b; }}
  .sec {{ padding: 14px 18px; }} .sec + .sec {{ border-top: 1px solid #f1f5f9; }}
  .label {{ font-size: 12px; font-weight: 600; color: #64748b; margin-bottom: 8px; }}
  summary.label {{ cursor: pointer; margin: 0; }} details[open] summary.label {{ margin-bottom: 8px; }}
  .grid {{ display: grid; grid-template-columns: minmax(120px, 34%) 1fr; gap: 6px 14px; font-size: 13.5px; }}
  .k {{ color: #64748b; }} .v {{ font-weight: 550; overflow-wrap: anywhere; }}
  .mail {{ border: 1px solid #e2e8f0; border-radius: 12px; background: #f8fafc; font-size: 13px; }}
  .mail .meta {{ padding: 10px 12px; border-bottom: 1px solid #e2e8f0; line-height: 1.6; overflow-wrap: anywhere; }}
  .mail .meta b {{ color: #64748b; font-weight: 600; }}
  .mail pre {{ margin: 0; padding: 12px; white-space: pre-wrap; font: inherit; line-height: 1.55; }}
  .actions {{ display: flex; flex-wrap: wrap; gap: 10px; padding: 14px 18px; border-top: 1px solid #e2e8f0; background: #f8fafc; }}
  button {{ border: 0; border-radius: 10px; padding: 10px 18px; font: 600 14px Inter, system-ui, sans-serif; cursor: pointer; }}
  button:disabled {{ opacity: .55; cursor: default; }}
  .approve {{ background: #16a34a; color: #fff; }} .approve:hover:not(:disabled) {{ background: #15803d; }}
  .reject {{ background: #dc2626; color: #fff; }} .reject:hover:not(:disabled) {{ background: #b91c1c; }}
  .ghost {{ background: #fff; color: #334155; border: 1px solid #cbd5e1; }}
  .reason {{ display: none; width: 100%; }} .reason.show {{ display: block; }}
  textarea {{ width: 100%; min-height: 64px; margin-bottom: 10px; padding: 10px; border: 1px solid #fca5a5; border-radius: 10px; font: 13.5px Inter, system-ui, sans-serif; resize: vertical; }}
  .note {{ width: 100%; font-size: 12.5px; color: #475569; }} .note:empty {{ display: none; }}
  @media (prefers-color-scheme: dark) {{
    body {{ color: #e2e8f0; }} .card {{ background: #0f172a; border-color: #1e293b; }}
    .head, .actions, .mail {{ background: #111827; border-color: #1e293b; }} .mail .meta {{ border-color: #1e293b; }}
    .sec + .sec {{ border-color: #1e293b; }} .ghost {{ background: #0f172a; color: #e2e8f0; border-color: #334155; }}
    textarea {{ background: #0f172a; color: #e2e8f0; }} .heading {{ color: #94a3b8; }}
  }}
</style></head><body>
{heading_html}{''.join(cards)}
<script>
  const post = (m) => window.parent !== window && window.parent.postMessage(m, '*');
  const height = () => post({{ type: 'iframe:height', height: document.documentElement.scrollHeight }});
  new ResizeObserver(height).observe(document.body); height();
  document.addEventListener('toggle', height, true);
  document.querySelectorAll('.card').forEach((card) => {{
    const q = (s) => card.querySelector(s);
    const [approve, reject] = [q('.approve'), q('.reject')];
    const reasonBox = q('.reason'), reason = q('textarea'), badge = q('.badge');
    const decide = (label, cls, text) => {{
      card.querySelectorAll('button').forEach((b) => (b.disabled = true));
      badge.textContent = label; badge.className = 'badge ' + cls;
      q('.note').textContent = 'Decision sent to the chat. Confirm it in the Biz GPT dialog if asked.';
      post({{ type: 'input:prompt:submit', text }});
      height();
    }};
    approve.onclick = () => decide('Approved', 'ok', card.dataset.approve);
    reject.onclick = () => {{ reasonBox.classList.add('show'); approve.disabled = reject.disabled = true; reason.focus(); height(); }};
    q('.cancel').onclick = () => {{ reasonBox.classList.remove('show'); approve.disabled = reject.disabled = false; height(); }};
    q('.confirm').onclick = () => {{
      if (!reason.value.trim()) {{ reason.focus(); return; }}
      decide('Rejected', 'no', card.dataset.reject + reason.value.trim());
    }};
  }});
</script>
</body></html>"""
