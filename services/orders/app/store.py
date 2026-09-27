"""SQLite persistence for orders, their audit trail, and which Gmail messages were already handled."""

import json
import secrets
import sqlite3
import threading
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id              TEXT PRIMARY KEY,
    reference       TEXT NOT NULL UNIQUE,
    status          TEXT NOT NULL,
    source          TEXT NOT NULL,          -- email | chat
    fields          TEXT NOT NULL,          -- extracted order fields (JSON)
    gmail_thread_id TEXT,
    last_message_id TEXT,                   -- RFC Message-ID of the customer's latest email, for threaded replies
    subject         TEXT,
    source_ref      TEXT,                   -- e.g. forms service form_id for chat orders
    reminders_sent  INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS orders_thread ON orders(gmail_thread_id);
CREATE UNIQUE INDEX IF NOT EXISTS orders_source_ref ON orders(source_ref);
CREATE TABLE IF NOT EXISTS events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id  TEXT NOT NULL,
    at        TEXT NOT NULL,
    type      TEXT NOT NULL,
    actor     TEXT NOT NULL,
    detail    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_order ON events(order_id);
CREATE TABLE IF NOT EXISTS processed_messages (
    message_id TEXT PRIMARY KEY,
    outcome    TEXT NOT NULL,
    at         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

STATUSES = ('new', 'missing_info', 'awaiting_customer', 'ready_for_approval', 'approved', 'processing', 'rejected')
CLOSED = ('approved', 'processing', 'rejected')


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Store:
    def __init__(self, path: str):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # ---- settings ----
    def get_setting(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return row[0] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute('INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)', (key, value))
            self._conn.commit()

    # ---- processed Gmail messages ----
    def is_processed(self, message_id: str) -> bool:
        with self._lock:
            return self._conn.execute('SELECT 1 FROM processed_messages WHERE message_id=?', (message_id,)).fetchone() is not None

    def mark_processed(self, message_id: str, outcome: str) -> None:
        with self._lock:
            self._conn.execute(
                'INSERT OR IGNORE INTO processed_messages(message_id, outcome, at) VALUES (?, ?, ?)', (message_id, outcome, now())
            )
            self._conn.commit()

    # ---- orders ----
    def create_order(self, *, source: str, fields: dict, status: str, gmail_thread_id=None, last_message_id=None,
                     subject=None, source_ref=None) -> dict:
        order_id = secrets.token_urlsafe(12)
        with self._lock:
            while True:
                reference = f'ORD-{secrets.token_hex(3).upper()}'
                if not self._conn.execute('SELECT 1 FROM orders WHERE reference=?', (reference,)).fetchone():
                    break
            ts = now()
            self._conn.execute(
                'INSERT INTO orders(id, reference, status, source, fields, gmail_thread_id, last_message_id, subject, '
                'source_ref, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                (order_id, reference, status, source, json.dumps(fields), gmail_thread_id, last_message_id, subject,
                 source_ref, ts, ts),
            )
            self._conn.commit()
        return self.get(order_id)

    def update_order(self, order_id: str, **changes) -> dict:
        if 'fields' in changes:
            changes['fields'] = json.dumps(changes['fields'])
        changes['updated_at'] = now()
        cols = ', '.join(f'{k}=?' for k in changes)
        with self._lock:
            self._conn.execute(f'UPDATE orders SET {cols} WHERE id=?', (*changes.values(), order_id))
            self._conn.commit()
        return self.get(order_id)

    def set_status_if(self, order_id: str, expected: tuple, status: str) -> bool:
        """Atomic status transition; False if the order is not in one of the expected states."""
        with self._lock:
            cur = self._conn.execute(
                f'UPDATE orders SET status=?, updated_at=? WHERE id=? AND status IN ({",".join("?" * len(expected))})',
                (status, now(), order_id, *expected),
            )
            self._conn.commit()
            return cur.rowcount == 1

    def get(self, order_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute('SELECT * FROM orders WHERE id=? OR reference=?', (order_id, order_id)).fetchone()
        return _order(row) if row else None

    def find_open_by_thread(self, thread_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                f'SELECT * FROM orders WHERE gmail_thread_id=? AND status NOT IN ({",".join("?" * len(CLOSED))}) '
                'ORDER BY created_at DESC LIMIT 1',
                (thread_id, *CLOSED),
            ).fetchone()
        return _order(row) if row else None

    def find_latest_by_thread(self, thread_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                'SELECT * FROM orders WHERE gmail_thread_id=? ORDER BY created_at DESC LIMIT 1', (thread_id,)
            ).fetchone()
        return _order(row) if row else None

    def find_by_source_ref(self, source_ref: str) -> dict | None:
        with self._lock:
            row = self._conn.execute('SELECT * FROM orders WHERE source_ref=?', (source_ref,)).fetchone()
        return _order(row) if row else None

    def list_orders(self, status: str | None = None, limit: int = 200) -> list[dict]:
        with self._lock:
            if status:
                rows = self._conn.execute('SELECT * FROM orders WHERE status=? ORDER BY updated_at DESC LIMIT ?', (status, limit)).fetchall()
            else:
                rows = self._conn.execute('SELECT * FROM orders ORDER BY updated_at DESC LIMIT ?', (limit,)).fetchall()
        return [_order(r) for r in rows]

    def counts(self) -> dict:
        with self._lock:
            rows = self._conn.execute('SELECT status, COUNT(*) FROM orders GROUP BY status').fetchall()
        out = {s: 0 for s in STATUSES}
        out.update({r[0]: r[1] for r in rows})
        return out

    # ---- audit trail ----
    def add_event(self, order_id: str, type_: str, actor: str, detail: dict | None = None) -> None:
        with self._lock:
            self._conn.execute(
                'INSERT INTO events(order_id, at, type, actor, detail) VALUES (?, ?, ?, ?, ?)',
                (order_id, now(), type_, actor, json.dumps(detail or {})),
            )
            self._conn.commit()

    def events(self, order_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute('SELECT * FROM events WHERE order_id=? ORDER BY id', (order_id,)).fetchall()
        return [{'at': r['at'], 'type': r['type'], 'actor': r['actor'], 'detail': json.loads(r['detail'])} for r in rows]


def _order(row: sqlite3.Row) -> dict:
    out = dict(row)
    out['fields'] = json.loads(out['fields'])
    return out
