"""
title: Automobile Lead Outreach (POC)
author: Biz GPT
description: AI Lead Generation & Outreach POC for customer Automobile Group. Finds real companies in Singapore and Malaysia by web search, reads contact details from each company's own website, adds an AI assessment, and runs a templated, POC-safe outreach email flow inside the chat. Isolated project: own model, own storage. Every email goes to the POC test inbox only.
"""

import asyncio
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from html import escape as esc
from typing import Optional
from urllib.parse import urlparse

import aiohttp
import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

# ---------------------------------------------------------------- POC safety (code, not config: the UI cannot change it)
POC_RECIPIENT = 'prsap94@gmail.com'
ENVIRONMENT = 'POC'

STATUSES = ['New', 'Contacted', 'Interested', 'Not Interested']
# WEB_SOURCED = real company found by web search, details read from its own website. VERIFIED = checked by a person.
# SAMPLE = old fictional POC leads; they are hidden everywhere.
VERIFICATION = ['WEB_SOURCED', 'VERIFIED', 'UNVERIFIED']
COMPANY_SIZES = ['Unknown', 'Small', 'Medium', 'Large', 'Enterprise']
PLACEHOLDERS = ['customer_name', 'company_name', 'contact_name', 'industry', 'sender_name', 'business_context']

DEFAULT_CUSTOMER = {
    'id': 'automobile',
    'name': 'Automobile Group',
    'industries': ['Automotive', 'Mining', 'Industrial'],
    'markets': ['Singapore', 'Malaysia'],
    'description': 'Business context spans automotive, mining and related industrial sectors.',
}

DEFAULT_TEMPLATE = {
    'subject': 'Introduction – Potential Collaboration with {{company_name}}',
    'body': (
        'Dear {{contact_name}},\n\n'
        "I hope you're doing well.\n\n"
        "I'm reaching out on behalf of {{customer_name}} regarding potential opportunities to collaborate with "
        '{{company_name}}.\n\n'
        "Based on your company's focus in {{industry}}, we believe there may be relevant areas where our teams could "
        'explore potential collaboration. {{business_context}}\n\n'
        'Would you be available for a short discussion to explore this further?\n\n'
        'Best regards,\n{{sender_name}}\n{{customer_name}}'
    ),
}

# The lead form is rendered from this list. Add a field here and it appears in the form, validation and storage.
LEAD_FIELDS = [
    {'key': 'company_name', 'label': 'Company Name', 'type': 'text', 'required': True, 'max': 120},
    {'key': 'industry', 'label': 'Industry', 'type': 'select', 'options': 'industries', 'required': True},
    {'key': 'sub_segment', 'label': 'Business Segment', 'type': 'text', 'max': 120},
    {'key': 'contact_name', 'label': 'Contact Name (leave empty for general enquiries)', 'type': 'text', 'max': 80},
    {'key': 'job_title', 'label': 'Target Role', 'type': 'text', 'max': 80},
    {'key': 'email', 'label': 'Email', 'type': 'email', 'max': 120},
    {'key': 'phone', 'label': 'Phone', 'type': 'text', 'max': 40},
    {'key': 'website', 'label': 'Website', 'type': 'text', 'max': 200},
    {'key': 'country', 'label': 'Country', 'type': 'text', 'max': 60},
    {'key': 'location', 'label': 'City', 'type': 'text', 'max': 80},
    {'key': 'address', 'label': 'Address (from website)', 'type': 'textarea', 'max': 300},
    {'key': 'company_size', 'label': 'Company Size', 'type': 'select', 'options': COMPANY_SIZES},
    {'key': 'business_relationship', 'label': 'Potential Relationship', 'type': 'text', 'max': 200},
    {'key': 'source', 'label': 'Lead Source', 'type': 'text', 'readonly': True},
    {'key': 'source_url', 'label': 'Source Pages', 'type': 'text', 'readonly': True},
    {'key': 'verification_status', 'label': 'Verification', 'type': 'select', 'options': VERIFICATION},
    {'key': 'relevance_score', 'label': 'Lead Relevance (%)', 'type': 'number', 'min': 0, 'max': 100},
    {'key': 'relevance_reason', 'label': 'Reason for Relevance', 'type': 'textarea', 'max': 600},
    {'key': 'recommendation', 'label': 'AI Recommendation (why this company)', 'type': 'textarea', 'max': 800},
    {'key': 'highlights', 'label': 'Key Highlights (one per line)', 'type': 'lines', 'max': 600},
    {'key': 'est_revenue_musd', 'label': 'Revenue Last Year (USD M, only if published)', 'type': 'number', 'float': True, 'min': 0, 'max': 100000},
    {'key': 'revenue_growth_pct', 'label': 'Revenue Growth YoY (%, only if published)', 'type': 'number', 'min': -100, 'max': 500},
    {'key': 'employees', 'label': 'Employees (only if published)', 'type': 'number', 'min': 0, 'max': 1000000},
    {'key': 'recommended_action', 'label': 'Recommended Next Step', 'type': 'text', 'max': 200},
    {'key': 'notes', 'label': 'Notes', 'type': 'textarea', 'max': 2000},
    {'key': 'status', 'label': 'Status', 'type': 'select', 'options': STATUSES, 'required': True},
]
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')


def relevance_label(score) -> str:
    score = int(score or 0)
    return 'High' if score >= 80 else 'Medium' if score >= 60 else 'Low'


