import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, new_id


class MessageDirection(str, enum.Enum):
    inbound = 'inbound'
    outbound = 'outbound'


class MessageStatus(str, enum.Enum):
    received = 'received'  # inbound, stored
    processed = 'processed'  # inbound, answered (or deliberately not answered)
    pending = 'pending'  # outbound, not yet accepted by Meta
    sent = 'sent'
    delivered = 'delivered'
    read = 'read'
    failed = 'failed'


# Meta status events can arrive out of order; never move a message backwards.
STATUS_RANK = {'pending': 0, 'sent': 1, 'delivered': 2, 'read': 3}


class Message(TimestampMixin, Base):
    __tablename__ = 'whatsapp_messages'
    __table_args__ = (Index('ix_message_conversation_created', 'conversation_id', 'created_at'),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey('whatsapp_conversations.id', ondelete='CASCADE'), nullable=False)
    # Meta's wamid. Unique: a webhook redelivery of the same message is rejected by the database.
    whatsapp_message_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    sender_phone: Mapped[str | None] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    # Media id / mime type / filename / template name, never file bytes.
    meta: Mapped[dict | None] = mapped_column(JSON)
    # When WhatsApp says the message happened (inbound) or when we sent it (outbound).
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
