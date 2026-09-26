"""Meta webhook payloads (parsed leniently) and the internal API request bodies."""

import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

PHONE_RE = re.compile(r'^\d{7,15}$')


def normalize_phone(value: str) -> str:
    """'+91 98765-43210' -> '919876543210' (WhatsApp wa_id format)."""
    digits = re.sub(r'[\s\-().+]', '', str(value or ''))
    if not PHONE_RE.match(digits):
        raise ValueError('phone number must be 7-15 digits in international format, e.g. +919876543210')
    return digits


# ---------- webhook ----------


class InboundMessage(BaseModel):
    whatsapp_message_id: str
    phone_number_id: str
    display_phone_number: str | None = None
    sender_phone: str
    sender_name: str | None = None
    message_type: str
    text: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime
    # True when the AI can do something useful with it (text, caption, button reply…).
    answerable: bool = True


class StatusUpdate(BaseModel):
    whatsapp_message_id: str
    status: str
    recipient: str | None = None
    timestamp: datetime
    error: str | None = None


class ParsedWebhook(BaseModel):
    messages: list[InboundMessage] = Field(default_factory=list)
    statuses: list[StatusUpdate] = Field(default_factory=list)


def _ts(value: Any) -> datetime:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


MEDIA_TYPES = ('image', 'document', 'audio', 'video', 'sticker')


def _parse_message(raw: dict, metadata: dict, names: dict[str, str]) -> InboundMessage | None:
    wamid, sender = raw.get('id'), raw.get('from')
    if not wamid or not sender:
        return None
    mtype = raw.get('type') or 'unknown'
    text: str | None = None
    meta: dict[str, Any] = {}
    answerable = True

    if mtype == 'text':
        text = (raw.get('text') or {}).get('body')
    elif mtype in MEDIA_TYPES:
        media = raw.get(mtype) or {}
        meta = {k: media.get(k) for k in ('id', 'mime_type', 'sha256', 'filename', 'caption') if media.get(k)}
        caption = media.get('caption')
        label = f"{mtype}{' ' + media['filename'] if media.get('filename') else ''}"
        text = f'[Customer sent {label}]' + (f' {caption}' if caption else '')
        # Images and documents get an AI reply; voice notes, video and stickers get the fixed reply.
        answerable = mtype in ('image', 'document')
    elif mtype == 'interactive':
        inter = raw.get('interactive') or {}
        reply = inter.get('button_reply') or inter.get('list_reply') or {}
        text = reply.get('title') or reply.get('id')
        meta = {'interactive_type': inter.get('type'), 'reply_id': reply.get('id')}
    elif mtype == 'button':
        button = raw.get('button') or {}
        text = button.get('text') or button.get('payload')
        meta = {'payload': button.get('payload')}
    elif mtype == 'location':
        loc = raw.get('location') or {}
        meta = {k: loc.get(k) for k in ('latitude', 'longitude', 'name', 'address') if loc.get(k) is not None}
        text = '[Customer shared a location] ' + ', '.join(str(v) for v in meta.values())
    elif mtype == 'reaction':
        reaction = raw.get('reaction') or {}
        meta = {'emoji': reaction.get('emoji'), 'message_id': reaction.get('message_id')}
        text = reaction.get('emoji')
        answerable = False
    else:
        # contacts, order, system, unsupported, and any type Meta adds later.
        errors = raw.get('errors') or []
        if errors:
            meta = {'errors': [{'code': e.get('code'), 'title': e.get('title')} for e in errors]}
        answerable = False

    if mtype in ('text', 'interactive', 'button') and not (text or '').strip():
        answerable = False

    return InboundMessage(
        whatsapp_message_id=wamid,
        phone_number_id=str(metadata.get('phone_number_id') or ''),
        display_phone_number=metadata.get('display_phone_number'),
        sender_phone=str(sender),
        sender_name=names.get(str(sender)),
        message_type=mtype,
        text=text,
        meta=meta,
        timestamp=_ts(raw.get('timestamp')),
        answerable=answerable,
    )


def parse_webhook(payload: dict) -> ParsedWebhook:
    """Extract messages and status events. Unknown shapes are skipped, never raised."""
    result = ParsedWebhook()
    for entry in payload.get('entry') or []:
        for change in (entry or {}).get('changes') or []:
            if (change or {}).get('field') != 'messages':
                continue
            value = change.get('value') or {}
            metadata = value.get('metadata') or {}
            names = {
                str(c.get('wa_id')): (c.get('profile') or {}).get('name')
                for c in value.get('contacts') or []
                if c.get('wa_id')
            }
            for raw in value.get('messages') or []:
                msg = _parse_message(raw or {}, metadata, names)
                if msg:
                    result.messages.append(msg)
            for raw in value.get('statuses') or []:
                if not raw.get('id') or not raw.get('status'):
                    continue
                errors = raw.get('errors') or []
                result.statuses.append(
                    StatusUpdate(
                        whatsapp_message_id=raw['id'],
                        status=raw['status'],
                        recipient=raw.get('recipient_id'),
                        timestamp=_ts(raw.get('timestamp')),
                        error='; '.join(f"{e.get('code')}: {e.get('title')}" for e in errors) or None,
                    )
                )
    return result


# ---------- internal API ----------


class SendTextRequest(BaseModel):
    to: str = Field(description='Recipient phone number in international format, e.g. +919876543210')
    text: str = Field(min_length=1, max_length=4096)
    preview_url: bool = False

    @field_validator('to')
    @classmethod
    def _normalize_to(cls, v: str) -> str:
        return normalize_phone(v)


class SendTemplateRequest(BaseModel):
    to: str
    template_name: str = Field(min_length=1, max_length=512, pattern=r'^[a-z0-9_]+$')
    language: str = Field(default='en_US', max_length=16)
    # Body placeholder values {{1}}, {{2}}, … in order.
    body_params: list[str] = Field(default_factory=list, max_length=20)
    # Raw Graph "components" array, for header/button parameters. Overrides body_params.
    components: list[dict[str, Any]] | None = None

    @field_validator('to')
    @classmethod
    def _normalize_to(cls, v: str) -> str:
        return normalize_phone(v)


class SettingsUpdate(BaseModel):
    agent_model: str | None = Field(default=None, min_length=1, max_length=255)
    auto_reply: bool | None = None
    is_active: bool | None = None


class CheckResult(BaseModel):
    ok: bool
    status: Literal['ok', 'error', 'not_configured']
    detail: str | None = None
