"""Message storage. The unique whatsapp_message_id column is the duplicate-webhook guard."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Message
from app.models.base import aware, utcnow
from app.models.message import STATUS_RANK
from app.schemas.whatsapp import InboundMessage, StatusUpdate


class MessageService:
    async def exists(self, session: AsyncSession, whatsapp_message_id: str) -> bool:
        return bool(await session.scalar(select(Message.id).where(Message.whatsapp_message_id == whatsapp_message_id)))

    async def store_inbound(self, session: AsyncSession, conversation: Conversation, msg: InboundMessage) -> Message | None:
        """Store an inbound message. Returns None when this wamid was already stored (redelivery)."""
        message = Message(
            conversation_id=conversation.id,
            whatsapp_message_id=msg.whatsapp_message_id,
            direction='inbound',
            message_type=msg.message_type,
            content=msg.text,
            sender_phone=msg.sender_phone,
            status='received',
            meta=msg.meta or None,
            timestamp=msg.timestamp,
        )
        session.add(message)
        conversation.last_inbound_at = max(filter(None, [aware(conversation.last_inbound_at), msg.timestamp]))
        conversation.last_message_at = max(filter(None, [aware(conversation.last_message_at), msg.timestamp]))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return None
        return message

    async def store_outbound(
        self,
        session: AsyncSession,
        conversation: Conversation,
        *,
        content: str,
        sender_phone: str | None,
        whatsapp_message_id: str | None,
        message_type: str = 'text',
        status: str = 'sent',
        error: str | None = None,
        meta: dict | None = None,
        timestamp: datetime | None = None,
    ) -> Message:
        now = timestamp or utcnow()
        fields = dict(
            conversation_id=conversation.id,
            whatsapp_message_id=whatsapp_message_id,
            direction='outbound',
            message_type=message_type,
            content=content,
            sender_phone=sender_phone,
            status=status,
            error=error,
            meta=meta,
            timestamp=now,
        )
        if whatsapp_message_id and await self.exists(session, whatsapp_message_id):
            # The customer already has this message; never lose the record over a clashing id.
            fields.update(whatsapp_message_id=None, error=f'duplicate wamid {whatsapp_message_id}')
        message = Message(**fields)
        session.add(message)
        if status != 'failed':
            conversation.last_message_at = now
        await session.commit()
        return message

    async def apply_status(self, session: AsyncSession, update: StatusUpdate) -> bool:
        """Apply a sent/delivered/read/failed event. Returns False for unknown messages."""
        message = await session.scalar(select(Message).where(Message.whatsapp_message_id == update.whatsapp_message_id))
        if not message:
            return False
        if update.status == 'failed':
            message.status = 'failed'
            message.error = update.error or message.error
        elif update.status in STATUS_RANK and STATUS_RANK[update.status] > STATUS_RANK.get(message.status, -1):
            message.status = update.status
        await session.commit()
        return True

    async def set_status(self, session: AsyncSession, message: Message, status: str, error: str | None = None) -> None:
        message.status = status
        if error:
            message.error = error[:2000]
        await session.commit()