def slug(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', (text or '').lower())[:40] or 'company'


class Tools:
    class Valves(BaseModel):
        AI_MODEL: str = Field(default='qwen2.5:7b', description='Model used by this project only (lead generation + email personalisation)')
        OPENWEBUI_API_URL: str = Field(default='http://localhost:8080', description='Biz GPT API as seen from the server')
        INTEGRATIONS_API_URL: str = Field(default='http://bizgpt-integrations:8002', description='Existing Biz GPT integrations service (Gmail via Nango)')
        SENDER_NAME: str = Field(default='Business Development Team', description='Signature name in outreach emails')
        DB_PATH: str = Field(default='/app/backend/data/automobile_lead_outreach/poc.db', description='POC storage (SQLite)')
        AI_TIMEOUT: int = Field(default=240, description='Seconds to wait for the model')

    def __init__(self):
        self.valves = self.Valves()

    # ============================================================ tools the model can call

    async def show_customer_profile(self, customer: str = '', __event_emitter__=None) -> str:
        """
        Show the customer profile (name, industries, markets) with buttons to generate leads.
        Call this when the user asks about the customer, its industries, or wants to start.
        :param customer: Customer name. Leave empty for the default customer (Automobile Group).
        """
        db = self._db()
        c = self._customer(db, customer)
        if not c:
            return json.dumps({'status': 'not_found', 'instructions': f'No customer named {customer}. Only configured customers can be used.'})
        counts = {r['industry']: r['n'] for r in db.execute(
            "SELECT json_extract(data,'$.industry') industry, COUNT(*) n FROM leads WHERE customer_id=? AND coalesce(json_extract(data,'$.verification_status'),'') != 'SAMPLE' GROUP BY 1", (c['id'],))}
        await self._embed(__event_emitter__, _profile_html(c, counts, self._template(db)))
        return json.dumps({'status': 'profile_displayed', 'customer': c, 'lead_counts': counts,
                           'instructions': 'The profile card is visible. Reply in one short sentence, then stop.'})

    async def update_customer_profile(self, customer: str = '', industries: str = '', markets: str = '', __event_emitter__=None) -> str:
        """
        Change the customer's target industries or geographic markets (e.g. add a new industry).
        :param customer: Customer name. Leave empty for the default customer (Automobile Group).
        :param industries: Full comma-separated list of industries, e.g. "Automotive, Mining, Industrial, Construction". Empty = unchanged.
        :param markets: Full comma-separated list of markets, e.g. "Malaysia, Singapore". Empty = unchanged.
        """
        db = self._db()
        c = self._customer(db, customer)
        if not c:
            return json.dumps({'status': 'not_found'})
        for key, raw in (('industries', industries), ('markets', markets)):
            items = [i.strip().title() if key == 'industries' else i.strip() for i in (raw or '').split(',') if i.strip()]
            items = [i[:60] for i in dict.fromkeys(items)][:12]
            if items:
                c[key] = items
        db.execute('UPDATE customers SET industries=?, markets=?, updated_at=? WHERE id=?',
                   (json.dumps(c['industries']), json.dumps(c['markets']), now(), c['id']))
        db.commit()
        return await self.show_customer_profile(c['name'], __event_emitter__)

    async def generate_leads(self, customer: str = '', industries: str = '', count: int = 6, location: str = '',
                             __user__: Optional[dict] = None, __request__=None, __event_emitter__=None) -> str:
        """
        Find REAL companies in Singapore and Malaysia that are good prospects for the customer: web search, AI selection,
        contact details read from each company's own website, then an AI assessment. Shows them as a lead list.
        :param customer: Customer name. Leave empty for the default customer (Automobile Group).
        :param industries: Comma-separated target industries from the profile, e.g. "Mining". Empty = all profile industries.
        :param count: Number of leads, 1-10 (default 6).
        :param location: Optional market, "Singapore" or "Malaysia". Empty = profile markets.
        """
        db = self._db()
        c = self._customer(db, customer)
        if not c:
            return json.dumps({'status': 'not_found'})
        wanted = [i.strip().lower() for i in (industries or '').split(',') if i.strip()]
        targets = [i for i in c['industries'] if not wanted or i.lower() in wanted] or c['industries']
        count = max(1, min(int(count or 6), 10))
        markets = [m for m in c['markets'] if not location or m.lower() == location.strip().lower()] or c['markets']
        existing = {domain_of(r[0]) for r in db.execute("SELECT json_extract(data,'$.website') FROM leads WHERE customer_id=?", (c['id'],)) if r[0]}

        await self._status(__event_emitter__, f'Searching the web for {", ".join(targets)} companies in {", ".join(markets)}…')
        results = await search_companies(targets, markets, existing)
        if not results:
            await self._status(__event_emitter__, 'No new companies found', done=True)
            return json.dumps({'status': 'no_results', 'instructions': 'Say no new companies were found by web search and suggest another industry or market.'})

        await self._status(__event_emitter__, f'AI is selecting real companies from {len(results)} search results…')
        try:
            raw = await self._ai_json(pick_prompt(c, targets, markets, results, count), pick_schema(targets, markets), __request__)
        except Exception as e:
            await self._status(__event_emitter__, 'Lead research failed', done=True)
            return json.dumps({'status': 'error', 'error': str(e)[:300], 'instructions': 'Tell the user lead research failed and they can retry.'})
        picks, rejected = validate_picks(raw, results, targets, markets)
        picks = picks[:count]

        await self._status(__event_emitter__, f'Reading contact details from {len(picks)} company websites…')
        sites = await asyncio.gather(*[fetch_site(p['website']) for p in picks])
        batch, ids = datetime.now().strftime('%Y%m%d%H%M%S'), []
        for pick, pages in zip(picks, sites):
            if DOMAIN_NAME_RE.search(pick['company_name']):
                pick['company_name'] = name_from_pages(pages)
                if not pick['company_name'] or DOMAIN_NAME_RE.search(pick['company_name']):
                    rejected.append({'company_name': pick['website'], 'reason': 'company name could not be read from its website'})
                    continue
            lead = build_web_lead(pick, extract_contacts(pages, domain_of(pick['website']), pick['country']), [u for u, _ in pages])
            lead_id = self._next_id(db, 'leads', 'L')
            db.execute('INSERT INTO leads (id, customer_id, data, batch_id, created_at, updated_at) VALUES (?,?,?,?,?,?)',
                       (lead_id, c['id'], json.dumps(lead), batch, now(), now()))
            ids.append(lead_id)
        db.commit()
        if not ids:
            await self._status(__event_emitter__, 'No valid companies found', done=True)
            return json.dumps({'status': 'no_valid_leads', 'rejected': rejected[:5],
                               'instructions': 'No search result passed validation. Tell the user and suggest retrying.'})
        new_leads = [self._lead(db, i) for i in ids]
        await self._fill_recommendations(db, c, new_leads, __request__, __event_emitter__)
        await self._status(__event_emitter__, f'{len(ids)} real companies added', done=True)
        rows = self._leads(db, c['id'])
        await self._embed(__event_emitter__, _lead_list_html(c, rows, highlight=ids, title=f'Real Company Leads – {len(ids)} new'))
        return json.dumps({'status': 'leads_displayed', 'new_lead_ids': ids, 'rejected_by_validation': len(rejected),
                           'instructions': 'The lead list is visible. In one or two short sentences say how many real companies were found '
                           'by web search, that contact details come from their own websites (see Source), and that the user can open a lead. '
                           'Do not list the leads as text.'})

    async def show_leads(self, customer: str = '', industry: str = '', status: str = '', search: str = '', __request__=None,
                         __event_emitter__=None) -> str:
        """
        Show the saved lead list with filters (industry, relevance, status, search).
        :param customer: Customer name. Leave empty for the default customer (Automobile Group).
        :param industry: Optional initial industry filter.
        :param status: Optional initial status filter: New, Contacted, Interested, Not Interested.
        :param search: Optional initial search text.
        """
        db = self._db()
        c = self._customer(db, customer)
        if not c:
            return json.dumps({'status': 'not_found'})
        rows = self._leads(db, c['id'])
        if not rows:
            return json.dumps({'status': 'empty', 'instructions': 'No leads yet. Offer to generate leads.'})
        if await self._fill_recommendations(db, c, rows, __request__, __event_emitter__):
            rows = self._leads(db, c['id'])
        await self._embed(__event_emitter__, _lead_list_html(c, rows, filters={'industry': industry, 'status': status, 'search': search}))
        return json.dumps({'status': 'leads_displayed', 'count': len(rows), 'instructions': 'The lead list is visible. Reply in one short sentence.'})

    async def show_lead_details(self, lead_id: str, __request__=None, __event_emitter__=None) -> str:
        """
        Open one lead in the editable lead details form.
        :param lead_id: Lead id such as "L-0003".
        """
        db = self._db()
        lead = self._lead(db, lead_id)
        if not lead:
            return json.dumps({'status': 'not_found', 'lead_id': lead_id})
        c = self._customer(db, lead['customer_id'])
        if await self._fill_recommendations(db, c, [lead], __request__, __event_emitter__):
            lead = self._lead(db, lead['id'])
        await self._embed(__event_emitter__, _lead_form_html(lead, c, self._emails_for(db, lead['id'])))
        return json.dumps({'status': 'form_displayed', 'lead_id': lead['id'],
                           'instructions': 'The lead form is visible. Reply in one short sentence, then stop.'})

    async def update_lead(self, lead_id: str, changes: str, __event_emitter__=None) -> str:
        """
        Save edits to a lead. Use it when a message says "Save lead L-xxxx changes: {...}"; pass that JSON unchanged.
        :param lead_id: Lead id such as "L-0003".
        :param changes: JSON object of changed fields, e.g. {"status": "Interested", "notes": "Call next week"}.
        """
        db = self._db()
        lead = self._lead(db, lead_id)
        if not lead:
            return json.dumps({'status': 'not_found', 'lead_id': lead_id})
        if isinstance(changes, str):
            try:
                changes = json.loads(changes)
            except json.JSONDecodeError:
                return json.dumps({'status': 'invalid', 'error': 'changes must be a JSON object'})
        c = self._customer(db, lead['customer_id'])
        clean, errors = validate_lead_changes(changes or {}, c['industries'])
        if errors:
            return json.dumps({'status': 'invalid', 'errors': errors, 'instructions': 'Tell the user which fields are invalid. Nothing was saved.'})
        data = {**lead['data'], **clean}
        db.execute('UPDATE leads SET data=?, updated_at=? WHERE id=?', (json.dumps(data), now(), lead['id']))
        db.commit()
        lead = self._lead(db, lead['id'])
        await self._embed(__event_emitter__, _lead_form_html(lead, c, self._emails_for(db, lead['id']), saved=sorted(clean)))
        return json.dumps({'status': 'saved', 'lead_id': lead['id'], 'changed_fields': sorted(clean),
                           'instructions': 'Say in one short sentence that the lead was saved.'})

    async def generate_email(self, lead_id: str, __request__=None, __event_emitter__=None) -> str:
        """
        Generate the personalised outreach email for a lead from the standard template and show the email preview.
        :param lead_id: Lead id such as "L-0003".
        """
        db = self._db()
        lead = self._lead(db, lead_id)
        if not lead:
            return json.dumps({'status': 'not_found', 'lead_id': lead_id})
        c = self._customer(db, lead['customer_id'])
        d = lead['data']
        await self._status(__event_emitter__, f'Personalising email for {d.get("company_name")}…')
        context = ''
        try:
            out = await self._ai_json(_context_prompt(c, d), {'type': 'object', 'properties': {'business_context': {'type': 'string'}},
                                                               'required': ['business_context']}, __request__)
            context = clean_context(out.get('business_context', ''))
        except Exception:
            context = ''
        if not context:
            context = f'We see a possible fit around {d.get("sub_segment") or d.get("industry")}.'
        values = {
            'customer_name': c['name'], 'company_name': d.get('company_name', ''), 'industry': d.get('industry', ''),
            'contact_name': (d.get('contact_name') or '').split()[0] if d.get('contact_name') else f'{d.get("company_name", "")} team',
            'sender_name': self.valves.SENDER_NAME,
            'business_context': context,
        }
        t = self._template(db)
        subject, body = render(t['subject'], values), render(t['body'], values)
        email_id = self._next_id(db, 'emails', 'E')
        db.execute('INSERT INTO emails (id, lead_id, intended_recipient, actual_recipient, subject, body, environment, email_status, created_at) '
                   'VALUES (?,?,?,?,?,?,?,?,?)', (email_id, lead['id'], d.get('email', ''), POC_RECIPIENT, subject, body, ENVIRONMENT, 'DRAFT', now()))
        db.commit()
        await self._status(__event_emitter__, 'Email ready for review', done=True)
        await self._embed(__event_emitter__, _email_preview_html(self._email(db, email_id), lead))
        return json.dumps({'status': 'preview_displayed', 'email_id': email_id,
                           'instructions': 'The email preview is visible. In one short sentence ask the user to review it and use '
                           'Send Test Email; mention it will go to the POC test inbox, not the lead. Do not repeat the email.'})

    async def update_email(self, email_id: str, subject: str, body: str, __event_emitter__=None) -> str:
        """
        Save the user's edits to a draft email. Use it when a message says "Update email E-xxxx"; copy subject and body exactly.
        :param email_id: Email id such as "E-0002".
        :param subject: The edited subject.
        :param body: The edited body, exactly as given.
        """
        db = self._db()
        e = self._email(db, email_id)
        if not e:
            return json.dumps({'status': 'not_found'})
        if e['email_status'] != 'DRAFT':
            return json.dumps({'status': 'refused', 'reason': 'Only draft emails can be edited.'})
        subject, body = (subject or '').strip()[:200], (body or '').strip()[:5000]
        if not subject or not body:
            return json.dumps({'status': 'invalid', 'error': 'subject and body are required'})
        db.execute('UPDATE emails SET subject=?, body=? WHERE id=?', (subject, body, e['id']))
        db.commit()
        await self._embed(__event_emitter__, _email_preview_html(self._email(db, e['id']), self._lead(db, e['lead_id']), saved=True))
        return json.dumps({'status': 'saved', 'email_id': e['id'], 'instructions': 'Say in one short sentence the edits were saved.'})

    async def send_test_email(self, email_id: str, __user__: Optional[dict] = None, __event_emitter__=None) -> str:
        """
        Send a reviewed draft email as a POC TEST email. Only call it after the user asked to send this email id.
        The recipient is always the POC test inbox; the lead is never contacted.
        :param email_id: Email id such as "E-0002".
        """
        db = self._db()
        e = self._email(db, email_id)
        if not e:
            return json.dumps({'status': 'not_found'})
        lead = self._lead(db, e['lead_id'])
        if e['email_status'] == 'TEST_SENT':
            await self._embed(__event_emitter__, _send_result_html(e, lead))
            return json.dumps({'status': 'already_sent', 'instructions': 'This email was already sent; say so. Generate a new email to send again.'})

        actual = POC_RECIPIENT  # enforced here, never taken from the lead, the model or the UI
        body = (f'[{ENVIRONMENT} TEST EMAIL]\nOriginal intended recipient: {e["intended_recipient"] or "-"}\n'
                f'Lead: {lead["data"].get("company_name")} ({lead["id"]})\n'
                '--------------------------------------------------\n\n' + e['body'])
        payload = {'user_id': (__user__ or {}).get('id', ''), 'integration': 'gmail', 'to': actual,
                   'subject': f'[TEST] {e["subject"]}', 'body': body, 'confirm': True}
        await self._status(__event_emitter__, f'Sending test email to {actual}…')
        status, error, message_id = 'TEST_SENT', None, None
        try:
            result = await self._integrations('POST', '/api/emails/send', payload)
            message_id = result.get('message_id')
            if result.get('status') != 'sent' or result.get('to') != actual:
                status, error = 'FAILED', f'Unexpected send result: {result}'
        except Exception as ex:
            status, error = 'FAILED', str(ex)[:400]
        db.execute('UPDATE emails SET actual_recipient=?, email_status=?, gmail_message_id=?, error=?, sent_at=? WHERE id=?',
                   (actual, status, message_id, error, now(), e['id']))
        db.commit()
        await self._status(__event_emitter__, 'Test email sent' if status == 'TEST_SENT' else 'Sending failed', done=True)
        await self._embed(__event_emitter__, _send_result_html(self._email(db, e['id']), lead))
        return json.dumps({'status': status, 'email_id': e['id'], 'actual_recipient': actual, 'intended_recipient': e['intended_recipient'],
                           'error': error, 'instructions': 'The result card is visible. Reply in one short sentence with the outcome.'})

    async def recommend_lead(self, lead_id: str, __request__=None, __event_emitter__=None) -> str:
        """
        Create or refresh the AI recommendation for one lead: why it is recommended, key highlights from the company's own
        website and the recommended next step. Use it for "Get AI recommendation for lead L-xxxx" or "why this lead".
        :param lead_id: Lead id such as "L-0003".
        """
        db = self._db()
        lead = self._lead(db, lead_id)
        if not lead:
            return json.dumps({'status': 'not_found', 'lead_id': lead_id})
        c = self._customer(db, lead['customer_id'])
        d = lead['data']
        await self._status(__event_emitter__, f'Analysing {d.get("company_name")} for {c["name"]}…')
        try:
            out = await self._ai_json(recommend_prompt(c, d), recommend_schema(), __request__)
        except Exception as e:
            await self._status(__event_emitter__, 'Recommendation failed', done=True)
            return json.dumps({'status': 'error', 'error': str(e)[:300]})
        rec = clean_web_recommendation(out, d)
        if not rec['recommendation']:
            await self._status(__event_emitter__, 'Recommendation failed validation', done=True)
            return json.dumps({'status': 'invalid', 'instructions': 'The AI output failed validation. Suggest retrying.'})
        db.execute('UPDATE leads SET data=?, updated_at=? WHERE id=?', (json.dumps({**d, **rec}), now(), lead['id']))
        db.commit()
        await self._status(__event_emitter__, 'AI recommendation ready', done=True)
        lead = self._lead(db, lead['id'])
        await self._embed(__event_emitter__, _lead_list_html(c, [lead], title=f'AI Recommendation – {d.get("company_name")}'))
        return json.dumps({'status': 'recommendation_displayed', 'lead_id': lead['id'],
                           'instructions': 'The recommendation card is visible. Reply in one short sentence; do not repeat it.'})

    async def show_email_template(self, __event_emitter__=None) -> str:
        """Show the reusable outreach email template and its placeholders."""
        t = self._template(self._db())
        await self._embed(__event_emitter__, _template_html(t))
        return json.dumps({'status': 'template_displayed', 'template': t, 'instructions': 'Reply in one short sentence.'})

    async def update_email_template(self, subject: str, body: str, __event_emitter__=None) -> str:
        """
        Replace the reusable outreach email template. Allowed placeholders: {{customer_name}}, {{company_name}},
        {{contact_name}}, {{industry}}, {{sender_name}}, {{business_context}}.
        :param subject: Template subject.
        :param body: Template body.
        """
        used = set(re.findall(r'{{\s*(\w+)\s*}}', f'{subject}\n{body}'))
        unknown = sorted(used - set(PLACEHOLDERS))
        if unknown or not subject.strip() or not body.strip():
            return json.dumps({'status': 'invalid', 'unknown_placeholders': unknown, 'allowed': PLACEHOLDERS})
        db = self._db()
        db.execute("UPDATE email_templates SET subject=?, body=?, updated_at=? WHERE id='default'", (subject.strip(), body.strip(), now()))
        db.commit()
        return await self.show_email_template(__event_emitter__)

    # ============================================================ storage

    def _db(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.valves.DB_PATH), exist_ok=True)
        db = sqlite3.connect(self.valves.DB_PATH)
        db.row_factory = sqlite3.Row
        db.executescript('''
            CREATE TABLE IF NOT EXISTS customers (id TEXT PRIMARY KEY, name TEXT, industries TEXT, markets TEXT, description TEXT, created_at TEXT, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS leads (id TEXT PRIMARY KEY, customer_id TEXT, data TEXT, batch_id TEXT, created_at TEXT, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS email_templates (id TEXT PRIMARY KEY, subject TEXT, body TEXT, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS emails (id TEXT PRIMARY KEY, lead_id TEXT, intended_recipient TEXT, actual_recipient TEXT, subject TEXT,
                body TEXT, environment TEXT, email_status TEXT, gmail_message_id TEXT, error TEXT, created_at TEXT, sent_at TEXT);
        ''')
        c = DEFAULT_CUSTOMER
        db.execute('INSERT OR IGNORE INTO customers VALUES (?,?,?,?,?,?,?)',
                   (c['id'], c['name'], json.dumps(c['industries']), json.dumps(c['markets']), c['description'], now(), now()))
        db.execute("INSERT OR IGNORE INTO email_templates VALUES ('default',?,?,?)", (DEFAULT_TEMPLATE['subject'], DEFAULT_TEMPLATE['body'], now()))
        db.commit()
        return db

    def _customer(self, db, name_or_id: str) -> Optional[dict]:
        r = db.execute('SELECT * FROM customers WHERE lower(name)=lower(?) OR id=lower(?)', ((name_or_id or DEFAULT_CUSTOMER['id']).strip(),) * 2).fetchone()
        if not r:
            return None
        return {**dict(r), 'industries': json.loads(r['industries']), 'markets': json.loads(r['markets'])}

    def _leads(self, db, customer_id: str) -> list:
        return [self._row_lead(r) for r in db.execute(
            "SELECT * FROM leads WHERE customer_id=? AND coalesce(json_extract(data,'$.verification_status'),'') != 'SAMPLE' ORDER BY id DESC", (customer_id,))]

    def _lead(self, db, lead_id: str) -> Optional[dict]:
        r = db.execute("SELECT * FROM leads WHERE id=? AND coalesce(json_extract(data,'$.verification_status'),'') != 'SAMPLE'", (normalize_id(lead_id, 'L'),)).fetchone()
        return self._row_lead(r) if r else None

    def _row_lead(self, r) -> dict:
        lead = {**dict(r), 'data': json.loads(r['data'])}
        lead['emails'] = []
        return lead

    def _email(self, db, email_id: str) -> Optional[dict]:
        r = db.execute('SELECT * FROM emails WHERE id=?', (normalize_id(email_id, 'E'),)).fetchone()
        return dict(r) if r else None

    def _emails_for(self, db, lead_id: str) -> list:
        return [dict(r) for r in db.execute('SELECT * FROM emails WHERE lead_id=? ORDER BY id DESC', (lead_id,))]

    def _template(self, db) -> dict:
        return dict(db.execute("SELECT subject, body, updated_at FROM email_templates WHERE id='default'").fetchone())

    def _next_id(self, db, table: str, prefix: str) -> str:
        n = db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] + 1
        while db.execute(f'SELECT 1 FROM {table} WHERE id=?', (f'{prefix}-{n:04d}',)).fetchone():
            n += 1
        return f'{prefix}-{n:04d}'

    # ============================================================ AI + integrations

    async def _fill_recommendations(self, db, c: dict, leads: list, request, emitter) -> int:
        """Generate the AI recommendation for every lead that has none, a few leads per model call. Returns how many were filled."""
        missing = [lead for lead in leads if not lead['data'].get('recommendation')]
        filled = 0
        for start in range(0, len(missing), RECOMMEND_BATCH):
            batch = missing[start:start + RECOMMEND_BATCH]
            await self._status(emitter, f'AI is analysing {len(missing)} lead(s) without a recommendation '
                                        f'({start + 1}-{start + len(batch)} of {len(missing)})…')
            try:
                out = await self._ai_json(recommend_batch_prompt(c, batch), recommend_batch_schema([lead['id'] for lead in batch]), request)
            except Exception:
                continue  # leave these for the next view; the card keeps its manual fallback button
            by_id = {normalize_id(i.get('lead_id'), 'L'): i for i in (out or {}).get('items') or [] if isinstance(i, dict)}
            for lead in batch:
                item = by_id.get(lead['id'])
                if not item:
                    continue
                d = lead['data']
                rec = clean_web_recommendation(item, d)
                if rec['recommendation']:
                    db.execute('UPDATE leads SET data=?, updated_at=? WHERE id=?', (json.dumps({**d, **rec}), now(), lead['id']))
                    lead['filled'] = True
                    filled += 1
            db.commit()
        # A small model sometimes drops an item from a batch: retry those one at a time.
        for lead in [lead for lead in missing if not lead.get('filled')][:RECOMMEND_BATCH]:
            d = lead['data']
            await self._status(emitter, f'AI is analysing {d.get("company_name")}…')
            try:
                out = await self._ai_json(recommend_prompt(c, d), recommend_schema(), request)
            except Exception:
                continue
            rec = clean_web_recommendation(out, d)
            if rec['recommendation']:
                db.execute('UPDATE leads SET data=?, updated_at=? WHERE id=?', (json.dumps({**d, **rec}), now(), lead['id']))
                db.commit()
                filled += 1
        if missing:
            await self._status(emitter, f'AI recommendations ready for {filled} of {len(missing)} lead(s)', done=True)
        return filled

    async def _ai_json(self, messages: list, schema: dict, request) -> dict:
        """Call ONLY this project's model through Biz GPT, force JSON output that matches the schema."""
        headers = {'Content-Type': 'application/json'}
        auth = request.headers.get('authorization') if request is not None else None
        if not auth and request is not None and request.cookies.get('token'):
            auth = f'Bearer {request.cookies["token"]}'
        if auth:
            headers['Authorization'] = auth
        payload = {'model': self.valves.AI_MODEL, 'stream': False, 'temperature': 0.4, 'messages': messages,
                   'response_format': {'type': 'json_schema', 'json_schema': {'name': 'output', 'schema': schema}}}
        url = self.valves.OPENWEBUI_API_URL.rstrip('/') + '/api/chat/completions'
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.valves.AI_TIMEOUT)) as s:
            async with s.post(url, json=payload, headers=headers) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RuntimeError(f'model call failed ({resp.status}): {str(data)[:200]}')
        content = data['choices'][0]['message']['content']
        content = re.sub(r'^```(?:json)?|```$', '', content.strip()).strip()
        return json.loads(content)

    async def _integrations(self, method: str, path: str, body: dict) -> dict:
        key = os.environ.get('INTEGRATIONS_API_KEY', '')  # server-side secret, never sent to the browser
        url = os.environ.get('INTEGRATIONS_API_URL') or self.valves.INTEGRATIONS_API_URL
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
            async with s.request(method, url.rstrip('/') + path, json=body, headers={'Authorization': f'Bearer {key}'}) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RuntimeError(f'email service error {resp.status}: {(data or {}).get("detail", data)}')
                return data

    async def _embed(self, emitter, html: str):
        if emitter:
            await emitter({'type': 'embeds', 'data': {'embeds': [html]}})

    async def _status(self, emitter, text: str, done: bool = False):
        if emitter:
            await emitter({'type': 'status', 'data': {'description': text, 'done': done}})


# ================================================================ validation / business rules (outside the LLM)

def normalize_id(value: str, prefix: str) -> str:
    m = re.search(r'(\d+)', str(value or ''))
    return f'{prefix}-{int(m.group(1)):04d}' if m else str(value)


def _text(v, limit: int) -> str:
    return re.sub(r'\s+', ' ', str(v or '')).strip()[:limit]


def validate_lead_changes(changes: dict, industries: list) -> tuple:
    fields = {f['key']: f for f in LEAD_FIELDS}
    clean, errors = {}, []
    for key, value in changes.items():
        f = fields.get(key)
        if not f or f.get('readonly'):
            errors.append(f'{key}: not an editable field')
            continue
        if f['type'] == 'lines':
            items = value if isinstance(value, list) else str(value or '').splitlines()
            value = [_text(i, 160) for i in items if _text(i, 160)][:6]
        elif f['type'] == 'number':
            try:
                value = round(float(value), 1) if f.get('float') else int(float(value))
            except (TypeError, ValueError):
                errors.append(f'{f["label"]}: must be a number')
                continue
            if not f.get('min', 0) <= value <= f.get('max', 100):
                errors.append(f'{f["label"]}: must be between {f.get("min", 0)} and {f.get("max", 100)}')
                continue
        else:
            value = str(value or '').strip()[: f.get('max', 200)]
            if f.get('required') and not value:
                errors.append(f'{f["label"]}: required')
                continue
            if f['type'] == 'email' and value and not EMAIL_RE.match(value):
                errors.append(f'{f["label"]}: not a valid email')
                continue
            if f['type'] == 'select':
                options = industries if f['options'] == 'industries' else f['options']
                if value not in options:
                    errors.append(f'{f["label"]}: must be one of {", ".join(options)}')
                    continue
        clean[key] = value
    return clean, errors


