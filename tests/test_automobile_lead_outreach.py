"""Offline tests for the Automobile Lead Outreach tool (no web, no model, no email).
Run inside the Biz GPT container: python3 tests/test_automobile_lead_outreach.py owui/tools/automobile_lead_outreach.py"""
import asyncio, importlib.util, json, os, sys, tempfile

path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'owui', 'tools', 'automobile_lead_outreach.py')
spec = importlib.util.spec_from_file_location('alo', path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

RESULTS = [
    {'n': 1, 'title': 'Autonas | Automotive Spare Parts Distributor', 'snippet': 'Autonas is a spare parts wholesaler in Shah Alam.',
     'url': 'https://www.autonas.com.my/about', 'domain': 'autonas.com.my', 'website': 'https://www.autonas.com.my',
     'industry_hint': 'Automotive', 'market_hint': 'Malaysia'},
    {'n': 2, 'title': 'Top 10 mining companies', 'snippet': 'A list of miners.', 'url': 'https://list.example.org/x',
     'domain': 'list.example.org', 'website': 'https://list.example.org', 'industry_hint': 'Mining', 'market_hint': 'Singapore'},
    {'n': 3, 'title': 'Granite Quarry Pte Ltd', 'snippet': 'Quarry operator.', 'url': 'https://granitequarry.sg/',
     'domain': 'granitequarry.sg', 'website': 'https://granitequarry.sg', 'industry_hint': 'Mining', 'market_hint': 'Singapore'},
]
HTML = '''<html><body><h1>Autonas Sdn Bhd</h1><p>Established 1998, 3 branches, distributor of 20,000 parts.</p>
<a href="mailto:sales@autonas.com.my">Email</a><a href="tel:+603-5122 1234">Call</a>
<p>Lot 5, Jalan Utas 15/7, Seksyen 15, 40200 Shah Alam, Selangor, Malaysia</p>
<p>Follow john@gmail.com logo@2x.png</p></body></html>'''


def test_validate_picks():
    raw = {'picks': [
        {'result': 1, 'company_name': 'Autonas', 'industry': 'Automotive', 'country': 'Singapore', 'city': 'Shah Alam', 'relevance_score': 91},
        {'result': 1, 'company_name': 'Autonas again', 'industry': 'Automotive'},            # duplicate domain
        {'result': 3, 'company_name': 'Imaginary Mining Corp', 'industry': 'Mining'},       # name not in the result
        {'result': 9, 'company_name': 'Ghost', 'industry': 'Mining'},                       # no such result
        {'result': 3, 'company_name': 'Granite Quarry', 'industry': 'Mining', 'city': 'Jurong', 'relevance_score': 70},
    ]}
    picks, rejected = m.validate_picks(raw, RESULTS, ['Automotive', 'Mining'], ['Singapore', 'Malaysia'])
    assert [p['company_name'] for p in picks] == ['Autonas', 'Granite Quarry'], picks
    a, g = picks
    assert a['country'] == 'Malaysia' and a['city'] == 'Shah Alam' and a['website'] == 'https://www.autonas.com.my'  # TLD wins, URL from result
    assert g['country'] == 'Singapore' and g['city'] == ''  # city not in the result text -> dropped
    assert len(rejected) == 3
    expo = [{'n': 1, 'title': 'Dong Feng Commercial Vehicles (Malaysia) Sdn Bhd', 'snippet': 'Exhibitor', 'domain': 'mcve.com.my',
             'url': 'https://www.mcve.com.my/all-exhibitors-2026/dong-feng-commercial-vehicles', 'website': 'https://www.mcve.com.my',
             'industry_hint': 'Automotive', 'market_hint': 'Malaysia'}]
    picks, rejected = m.validate_picks({'picks': [{'result': 1, 'company_name': 'Dong Feng Commercial Vehicles', 'industry': 'Automotive'}]},
                                       expo, ['Automotive'], ['Malaysia'])
    assert not picks and 'not the company' in rejected[0]['reason'], rejected


def test_diversify():
    ps = [{'industry': 'Automotive', 'country': 'Malaysia', 'n': i} for i in range(3)] + [{'industry': 'Mining', 'country': 'Singapore', 'n': 9}]
    assert [p['industry'] for p in m.diversify(ps)][:2] == ['Automotive', 'Mining']


def test_names_and_bot_pages():
    assert m.is_bot_challenge('<html><title>Just a moment...</title>')
    assert m.name_from_pages([('u', '<title>Ethical Gold Mining Company and Trusted Gold Suppliers- Dullocal Miners</title>')]) == 'Dullocal Miners'
    assert m.name_from_pages([('u', '<meta property="og:site_name" content="Saiko"><title>x</title>')]) == 'Saiko'
    assert m.DOMAIN_NAME_RE.search('bukomengineering.com.sg') and not m.DOMAIN_NAME_RE.search('Saiko Sdn Bhd')


def test_blocked_and_domain():
    assert m.is_blocked('facebook.com') and m.is_blocked('my.linkedin.com') and m.is_blocked('mpob.gov.my')
    assert not m.is_blocked('autonas.com.my')
    assert m.domain_of('https://www.Autonas.com.my/x') == 'autonas.com.my'


def test_extract_contacts():
    c = m.extract_contacts([('https://www.autonas.com.my/', HTML)], 'autonas.com.my', 'Malaysia')
    assert c['email'] == 'sales@autonas.com.my', c
    assert c['phone'].startswith('+603'), c
    assert c['address'].startswith('Lot 5, Jalan Utas') and c['address'].endswith('Malaysia'), c['address']
    assert m.phone_for_market(['+44 (0) 20 7546 0010', '+65 6123 4567'], 'Singapore') == '+65 6123 4567'
    assert m.phone_for_market(['+44 (0) 20 7546 0010'], 'Singapore') == ''
    assert m.phone_for_market(['03-8021 9068'], 'Malaysia') == '03-8021 9068'
    assert m.clean_address('Saiko sales@saiko.com.my No.9, Jalan Pusat Segambut, 51200 Kuala Lumpur, Malaysia').startswith('No.9, Jalan')
    assert m.clean_address('Your Full Name * E-Mail * Submit Find us: 47100 Puchong Malaysia') == ''
    none = m.extract_contacts([('https://x.sg/', '<p>only john@gmail.com</p>')], 'x.sg')
    assert none['email'] == '' and none['phone'] == ''  # foreign-domain email is not used as the company email


def test_clean_web_recommendation():
    d = {'source_excerpt': 'Established 1998, 3 branches, distributor of 20,000 parts.', 'relevance_reason': 'Large parts distributor in Selangor.'}
    rec = m.clean_web_recommendation({'why_recommended': 'Short', 'recommended_action': 'Call sales.',
                                      'highlights': ['Established in 1998', 'Revenue of USD 50M', 'Operates 12 branches', '3 branches in Malaysia']}, d)
    assert rec['highlights'] == ['Established in 1998', '3 branches in Malaysia'], rec['highlights']  # invented numbers/revenue dropped
    assert rec['recommendation'] == 'Large parts distributor in Selangor.'


def test_validate_changes():
    ok, err = m.validate_lead_changes({'status': 'Interested', 'relevance_score': '77', 'highlights': 'A\n\nB', 'verification_status': 'VERIFIED'}, ['Mining'])
    assert ok == {'status': 'Interested', 'relevance_score': 77, 'highlights': ['A', 'B'], 'verification_status': 'VERIFIED'} and not err
    ok, err = m.validate_lead_changes({'status': 'Won', 'email': 'bad', 'source': 'x', 'source_url': 'y', 'industry': 'Food', 'relevance_score': 400}, ['Mining'])
    assert not ok and len(err) == 6, err


def test_render_and_context():
    v = {'customer_name': 'Automobile Group', 'company_name': 'ABC', 'contact_name': 'ABC team', 'industry': 'Mining', 'sender_name': 'BD', 'business_context': 'X.'}
    body = m.render(m.DEFAULT_TEMPLATE['body'], v)
    assert 'Dear ABC team,' in body and '{{' not in body
    echo = m.clean_context('We believe there may be relevant areas where our teams could explore potential collaboration in enhancing your mining operations.')
    assert echo == 'Enhancing your mining operations.', echo


def test_flow_offline():
    t = m.Tools(); t.valves.DB_PATH = os.path.join(tempfile.mkdtemp(), 'poc.db')
    embeds = []
    async def emit(ev):
        if ev['type'] == 'embeds': embeds.extend(ev['data']['embeds'])
    async def fake_search(industries, markets, existing, per_query=8):
        return [r for r in RESULTS if r['domain'] not in existing]
    async def fake_fetch(website):
        return [(website + '/', HTML)] if 'autonas' in website else []
    async def fake_ai(messages, schema, request):
        props = schema['properties']
        if 'picks' in props:
            return {'picks': [{'result': 1, 'company_name': 'Autonas', 'industry': 'Automotive', 'country': 'Malaysia', 'city': 'Shah Alam',
                               'what_they_do': 'Spare parts wholesaler', 'company_size': 'Unknown', 'business_relationship': 'Parts supply',
                               'target_role': 'Procurement Manager', 'relevance_score': 88, 'relevance_reason': 'Big parts distributor.'},
                              {'result': 3, 'company_name': 'Granite Quarry', 'industry': 'Mining', 'country': 'Singapore', 'city': '',
                               'what_they_do': 'Quarry', 'company_size': 'Unknown', 'business_relationship': 'Equipment',
                               'target_role': 'Plant Manager', 'relevance_score': 75, 'relevance_reason': 'Runs a quarry fleet.'}]}
        if 'items' in props:  # batch: drop the first lead, the single retry must fill it
            ids = props['items']['items']['properties']['lead_id']['enum'][1:]
            return {'items': [{'lead_id': i, 'why_recommended': f'Batch reason for {i}: runs a fleet that needs service.',
                               'highlights': ['Established 1998', 'Invented 99 depots'], 'recommended_action': 'Call.'} for i in ids]}
        if 'why_recommended' in props:
            return {'why_recommended': 'Single reason: distributor of 20,000 parts with 3 branches.', 'highlights': ['3 branches', 'Founded 1998'],
                    'recommended_action': 'Offer bulk supply to the Procurement Manager.'}
        return {'business_context': 'For example, we could support your parts supply for commercial fleets.'}
    sent = {}
    async def fake_integrations(method, path, body):
        sent.update(body); return {'status': 'sent', 'message_id': 'abc123', 'to': body['to']}
    m.search_companies, m.fetch_site = fake_search, fake_fetch
    t._ai_json = fake_ai; t._integrations = fake_integrations
    run = lambda c: json.loads(asyncio.run(c))

    # an old fictional SAMPLE lead exists but is hidden everywhere
    db = t._db()
    db.execute("INSERT INTO leads VALUES ('L-0001','automobile',?, 'b', 'x', 'x')", (json.dumps({'company_name': 'Fake Co', 'industry': 'Mining',
               'verification_status': 'SAMPLE', 'website': 'https://www.fakeco.example', 'status': 'New'}),)); db.commit()

    prof = run(t.show_customer_profile('Automobile Group', __event_emitter__=emit))
    assert prof['lead_counts'] == {} and prof['customer']['markets'] == ['Singapore', 'Malaysia']
    r = run(t.generate_leads('Automobile Group', '', 6, __event_emitter__=emit))
    assert r['new_lead_ids'] == ['L-0002', 'L-0003'], r
    a = t._lead(t._db(), 'L-0002')['data']
    assert a['verification_status'] == 'WEB_SOURCED' and a['email'] == 'sales@autonas.com.my' and a['phone'].startswith('+603')
    assert a['website'] == 'https://www.autonas.com.my' and 'autonas.com.my' in a['source_url'] and a['location'] == 'Shah Alam'
    assert a['recommendation'].startswith('Single reason') and a['highlights'] == ['3 branches', 'Founded 1998'], a  # retry filled L-0002
    q = t._lead(t._db(), 'L-0003')['data']
    assert q['email'] == '' and q['phone'] == ''  # site unreachable -> nothing invented
    assert q['recommendation'] and all(h not in ('Invented 99 depots', 'Established 1998') for h in q.get('highlights', []))  # unsupported claims dropped
    html = embeds[-1]
    assert 'Fake Co' not in html and 'SAMPLE' not in html.replace("'SAMPLE'", '') and 'Real Company Leads' in html and 'source_excerpt' not in html
    assert t._lead(t._db(), 'L-0001') is None  # hidden

    e = run(t.generate_email('L-0002', __event_emitter__=emit)); assert e['email_id'] == 'E-0001'
    body = t._email(t._db(), 'E-0001')['body']
    assert 'Dear Autonas team,' in body and 'Automobile Group' in body
    s = run(t.send_test_email('E-0001', __user__={'id': 'u1'}, __event_emitter__=emit))
    assert s['status'] == 'TEST_SENT' and sent['to'] == 'prsap94@gmail.com' and s['intended_recipient'] == 'sales@autonas.com.my'
    assert run(t.send_test_email('E-0001', __user__={'id': 'u1'}))['status'] == 'already_sent'
    # a second run skips companies that are already leads
    again = run(t.generate_leads('Automobile Group', '', 6))
    assert again['status'] in ('no_results', 'no_valid_leads'), again
    assert len(t._leads(t._db(), 'automobile')) == 2  # no duplicates of existing companies


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn(); print('PASS', name)
