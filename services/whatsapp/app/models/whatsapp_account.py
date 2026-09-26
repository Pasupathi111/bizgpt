from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, new_id


class WhatsAppAccount(TimestampMixin, Base):
    """One WhatsApp Business phone number. The access token stays in the environment, never here."""

    __tablename__ = 'whatsapp_accounts'

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    phone_number_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    business_account_id: Mapped[str | None] = mapped_column(String(64))
    display_phone_number: Mapped[str | None] = mapped_column(String(32))
    verified_name: Mapped[str | None] = mapped_column(String(255))
    agent_model: Mapped[str] = mapped_column(String(255), nullable=False)
    auto_reply: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # False = "Disconnected" in the Integrations page: messages are still stored, never answered.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
