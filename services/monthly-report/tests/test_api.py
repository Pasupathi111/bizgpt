"""End-to-end API workflow with a fake model: upload -> analyse -> review -> generate -> approve -> PDF."""

import asyncio
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import ai, main

USER = {'id': 'u1', 'email': 'coordinator@example.com', 'name': 'Coordinator', 'role': 'user', 'token': 't'}
# filename -> what the fake model "sees"
FAKE = {
    'a_before.jpg': {'stage': 'BEFORE', 'stage_confidence': 94, 'visible_text': 'ZONE A', 'work_type': 'Grass Cutting', 'work_type_confidence': 95},
    'a_during.jpg': {'stage': 'DURING', 'stage_confidence': 91, 'people_working': True, 'visible_text': 'ZONE A', 'work_type': 'Grass Cutting', 'work_type_confidence': 92},
    'a_after.jpg': {'stage': 'AFTER', 'stage_confidence': 93, 'visible_text': 'ZONE A', 'work_type': 'Grass Cutting', 'work_type_confidence': 90},
    'b_before.jpg': {'stage': 'BEFORE', 'stage_confidence': 90, 'visible_text': '', 'work_type': 'Tree Maintenance', 'work_type_confidence': 92, 'issues': ['Fallen branch on footpath']},
    'b_after.jpg': {'stage': 'AFTER', 'stage_confidence': 89, 'visible_text': 'Zone B 2026-09-10', 'work_type': 'Tree Maintenance', 'work_type_confidence': 88},
    'broken.jpg': 'not json at all',
}


@pytest.fixture
def client(monkeypatch):
    main.app.dependency_overrides[main.current_user] = lambda: USER
    current = {}

    async def fake_analyse(path, project, work_types, auth):
        name = current[path]
        answer = FAKE[name]
        return ai.normalise_photo(ai.parse_json(answer if isinstance(answer, str) else json.dumps(answer)), project, work_types)

    async def fake_write(facts, auth):
        assert 'Zone B: During photo missing' in facts['missing_information']
        return {k: f'{k} text for {facts["project"]}' for k in ai.NARRATIVE_KEYS}

    monkeypatch.setattr(ai, 'analyse_photo', fake_analyse)
    monkeypatch.setattr(ai, 'write_report', fake_write)
    with TestClient(main.app) as c:
        c.current = current
        yield c
    main.app.dependency_overrides.clear()


def jpeg(color=(40, 140, 60)):
    buf = io.BytesIO()
    Image.new('RGB', (320, 240), color).save(buf, 'JPEG')
    return buf.getvalue()


def wait_processed(client, rid):
    for _ in range(100):
        r = client.get(f'/api/reports/{rid}').json()
        if r['status'] != 'processing':
            return r
        asyncio.run(asyncio.sleep(0.05))
    raise AssertionError('processing did not finish')


