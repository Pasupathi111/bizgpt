from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.message import MessageOut


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    wa_id: str
    profile_name: str | None
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    contact: ContactOut
    openwebui_chat_id: str | None
    status: str
    last_inbound_at: datetime | None
    last_message_at: datetime | None
    created_at: datetime
    # Meta only allows free-form replies within 24 hours of the customer's last message.
    within_service_window: bool = False


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = []
