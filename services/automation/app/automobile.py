"""Automobile client lead capture: score an enquiry and write the email that goes to the sales team.

Scoring is plain rules (not AI) so the grade is explainable and the same every time.
"""

import os
import re

# Leads go to this one address only; it is never taken from the form (the customer is not emailed).
LEADS_EMAIL_TO = os.getenv('AUTOMOBILE_LEADS_EMAIL_TO', 'prsap94@gmail.com').strip()

TIMELINE_POINTS = {
    'Within 2 weeks': 35,
    'Within 1 month': 25,
    '1-3 months': 15,
    '3+ months': 5,
    'Just exploring': 0,
}
FINANCE_POINTS = {'Loan needed': 15, 'Cash / full payment': 15, 'Not decided': 5}
NEXT_ACTION = {
    'Hot': 'Call within 1 hour and book the test drive / showroom visit.',
    'Warm': 'Call today, share the brochure and on-road price, and offer a test drive.',
    'Cold': 'Add to the nurture list: send the brochure and follow up in 2 weeks.',
}
FIELDS = [
    ('customer_name', 'Name'), ('customer_phone', 'Phone'), ('customer_email', 'Email'), ('city', 'City'),
    ('vehicle_type', 'Vehicle type'), ('model_interest', 'Model of interest'), ('fuel_type', 'Fuel'),
    ('budget', 'Budget'), ('purchase_timeline', 'Purchase timeline'), ('finance', 'Finance'),
    ('trade_in', 'Trade-in'), ('test_drive', 'Test drive'), ('preferred_contact_time', 'Best time to call'),
    ('lead_source', 'Lead source'), ('notes', 'Notes'),
]


def valid_recipient(address: str) -> bool:
    return bool(re.fullmatch(r'[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+', address or ''))


def score_lead(values: dict) -> dict:
    points, reasons = 0, []

    def add(n: int, why: str):
        nonlocal points
        if n:
            points += n
            reasons.append(f'+{n} {why}')

    timeline = values.get('purchase_timeline')
    add(TIMELINE_POINTS.get(timeline, 0), f'buying {str(timeline).lower()}')
    if values.get('test_drive') == 'Yes':
        add(20, 'wants a test drive')
    finance = values.get('finance')
    add(FINANCE_POINTS.get(finance, 0), f'finance: {str(finance).lower()}')
    if values.get('trade_in') == 'Yes':
        add(10, 'has a trade-in')
    if str(values.get('model_interest') or '').strip():
        add(10, 'specific model in mind')
    if values.get('budget'):
        add(5, 'budget stated')
    if str(values.get('customer_email') or '').strip():
        add(5, 'email given')
    points = min(points, 100)
    grade = 'Hot' if points >= 65 else 'Warm' if points >= 40 else 'Cold'
    return {'score': points, 'grade': grade, 'reasons': reasons, 'next_action': NEXT_ACTION[grade]}


def lead_email(reference: str, values: dict, scored: dict, submitted_by: str | None) -> tuple[str, str]:
    vehicle = values.get('model_interest') or values.get('vehicle_type') or 'vehicle'
    subject = f'[{scored["grade"]} lead {scored["score"]}/100] {values.get("customer_name", "New enquiry")} - {vehicle} ({reference})'
    width = max(len(label) for _, label in FIELDS)
    rows = [f'{label.ljust(width)} : {values[key]}' for key, label in FIELDS if values.get(key) not in (None, '')]
    body = '\n'.join([
        'New automobile sales lead from Biz GPT.',
        '',
        f'Reference   : {reference}',
        f'Lead grade  : {scored["grade"]} ({scored["score"]}/100)',
        f'Next action : {scored["next_action"]}',
        '',
        'Customer and enquiry',
        '--------------------',
        *rows,
        '',
        'Why this grade',
        '--------------',
        *(scored['reasons'] or ['No buying signals given yet.']),
        '',
        f'Captured by {submitted_by or "Biz GPT"}. This email goes only to the sales inbox; the customer has not been contacted.',
    ])
    return subject, body
