"""Gmail intake: parsing google_workspace_mcp output, and email -> report import (fake mailbox, fake model)."""

import base64
import io
import json

import pytest
from PIL import Image

from app import ai, gmail, intake
from app.store import Store

MESSAGE = """Message ID: 18f01
Subject: Taman Park - September 2026 site photos
From: Site Team <Site.Team@example.com>
Date: Tue, 22 Sep 2026 09:10:00 +0800
To: reports@example.com
Cc: [not present in Gmail response]

--- BODY ---
Attached are the September photos.

--- ATTACHMENTS ---
1. IMG_0101.jpg (image/jpeg, 41.2 KB)
   Attachment ID: ANGjdJ_abc
   Use get_gmail_attachment_content(message_id='18f01', attachment_id='ANGjdJ_abc', attachment_index=0) to download
2. notes.pdf (application/pdf, 10.0 KB)
   Attachment ID: ANGjdJ_def
   Use get_gmail_attachment_content(message_id='18f01', attachment_id='ANGjdJ_def', attachment_index=1) to download"""


def jpeg():
    buf = io.BytesIO()
    Image.new('RGB', (64, 48), (40, 140, 60)).save(buf, 'JPEG')
    return buf.getvalue()


def test_parse_message_finds_image_attachments():
    m = gmail.parse_message('18f01', MESSAGE)
    assert m['subject'] == 'Taman Park - September 2026 site photos' and m['from_email'] == 'site.team@example.com'
    assert [a['filename'] for a in m['attachments']] == ['IMG_0101.jpg', 'notes.pdf']
    assert m['images'] == [{'index': 0, 'filename': 'IMG_0101.jpg', 'mime': 'image/jpeg', 'attachment_id': 'ANGjdJ_abc'}]
    assert m['body'] == 'Attached are the September photos.'


def test_parse_attachment_base64_block():
    data = jpeg()
    text = ('Attachment downloaded successfully!\nMessage ID: 18f01\n\n📎 Download URL: http://x/attachments/1\n'
            f'\n📦 Base64 content (99 chars, standard base64):\n{base64.b64encode(data).decode()}')
    assert gmail.parse_attachment(text) == data
    assert gmail.parse_attachment('Base64-encoded content (first 100 characters shown):\n/9j/4AAQ...') is None


class FakeGmail:
    def __init__(self, emails):
        self.emails = emails

    async def search(self, query, page_size=25):
        return list(self.emails)

    async def read(self, message_id):
        e = self.emails[message_id]
        return {'message_id': message_id, 'subject': e['subject'], 'from': 'Site <site@example.com>', 'from_email': 'site@example.com',
                'date': 'Tue, 22 Sep 2026', 'body': e['body'], 'attachments': e['images'], 'images': e['images']}

    async def download(self, message_id, att):
        return b'not an image' if att['filename'] == 'broken.jpg' else jpeg()


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def run(coro):
    import asyncio
    return asyncio.run(coro)


def test_import_routes_emails_and_never_imports_twice(store, monkeypatch):
    img = lambda n: {'index': 0, 'filename': n, 'mime': 'image/jpeg', 'attachment_id': n}  # noqa: E731
    fake = FakeGmail({
        'm1': {'subject': 'Taman Park September 2026 photos', 'body': '', 'images': [img('A.jpg'), img('broken.jpg')]},
        'm2': {'subject': 'Drain photos', 'body': 'see attached', 'images': [img('C.jpg')]},
        'm3': {'subject': 'Lunch', 'body': 'menu', 'images': []},
    })
    answers = {'Taman Park September 2026 photos': {'is_site_photos': True, 'project': 'taman-park', 'month': '2026-09'},
               'Drain photos': {'is_site_photos': True, 'project': 'taman-park', 'month': '2026-09'}}  # a guess

    async def fake_complete(messages, auth, json_mode=True):
        subject = messages[0]['content'].split('Subject: ')[1].split('\n')[0]
        return json.dumps(answers[subject])
    monkeypatch.setattr(ai, 'complete', fake_complete)

    added = []

    def add_photo(rid, name, data):
        if data == b'not an image':
            return False
        store.add_photo(rid, name, data, 'image/jpeg', None)
        added.append((rid, name))
        return True

    out = run(intake.import_from_gmail(store, fake, add_photo, 'token'))
    assert [i['subject'] for i in out['imported']] == ['Taman Park September 2026 photos']
    assert out['imported'][0]['added'] == 1 and out['imported'][0]['failed'] == ['broken.jpg: not a readable image']
    assert [n['subject'] for n in out['needs_info']] == ['Drain photos']  # the model's guess is refused
    assert out['skipped'][0]['reason'] == 'no image attachments'
    rid = out['reports'][0]
    assert store.get_report(rid)['project_id'] == 'taman-park' and store.get_report(rid)['month'] == '2026-09'

    # Second run: nothing new is imported; the coordinator names the project/month for the pending email.
    again = run(intake.import_from_gmail(store, fake, add_photo, 'token', project_id='taman-park', month='2026-09'))
    assert [i['subject'] for i in again['imported']] == ['Drain photos']
    assert again['imported'][0]['report_id'] == rid  # joins the open report for the same project/month
    assert [n for _, n in added] == ['A.jpg', 'C.jpg']


