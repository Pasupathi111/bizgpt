"""SQLite persistence for reports and photos; photo files live next to the database."""

import json
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

REPORT_STATUSES = ['draft', 'processing', 'analyzed', 'in_review', 'rejected', 'approved']

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    month TEXT NOT NULL,
    status TEXT NOT NULL,
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    progress TEXT NOT NULL DEFAULT '{}',
    content TEXT,
    remarks TEXT NOT NULL DEFAULT '',
    decision TEXT
);
CREATE TABLE IF NOT EXISTS photos (
    id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL REFERENCES reports(id),
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    media_type TEXT NOT NULL,
    exif_datetime TEXT,
    status TEXT NOT NULL,
    ai TEXT,
    error TEXT,
    overrides TEXT NOT NULL DEFAULT '{}',
    reviewed INTEGER NOT NULL DEFAULT 0,
    excluded INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gmail_messages (
    message_id TEXT PRIMARY KEY,
    subject TEXT,
    sender TEXT,
    status TEXT NOT NULL,
    report_id TEXT,
    photos INTEGER NOT NULL DEFAULT 0,
    detail TEXT,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id TEXT NOT NULL,
    type TEXT NOT NULL,
    actor TEXT,
    detail TEXT,
    at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.photo_dir = self.data_dir / 'photos'
        self.pdf_dir = self.data_dir / 'pdf'
        self.library_dir = self.data_dir / 'library'  # approved photos + PDF, one folder per project/month
        self.photo_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.data_dir / 'monthly_report.db', check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)

    def _exec(self, sql: str, args: tuple = ()):
        with self._lock:
            cur = self._db.execute(sql, args)
            self._db.commit()
            return cur

    def _all(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, args).fetchall()]

    # ------------------------------------------------------------ reports
    def create_report(self, project_id: str, month: str, created_by: str | None, report_id: str | None = None) -> dict:
        rid = report_id or f'MR-{secrets.token_hex(3).upper()}'
        ts = now()
        self._exec(
            'INSERT INTO reports (id, project_id, month, status, created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?)',
            (rid, project_id, month, 'draft', created_by, ts, ts),
        )
        self.event(rid, 'created', created_by, f'{project_id} {month}')
        return self.get_report(rid)

    def get_report(self, rid: str) -> dict | None:
        rows = self._all('SELECT * FROM reports WHERE id = ?', (rid,))
        if not rows:
            return None
        r = rows[0]
        r['progress'] = json.loads(r['progress'] or '{}')
        r['content'] = json.loads(r['content']) if r['content'] else None
        r['decision'] = json.loads(r['decision']) if r['decision'] else None
        return r

    def list_reports(self) -> list[dict]:
        rows = self._all(
            'SELECT r.id, r.project_id, r.month, r.status, r.created_by, r.created_at, r.updated_at, '
            '(SELECT COUNT(*) FROM photos p WHERE p.report_id = r.id) AS photo_count '
            'FROM reports r ORDER BY r.created_at DESC LIMIT 200'
        )
        return rows

    def update_report(self, rid: str, **fields):
        encoded = {k: json.dumps(v) if k in ('progress', 'content', 'decision') and v is not None else v for k, v in fields.items()}
        encoded['updated_at'] = now()
        cols = ', '.join(f'{k} = ?' for k in encoded)
        self._exec(f'UPDATE reports SET {cols} WHERE id = ?', (*encoded.values(), rid))

    # ------------------------------------------------------------ photos
    def add_photo(self, rid: str, filename: str, data: bytes, media_type: str, exif_datetime: str | None) -> dict:
        pid = secrets.token_hex(8)
        suffix = Path(filename).suffix.lower() or '.jpg'
        path = self.photo_dir / f'{rid}-{pid}{suffix}'
        path.write_bytes(data)
        position = self._all('SELECT COALESCE(MAX(position), 0) + 1 AS n FROM photos WHERE report_id = ?', (rid,))[0]['n']
        self._exec(
            'INSERT INTO photos (id, report_id, filename, path, media_type, exif_datetime, status, position, created_at) '
            'VALUES (?,?,?,?,?,?,?,?,?)',
            (pid, rid, filename, str(path), media_type, exif_datetime, 'pending', position, now()),
        )
        return self.get_photo(rid, pid)

    def get_photo(self, rid: str, pid: str) -> dict | None:
        rows = self._all('SELECT * FROM photos WHERE report_id = ? AND id = ?', (rid, pid))
        return self._photo(rows[0]) if rows else None

    def photos(self, rid: str) -> list[dict]:
        return [self._photo(r) for r in self._all('SELECT * FROM photos WHERE report_id = ? ORDER BY position', (rid,))]

    def update_photo(self, pid: str, **fields):
        encoded = {k: json.dumps(v) if k in ('ai', 'overrides') and v is not None else v for k, v in fields.items()}
        cols = ', '.join(f'{k} = ?' for k in encoded)
        self._exec(f'UPDATE photos SET {cols} WHERE id = ?', (*encoded.values(), pid))

    def delete_photo(self, rid: str, pid: str) -> bool:
        photo = self.get_photo(rid, pid)
        if not photo:
            return False
        Path(photo['path']).unlink(missing_ok=True)
        self._exec('DELETE FROM photos WHERE id = ?', (pid,))
        return True

    @staticmethod
    def _photo(row: dict) -> dict:
        row['ai'] = json.loads(row['ai']) if row['ai'] else None
        row['overrides'] = json.loads(row['overrides'] or '{}')
        row['reviewed'] = bool(row['reviewed'])
        row['excluded'] = bool(row['excluded'])
        return row

    # ------------------------------------------------------------ gmail intake
    def gmail_seen(self, message_id: str) -> dict | None:
        rows = self._all('SELECT * FROM gmail_messages WHERE message_id = ?', (message_id,))
        return rows[0] if rows else None

    def gmail_record(self, message_id: str, subject: str, sender: str, status: str, report_id: str | None = None,
                     photos: int = 0, detail: str | None = None):
        self._exec(
            'INSERT OR REPLACE INTO gmail_messages (message_id, subject, sender, status, report_id, photos, detail, at) '
            'VALUES (?,?,?,?,?,?,?,?)',
            (message_id, subject, sender, status, report_id, photos, detail, now()),
        )

    def gmail_recent(self, limit: int = 30) -> list[dict]:
        return self._all('SELECT * FROM gmail_messages ORDER BY at DESC LIMIT ?', (limit,))

    def find_open_report(self, project_id: str, month: str) -> dict | None:
        rows = self._all(
            "SELECT id FROM reports WHERE project_id = ? AND month = ? AND status IN ('draft','analyzed','in_review','rejected') "
            'ORDER BY created_at DESC LIMIT 1', (project_id, month))
        return self.get_report(rows[0]['id']) if rows else None

    # ------------------------------------------------------------ events
    def event(self, rid: str, type_: str, actor: str | None = None, detail: str | None = None):
        self._exec('INSERT INTO events (report_id, type, actor, detail, at) VALUES (?,?,?,?,?)', (rid, type_, actor, detail, now()))

    def events(self, rid: str) -> list[dict]:
        return self._all('SELECT type, actor, detail, at FROM events WHERE report_id = ? ORDER BY id', (rid,))

    def delete_report(self, rid: str) -> list[str]:
        """Remove a report with its photos, PDF and history; its Gmail emails become importable again.
        Returns the photo file paths so the caller can delete the files."""
        paths = [r['path'] for r in self._all('SELECT path FROM photos WHERE report_id = ?', (rid,))]
        with self._lock:
            for sql in ('DELETE FROM photos WHERE report_id = ?', 'DELETE FROM events WHERE report_id = ?',
                        'DELETE FROM gmail_messages WHERE report_id = ?', 'DELETE FROM reports WHERE id = ?'):
                self._db.execute(sql, (rid,))
            self._db.commit()
        return paths

    def cache_get(self, key: str) -> dict | None:
        """Earlier AI answer for exactly the same input, so the same photos always give the same result."""
        rows = self._all('SELECT value FROM ai_cache WHERE key = ?', (key,))
        return json.loads(rows[0]['value']) if rows else None

    def cache_put(self, key: str, value: dict):
        self._exec('INSERT OR REPLACE INTO ai_cache (key, value, at) VALUES (?,?,?)', (key, json.dumps(value), now()))

    def pdf_path(self, rid: str) -> Path:
        return self.pdf_dir / f'{rid}.pdf'
