"""Order workflow: Gmail intake -> extract -> validate -> ask for missing info -> approve / reject."""

import asyncio
import logging
import os
import re
import time
from datetime import date

import httpx

from .extract import ExtractionError, extract_new, merge_reply, validate
from .gmail import MAILBOX, Gmail, GmailError
from .store import CLOSED, Store

log = logging.getLogger('orders')

POLL_SECONDS = int(os.getenv('ORDERS_POLL_SECONDS', '60'))
MAX_MISSING_INFO_EMAILS = int(os.getenv('ORDERS_MAX_MISSING_INFO_EMAILS', '3'))
FORMS_API_URL = os.getenv('FORMS_API_URL', 'http://bizgpt-forms:8000').rstrip('/')
FORMS_API_KEY = os.getenv('FORMS_API_KEY', '')
SIGNATURE = os.getenv('ORDERS_SIGNATURE', 'Biz GPT Orders team')
IGNORED_SENDERS = re.compile(r'(no-?reply|mailer-daemon|postmaster|notifications?@|bounce)', re.I)


class WorkflowError(RuntimeError):
    pass


class Workflow:
    def __init__(self, store: Store, gmail: Gmail):
        self.store = store
        self.gmail = gmail
        self._failures: dict[str, int] = {}
        self.last_poll: dict = {}

    # ------------------------------------------------------------------ intake
    def watermark(self) -> int:
        """Emails and chat orders before the service's first start are never acted on."""
        value = self.store.get_setting('since_epoch')
        if value is None:
            value = str(int(time.time()))
            self.store.set_setting('since_epoch', value)
        return int(value)

    async def poll_once(self) -> dict:
        since = self.watermark()
        stats = {'checked': 0, 'orders_created': 0, 'orders_updated': 0, 'ignored': 0, 'errors': 0}
        query = f'in:inbox after:{since} -from:me'
        messages = await self.gmail.search(query, page_size=25)
        for msg in reversed(messages):  # oldest first
            if self.store.is_processed(msg['message_id']):
                continue
            stats['checked'] += 1
            try:
                outcome = await self._handle_message(msg)
                self.store.mark_processed(msg['message_id'], outcome)
                stats[{'created': 'orders_created', 'updated': 'orders_updated'}.get(outcome, 'ignored')] += 1
            except (ExtractionError, GmailError, httpx.HTTPError) as e:
                stats['errors'] += 1
                count = self._failures[msg['message_id']] = self._failures.get(msg['message_id'], 0) + 1
                log.warning('message %s failed (%s/3): %s', msg['message_id'], count, e)
                if count >= 3:
                    self.store.mark_processed(msg['message_id'], f'error: {str(e)[:200]}')
        stats['chat_orders_imported'] = await self._import_chat_orders(since)
        self.last_poll = {'at': int(time.time()), **stats}
        return stats

    async def _handle_message(self, msg: dict) -> str:
        email = await self.gmail.read(msg['message_id'])
        if email['from_email'] == MAILBOX.lower() or IGNORED_SENDERS.search(email['from']):
            return 'ignored: automated or own sender'
        today = date.today().isoformat()

        order = self.store.find_open_by_thread(msg['thread_id'])
        if order:
            fields = await merge_reply(order['fields'], email, today)
            order = self.store.update_order(order['id'], fields=fields, last_message_id=email['rfc_message_id'] or order['last_message_id'])
            self.store.add_event(order['id'], 'customer_replied', email['from_email'],
                                 {'gmail_message_id': msg['message_id'], 'excerpt': email['body'][:500]})
            await self.evaluate(order)
            return 'updated'

        closed = self.store.find_latest_by_thread(msg['thread_id'])
        if closed:  # the thread's order is already decided; keep the message on it instead of starting a new order
            self.store.add_event(closed['id'], 'customer_wrote_after_decision', email['from_email'],
                                 {'gmail_message_id': msg['message_id'], 'excerpt': email['body'][:500]})
            return 'logged on closed order'

        result = await extract_new(email, today)
        if not result['is_order']:
            return f'not an order: {result["reason"]}'
        order = self.store.create_order(
            source='email', fields=result['fields'], status='new', gmail_thread_id=msg['thread_id'],
            last_message_id=email['rfc_message_id'], subject=email['subject'],
        )
        self.store.add_event(order['id'], 'order_created', email['from_email'],
                             {'gmail_message_id': msg['message_id'], 'subject': email['subject'], 'excerpt': email['body'][:500]})
        await self.evaluate(order)
        return 'created'

    async def _import_chat_orders(self, since: int) -> int:
        """T-shirt orders submitted through the Biz GPT chat form join the same workflow."""
        if not FORMS_API_KEY:
            return 0
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f'{FORMS_API_URL}/api/forms', params={'limit': 200},
                                    headers={'Authorization': f'Bearer {FORMS_API_KEY}'})
        if resp.status_code >= 400:
            return 0
        imported = 0
        for form in resp.json():
            if form['form_type'] != 'tshirt_order' or form['status'] != 'executed':
                continue
            if _epoch(form['created_at']) < since or self.store.find_by_source_ref(form['form_id']):
                continue
            v = form.get('values') or {}
            reference = (form.get('result') or {}).get('reference')
            fields = {
                'customer_name': v.get('customer_name'),
                'customer_email': (v.get('customer_email') or '').lower() or None,
                'customer_phone': v.get('customer_phone'),
                'delivery_address': v.get('delivery_location'),
                'items': [{'size': v.get('size'), 'color': v.get('color'), 'quantity': v.get('quantity'),
                           'print_text': v.get('print_text')}],
                'payment_method': v.get('payment_method'),
                'preferred_delivery_time': ' '.join(x for x in (v.get('delivery_date'), v.get('delivery_time')) if x) or None,
                'notes': ' · '.join(x for x in (f'Service level: {v["service_level"]}' if v.get('service_level') else None,
                                                v.get('notes')) if x) or None,
            }
            order = self.store.create_order(source='chat', fields=fields, status='new', source_ref=form['form_id'],
                                            subject=f'T-shirt order {reference}' if reference else 'T-shirt order')
            self.store.add_event(order['id'], 'order_created', (form.get('context') or {}).get('user_email') or 'biz-gpt-chat',
                                 {'source': 'Biz GPT chat form', 'form_reference': reference})
            await self.evaluate(order)
            imported += 1
        return imported

    # -------------------------------------------------------------- validation
    async def evaluate(self, order: dict) -> dict:
        check = validate(order['fields'])
        self.store.add_event(order['id'], 'validated', 'system', {'missing': check['missing']})
        if check['complete']:
            return self.store.update_order(order['id'], status='ready_for_approval')

        order = self.store.update_order(order['id'], status='missing_info')
        if order['reminders_sent'] >= MAX_MISSING_INFO_EMAILS:
            self.store.add_event(order['id'], 'missing_info_limit', 'system',
                                 {'note': f'Stopped after {MAX_MISSING_INFO_EMAILS} requests; follow up manually.'})
            return order
        to = order['fields'].get('customer_email')
        if not to:
            self.store.add_event(order['id'], 'email_skipped', 'system', {'reason': 'No customer email to reply to.'})
            return order
        subject, body = missing_info_email(order, check['missing'])
        try:
            gmail_id = await self._send(order, to, subject, body)
        except GmailError as e:
            self.store.add_event(order['id'], 'email_failed', 'system', {'kind': 'missing_info_request', 'error': str(e)[:300]})
            return order
        self.store.add_event(order['id'], 'missing_info_requested', MAILBOX,
                             {'to': to, 'missing': check['missing'], 'gmail_message_id': gmail_id, 'subject': subject})
        return self.store.update_order(order['id'], status='awaiting_customer', reminders_sent=order['reminders_sent'] + 1)

    # --------------------------------------------------------------- decisions
    async def approve(self, order_id: str, actor: str) -> dict:
        order = self._require(order_id)
        if not validate(order['fields'])['complete']:
            raise WorkflowError('Order is missing required information.')
        if not self.store.set_status_if(order['id'], ('ready_for_approval',), 'approved'):
            raise WorkflowError(f'Order is {order["status"].replace("_", " ")}, not ready for approval.')
        self.store.add_event(order['id'], 'approved', actor)
        return await self.send_confirmation(order['id'], actor)

    async def send_confirmation(self, order_id: str, actor: str) -> dict:
        """approved -> confirmation email -> processing. Safe to retry: only acts while still 'approved'."""
        order = self._require(order_id)
        if order['status'] != 'approved':
            raise WorkflowError(f'Order is {order["status"]}; the confirmation is only sent from approved.')
        subject, body = confirmation_email(order)
        try:
            gmail_id = await self._send(order, order['fields']['customer_email'], subject, body)
        except GmailError as e:
            self.store.add_event(order['id'], 'email_failed', 'system', {'kind': 'confirmation', 'error': str(e)[:300]})
            raise WorkflowError('Approved, but the confirmation email failed. Retry sending it.') from e
        self.store.add_event(order['id'], 'confirmation_sent', MAILBOX,
                             {'to': order['fields']['customer_email'], 'gmail_message_id': gmail_id, 'subject': subject})
        self.store.set_status_if(order['id'], ('approved',), 'processing')
        self.store.add_event(order['id'], 'processing_started', actor)
        return self.store.get(order['id'])

    async def reject(self, order_id: str, actor: str, reason: str) -> dict:
        order = self._require(order_id)
        reason = reason.strip()
        if not reason:
            raise WorkflowError('A rejection reason is required.')
        if not self.store.set_status_if(order['id'], ('new', 'missing_info', 'awaiting_customer', 'ready_for_approval'), 'rejected'):
            raise WorkflowError(f'Order is {order["status"]} and can no longer be rejected.')
        self.store.add_event(order['id'], 'rejected', actor, {'reason': reason})
        to = order['fields'].get('customer_email')
        if not to:
            self.store.add_event(order['id'], 'email_skipped', 'system', {'reason': 'No customer email for the rejection notice.'})
            return self.store.get(order['id'])
        subject, body = rejection_email(order, reason)
        try:
            gmail_id = await self._send(order, to, subject, body)
            self.store.add_event(order['id'], 'rejection_sent', MAILBOX, {'to': to, 'gmail_message_id': gmail_id, 'subject': subject})
        except GmailError as e:
            self.store.add_event(order['id'], 'email_failed', 'system', {'kind': 'rejection', 'error': str(e)[:300]})
            raise WorkflowError('Rejected, but the rejection email failed to send.') from e
        return self.store.get(order['id'])

    # ----------------------------------------------------------------- helpers
    def _require(self, order_id: str) -> dict:
        order = self.store.get(order_id)
        if not order:
            raise WorkflowError('Order not found.')
        return order

    async def _send(self, order: dict, to: str, subject: str, body: str) -> str:
        return await self.gmail.send(to=to, subject=subject, body=body, thread_id=order.get('gmail_thread_id'),
                                     in_reply_to=order.get('last_message_id'))

    async def run_forever(self) -> None:
        while True:
            try:
                stats = await self.poll_once()
                if any(v for k, v in stats.items() if k != 'checked'):
                    log.info('poll: %s', stats)
            except Exception as e:  # keep polling through transient failures
                log.exception('poll failed: %s', e)
                self.last_poll = {'at': int(time.time()), 'error': str(e)[:300]}
            await asyncio.sleep(POLL_SECONDS)


