"""SQLite connection helpers for ResumeIQ."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
DEFAULT_DB_PATH = BASE_DIR / "database" / "resumeiq.db"


def resolve_db_path(db_path: str | Path | None = None) -> Path:
    """Return an absolute database path (relative paths live in the project)."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    path = Path(db_path)
    if not path.is_absolute():
        path = BASE_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a connection with row access by name and foreign keys enforced."""
    path = resolve_db_path(db_path)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session(db_path: str | Path | None = None):
    """Transactional connection that always closes."""
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str | Path | None = None) -> Path:
    """Create tables (idempotent) and seed the singleton profile row."""
    path = resolve_db_path(db_path)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = connect(path)
    try:
        conn.executescript(schema)
        conn.execute("INSERT OR IGNORE INTO profile (id) VALUES (1)")
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('default_template', 'classic')"
        )
        conn.commit()
    finally:
        conn.close()
    return path