def clean_context(text: str) -> str:
    text = _text(text, 300)
    # The template already says this; a model echo would duplicate it in the email.
    text = re.sub(r'^.*?relevant areas where our teams could explore potential collaboration\s*(in|around|on|,)?\s*', '', text, flags=re.I)
    if re.search(r'https?://|www\.|@|\d{4,}|{{', text) or len(text) < 20:
        return ''
    text = text[0].upper() + text[1:]
    return text if text.endswith(('.', '!', '?')) else text + '.'


def render(template: str, values: dict) -> str:
    return re.sub(r'{{\s*(\w+)\s*}}', lambda m: str(values.get(m.group(1), m.group(0))), template)


# ================================================================ prompts

# ================================================================ real-company research (web search + company website)

SEARCH_QUERIES = {
    'Automotive': ['automotive parts manufacturer', 'commercial vehicle distributor', 'automotive components company'],
    'Mining': ['mining company', 'quarry operator', 'mining equipment supplier'],
    'Industrial': ['industrial engineering company', 'heavy equipment rental company', 'industrial machinery manufacturer'],
}
BLOCKED_DOMAINS = (
    'facebook.com', 'linkedin.com', 'instagram.com', 'twitter.com', 'x.com', 'youtube.com', 'tiktok.com', 'wikipedia.org',
    'yellowpages.my', 'yellowpages.com.sg', 'yelp.com', 'alibaba.com', 'indiamart.com', 'made-in-china.com', 'globalsources.com',
    'jobstreet.com', 'jobstreet.com.my', 'jobstreet.com.sg', 'indeed.com', 'glassdoor.com', 'hiredly.com', 'mycareersfuture.gov.sg',
    'mudah.my', 'carousell.com', 'carousell.com.my', 'carousell.sg', 'lazada.com.my', 'lazada.sg', 'shopee.com.my', 'shopee.sg',
    'amazon.com', 'bloomberg.com', 'reuters.com', 'thestar.com.my', 'nst.com.my', 'straitstimes.com', 'theedgemalaysia.com',
    'theedgesingapore.com', 'businesstimes.com.sg', 'marketscreener.com', 'crunchbase.com', 'zoominfo.com', 'dnb.com',
    'opencorporates.com', 'sgpbusiness.com', 'recordowl.com', 'ctoscredit.com.my', 'kompass.com', 'europages.com', 'tripadvisor.com',
    'google.com', 'statista.com', 'researchandmarkets.com', 'mordorintelligence.com', 'ensun.io', 'f6s.com', 'tracxn.com',
    'medium.com', 'reddit.com', 'quora.com', 'scribd.com', 'slideshare.net', 'bizfile.gov.sg', 'ssm.com.my', 'infobel.com',
    'companieshouse.id', 'malaysiaexporters.com', 'sgbizdir.com', 'businesslist.my', 'cybo.com', 'waze.com', 'foursquare.com',
    # removed by the user after review
    'dullocalminers.com',
)
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
PHONE_RE = re.compile(r'(?:\+\s?\(?6[05]\)?[\s\-.]?\d[\d\s\-.]{6,13}\d|\b0\d{1,2}[\s\-]\d{3,4}[\s\-]?\d{4}\b|\b[689]\d{3}\s\d{4}\b)')
EMAIL_FIND_RE = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
ADDRESS_RE = re.compile(r'([A-Z0-9][^|•]{15,170}?\b\d{5,6}\b[^|•]{0,40}?(?:Malaysia|Singapore))')
NAME_STOP = {'sdn', 'bhd', 'pte', 'ltd', 'berhad', 'the', 'and', 'group', 'company', 'inc', 'limited', 'holdings', 'industries',
             'industry', 'engineering', 'services', 'solutions', 'malaysia', 'singapore', 'asia', 'pacific', 'international', 'corp',
             'corporation', 'enterprise', 'enterprises', 'trading', 'official', 'website', 'home', 'welcome'}


def domain_of(url: str) -> str:
    netloc = urlparse(url if '//' in str(url) else f'https://{url}').netloc.lower().split(':')[0]
    return netloc[4:] if netloc.startswith('www.') else netloc


def is_blocked(domain: str) -> bool:
    if any(domain == b or domain.endswith('.' + b) for b in BLOCKED_DOMAINS):
        return True
    return bool(re.search(r'\.(gov|edu|ac)(\.[a-z]{2})?$', domain))


def web_search(query: str, n: int = 8) -> list:
    """DuckDuckGo search through the ddgs library that ships with Biz GPT (no API key)."""
    from ddgs import DDGS
    return list(DDGS().text(query, max_results=n))


async def search_companies(industries: list, markets: list, existing_domains: set, per_query: int = 6) -> list:
    plan = [(ind, mkt, f'{q} {mkt}') for ind in industries for q in SEARCH_QUERIES.get(ind, [f'{ind} company'])[:2] for mkt in markets][:12]
    batches = await asyncio.gather(*[asyncio.to_thread(web_search, q, per_query) for _, _, q in plan], return_exceptions=True)
    results, seen = [], set(existing_domains)
    for (ind, mkt, q), batch in zip(plan, batches):
        if isinstance(batch, Exception):
            continue
        for r in batch:
            url = r.get('href') or r.get('url') or ''
            d = domain_of(url)
            if not d or d in seen or is_blocked(d):
                continue
            seen.add(d)
            results.append({'n': len(results) + 1, 'title': _text(r.get('title'), 140), 'snippet': _text(r.get('body'), 220),
                            'url': url, 'domain': d, 'website': f'https://{urlparse(url).netloc}', 'industry_hint': ind, 'market_hint': mkt})
    return results[:24]


def pick_schema(industries: list, markets: list) -> dict:
    return {'type': 'object', 'required': ['picks'], 'properties': {'picks': {'type': 'array', 'items': {
        'type': 'object',
        'required': ['result', 'company_name', 'industry', 'country', 'city', 'what_they_do', 'company_size', 'business_relationship',
                     'target_role', 'relevance_score', 'relevance_reason'],
        'properties': {
            'result': {'type': 'integer'}, 'company_name': {'type': 'string'}, 'industry': {'type': 'string', 'enum': industries},
            'country': {'type': 'string', 'enum': markets}, 'city': {'type': 'string'}, 'what_they_do': {'type': 'string'},
            'company_size': {'type': 'string', 'enum': COMPANY_SIZES}, 'business_relationship': {'type': 'string'},
            'target_role': {'type': 'string'}, 'relevance_score': {'type': 'integer'}, 'relevance_reason': {'type': 'string'},
        }}}}}


def pick_prompt(c: dict, industries: list, markets: list, results: list, count: int) -> list:
    listing = '\n'.join(f'[{r["n"]}] {r["title"]} | {r["domain"]} | {r["snippet"]}' for r in results)
    return [
        {'role': 'system', 'content': 'You are a B2B lead researcher. You only use the search results given to you and never add facts. '
         'Return JSON only.'},
        {'role': 'user', 'content': f'Seller: {c["name"]} ({c["description"]}). Target industries: {", ".join(industries)}. '
         f'Markets: {", ".join(markets)}.\n\nWeb search results:\n{listing}\n\n'
         f'Pick up to {min(count * 2, 12)} results that are the OFFICIAL WEBSITE of ONE real company that could buy from or partner with '
         f'{c["name"]}. Skip directories, "top 10" lists, news, marketplaces, job sites, associations and government pages. '
         'Prefer a mix of industries and both markets. For each pick give: result (the number in brackets), company_name exactly as '
         'written in that result, industry, country, city (only if the result states it, else ""), what_they_do (from the snippet, '
         'max 12 words), company_size (Unknown unless the snippet says), business_relationship (how they could work with the seller), '
         'target_role (who to approach, e.g. Procurement Manager), relevance_score 0-100, relevance_reason (one sentence based on the snippet).'},
    ]