def test_project_and_month_must_be_written_in_the_email():
    p = {'id': 'taman-park', 'name': 'Taman Park Landscape Maintenance'}
    assert ai.project_named_in('Taman Park - September 2026 site photos', p)
    assert not ai.project_named_in('Zone C drain works photos', p)
    assert ai.month_named_in('photos for Sept 2026'.replace('Sept', 'Sep'), '2026-09')
    assert ai.month_named_in('Report 2026-09', '2026-09') and ai.month_named_in('09/2026 photos', '2026-09')
    assert not ai.month_named_in('Photos from the drain cleaning', '2026-09')


def test_project_and_month_read_from_text_when_model_is_sloppy():
    cfg = {'projects': [{'id': 'taman-park', 'name': 'Taman Park Landscape Maintenance'},
                        {'id': 'harbour-road', 'name': 'Harbour Road Civil Maintenance'}]}
    text = 'Taman Park - September 2026 site photos\nHi, attached are the photos.'
    for raw in ({'project': 'Taman Park', 'month': '2026-9'}, {'project': None, 'month': None}, {'project': 'harbour-road', 'month': '2026-10'}):
        out = ai.normalise_email(raw, cfg, text)
        assert (out['project_id'], out['month']) == ('taman-park', '2026-09')
    assert ai.normalise_email({'project': 'taman-park', 'month': '2026-09'}, cfg, 'Zone C drain works photos') == \
        {'is_site_photos': True, 'project_id': None, 'month': None}
    assert ai.find_month_in('photos for Sep 2026 and Oct 2026') is None  # two months: ask


def test_bounces_are_ignored_and_failed_downloads_are_retried(store, monkeypatch):
    img = lambda n: {'index': 0, 'filename': n, 'mime': 'image/jpeg', 'attachment_id': n}  # noqa: E731
    fake = FakeGmail({
        'b1': {'subject': 'Delivery Status Notification (Failure)', 'body': 'Address not found', 'images': [img('icon.png')]},
        'm1': {'subject': 'Taman Park October 2026 photos', 'body': '', 'images': [img('A.jpg')]},
    })

    async def fake_complete(messages, auth, json_mode=True):
        return json.dumps({'is_site_photos': True, 'project': 'taman-park', 'month': '2026-10'})
    monkeypatch.setattr(ai, 'complete', fake_complete)

    async def broken_download(message_id, att):
        raise gmail.GmailError('Unknown tool')
    monkeypatch.setattr(fake, 'download', broken_download)
    add_photo = lambda rid, name, data: store.add_photo(rid, name, data, 'image/jpeg', None) or True  # noqa: E731

    out = run(intake.import_from_gmail(store, fake, add_photo, 'token', project_id='taman-park', month='2026-10'))
    assert out['imported'] == [] and store.gmail_seen('b1')['status'] == 'ignored'  # bounce never joins a report
    assert store.gmail_seen('m1')['status'] == 'failed'

    monkeypatch.setattr(fake, 'download', FakeGmail.download.__get__(fake))  # attachments downloadable again
    again = run(intake.import_from_gmail(store, fake, add_photo, 'token'))
    assert [(i['subject'], i['added']) for i in again['imported']] == [('Taman Park October 2026 photos', 1)]


def test_only_month_leaves_other_months_pending(store, monkeypatch):
    img = lambda n: {'index': 0, 'filename': n, 'mime': 'image/jpeg', 'attachment_id': n}  # noqa: E731
    fake = FakeGmail({
        'oct': {'subject': 'Taman Park October 2026 photos', 'body': '', 'images': [img('O.jpg')]},
        'sep': {'subject': 'Taman Park September 2026 photos', 'body': '', 'images': [img('S.jpg')]},
    })
    months = {'Taman Park October 2026 photos': '2026-10', 'Taman Park September 2026 photos': '2026-09'}

    async def fake_complete(messages, auth, json_mode=True):
        subject = messages[0]['content'].split('Subject: ')[1].split('\n')[0]
        return json.dumps({'is_site_photos': True, 'project': 'taman-park', 'month': months[subject]})
    monkeypatch.setattr(ai, 'complete', fake_complete)
    add_photo = lambda rid, name, data: store.add_photo(rid, name, data, 'image/jpeg', None) or True  # noqa: E731

    sep = run(intake.import_from_gmail(store, fake, add_photo, 'token', only_month='2026-09'))
    assert [i['subject'] for i in sep['imported']] == ['Taman Park September 2026 photos']
    assert store.gmail_seen('oct') is None  # October untouched, still importable
    octo = run(intake.import_from_gmail(store, fake, add_photo, 'token', only_month='2026-10'))
    assert [i['subject'] for i in octo['imported']] == ['Taman Park October 2026 photos']
