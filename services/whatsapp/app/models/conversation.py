from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, new_id


class Conversation(TimestampMixin, Base):
    """A session with one contact. A new one starts after conversation_timeout_hours of silence.

    openwebui_chat_id links it to the Biz GPT chat that mirrors it.
    """

    __tablename__ = 'whatsapp_conversations'
    __table_args__ = (Index('ix_conversation_contact_status', 'contact_id', 'status'),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey('whatsapp_accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    contact_id: Mapped[str] = mapped_column(ForeignKey('whatsapp_contacts.id', ondelete='CASCADE'), nullable=False)
    openwebui_chat_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16), default='open', nullable=False)  # open | closed
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