def name_grounded(name: str, text: str) -> bool:
    tokens = [t for t in re.findall(r'[a-z0-9]+', name.lower()) if len(t) >= 3 and t not in NAME_STOP]
    return bool(tokens) and any(t in text for t in tokens)


def validate_picks(raw: dict, results: list, industries: list, markets: list) -> tuple:
    """Keep only picks that point at a real search result whose text contains the company name. The URL always comes from the result."""
    by_n = {r['n']: r for r in results}
    picks, rejected, used = [], [], set()
    for item in (raw or {}).get('picks') or []:
        if not isinstance(item, dict):
            continue
        r = by_n.get(item.get('result'))
        name = _text(item.get('company_name'), 120)
        if not r or r['domain'] in used:
            rejected.append({'company_name': name, 'reason': 'unknown or duplicate result'})
            continue
        text = f'{r["title"]} {r["snippet"]} {r["domain"]}'.lower()
        if len(name) < 3 or not name_grounded(name, text):
            rejected.append({'company_name': name, 'reason': 'name not found in the search result'})
            continue
        path = urlparse(r['url']).path.strip('/')
        if not name_grounded(name, r['domain'].replace('-', '')) and (path.count('/') >= 1 or re.search(
                r'exhibitor|directory|listing|member|supplier|compan(y|ies)|brands?|dealers?|partners?|news|blog|article', path, re.I)):
            rejected.append({'company_name': name, 'reason': f'{r["domain"]} is not the company\'s own website'})
            continue
        industry = next((i for i in industries if i.lower() == str(item.get('industry', '')).lower()), r['industry_hint'])
        country = ('Malaysia' if r['domain'].endswith('.my') else 'Singapore' if r['domain'].endswith('.sg')
                   else next((m for m in markets if m.lower() == str(item.get('country', '')).lower()), r['market_hint']))
        if country not in markets:
            rejected.append({'company_name': name, 'reason': f'outside markets ({country})'})
            continue
        city = _text(item.get('city'), 60)
        size = _text(item.get('company_size'), 20).title()
        try:
            score = max(0, min(100, int(float(item.get('relevance_score', 0)))))
        except (TypeError, ValueError):
            score = 50
        used.add(r['domain'])
        picks.append({
            'company_name': name, 'industry': industry, 'country': country,
            'city': city if city and city.lower() in text else '',
            'what_they_do': _text(item.get('what_they_do'), 120), 'company_size': size if size in COMPANY_SIZES else 'Unknown',
            'business_relationship': _text(item.get('business_relationship'), 200), 'target_role': _text(item.get('target_role'), 80),
            'relevance_score': score, 'relevance_reason': _text(item.get('relevance_reason'), 600),
            'website': r['website'], 'search_url': r['url'], 'snippet': r['snippet'],
        })
    picks.sort(key=lambda p: -p['relevance_score'])
    return diversify(picks), rejected


def diversify(picks: list) -> list:
    """Round-robin over (industry, country) groups, best score first in each, so one segment cannot fill the whole list."""
    groups = {}
    for p in picks:
        groups.setdefault((p['industry'], p['country']), []).append(p)
    ordered = []
    while any(groups.values()):
        for key in list(groups):
            if groups[key]:
                ordered.append(groups[key].pop(0))
    return ordered


async def fetch_site(website: str) -> list:
    """Homepage plus the first contact page that answers. Returns [(url, html)]."""
    pages = []
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10, headers={'User-Agent': UA}) as client:
            for path in ('', 'contact', 'contact-us', 'contactus', 'contact-us/'):
                if len(pages) >= 2:
                    break
                try:
                    r = await client.get(website.rstrip('/') + '/' + path)
                except Exception:
                    continue
                if r.status_code == 200 and 'html' in r.headers.get('content-type', '') and not is_bot_challenge(r.text):
                    if not any(str(r.url) == u for u, _ in pages):
                        pages.append((str(r.url), r.text[:400000]))
    except Exception:
        pass
    return pages


def is_bot_challenge(html: str) -> bool:
    head = html[:4000].lower()
    return 'just a moment' in head or 'cf-browser-verification' in head or 'challenge-platform' in head or 'attention required' in head


DOMAIN_NAME_RE = re.compile(r'\.(com|net|org|sg|my|biz|asia|co)\b', re.I)


def name_from_pages(pages: list) -> str:
    """The company name as the site states it: og:site_name, else the <title> part that is not a slogan."""
    for _, html in pages[:1]:
        soup = BeautifulSoup(html[:200000], 'html.parser')
        og = soup.find('meta', attrs={'property': 'og:site_name'})
        if og and _text(og.get('content'), 80):
            return _text(og.get('content'), 80)
        title = _text(soup.title.string if soup.title and soup.title.string else '', 160)
        parts = [p.strip() for p in re.split(r'\s*[|–—]\s*|\s+-\s*|\s*-\s+|:\s', title) if p.strip()]
        if parts:
            return min(parts, key=len)[:80]
    return ''


def _same_site(email_domain: str, site_domain: str) -> bool:
    core = site_domain.split('.')[0] if site_domain.count('.') >= 1 else site_domain
    return email_domain == site_domain or email_domain.endswith('.' + site_domain) or (len(core) >= 4 and core in email_domain)


def phone_for_market(phones: list, country: str) -> str:
    for ph in phones:
        digits = re.sub(r'\D', '', ph)
        if country == 'Malaysia' and (digits.startswith('60') or (ph.strip().startswith('0') and 9 <= len(digits) <= 11)):
            return ph
        if country == 'Singapore' and ((digits.startswith('65') and len(digits) == 10) or (len(digits) == 8 and digits[0] in '689')):
            return ph
    return ''


def clean_address(a: str) -> str:
    a = PHONE_RE.sub(' ', EMAIL_FIND_RE.sub(' ', a or ''))
    if re.search(r'submit|your (full )?name|e-?mail\s*\*|message\s*\*|copyright|all rights', a, re.I):
        return ''
    m = re.search(r'\b(No\.?\s?\d|Lot\s?\d|Level\s?\d|Block\s|Blk\s|Unit\s|Wisma\s|Menara\s|PT\s?\d|\d{1,5}[A-Z]?,?\s+'
                  r'(Jalan|Jln|Lorong|Persiaran|Lebuh|Lebuhraya|Road|Street|Avenue|Ave|Drive|Rd|St|Lane|Way|Loop|Crescent|Link))', a, re.I)
    if m:
        a = a[m.start():]
    a = _text(a, 250)
    return a if len(a) >= 15 else ''


def extract_contacts(pages: list, site_domain: str, country: str = '') -> dict:
    """Phone, general email and address read from the company's own pages (patterns only, no AI)."""
    emails, phones, texts = [], [], []
    for _, html in pages:
        soup = BeautifulSoup(html, 'html.parser')
        emails += [a.get('href', '')[7:].split('?')[0] for a in soup.select('a[href^="mailto:"]')]
        phones += [a.get('href', '')[4:] for a in soup.select('a[href^="tel:"]')]
        for t in soup(['script', 'style', 'noscript', 'svg']):
            t.decompose()
        text = re.sub(r'\s+', ' ', soup.get_text(' ')).strip()
        texts.append(text)
        emails += EMAIL_FIND_RE.findall(text)
        phones += PHONE_RE.findall(text)
    clean_emails = []
    for e in emails:
        e = e.strip().strip('.').lower()
        if (EMAIL_RE.match(e) and not re.search(r'\.(png|jpe?g|gif|webp|svg)$', e)
                and not re.search(r'example|sentry|wixpress|yourdomain|domain\.com|email\.com', e) and e not in clean_emails):
            clean_emails.append(e)
    rank = lambda e: (not _same_site(e.split('@')[1], site_domain),  # noqa: E731
                      next((i for i, k in enumerate(('sales', 'enquir', 'inquir', 'info', 'contact', 'admin')) if e.startswith(k)), 9))
    clean_emails.sort(key=rank)
    email = clean_emails[0] if clean_emails and _same_site(clean_emails[0].split('@')[1], site_domain) else ''
    clean_phones = []
    for ph in phones:
        ph = re.sub(r'\s+', ' ', ph).strip()
        if 8 <= len(re.sub(r'\D', '', ph)) <= 13 and ph not in clean_phones:
            clean_phones.append(ph)
    joined = ' | '.join(texts)
    address = ''
    for a in ADDRESS_RE.finditer(joined):
        if (not country or country in a.group(1)) and (address := clean_address(a.group(1))):
            break
    phone = phone_for_market(clean_phones, country) if country else (clean_phones[0] if clean_phones else '')
    return {'email': email, 'phone': phone, 'address': address, 'text': joined[:6000]}


def build_web_lead(pick: dict, contacts: dict, page_urls: list) -> dict:
    text = (contacts.get('text') or '').lower()
    city = pick['city'] or next((c for c in ('Kuala Lumpur', 'Shah Alam', 'Petaling Jaya', 'Johor Bahru', 'Penang', 'Ipoh', 'Klang',
                                             'Kuching', 'Kota Kinabalu', 'Seremban', 'Melaka', 'Kuantan', 'Singapore')
                                 if c.lower() in (contacts.get('address') or '').lower()), '')
    return {
        'company_name': pick['company_name'], 'industry': pick['industry'], 'sub_segment': pick['what_they_do'],
        'contact_name': '', 'job_title': pick['target_role'] or 'Procurement Manager',
        'email': contacts.get('email', ''), 'phone': contacts.get('phone', ''), 'website': pick['website'],
        'country': pick['country'], 'location': city, 'address': contacts.get('address', ''),
        'company_size': pick['company_size'], 'business_relationship': pick['business_relationship'],
        'source': 'Web search (DuckDuckGo) + company website', 'source_url': ' '.join(dict.fromkeys([*page_urls, pick['search_url']]))[:500],
        'verification_status': 'WEB_SOURCED', 'verified_on': now(),
        'relevance_score': pick['relevance_score'], 'relevance_reason': pick['relevance_reason'],
        'source_excerpt': (pick['snippet'] + ' | ' + (contacts.get('text') or ''))[:3000] if text or pick['snippet'] else pick['snippet'],
        'notes': '', 'status': 'New',
    }


