"""Structured JSON logs with secret redaction.

Every record passes through RedactingFilter, which removes the configured secret values and
anything that looks like a bearer token or an access_token query parameter. Phone numbers
should be logged through mask_phone().
"""

import json
import logging
import re
import sys
from datetime import datetime, timezone

_PATTERNS = [
    re.compile(r'(Bearer\s+)[A-Za-z0-9._\-~+/=]+', re.I),
    re.compile(r'(access_token=)[^&\s"]+', re.I),
    re.compile(r'(verify_token=)[^&\s"]+', re.I),  # Meta webhook verification query
    re.compile(r'(EAA)[A-Za-z0-9]{20,}'),  # Meta user/system-user tokens
    re.compile(r'(sk-)[A-Za-z0-9]{16,}'),  # Open WebUI API keys
]


class RedactingFilter(logging.Filter):
    def __init__(self, secrets: list[str] | None = None):
        super().__init__()
        self.secrets = [s for s in (secrets or []) if len(s) >= 4]

    def redact(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, '***')
        for pattern in _PATTERNS:
            text = pattern.sub(r'\1***', text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact the template and each argument in place: uvicorn's formatters read record.args.
        if isinstance(record.msg, str):
            record.msg = self.redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(self.redact(a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: self.redact(v) if isinstance(v, str) else v for k, v in record.args.items()}
        for key, value in list(record.__dict__.get('extra_fields', {}).items()):
            if isinstance(value, str):
                record.extra_fields[key] = self.redact(value)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            'ts': datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'msg': record.getMessage(),
        }
        payload.update(getattr(record, 'extra_fields', {}) or {})
        if record.exc_info:
            payload['exc'] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class StdoutHandler(logging.StreamHandler):
    """Writes to whatever sys.stdout is at emit time (keeps pytest capture working)."""

    @property
    def stream(self):
        return sys.stdout

    @stream.setter
    def stream(self, _value):
        pass


def setup_logging(level: str, secrets: list[str]) -> None:
    handler = StdoutHandler()
    handler.setFormatter(JsonFormatter())
    redactor = RedactingFilter(secrets)
    handler.addFilter(redactor)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # uvicorn logs request lines (with query strings) through its own handlers.
    for name in ('uvicorn.access', 'uvicorn.error'):
        logger = logging.getLogger(name)
        if not any(isinstance(f, RedactingFilter) for f in logger.filters):
            logger.addFilter(redactor)
    # httpx logs full request URLs at INFO; keep it quiet.
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)


def mask_phone(phone: str | None) -> str:
    if not phone:
        return ''
    return phone[:3] + '*' * max(0, len(phone) - 6) + phone[-3:] if len(phone) > 6 else '***'


def log_extra(**fields) -> dict:
    return {'extra': {'extra_fields': fields}}
