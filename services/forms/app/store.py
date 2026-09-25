"""SQLite persistence for form instances (one row per form shown to a user)."""

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS forms (
    id          TEXT PRIMARY KEY,
    form_type   TEXT NOT NULL,
    status      TEXT NOT NULL,          -- draft | submitted | executed | failed
    prefill     TEXT NOT NULL,
    missing     TEXT NOT NULL,
    values_json TEXT,
    result      TEXT,
    context     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS forms_created ON forms(created_at);
CREATE TABLE IF NOT EXISTS json_views (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT NOT NULL,
    schema      TEXT NOT NULL,
    ui_schema   TEXT NOT NULL,
    data_json   TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS json_views_created ON json_views(created_at);
"""

JSON_COLUMNS = ('prefill', 'missing', 'values_json', 'result', 'context')
VIEW_JSON_COLUMNS = ('schema', 'ui_schema', 'data_json')


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Store:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)

    def create(self, form_id: str, form_type: str, prefill: dict, missing: list, context: dict, ttl_hours: int) -> dict:
        now = _now()
        row = {
            'id': form_id,
            'form_type': form_type,
            'status': 'draft',
            'prefill': json.dumps(prefill),
            'missing': json.dumps(missing),
            'values_json': None,
            'result': None,
            'context': json.dumps(context),
            'created_at': now.isoformat(),
            'updated_at': now.isoformat(),
            'expires_at': (now + timedelta(hours=ttl_hours)).isoformat(),
        }
        with self._lock:
            self._conn.execute(
                f'INSERT INTO forms ({",".join(row)}) VALUES ({",".join("?" * len(row))})', tuple(row.values())
            )
            self._conn.commit()
        return self.get(form_id)

    def get(self, form_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute('SELECT * FROM forms WHERE id = ?', (form_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        for col in JSON_COLUMNS:
            data[col] = json.loads(data[col]) if data[col] else None
        data['values'] = data.pop('values_json')
        data['expired'] = datetime.fromisoformat(data['expires_at']) < _now() and data['status'] == 'draft'
        return data

    def claim_for_submit(self, form_id: str, values: dict) -> bool:
        """Atomically move draft -> submitted so a form can only be submitted once."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE forms SET status='submitted', values_json=?, updated_at=? WHERE id=? AND status='draft'",
                (json.dumps(values), _now().isoformat(), form_id),
            )
            self._conn.commit()
            return cur.rowcount == 1

    def finish(self, form_id: str, status: str, result: dict) -> None:
        with self._lock:
            self._conn.execute(
                'UPDATE forms SET status=?, result=?, updated_at=? WHERE id=?',
                (status, json.dumps(result), _now().isoformat(), form_id),
            )
            self._conn.commit()

    def recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            ids = [r[0] for r in self._conn.execute('SELECT id FROM forms ORDER BY created_at DESC LIMIT ?', (limit,))]
        return [self.get(i) for i in ids]

    def create_view(
        self,
        view_id: str,
        title: str,
        description: str,
        schema: dict,
        ui_schema: dict,
        data: dict,
        ttl_hours: int,
    ) -> dict:
        now = _now()
        row = {
            'id': view_id,
            'title': title,
            'description': description,
            'schema': json.dumps(schema),
            'ui_schema': json.dumps(ui_schema),
            'data_json': json.dumps(data),
            'created_at': now.isoformat(),
            'expires_at': (now + timedelta(hours=ttl_hours)).isoformat(),
        }
        with self._lock:
            self._conn.execute(
                f'INSERT INTO json_views ({",".join(row)}) VALUES ({",".join("?" * len(row))})', tuple(row.values())
            )
            self._conn.commit()
        return self.get_view(view_id)

    def get_view(self, view_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute('SELECT * FROM json_views WHERE id = ?', (view_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        for col in VIEW_JSON_COLUMNS:
            data[col] = json.loads(data[col]) if data[col] else None
        data['data'] = data.pop('data_json')
        data['expired'] = datetime.fromisoformat(data['expires_at']) < _now()
        return data