# ================================================================ AI assessment, grounded in the company's own website

RECOMMENDATION_PROPS = {
    'why_recommended': {'type': 'string'},
    'highlights': {'type': 'array', 'items': {'type': 'string'}},
    'recommended_action': {'type': 'string'},
}
RECOMMENDATION_KEYS = list(RECOMMENDATION_PROPS)
RECOMMEND_BATCH = 3


def _guide(c: dict) -> str:
    return (f'why_recommended (2 full sentences: why this company is a good prospect for {c["name"]}, based on what the website text '
            f'says they do, and what {c["name"]} could offer them), highlights (3 short facts about the company taken from the website '
            'text, max 14 words each, e.g. products, services, branches, years in business, certifications, brands, fleet or plant details; '
            'only facts stated in the text), recommended_action (one concrete next step for the target role, naming what to offer).')


RECOMMEND_SYSTEM = ('You are a B2B sales analyst. Use ONLY facts found in the website text you are given. Never invent numbers, revenue, '
                    'customers, awards or people. No links, emails or phone numbers. Return JSON only.')


def recommend_schema() -> dict:
    return {'type': 'object', 'required': RECOMMENDATION_KEYS, 'properties': RECOMMENDATION_PROPS}


def recommend_batch_schema(lead_ids: list) -> dict:
    return {'type': 'object', 'required': ['items'], 'properties': {'items': {'type': 'array', 'items': {
        'type': 'object', 'required': ['lead_id', *RECOMMENDATION_KEYS],
        'properties': {'lead_id': {'type': 'string', 'enum': lead_ids}, **RECOMMENDATION_PROPS}}}}}


def _profile(lead_id: str, d: dict, excerpt: int) -> str:
    return (f'lead_id {lead_id}: {d.get("company_name")} ({d.get("industry")}, {d.get("country")}), target role {d.get("job_title")}. '
            f'Website text: """{(d.get("source_excerpt") or "")[:excerpt]}"""')


def recommend_batch_prompt(c: dict, leads: list) -> list:
    profiles = '\n\n'.join(_profile(lead['id'], lead['data'], 1200) for lead in leads)
    return [{'role': 'system', 'content': RECOMMEND_SYSTEM},
            {'role': 'user', 'content': f'Seller: {c["name"]} ({c["description"]}).\n\nProspects:\n{profiles}\n\n'
             f'Return one item per prospect ({len(leads)} items), each with its lead_id and: ' + _guide(c)}]


def recommend_prompt(c: dict, d: dict) -> list:
    return [{'role': 'system', 'content': RECOMMEND_SYSTEM},
            {'role': 'user', 'content': f'Seller: {c["name"]} ({c["description"]}).\n\nProspect: {_profile("-", d, 2500)}\n\nGive: ' + _guide(c)}]


def clean_web_recommendation(item: dict, d: dict) -> dict:
    """Drop any highlight with a number or money claim that is not in the company's own text."""
    source = (d.get('source_excerpt') or '').lower()
    highlights = []
    for h in item.get('highlights') or []:
        h = _text(h, 160)
        if not h or re.search(r'https?://|www\.|@', h) or h.lower() in (x.lower() for x in highlights):
            continue
        if any(n.strip('.,') not in source for n in re.findall(r'\d[\d,.]*', h)):
            continue
        if re.search(r'revenue|turnover|profit|usd|rm\s?\d|\$', h, re.I) and not re.search(r'revenue|turnover|profit', source):
            continue
        highlights.append(h)
    action = _text(item.get('recommended_action'), 200)
    why = _text(item.get('why_recommended') or item.get('recommendation'), 800)
    if len(why) < 40 or why.lower() == action.lower():
        why = _text(d.get('relevance_reason'), 800)
    return {'recommendation': why, 'highlights': highlights[:4], 'recommended_action': action}


def _context_prompt(c: dict, d: dict) -> list:
    return [
        {'role': 'system', 'content': 'You write one short, specific, polite sentence for a B2B outreach email. No greetings, '
         'no sign-off, no links, no phone numbers, no email addresses, no claims of facts about the prospect. Return JSON only.'},
        {'role': 'user', 'content': f'Sender company: {c["name"]} (industries: {", ".join(c["industries"])}).\n'
         f'Prospect: {d.get("company_name")}, {d.get("industry")} / {d.get("sub_segment")}, {d.get("location")}, {d.get("country")}.\n'
         f'Possible relationship: {d.get("business_relationship")}.\nWhy relevant: {d.get("relevance_reason")}\n\n'
         'Write business_context: ONE new sentence (max 30 words) that starts with "For example," and names one concrete area '
         'where the two companies could work together. Do not repeat the words "relevant areas" or "explore potential collaboration".'},
    ]


# ================================================================ in-chat UI (self-contained HTML embeds)

CSS = '''
*{box-sizing:border-box}body{margin:0;font-family:Inter,system-ui,Arial,sans-serif;color:#0f172a;background:transparent;font-size:14px}
.card{border:1px solid #e2e8f0;border-radius:16px;background:#fff;overflow:hidden;margin-bottom:12px}
.head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 18px;border-bottom:1px solid #e2e8f0;background:#f8fafc;flex-wrap:wrap}
.eyebrow{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#64748b}
.title{margin-top:2px;font-size:17px;font-weight:650}.sec{padding:14px 18px}.sec+.sec{border-top:1px solid #f1f5f9}
.label{font-size:12px;font-weight:600;color:#64748b;margin-bottom:8px}
.grid{display:grid;grid-template-columns:minmax(120px,32%) 1fr;gap:6px 14px}.k{color:#64748b}.v{font-weight:550;overflow-wrap:anywhere}
.chips{display:flex;flex-wrap:wrap;gap:6px}.chip{padding:4px 10px;border-radius:999px;background:#eef2ff;color:#3730a3;font-size:12.5px;font-weight:600}
.badge{display:inline-block;padding:3px 9px;border-radius:999px;font-size:11.5px;font-weight:700;white-space:nowrap}
.b-web_sourced{background:#dbeafe;color:#1e40af}.b-verified{background:#dcfce7;color:#166534}.b-unverified{background:#e2e8f0;color:#334155}
.b-test{background:#ede9fe;color:#5b21b6}.b-ok{background:#dcfce7;color:#166534}.b-fail{background:#fee2e2;color:#991b1b}.b-draft{background:#e0f2fe;color:#075985}
.r-High{background:#dcfce7;color:#166534}.r-Medium{background:#fef9c3;color:#854d0e}.r-Low{background:#f1f5f9;color:#475569}
button{border:0;border-radius:10px;padding:8px 14px;font:600 13px Inter,system-ui,sans-serif;cursor:pointer;background:#0f172a;color:#fff}
button.ghost{background:#fff;color:#0f172a;border:1px solid #cbd5e1}button.green{background:#16a34a}button:disabled{opacity:.5;cursor:default}
.actions{display:flex;flex-wrap:wrap;gap:8px;padding:12px 18px;border-top:1px solid #e2e8f0;background:#f8fafc}
.filters{display:flex;flex-wrap:wrap;gap:8px;padding:12px 18px;border-bottom:1px solid #e2e8f0}
select,input,textarea{font:13.5px Inter,system-ui,sans-serif;padding:7px 9px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;color:#0f172a}
textarea{width:100%;resize:vertical}.filters input{flex:1;min-width:160px}
.lead{border:1px solid #e2e8f0;border-radius:12px;margin:10px 18px;overflow:hidden}.lead.new{border-color:#818cf8}
.lead .top{display:flex;justify-content:space-between;gap:10px;padding:10px 14px;background:#f8fafc;flex-wrap:wrap;align-items:center}
.lead .name{font-weight:650;font-size:15px}.lead .body{padding:10px 14px}.lead .grid{font-size:13px}
.lead .actions{padding:8px 14px}.muted{color:#64748b;font-size:12.5px}.empty{padding:18px;color:#64748b}
.form{display:grid;grid-template-columns:1fr 1fr;gap:10px 14px}.form .full{grid-column:1/-1}
.form label{display:block;font-size:12px;font-weight:600;color:#475569;margin-bottom:4px}.form input,.form select,.form textarea{width:100%}
.form .dirty{border-color:#6366f1;background:#eef2ff}.req{color:#dc2626}
.mail{border:1px solid #e2e8f0;border-radius:12px;background:#f8fafc}.mail .meta{padding:10px 12px;border-bottom:1px solid #e2e8f0;line-height:1.7}
.mail pre{margin:0;padding:12px;white-space:pre-wrap;font:inherit;line-height:1.55}.warn{background:#faf5ff;border:1px solid #ddd6fe;border-radius:10px;padding:10px 12px;color:#5b21b6;font-size:13px;line-height:1.6}
.rec{margin-top:10px;border:1px solid #c7d2fe;background:#eef2ff;border-radius:10px;padding:10px 12px}
.rec .t{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#4338ca;margin-bottom:6px;display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
.rec p{margin:0 0 8px;line-height:1.5}.rec ul{margin:0 0 8px;padding-left:0;list-style:none}.rec li{padding:2px 0 2px 22px;position:relative}
.rec li:before{content:'★';position:absolute;left:2px;color:#f59e0b}.metrics{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px}
.metric{background:#fff;border:1px solid #c7d2fe;border-radius:8px;padding:4px 8px;font-size:12.5px}.metric b{font-size:13.5px}
.up{color:#15803d}.down{color:#b91c1c}.next{font-size:13px}.est{font-size:11px;color:#6366f1;font-weight:600;text-transform:none;letter-spacing:0}
.picks{padding:10px 18px;border-bottom:1px solid #e2e8f0;background:#fffbeb;font-size:13px;line-height:1.6}
a{color:#2563eb;text-decoration:none}a:hover{text-decoration:underline}
.ok-big{font-size:18px;font-weight:700;color:#166534}.fail-big{font-size:18px;font-weight:700;color:#991b1b}
@media (max-width:560px){.form{grid-template-columns:1fr}.grid{grid-template-columns:1fr}}
@media (prefers-color-scheme:dark){body{color:#e2e8f0}.card,.lead{background:#0f172a;border-color:#1e293b}
.head,.actions,.mail,.lead .top{background:#111827;border-color:#1e293b}select,input,textarea,button.ghost{background:#0f172a;color:#e2e8f0;border-color:#334155}
.sec+.sec,.filters{border-color:#1e293b}.rec{background:#1e1b4b;border-color:#3730a3}.rec .t{color:#a5b4fc}
.metric{background:#0f172a;border-color:#3730a3}.picks{background:#1c1917;border-color:#1e293b}.chip{background:#1e1b4b;color:#c7d2fe}.warn{background:#1e1b4b;border-color:#3730a3;color:#c4b5fd}}
'''

