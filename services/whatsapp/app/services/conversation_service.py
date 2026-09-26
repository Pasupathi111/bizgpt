"""phone number -> Contact -> Conversation -> Biz GPT chat."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import Contact, Conversation, Message, WhatsAppAccount
from app.models.base import aware, utcnow

SERVICE_WINDOW = timedelta(hours=24)


def within_service_window(conversation: Conversation, now: datetime | None = None) -> bool:
    last = aware(conversation.last_inbound_at)
    return bool(last and (now or utcnow()) - last < SERVICE_WINDOW)


class ConversationService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def get_or_create_account(self, session: AsyncSession, phone_number_id: str | None = None) -> WhatsAppAccount:
        """The account for a phone number id (defaults to WHATSAPP_PHONE_NUMBER_ID), created on first use."""
        pnid = phone_number_id or self.settings.whatsapp_phone_number_id or 'unconfigured'
        account = await session.scalar(select(WhatsAppAccount).where(WhatsAppAccount.phone_number_id == pnid))
        if account:
            return account
        account = WhatsAppAccount(
            phone_number_id=pnid,
            business_account_id=self.settings.whatsapp_business_account_id or None,
            agent_model=self.settings.whatsapp_agent_model,
            auto_reply=self.settings.auto_reply_enabled,
        )
        session.add(account)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            account = await session.scalar(select(WhatsAppAccount).where(WhatsAppAccount.phone_number_id == pnid))
        return account

    async def find_contact(self, session: AsyncSession, account_id: str, wa_id: str) -> Contact | None:
        return await session.scalar(select(Contact).where(Contact.account_id == account_id, Contact.wa_id == wa_id))

    async def find_or_create_contact(self, session: AsyncSession, account_id: str, wa_id: str, name: str | None = None) -> Contact:
        contact = await self.find_contact(session, account_id, wa_id)
        if contact:
            if name and contact.profile_name != name:
                contact.profile_name = name
                await session.commit()
            return contact
        contact = Contact(account_id=account_id, wa_id=wa_id, profile_name=name)
        session.add(contact)
        try:
            await session.commit()
        except IntegrityError:  # created concurrently by another webhook delivery
            await session.rollback()
            contact = await self.find_contact(session, account_id, wa_id)
        return contact

    async def current_conversation(self, session: AsyncSession, contact_id: str) -> Conversation | None:
        return await session.scalar(
            select(Conversation)
            .where(Conversation.contact_id == contact_id, Conversation.status == 'open')
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )

    async def find_or_create_conversation(self, session: AsyncSession, contact: Contact, now: datetime | None = None) -> Conversation:
        """The open conversation, or a new one after conversation_timeout_hours of silence."""
        now = now or utcnow()
        conversation = await self.current_conversation(session, contact.id)
        if conversation:
            last = aware(conversation.last_message_at) or aware(conversation.created_at)
            if now - last < timedelta(hours=self.settings.conversation_timeout_hours):
                return conversation
            conversation.status = 'closed'
        conversation = Conversation(account_id=contact.account_id, contact_id=contact.id, status='open', last_message_at=now)
        session.add(conversation)
        await session.commit()
        return conversation

    async def history(self, session: AsyncSession, conversation_id: str, limit: int | None = None) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.status != 'failed')
            .order_by(Message.created_at.desc())
        )
        if limit:
            stmt = stmt.limit(limit)
        return list(reversed((await session.scalars(stmt)).all()))

    async def list_conversations(self, session: AsyncSession, account_id: str, limit: int = 50, offset: int = 0) -> list[Conversation]:
        return list(
            (
                await session.scalars(
                    select(Conversation)
                    .where(Conversation.account_id == account_id)
                    .order_by(Conversation.last_message_at.desc().nulls_last())
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
        )

    async def stats(self, session: AsyncSession, account_id: str) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=1)
        base = select(func.count(Message.id)).join(Conversation).where(Conversation.account_id == account_id)
        return {
            'contacts': await session.scalar(select(func.count(Contact.id)).where(Contact.account_id == account_id)) or 0,
            'conversations': await session.scalar(select(func.count(Conversation.id)).where(Conversation.account_id == account_id)) or 0,
            'messages_inbound': await session.scalar(base.where(Message.direction == 'inbound')) or 0,
            'messages_outbound': await session.scalar(base.where(Message.direction == 'outbound')) or 0,
            'messages_failed': await session.scalar(base.where(Message.status == 'failed')) or 0,
            'messages_24h': await session.scalar(base.where(Message.timestamp >= since)) or 0,
        }
