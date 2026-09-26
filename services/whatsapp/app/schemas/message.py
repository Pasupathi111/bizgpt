from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    whatsapp_message_id: str | None
    direction: str
    message_type: str
    content: str | None
    sender_phone: str | None
    status: str
    error: str | None
    meta: dict[str, Any] | None
    timestamp: datetime
    created_at: datetime