BRIDGE = '''
const post=(m)=>window.parent!==window&&window.parent.postMessage(m,'*');
const height=()=>post({type:'iframe:height',height:document.documentElement.scrollHeight});
new ResizeObserver(height).observe(document.body);height();
let busy=false;const ask=(text)=>{if(busy)return;busy=true;document.querySelectorAll('button').forEach(b=>b.dataset.was=b.disabled);
document.querySelectorAll('button').forEach(b=>b.disabled=true);post({type:'input:prompt:submit',text});
setTimeout(()=>{busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=b.dataset.was==='true')},4000)};
'''


def _page(body: str, script: str = '', data=None) -> str:
    data_tag = ''
    if data is not None:
        data_tag = '<script type="application/json" id="data">' + json.dumps(data).replace('</', '<\\/') + '</script>'
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>{body}{data_tag}'
            f'<script>{BRIDGE}{script}</script></body></html>')


def _verif_badge(v: str) -> str:
    v = v or 'WEB_SOURCED'
    label = {'WEB_SOURCED': 'REAL COMPANY · WEB SOURCED', 'VERIFIED': 'VERIFIED LEAD', 'UNVERIFIED': 'NOT VERIFIED'}.get(v, v)
    return f'<span class="badge b-{esc(v.lower())}">{esc(label)}</span>'


def _profile_html(c: dict, counts: dict, template: dict) -> str:
    chips = ''.join(f'<span class="chip">{esc(i)}{f" · {counts[i]} leads" if counts.get(i) else ""}</span>' for i in c['industries'])
    markets = ''.join(f'<span class="chip">{esc(m)}</span>' for m in c['markets'])
    buttons = ''.join(f'<button class="ghost" data-ask="Generate 4 leads for {esc(c["name"])} in the {esc(i)} industry">{esc(i)} leads</button>'
                      for i in c['industries'])
    body = f'''<div class="card"><div class="head"><div><div class="eyebrow">Customer profile · Lead Generation POC</div>
<div class="title">{esc(c['name'])}</div></div><span class="badge b-test">{ENVIRONMENT}</span></div>
<div class="sec"><div class="label">Industries</div><div class="chips">{chips}</div></div>
<div class="sec"><div class="label">Geographic markets</div><div class="chips">{markets}</div></div>
<div class="sec"><div class="label">Context</div>{esc(c['description'])}</div>
<div class="sec"><div class="label">Outreach</div><div class="grid"><div class="k">Email template</div><div class="v">{esc(template['subject'])}</div>
<div class="k">Test delivery</div><div class="v">All emails go to {POC_RECIPIENT}</div></div></div>
<div class="actions"><button data-ask="Generate 6 leads for {esc(c['name'])} across all its industries">Generate leads (all industries)</button>{buttons}
<button class="ghost" data-ask="Show the {esc(c['name'])} lead list">View lead list</button></div></div>'''
    script = "document.querySelectorAll('[data-ask]').forEach(b=>b.onclick=()=>{b.disabled=true;ask(b.dataset.ask)});"
    return _page(body, script)


def _lead_list_html(c: dict, leads: list, highlight: Optional[list] = None, title: str = 'Real Company Leads', filters: Optional[dict] = None) -> str:
    rows = [{'id': lead['id'], **{k: v for k, v in lead['data'].items() if k != 'source_excerpt'}, 'relevance': relevance_label(lead['data'].get('relevance_score')),
             'new': lead['id'] in (highlight or [])} for lead in leads]
    industries = sorted(set(c['industries']) | {r['industry'] for r in rows})
    opt = lambda items: ''.join(f'<option>{esc(i)}</option>' for i in items)  # noqa: E731
    body = f'''<div class="card"><div class="head"><div><div class="eyebrow">Customer: {esc(c['name'])} · Industry: {esc(' + '.join(c['industries']))}</div>
<div class="title">{esc(title)}</div></div><span class="muted" id="count"></span></div>
<div class="filters"><select id="f-ind"><option value="">Industry: All</option>{opt(industries)}</select>
<select id="f-rel"><option value="">Relevance: All</option>{opt(['High', 'Medium', 'Low'])}</select>
<select id="f-st"><option value="">Status: All</option>{opt(STATUSES)}</select>
<select id="f-sort"><option value="rel">Sort: AI relevance</option><option value="rev">Sort: Est. revenue</option><option value="new">Sort: Newest</option></select>
<input id="f-q" placeholder="Search companies…"></div>{_top_picks_html(rows)}<div id="list"></div>
<div class="sec muted">Companies were found by web search; website, phone, email and address come from each company's own site (see Source). The AI assessment is a model opinion based on that site. Check details before real outreach.</div></div>'''
    script = f'''
const leads=JSON.parse(document.getElementById('data').textContent);const init={json.dumps(filters or {})};
const $=(id)=>document.getElementById(id);const e=(s)=>String(s??'').replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]));
const vb=(v)=>{{v=v||'WEB_SOURCED';const l={{WEB_SOURCED:'REAL COMPANY · WEB SOURCED',VERIFIED:'VERIFIED LEAD',UNVERIFIED:'NOT VERIFIED'}}[v]||v;return `<span class="badge b-${{v.toLowerCase()}}">${{l}}</span>`}};
const link=(u,t)=>u?`<a href="${{e(u)}}" target="_blank" rel="noopener noreferrer">${{e(t||u)}}</a>`:'—';
const lrow=(k,h)=>`<div class="k">${{k}}</div><div class="v">${{h}}</div>`;
const row=(k,v)=>`<div class="k">${{k}}</div><div class="v">${{e(v)||'—'}}</div>`;
const money=(m)=>m==null||m===''?'':(m>=1000?`USD ${{(m/1000).toFixed(1)}}B`:`USD ${{Number(m).toFixed(1).replace(/\.0$/,'')}}M`);
function rec(l){{if(!l.recommendation)return `<div class="rec"><div class="t">AI Recommendation</div><p class="muted">No AI recommendation yet.</p>
<button class="ghost" data-ask="Get AI recommendation for lead ${{l.id}}">Get AI recommendation</button></div>`;
const g=Number(l.revenue_growth_pct||0);const hs=(l.highlights||[]).map(h=>`<li>${{e(h)}}</li>`).join('');
const hasRev=l.est_revenue_musd!=null&&l.est_revenue_musd!=='';
return `<div class="rec"><div class="t"><span>AI Recommendation · why ${{e(l.company_name)}}</span><span class="est">AI assessment based on the company's website</span></div>
<div class="metrics"><span class="metric">Revenue last year <b>${{hasRev?money(l.est_revenue_musd):'Not publicly disclosed'}}</b></span>
${{hasRev&&l.revenue_growth_pct!=null&&l.revenue_growth_pct!==''?`<span class="metric">Growth <b class="${{g>=0?'up':'down'}}">${{g>=0?'▲':'▼'}} ${{Math.abs(g)}}%</b></span>`:''}}
${{l.employees?`<span class="metric">Employees <b>${{Number(l.employees).toLocaleString()}}</b></span>`:''}}
${{l.company_size&&l.company_size!=='Unknown'?`<span class="metric">Size <b>${{e(l.company_size)}}</b></span>`:''}}</div>
<p>${{e(l.recommendation)}}</p>${{hs?`<ul>${{hs}}</ul>`:''}}${{l.recommended_action?`<div class="next"><b>Recommended next step:</b> ${{e(l.recommended_action)}}</div>`:''}}</div>`}}
function card(l){{return `<div class="lead ${{l.new?'new':''}}"><div class="top"><div><div class="name">${{e(l.company_name)}}</div>
<div class="muted">${{e(l.id)}} · ${{e(l.industry)}}${{l.sub_segment?' · '+e(l.sub_segment):''}}</div></div>
<div>${{vb(l.verification_status)}} <span class="badge r-${{l.relevance}}">${{l.relevance}} · ${{l.relevance_score}}%</span></div></div>
<div class="body"><div class="grid">${{row('Location',[l.location,l.country].filter(Boolean).join(', '))}}${{l.address?row('Address',l.address):''}}
${{lrow('Website',link(l.website,(l.website||'').replace(/^https?:\/\//,'')))}}${{row('Phone',l.phone||'Not listed on website')}}
${{row('Contact',(l.contact_name||'General enquiries')+(l.job_title?' · target: '+l.job_title:''))}}${{row('Email',l.email||'Not listed on website')}}
${{row('Reason',l.relevance_reason)}}${{row('Status',l.status)}}${{lrow('Source',(l.source_url||'').split(' ').filter(Boolean).slice(0,2).map(u=>link(u,u.replace(/^https?:\/\//,'').slice(0,60))).join('<br>')||'—')}}</div>${{rec(l)}}</div>
<div class="actions"><button class="ghost" data-ask="Open lead ${{l.id}} details">View Details</button><button class="ghost" data-ask="Edit lead ${{l.id}}">Edit</button>
<button data-ask="Generate outreach email for lead ${{l.id}}">Send Email</button></div></div>`}}
function draw(){{const i=$('f-ind').value,r=$('f-rel').value,s=$('f-st').value,q=$('f-q').value.toLowerCase();
const so=$('f-sort').value;const shown=leads.filter(l=>(!i||l.industry===i)&&(!r||l.relevance===r)&&(!s||l.status===s)&&(!q||(l.company_name+' '+l.location+' '+l.sub_segment+' '+l.contact_name+' '+(l.recommendation||'')).toLowerCase().includes(q)))
.sort((a,b)=>so==='rev'?(b.est_revenue_musd||0)-(a.est_revenue_musd||0):so==='new'?b.id.localeCompare(a.id):(b.relevance_score||0)-(a.relevance_score||0));
$('list').innerHTML=shown.map(card).join('')||'<div class="empty">No leads match these filters.</div>';$('count').textContent=`${{shown.length}} of ${{leads.length}} leads`;
document.querySelectorAll('[data-ask]').forEach(b=>b.onclick=()=>ask(b.dataset.ask));height();}}
$('f-ind').value=init.industry||'';$('f-st').value=init.status||'';$('f-q').value=init.search||'';
['f-ind','f-rel','f-st','f-sort'].forEach(id=>$(id).onchange=draw);$('f-q').oninput=draw;draw();'''
    return _page(body, script, rows)


