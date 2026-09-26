"""Contact and conversation mapping, directly against the services."""

from datetime import timedelta

import pytest

from app.db import create_all, get_engine, init_engine, session_factory
from app.models.base import utcnow
from app.schemas.whatsapp import InboundMessage
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService


@pytest.fixture
async def session(settings):
    init_engine(settings.database_url)
    await create_all()
    async with session_factory()() as s:
        yield s
    await get_engine().dispose()


def _inbound(wamid='wamid.1', text='hi', ts=None):
    return InboundMessage(
        whatsapp_message_id=wamid, phone_number_id='1111111111', sender_phone='919876543210',
        message_type='text', text=text, timestamp=ts or utcnow(),
    )


async def test_new_contact(session, settings):
    svc = ConversationService(settings)
    account = await svc.get_or_create_account(session)
    contact = await svc.find_or_create_contact(session, account.id, '919876543210', 'Priya')
    assert contact.id and contact.wa_id == '919876543210' and contact.profile_name == 'Priya'
    assert account.agent_model == settings.whatsapp_agent_model


async def test_existing_contact_is_reused_and_name_updated(session, settings):
    svc = ConversationService(settings)
    account = await svc.get_or_create_account(session)
    first = await svc.find_or_create_contact(session, account.id, '919876543210', 'Priya')
    again = await svc.find_or_create_contact(session, account.id, '919876543210', 'Priya S')
    assert again.id == first.id
    assert again.profile_name == 'Priya S'


async def test_account_is_created_once(session, settings):
    svc = ConversationService(settings)
    a = await svc.get_or_create_account(session)
    b = await svc.get_or_create_account(session)
    assert a.id == b.id


async def test_new_and_existing_conversation(session, settings):
    svc = ConversationService(settings)
    account = await svc.get_or_create_account(session)
    contact = await svc.find_or_create_contact(session, account.id, '919876543210')
    conv = await svc.find_or_create_conversation(session, contact)
    assert conv.status == 'open'
    same = await svc.find_or_create_conversation(session, contact)
    assert same.id == conv.id


async def test_conversation_rolls_over_after_timeout(session, settings):
    svc = ConversationService(settings)
    account = await svc.get_or_create_account(session)
    contact = await svc.find_or_create_contact(session, account.id, '919876543210')
    old = await svc.find_or_create_conversation(session, contact)
    later = utcnow() + timedelta(hours=settings.conversation_timeout_hours + 1)
    new = await svc.find_or_create_conversation(session, contact, now=later)
    assert new.id != old.id
    await session.refresh(old)
    assert old.status == 'closed'


async def test_duplicate_message_rejected_by_database(session, settings):
    svc, msgs = ConversationService(settings), MessageService()
    account = await svc.get_or_create_account(session)
    contact = await svc.find_or_create_contact(session, account.id, '919876543210')
    conv = await svc.find_or_create_conversation(session, contact)
    assert await msgs.store_inbound(session, conv, _inbound('wamid.same')) is not None
    conv = await svc.find_or_create_conversation(session, contact)
    assert await msgs.store_inbound(session, conv, _inbound('wamid.same')) is None
    assert await msgs.exists(session, 'wamid.same')


async def test_history_order_and_limit(session, settings):
    svc, msgs = ConversationService(settings), MessageService()
    account = await svc.get_or_create_account(session)
    contact = await svc.find_or_create_contact(session, account.id, '919876543210')
    conv = await svc.find_or_create_conversation(session, contact)
    base = utcnow()
    for i in range(5):
        await msgs.store_inbound(session, conv, _inbound(f'wamid.{i}', f'm{i}', base + timedelta(seconds=i)))
    history = await svc.history(session, conv.id, limit=3)
    assert [m.content for m in history] == ['m2', 'm3', 'm4']
