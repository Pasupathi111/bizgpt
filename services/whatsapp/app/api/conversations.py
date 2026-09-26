from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db import get_session
from app.models import Contact, Conversation, Message
from app.schemas.conversation import ContactOut, ConversationDetail, ConversationOut
from app.schemas.message import MessageOut
from app.schemas.whatsapp import normalize_phone
from app.services.conversation_service import within_service_window
from app.services.whatsapp_service import WhatsAppService

router = APIRouter(prefix='/api/whatsapp', tags=['conversations'], dependencies=[Depends(deps.require_api_key)])


async def _out(session: AsyncSession, conversation: Conversation, contact: Contact | None = None) -> ConversationOut:
    contact = contact or await session.get(Contact, conversation.contact_id)
    return ConversationOut(
        id=conversation.id,
        contact=ContactOut.model_validate(contact),
        openwebui_chat_id=conversation.openwebui_chat_id,
        status=conversation.status,
        last_inbound_at=conversation.last_inbound_at,
        last_message_at=conversation.last_message_at,
        created_at=conversation.created_at,
        within_service_window=within_service_window(conversation),
    )


def _phone(value: str) -> str:
    try:
        return normalize_phone(value)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get('/contacts/{phone}', response_model=ContactOut)
async def get_contact(phone: str, session: AsyncSession = Depends(get_session), service: WhatsAppService = Depends(deps.whatsapp)):
    account = await service.conversations.get_or_create_account(session)
    contact = await service.conversations.find_contact(session, account.id, _phone(phone))
    if not contact:
        raise HTTPException(404, 'No WhatsApp contact with that number')
    return contact


@router.get('/conversations', response_model=list[ConversationOut])
async def list_conversations(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    phone: str | None = None,
    session: AsyncSession = Depends(get_session),
    service: WhatsAppService = Depends(deps.whatsapp),
):
    account = await service.conversations.get_or_create_account(session)
    if phone:
        contact = await service.conversations.find_contact(session, account.id, _phone(phone))
        if not contact:
            return []
        rows = (
            await session.scalars(
                select(Conversation).where(Conversation.contact_id == contact.id).order_by(Conversation.created_at.desc()).limit(limit).offset(offset)
            )
        ).all()
    else:
        rows = await service.conversations.list_conversations(session, account.id, limit, offset)
    return [await _out(session, c) for c in rows]


@router.get('/conversations/{conversation_id}', response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    service: WhatsAppService = Depends(deps.whatsapp),
):
    conversation = await session.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(404, 'Conversation not found')
    out = await _out(session, conversation)
    messages = await _messages(session, service, conversation.id, limit)
    return ConversationDetail(**out.model_dump(), messages=messages)


async def _messages(session: AsyncSession, service: WhatsAppService, conversation_id: str, limit: int) -> list[MessageOut]:
    rows = (
        await session.scalars(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.desc()).limit(limit)
        )
    ).all()
    return [MessageOut.model_validate(m) for m in reversed(rows)]


@router.get('/messages', response_model=list[MessageOut])
async def get_messages(
    phone: str,
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    service: WhatsAppService = Depends(deps.whatsapp),
):
    """Latest messages with one contact, across their conversations."""
    account = await service.conversations.get_or_create_account(session)
    contact = await service.conversations.find_contact(session, account.id, _phone(phone))
    if not contact:
        return []
    rows = (
        await session.scalars(
            select(Message)
            .join(Conversation)
            .where(Conversation.contact_id == contact.id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [MessageOut.model_validate(m) for m in reversed(rows)]
