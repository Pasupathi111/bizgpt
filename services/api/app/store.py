import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS workflow_runs (
    id               TEXT PRIMARY KEY,
    workflow_id      TEXT NOT NULL,
    provider_run_id  TEXT,
    provider_task_id TEXT,
    status           TEXT NOT NULL,
    inputs_json      TEXT NOT NULL,
    outputs_json     TEXT,
    error            TEXT,
    started_at       TEXT NOT NULL,
    finished_at      TEXT
);
CREATE INDEX IF NOT EXISTS workflow_runs_started_at ON workflow_runs(started_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)

    def create_run(self, run_id: str, workflow_id: str, inputs: dict) -> dict:
        row = {
            'id': run_id,
            'workflow_id': workflow_id,
            'provider_run_id': None,
            'provider_task_id': None,
            'status': 'pending',
            'inputs_json': json.dumps(inputs),
            'outputs_json': None,
            'error': None,
            'started_at': _now(),
            'finished_at': None,
        }
        with self._lock:
            self._conn.execute(
                f'INSERT INTO workflow_runs ({",".join(row)}) VALUES ({",".join("?" * len(row))})',
                tuple(row.values()),
            )
            self._conn.commit()
        return self.get_run(run_id)

    def set_run_status(
        self,
        run_id: str,
        *,
        status: str,
        provider_run_id: str | None = None,
        provider_task_id: str | None = None,
        error: str | None = None,
    ) -> dict:
        with self._lock:
            current = self._conn.execute(
                'SELECT provider_run_id, provider_task_id, error FROM workflow_runs WHERE id = ?',
                (run_id,),
            ).fetchone()
            if not current:
                return None
            self._conn.execute(
                """
                UPDATE workflow_runs
                SET status = ?, provider_run_id = ?, provider_task_id = ?, error = ?
                WHERE id = ?
                """,
                (
                    status,
                    provider_run_id if provider_run_id is not None else current['provider_run_id'],
                    provider_task_id if provider_task_id is not None else current['provider_task_id'],
                    error if error is not None else current['error'],
                    run_id,
                ),
            )
            self._conn.commit()
        return self.get_run(run_id)

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        provider_run_id: str | None = None,
        provider_task_id: str | None = None,
        outputs: dict | None = None,
        error: str | None = None,
    ) -> dict:
        with self._lock:
            self._conn.execute(
                """
                UPDATE workflow_runs
                SET status = ?, provider_run_id = ?, provider_task_id = ?, outputs_json = ?, error = ?, finished_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    provider_run_id,
                    provider_task_id,
                    json.dumps(outputs) if outputs is not None else None,
                    error,
                    _now(),
                    run_id,
                ),
            )
            self._conn.commit()
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute('SELECT * FROM workflow_runs WHERE id = ?', (run_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data['inputs'] = json.loads(data.pop('inputs_json') or '{}')
        data['outputs'] = json.loads(data.pop('outputs_json') or '{}')
        return data

    def recent_runs(self, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                'SELECT id FROM workflow_runs ORDER BY started_at DESC LIMIT ?',
                (limit,),
            ).fetchall()
        return [self.get_run(row['id']) for row in rows]

    def runs_for_workflow(self, workflow_id: str, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                'SELECT id FROM workflow_runs WHERE workflow_id = ? ORDER BY started_at DESC LIMIT ?',
                (workflow_id, limit),
            ).fetchall()
        return [self.get_run(row['id']) for row in rows]
