from __future__ import annotations
import os
import sqlite3
import time
import json
from typing import Dict, Optional

# SQLite-backed job store. Database file is stored under ./storage/ingest_jobs.sqlite by default.
DB_PATH = os.environ.get("INGEST_JOBS_DB", "./storage/ingest_jobs.sqlite")


def _ensure_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                session_id TEXT,
                status TEXT,
                progress INTEGER,
                result TEXT,
                ts_created INTEGER,
                ts_updated INTEGER
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _now_ms() -> int:
    return int(time.time() * 1000)


def create_job(session_id: str) -> str:
    """Create a new job and persist to sqlite. Returns job_id."""
    _ensure_db()
    job_id = f"job-{_now_ms()}"
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO jobs (job_id, session_id, status, progress, result, ts_created, ts_updated) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_id, session_id, "pending", 0, None, _now_ms(), _now_ms()),
        )
        conn.commit()
    finally:
        conn.close()
    return job_id


def get_job(job_id: str) -> Optional[Dict]:
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT job_id, session_id, status, progress, result, ts_created, ts_updated FROM jobs WHERE job_id = ?",
            (job_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        job = {
            "job_id": row[0],
            "session_id": row[1],
            "status": row[2],
            "progress": int(row[3] or 0),
            "result": json.loads(row[4]) if row[4] else None,
            "ts_created": int(row[5] or 0),
            "ts_updated": int(row[6] or 0),
        }
        return job
    finally:
        conn.close()


def _update_job_row(
    job_id: str,
    status: str | None = None,
    progress: int | None = None,
    result: Dict | None = None,
) -> None:
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        fields = []
        params = []
        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if progress is not None:
            fields.append("progress = ?")
            params.append(int(max(0, min(100, int(progress)))))
        if result is not None:
            fields.append("result = ?")
            params.append(json.dumps(result, ensure_ascii=False))
        # always update timestamp
        fields.append("ts_updated = ?")
        params.append(_now_ms())
        params.append(job_id)
        if not fields:
            return
        sql = f"UPDATE jobs SET {', '.join(fields)} WHERE job_id = ?"
        cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def set_job_progress(job_id: str, percent: int) -> None:
    _update_job_row(job_id, progress=percent)


def set_job_done(job_id: str, result: Dict | None = None) -> None:
    _update_job_row(job_id, status="done", progress=100, result=result)


def set_job_failed(job_id: str, error: str) -> None:
    _update_job_row(job_id, status="failed", result={"error": error})
