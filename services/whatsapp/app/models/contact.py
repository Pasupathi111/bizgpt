from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, new_id


class Contact(TimestampMixin, Base):
    __tablename__ = 'whatsapp_contacts'
    __table_args__ = (UniqueConstraint('account_id', 'wa_id', name='uq_contact_account_wa_id'),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey('whatsapp_accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    # WhatsApp id = phone number in international format without "+", e.g. 919876543210.
    wa_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    profile_name: Mapped[str | None] = mapped_column(String(255))
