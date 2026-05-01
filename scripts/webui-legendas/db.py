import sqlite3
import os
import threading
import time
from pathlib import Path

from config import MEDIA_DIR

DB_DIR = os.path.join(MEDIA_DIR, ".legendas-webui")
DB_PATH = os.path.join(DB_DIR, "jobs.db")

_local = threading.local()


def _get_conn():
    if not hasattr(_local, "conn"):
        Path(DB_DIR).mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def init_db():
    db = _get_conn()
    db.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'external',
            video_path TEXT,
            stream_index INTEGER,
            codec TEXT,
            language TEXT,
            output TEXT NOT NULL,
            filename TEXT,
            score INTEGER DEFAULT 0,
            reason TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            error TEXT,
            created_at REAL NOT NULL,
            started_at REAL,
            completed_at REAL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS translated (
            output TEXT PRIMARY KEY,
            source TEXT,
            source_type TEXT,
            language TEXT,
            completed_at REAL NOT NULL
        )
    """)
    db.commit()


def insert_job(job_data):
    db = _get_conn()
    cursor = db.execute(
        """INSERT INTO jobs
           (source, source_type, video_path, stream_index, codec,
            language, output, filename, score, reason, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
        (
            job_data.get("source"),
            job_data.get("source_type", "external"),
            job_data.get("video_path"),
            job_data.get("stream_index"),
            job_data.get("codec"),
            job_data.get("language"),
            job_data.get("output"),
            job_data.get("filename"),
            job_data.get("score", 0),
            job_data.get("reason"),
            time.time(),
        ),
    )
    db.commit()
    return cursor.lastrowid


def update_job_status(job_id, status, error=None):
    db = _get_conn()
    now = time.time()
    if status == "running":
        db.execute(
            "UPDATE jobs SET status = ?, started_at = ? WHERE id = ?",
            (status, now, job_id),
        )
    elif status in ("completed", "failed"):
        db.execute(
            "UPDATE jobs SET status = ?, completed_at = ?, error = ? WHERE id = ?",
            (status, now, error, job_id),
        )
    else:
        db.execute(
            "UPDATE jobs SET status = ?, error = ? WHERE id = ?",
            (status, error, job_id),
        )
    db.commit()


def mark_translated(output, source, source_type, language):
    db = _get_conn()
    db.execute(
        "INSERT OR REPLACE INTO translated (output, source, source_type, language, completed_at) VALUES (?, ?, ?, ?, ?)",
        (output, source, source_type, language, time.time()),
    )
    db.commit()


def is_already_translated(output):
    db = _get_conn()
    row = db.execute("SELECT 1 FROM translated WHERE output = ?", (output,)).fetchone()
    return row is not None


def load_pending_jobs():
    db = _get_conn()
    rows = db.execute(
        "SELECT * FROM jobs WHERE status = 'pending' ORDER BY score DESC, created_at ASC"
    ).fetchall()
    return [dict(row) for row in rows]


def get_job(job_id):
    db = _get_conn()
    row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(status=None, limit=50):
    db = _get_conn()
    if status:
        rows = db.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def get_completed_jobs(limit=20):
    db = _get_conn()
    rows = db.execute(
        "SELECT * FROM jobs WHERE status = 'completed' ORDER BY completed_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def count_jobs(status=None):
    db = _get_conn()
    if status:
        row = db.execute(
            "SELECT COUNT(*) as cnt FROM jobs WHERE status = ?", (status,)
        ).fetchone()
    else:
        row = db.execute("SELECT COUNT(*) as cnt FROM jobs").fetchone()
    return row["cnt"] if row else 0


def job_source_exists(source, output):
    db = _get_conn()
    row = db.execute(
        "SELECT 1 FROM jobs WHERE source = ? AND output = ? AND status IN ('pending', 'running')",
        (source, output),
    ).fetchone()
    if row:
        return True
    row = db.execute("SELECT 1 FROM translated WHERE output = ?", (output,)).fetchone()
    return row is not None


def cleanup_old_jobs(keep=200):
    db = _get_conn()
    db.execute(
        "DELETE FROM jobs WHERE id NOT IN (SELECT id FROM jobs ORDER BY created_at DESC LIMIT ?)",
        (keep,),
    )
    db.commit()