# -------------------------------------------------------------------- emails
def _greeting(order: dict) -> str:
    return f'Dear {order["fields"].get("customer_name") or "customer"},'


def _reply_subject(order: dict, fallback: str) -> str:
    subject = order.get('subject') or ''
    if order.get('gmail_thread_id') and subject:
        return subject if subject.lower().startswith('re:') else f'Re: {subject}'
    return fallback


def order_summary(order: dict) -> str:
    f = order['fields']
    lines = []
    for item in f.get('items') or []:
        desc = ' '.join(x for x in (str(item.get('quantity') or '?') + ' ×', item.get('color') or '', 'T-shirt',
                                    f'size {item["size"]}' if item.get('size') else '') if x)
        lines.append(f'- {desc}' + (f' — print: "{item["print_text"]}"' if item.get('print_text') else ''))
    for label, key in (('Delivery address', 'delivery_address'), ('Preferred delivery time', 'preferred_delivery_time'),
                       ('Payment method', 'payment_method'), ('Phone', 'customer_phone'), ('Notes', 'notes')):
        if f.get(key):
            lines.append(f'- {label}: {f[key]}')
    return '\n'.join(lines) or '- (no details yet)'


def missing_info_email(order: dict, missing: list[str]) -> tuple[str, str]:
    subject = _reply_subject(order, f'Your T-shirt order {order["reference"]}: a few details needed')
    wanted = '\n'.join(f'- {label}' for label in missing)
    body = (
        f'{_greeting(order)}\n\n'
        f'Thank you for your T-shirt order. We have registered it as {order["reference"]}.\n\n'
        f'To process it, please reply to this email with the following details:\n{wanted}\n\n'
        f'Here is what we have so far:\n{order_summary(order)}\n\n'
        f'Best regards,\n{SIGNATURE}'
    )
    return subject, body


def confirmation_email(order: dict) -> tuple[str, str]:
    subject = _reply_subject(order, f'Your T-shirt order {order["reference"]} is confirmed')
    body = (
        f'{_greeting(order)}\n\n'
        f'Good news: your T-shirt order {order["reference"]} has been approved and is now being processed.\n\n'
        f'Order details:\n{order_summary(order)}\n\n'
        'We will contact you if anything changes before delivery.\n\n'
        f'Best regards,\n{SIGNATURE}'
    )
    return subject, body


def rejection_email(order: dict, reason: str) -> tuple[str, str]:
    subject = _reply_subject(order, f'About your T-shirt order {order["reference"]}')
    body = (
        f'{_greeting(order)}\n\n'
        f'Thank you for your T-shirt order {order["reference"]}. Unfortunately we cannot accept it as requested.\n\n'
        f'Reason: {reason}\n\n'
        f'Order details:\n{order_summary(order)}\n\n'
        'You are welcome to reply to this email if you would like to change the order.\n\n'
        f'Best regards,\n{SIGNATURE}'
    )
    return subject, body


def _epoch(iso: str) -> int:
    from datetime import datetime
    try:
        return int(datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp())
    except ValueError:
        return 0