def _top_picks_html(rows: list) -> str:
    picks = sorted([r for r in rows if r.get('recommendation')], key=lambda r: -(r.get('relevance_score') or 0))[:3]
    if len(rows) < 2 or not picks:
        return ''
    items = ' · '.join(f'<b>{esc(r["company_name"])}</b> ({r.get("relevance_score")}%, {esc(r.get("industry", ""))})' for r in picks)
    return f'<div class="picks">⭐ <b>AI top picks:</b> {items}</div>'


def _lead_form_html(lead: dict, c: dict, emails: list, saved: Optional[list] = None) -> str:
    fields = [{**f, 'options': c['industries'] if f.get('options') == 'industries' else f.get('options')} for f in LEAD_FIELDS]
    d = lead['data']
    history = ''.join(f'<div class="k">{esc(m["id"])}</div><div class="v">{esc(m["email_status"])} · {esc(m["subject"])}</div>' for m in emails[:5])
    saved_note = f'<span class="badge b-ok">Saved: {esc(", ".join(saved))}</span>' if saved else ''
    body = f'''<div class="card"><div class="head"><div><div class="eyebrow">Lead details · {esc(lead['id'])}</div>
<div class="title">{esc(d.get('company_name'))}</div></div><div>{saved_note} {_verif_badge(d.get('verification_status'))}
<span class="badge r-{relevance_label(d.get('relevance_score'))}">{relevance_label(d.get('relevance_score'))} relevance</span></div></div>
<div class="sec"><div class="form" id="form"></div></div>
{f'<div class="sec"><div class="label">Emails</div><div class="grid">{history}</div></div>' if history else ''}
<div class="actions"><button id="save" disabled>Save Lead</button><button class="ghost" id="email">Generate Email</button><button class="ghost" id="recbtn">AI Recommendation</button><span class="muted" id="note"></span></div></div>'''
    script = f'''
const D=JSON.parse(document.getElementById('data').textContent);const F=D.fields,V=D.values,ID={json.dumps(lead['id'])};
const form=document.getElementById('form');const e=(s)=>String(s??'').replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]));
F.forEach(f=>{{const w=document.createElement('div');if(f.type==='textarea'||f.type==='lines')w.className='full';
const v=V[f.key]??'';let input;
if(f.type==='lines'){{input=`<textarea rows="4">${{e(Array.isArray(v)?v.join('\n'):v)}}</textarea>`}}
else if(f.type==='select'){{input=`<select>${{(f.options||[]).map(o=>`<option ${{o===v?'selected':''}}>${{e(o)}}</option>`).join('')}}</select>`}}
else if(f.type==='textarea'){{input=`<textarea rows="3">${{e(v)}}</textarea>`}}
else{{input=`<input type="${{f.type==='number'?'number':f.type==='email'?'email':'text'}}" value="${{e(v)}}" ${{f.readonly?'readonly':''}} ${{f.max&&f.type!=='number'?'maxlength='+f.max:''}}>`}}
w.innerHTML=`<label>${{e(f.label)}} ${{f.required?'<span class="req">*</span>':''}}</label>${{input}}`;
const el=w.querySelector('input,select,textarea');el.dataset.key=f.key;el.oninput=el.onchange=check;form.appendChild(w)}});
function changes(){{const out={{}};form.querySelectorAll('[data-key]').forEach(el=>{{const k=el.dataset.key;const f=F.find(x=>x.key===k);if(f.readonly)return;
let v=el.value;if(f.type==='number')v=v===''?'':Number(v);const old=Array.isArray(V[k])?V[k].join('\n'):(V[k]??'');if(String(v)!==String(old)){{out[k]=v;el.classList.add('dirty')}}else el.classList.remove('dirty')}});return out}}
function check(){{const c=changes();document.getElementById('save').disabled=!Object.keys(c).length;document.getElementById('note').textContent=Object.keys(c).length?Object.keys(c).length+' unsaved change(s)':''}}
document.getElementById('save').onclick=()=>{{const c=changes();if(!Object.keys(c).length)return;document.getElementById('save').disabled=true;
document.getElementById('note').textContent='Sent to chat for saving…';ask(`Save lead ${{ID}} changes: ${{JSON.stringify(c)}}`)}};
document.getElementById('email').onclick=()=>ask(`Generate outreach email for lead ${{ID}}`);
document.getElementById('recbtn').onclick=()=>ask(`Get AI recommendation for lead ${{ID}}`);'''
    return _page(body, script, {'fields': fields, 'values': {k: v for k, v in d.items() if k != 'source_excerpt'}})


def _email_status_badge(status: str) -> str:
    cls = {'DRAFT': 'b-draft', 'TEST_SENT': 'b-ok', 'FAILED': 'b-fail'}.get(status, 'b-draft')
    label = {'DRAFT': 'DRAFT · TEST EMAIL', 'TEST_SENT': 'TEST EMAIL SENT', 'FAILED': 'SEND FAILED'}.get(status, status)
    return f'<span class="badge {cls}">{esc(label)}</span>'


def _email_preview_html(e: dict, lead: dict, saved: bool = False) -> str:
    d = lead['data']
    body = f'''<div class="card"><div class="head"><div><div class="eyebrow">Email preview · {esc(e['id'])} · {esc(lead['id'])}</div>
<div class="title">{esc(d.get('company_name'))}</div></div><div>{'<span class="badge b-ok">Edits saved</span> ' if saved else ''}{_email_status_badge(e['email_status'])}</div></div>
<div class="sec"><div class="warn"><b>Original Lead Email:</b> {esc(e['intended_recipient'] or '—')} (not contacted)<br>
<b>POC Delivery Email:</b> {esc(e['actual_recipient'])}<br><b>Environment:</b> {esc(e['environment'])} · <b>Status:</b> TEST EMAIL</div></div>
<div class="sec"><div class="mail" id="view"><div class="meta"><b>To:</b> {esc(e['intended_recipient'])} → delivered to {esc(e['actual_recipient'])}<br>
<b>Subject:</b> <span id="s">{esc(e['subject'])}</span></div><pre id="b">{esc(e['body'])}</pre></div>
<div id="edit" style="display:none"><label class="label">Subject</label><input id="es" style="width:100%;margin-bottom:10px" maxlength="200">
<label class="label">Body</label><textarea id="eb" rows="14"></textarea></div></div>
<div class="actions"><button class="ghost" id="toggle">Edit Email</button><button class="ghost" id="savebtn" style="display:none">Save changes</button>
<button class="green" id="send">Send Test Email</button><span class="muted" id="note"></span></div></div>'''
    script = f'''
const E={json.dumps({'id': e['id'], 'subject': e['subject'], 'body': e['body'], 'status': e['email_status']})};
const $=(id)=>document.getElementById(id);let editing=false;
if(E.status!=='DRAFT'){{['toggle','send'].forEach(id=>$(id).disabled=true);$('note').textContent='Already '+E.status.toLowerCase().replace('_',' ')}}
const dirty=()=>editing&&($('es').value!==E.subject||$('eb').value!==E.body);
$('toggle').onclick=()=>{{editing=!editing;$('view').style.display=editing?'none':'';$('edit').style.display=editing?'':'none';$('savebtn').style.display=editing?'':'none';
$('toggle').textContent=editing?'Cancel edit':'Edit Email';if(editing){{$('es').value=E.subject;$('eb').value=E.body}};upd();height()}};
function upd(){{$('send').disabled=E.status!=='DRAFT'||dirty();$('note').textContent=dirty()?'Save changes before sending':''}}
$('es').oninput=$('eb').oninput=upd;
$('savebtn').onclick=()=>{{if(!dirty())return;$('savebtn').disabled=true;ask(`Update email ${{E.id}}\\nSUBJECT: ${{$('es').value}}\\nBODY:\\n${{$('eb').value}}`)}};
$('send').onclick=()=>{{$('send').disabled=true;$('toggle').disabled=true;$('note').textContent='Sending request posted to chat for confirmation…';ask(`Send test email ${{E.id}}`)}};'''
    return _page(body, script)


def _send_result_html(e: dict, lead: dict) -> str:
    ok = e['email_status'] == 'TEST_SENT'
    rows = [('Lead', f'{lead["data"].get("company_name")} ({lead["id"]})'), ('Original Intended Recipient', e['intended_recipient']),
            ('Actual POC Recipient', e['actual_recipient']), ('Subject', f'[TEST] {e["subject"]}'), ('Environment', e['environment']),
            ('Status', 'TEST EMAIL SENT' if ok else 'FAILED'), ('Sent at', e.get('sent_at')), ('Gmail message id', e.get('gmail_message_id'))]
    if not ok:
        rows.append(('Error', e.get('error')))
    grid = ''.join(f'<div class="k">{esc(k)}</div><div class="v">{esc(str(v or "—"))}</div>' for k, v in rows)
    head = '<div class="ok-big">✓ Email Sent</div>' if ok else '<div class="fail-big">✕ Email not sent</div>'
    body = f'''<div class="card"><div class="head"><div><div class="eyebrow">Email send result · {esc(e['id'])}</div>{head}</div>
{_email_status_badge(e['email_status'])}</div><div class="sec"><div class="grid">{grid}</div></div>
<div class="sec muted">POC safety: delivery is fixed to {POC_RECIPIENT}; the lead's address was not contacted.</div></div>'''
    return _page(body)


def _template_html(t: dict) -> str:
    chips = ''.join(f'<span class="chip">{{{{{p}}}}}</span>' for p in PLACEHOLDERS)
    body = f'''<div class="card"><div class="head"><div><div class="eyebrow">Reusable outreach template</div><div class="title">Email template</div></div>
<span class="muted">updated {esc(t.get('updated_at') or '')}</span></div><div class="sec"><div class="mail"><div class="meta"><b>Subject:</b> {esc(t['subject'])}</div>
<pre>{esc(t['body'])}</pre></div></div><div class="sec"><div class="label">Placeholders</div><div class="chips">{chips}</div></div></div>'''
    return _page(body)