def test_full_workflow(client):
    r = client.post('/api/reports', json={'project_id': 'taman-park', 'month': '2026-09'}).json()
    rid = r['id']
    assert r['status'] == 'draft'

    files = [('files', (name, jpeg(), 'image/jpeg')) for name in FAKE] + [('files', ('notes.txt', b'hello', 'text/plain'))]
    up = client.post(f'/api/reports/{rid}/photos', files=files).json()
    assert up['added'] == 6 and up['rejected'][0]['filename'] == 'notes.txt'
    for p in up['report']['photos']:
        client.current[main.store.get_photo(rid, p['id'])['path']] = p['filename']

    assert client.post(f'/api/reports/{rid}/process').status_code == 200
    r = wait_processed(client, rid)
    assert r['status'] == 'analyzed'
    by_name = {p['filename']: p for p in r['photos']}
    assert by_name['broken.jpg']['status'] == 'error'  # invalid model answer did not crash the batch
    assert by_name['b_before.jpg']['review_reasons'] == ['Location unknown']  # no sign in the photo
    assert r['validation']['missing'] == ['Zone B: Before photo missing', 'Zone B: During photo missing',
                                          'Zone C: no photos uploaded', '1 photo(s) have no location']

    # Approve is blocked before generation and review.
    r = client.post(f'/api/reports/{rid}/generate').json()
    assert r['status'] == 'in_review' and r['content']['sections']['executive_summary']
    blocked = client.post(f'/api/reports/{rid}/approve')
    assert blocked.status_code == 409 and 'need human review' in blocked.json()['detail']

    # Human review: confirm the low-confidence location, exclude the broken photo.
    bad = client.patch(f'/api/reports/{rid}/photos/{by_name["b_before.jpg"]["id"]}', json={'location': 'Zone B', 'fields_set': ['location']})
    assert bad.status_code == 200
    assert bad.json()['validation']['missing'] == ['Zone B: During photo missing', 'Zone C: no photos uploaded']
    invalid = client.patch(f'/api/reports/{rid}/photos/{by_name["a_after.jpg"]["id"]}', json={'stage': 'LATER', 'fields_set': ['stage']})
    assert invalid.status_code == 400
    r = client.patch(f'/api/reports/{rid}/photos/{by_name["broken.jpg"]["id"]}', json={'excluded': True}).json()
    assert r['needs_review'] == 0

    # Edit text, reject, fix, approve.
    r = client.put(f'/api/reports/{rid}/draft', json={'sections': {'remarks': 'Checked on site.'}, 'remarks': 'All good.'}).json()
    assert r['content']['sections']['remarks'] == 'Checked on site.'
    assert client.post(f'/api/reports/{rid}/reject', json={'reason': 'Wrong summary'}).json()['status'] == 'rejected'
    assert client.put(f'/api/reports/{rid}/draft', json={'remarks': 'Fixed.'}).json()['status'] == 'in_review'
    r = client.post(f'/api/reports/{rid}/approve').json()
    assert r['status'] == 'approved' and r['decision']['by'] == 'Coordinator' and r['has_pdf']

    pdf = client.get(f'/api/reports/{rid}/pdf')
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF')
    # Approved reports are read-only.
    assert client.post(f'/api/reports/{rid}/generate').status_code == 409


def test_intake_webhook_creates_report(client):
    resp = client.post('/api/intake', json={'reference': 'MR-ABC123', 'values': {'project': 'Harbour Road Civil Maintenance', 'month': '2026-08'}})
    assert resp.json() == {'report_id': 'MR-ABC123', 'path': '/monthly-report?report=MR-ABC123'}
    assert client.post('/api/intake', json={'reference': 'X', 'values': {'project': 'nope', 'month': '2026-08'}}).status_code == 400


def test_bad_input(client):
    assert client.post('/api/reports', json={'project_id': 'taman-park', 'month': '2026-13'}).status_code == 400
    assert client.post('/api/reports', json={'project_id': 'nope', 'month': '2026-09'}).status_code == 400
    rid = client.post('/api/reports', json={'project_id': 'taman-park', 'month': '2026-09'}).json()['id']
    assert client.post(f'/api/reports/{rid}/process').status_code == 400  # no photos
    assert client.post(f'/api/reports/{rid}/generate').status_code == 400  # nothing analysed
    assert client.get('/api/reports/NOPE').status_code == 404


def test_model_unavailable_is_reported_per_photo(client, monkeypatch):
    async def down(*_a, **_k):
        raise ai.ModelError('model monthly-report-vision is unavailable (ConnectError)')
    monkeypatch.setattr(ai, 'analyse_photo', down)
    rid = client.post('/api/reports', json={'project_id': 'taman-park', 'month': '2026-09'}).json()['id']
    client.post(f'/api/reports/{rid}/photos', files=[('files', ('x.jpg', jpeg(), 'image/jpeg'))])
    client.post(f'/api/reports/{rid}/process')
    r = wait_processed(client, rid)
    assert r['photos'][0]['status'] == 'error' and 'unavailable' in r['photos'][0]['error']
    assert r['needs_review'] == 1
