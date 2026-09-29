"""Metadata persistence with PostgreSQL production mode and SQLite fallback.

The public functions preserve the original store API so routers do not depend
on one SQL engine. PostgreSQL is used in production; ``auto`` mode falls back
to SQLite for a zero-configuration local preview.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional


logger = logging.getLogger(__name__)
# Keep the original local filename so existing development sessions migrate in
# place when the replay-capsule tables are added.
DB_PATH = Path(__file__).parent.parent / "db" / "sessions.db"


class _SQLiteStore:
    backend = "sqlite"

    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._setup()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _setup(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS files (
                    file_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    paper_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL DEFAULT '',
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    page_count INTEGER NOT NULL DEFAULT 0,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_files_content_hash
                    ON files(content_hash) WHERE content_hash <> '';
                CREATE TABLE IF NOT EXISTS answer_capsules (
                    capsule_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    answer_hash TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_capsules_session_created
                    ON answer_capsules(session_id, created_at DESC);
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(files)").fetchall()}
            if "content_hash" not in columns:
                conn.execute("ALTER TABLE files ADD COLUMN content_hash TEXT NOT NULL DEFAULT ''")

    def create_session(self, session_id: str, title: str = "") -> dict:
        now = time.time()
        with self._connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, title, now, now),
            )
        return {"session_id": session_id, "title": title, "created_at": now, "updated_at": now}

    def update_session(self, session_id: str, title: Optional[str] = None) -> bool:
        values: list[Any] = [time.time()]
        assignments = ["updated_at = ?"]
        if title is not None:
            assignments.append("title = ?")
            values.append(title)
        values.append(session_id)
        with self._connection() as conn:
            cursor = conn.execute(
                f"UPDATE sessions SET {', '.join(assignments)} WHERE session_id = ?", values
            )
            return cursor.rowcount > 0

    def list_sessions(self) -> list[dict]:
        with self._connection() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC"
            ).fetchall()]

    def get_session(self, session_id: str) -> Optional[dict]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
            return dict(row) if row else None

    def delete_session(self, session_id: str) -> bool:
        with self._connection() as conn:
            conn.execute("DELETE FROM answer_capsules WHERE session_id = ?", (session_id,))
            cursor = conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            return cursor.rowcount > 0

    def add_file(
        self, file_id: str, filename: str, paper_id: str, content_hash: str = "",
        size_bytes: int = 0, page_count: int = 0, chunk_count: int = 0,
    ) -> dict:
        now = time.time()
        with self._connection() as conn:
            conn.execute(
                """INSERT INTO files
                   (file_id, filename, paper_id, content_hash, size_bytes, page_count, chunk_count, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(file_id) DO UPDATE SET
                     filename=excluded.filename, paper_id=excluded.paper_id,
                     content_hash=excluded.content_hash, size_bytes=excluded.size_bytes,
                     page_count=excluded.page_count, chunk_count=excluded.chunk_count""",
                (file_id, filename, paper_id, content_hash, size_bytes, page_count, chunk_count, now),
            )
        return {
            "file_id": file_id, "filename": filename, "paper_id": paper_id,
            "content_hash": content_hash, "size_bytes": size_bytes,
            "page_count": page_count, "chunk_count": chunk_count, "created_at": now,
        }

    def list_files(self) -> list[dict]:
        with self._connection() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM files ORDER BY created_at DESC"
            ).fetchall()]

    def get_file(self, file_id: str) -> Optional[dict]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM files WHERE file_id = ?", (file_id,)).fetchone()
            return dict(row) if row else None

    def get_file_by_hash(self, content_hash: str) -> Optional[dict]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM files WHERE content_hash = ?", (content_hash,)).fetchone()
            return dict(row) if row else None

    def delete_file_record(self, file_id: str) -> Optional[dict]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM files WHERE file_id = ?", (file_id,)).fetchone()
            if not row:
                return None
            conn.execute("DELETE FROM files WHERE file_id = ?", (file_id,))
            return dict(row)

    def clear_all_files(self) -> int:
        with self._connection() as conn:
            cursor = conn.execute("DELETE FROM files")
            return cursor.rowcount

    def save_capsule(self, capsule: dict) -> dict:
        with self._connection() as conn:
            conn.execute(
                """INSERT INTO answer_capsules
                   (capsule_id, session_id, query, answer_hash, payload, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    capsule["capsule_id"], capsule["session_id"], capsule["query"],
                    capsule["answer_hash"], json.dumps(capsule, ensure_ascii=False), capsule["created_at"],
                ),
            )
        return capsule

    def list_capsules(self, session_id: str) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT payload FROM answer_capsules WHERE session_id = ? ORDER BY created_at DESC",
                (session_id,),
            ).fetchall()
            return [json.loads(row["payload"]) for row in rows]

    def get_capsule(self, capsule_id: str) -> Optional[dict]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT payload FROM answer_capsules WHERE capsule_id = ?", (capsule_id,)
            ).fetchone()
            return json.loads(row["payload"]) if row else None

    def close(self) -> None:
        return None


class _PostgresStore:
    backend = "postgres"

    def __init__(self, uri: str):
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        self.pool = ConnectionPool(
            conninfo=uri,
            min_size=1,
            max_size=8,
            kwargs={"row_factory": dict_row},
            open=True,
        )
        self.pool.wait(timeout=5)
        self._setup()

    def _setup(self) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    created_at DOUBLE PRECISION NOT NULL,
                    updated_at DOUBLE PRECISION NOT NULL
                );
                CREATE TABLE IF NOT EXISTS files (
                    file_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    paper_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL DEFAULT '',
                    size_bytes BIGINT NOT NULL DEFAULT 0,
                    page_count INTEGER NOT NULL DEFAULT 0,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    created_at DOUBLE PRECISION NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_files_content_hash
                    ON files(content_hash) WHERE content_hash <> '';
                CREATE TABLE IF NOT EXISTS answer_capsules (
                    capsule_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                    query TEXT NOT NULL,
                    answer_hash TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    created_at DOUBLE PRECISION NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_capsules_session_created
                    ON answer_capsules(session_id, created_at DESC);
                """
            )

    def create_session(self, session_id: str, title: str = "") -> dict:
        now = time.time()
        with self.pool.connection() as conn:
            conn.execute(
                """INSERT INTO sessions (session_id, title, created_at, updated_at)
                   VALUES (%s, %s, %s, %s) ON CONFLICT (session_id) DO NOTHING""",
                (session_id, title, now, now),
            )
        return {"session_id": session_id, "title": title, "created_at": now, "updated_at": now}

    def update_session(self, session_id: str, title: Optional[str] = None) -> bool:
        with self.pool.connection() as conn:
            if title is None:
                cursor = conn.execute(
                    "UPDATE sessions SET updated_at=%s WHERE session_id=%s", (time.time(), session_id)
                )
            else:
                cursor = conn.execute(
                    "UPDATE sessions SET updated_at=%s, title=%s WHERE session_id=%s",
                    (time.time(), title, session_id),
                )
            return cursor.rowcount > 0

    def list_sessions(self) -> list[dict]:
        with self.pool.connection() as conn:
            return list(conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC").fetchall())

    def get_session(self, session_id: str) -> Optional[dict]:
        with self.pool.connection() as conn:
            return conn.execute("SELECT * FROM sessions WHERE session_id=%s", (session_id,)).fetchone()

    def delete_session(self, session_id: str) -> bool:
        with self.pool.connection() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE session_id=%s", (session_id,))
            return cursor.rowcount > 0

    def add_file(
        self, file_id: str, filename: str, paper_id: str, content_hash: str = "",
        size_bytes: int = 0, page_count: int = 0, chunk_count: int = 0,
    ) -> dict:
        now = time.time()
        with self.pool.connection() as conn:
            conn.execute(
                """INSERT INTO files
                   (file_id, filename, paper_id, content_hash, size_bytes, page_count, chunk_count, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (file_id) DO UPDATE SET
                     filename=EXCLUDED.filename, paper_id=EXCLUDED.paper_id,
                     content_hash=EXCLUDED.content_hash, size_bytes=EXCLUDED.size_bytes,
                     page_count=EXCLUDED.page_count, chunk_count=EXCLUDED.chunk_count""",
                (file_id, filename, paper_id, content_hash, size_bytes, page_count, chunk_count, now),
            )
        return {
            "file_id": file_id, "filename": filename, "paper_id": paper_id,
            "content_hash": content_hash, "size_bytes": size_bytes,
            "page_count": page_count, "chunk_count": chunk_count, "created_at": now,
        }

    def list_files(self) -> list[dict]:
        with self.pool.connection() as conn:
            return list(conn.execute("SELECT * FROM files ORDER BY created_at DESC").fetchall())

    def get_file(self, file_id: str) -> Optional[dict]:
        with self.pool.connection() as conn:
            return conn.execute("SELECT * FROM files WHERE file_id=%s", (file_id,)).fetchone()

    def get_file_by_hash(self, content_hash: str) -> Optional[dict]:
        with self.pool.connection() as conn:
            return conn.execute("SELECT * FROM files WHERE content_hash=%s", (content_hash,)).fetchone()

    def delete_file_record(self, file_id: str) -> Optional[dict]:
        with self.pool.connection() as conn:
            return conn.execute("DELETE FROM files WHERE file_id=%s RETURNING *", (file_id,)).fetchone()

    def clear_all_files(self) -> int:
        with self.pool.connection() as conn:
            return conn.execute("DELETE FROM files").rowcount

    def save_capsule(self, capsule: dict) -> dict:
        from psycopg.types.json import Jsonb

        with self.pool.connection() as conn:
            conn.execute(
                """INSERT INTO answer_capsules
                   (capsule_id, session_id, query, answer_hash, payload, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    capsule["capsule_id"], capsule["session_id"], capsule["query"],
                    capsule["answer_hash"], Jsonb(capsule), capsule["created_at"],
                ),
            )
        return capsule

    def list_capsules(self, session_id: str) -> list[dict]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT payload FROM answer_capsules WHERE session_id=%s ORDER BY created_at DESC",
                (session_id,),
            ).fetchall()
            return [row["payload"] for row in rows]

    def get_capsule(self, capsule_id: str) -> Optional[dict]:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT payload FROM answer_capsules WHERE capsule_id=%s", (capsule_id,)
            ).fetchone()
            return row["payload"] if row else None

    def close(self) -> None:
        self.pool.close()


_store: _SQLiteStore | _PostgresStore | None = None


def initialize_store(postgres_uri: str = "", backend: str = "auto") -> str:
    """Initialize metadata persistence and return the selected backend name."""
    global _store
    if _store is not None:
        return _store.backend
    if backend in {"auto", "postgres"} and postgres_uri:
        try:
            _store = _PostgresStore(postgres_uri)
            logger.info("Metadata store: PostgreSQL")
            return _store.backend
        except Exception as exc:
            if backend == "postgres":
                raise
            logger.warning("PostgreSQL metadata unavailable; using SQLite fallback: %s", exc)
    _store = _SQLiteStore()
    logger.info("Metadata store: SQLite fallback")
    return _store.backend


def close_store() -> None:
    global _store
    if _store is not None:
        _store.close()
        _store = None


def _get_store():
    global _store
    if _store is None:
        _store = _SQLiteStore()
    return _store


def store_backend() -> str:
    return _get_store().backend


def create_session(session_id: str, title: str = "") -> dict:
    return _get_store().create_session(session_id, title)


def update_session(session_id: str, title: Optional[str] = None) -> bool:
    return _get_store().update_session(session_id, title)


def list_sessions() -> list[dict]:
    return _get_store().list_sessions()


def get_session(session_id: str) -> Optional[dict]:
    return _get_store().get_session(session_id)


def delete_session(session_id: str) -> bool:
    return _get_store().delete_session(session_id)


def add_file(
    file_id: str, filename: str, paper_id: str, content_hash: str = "",
    size_bytes: int = 0, page_count: int = 0, chunk_count: int = 0,
) -> dict:
    return _get_store().add_file(
        file_id, filename, paper_id, content_hash, size_bytes, page_count, chunk_count
    )


def list_files() -> list[dict]:
    return _get_store().list_files()


def get_file(file_id: str) -> Optional[dict]:
    return _get_store().get_file(file_id)


def get_file_by_hash(content_hash: str) -> Optional[dict]:
    return _get_store().get_file_by_hash(content_hash)


def delete_file_record(file_id: str) -> Optional[dict]:
    return _get_store().delete_file_record(file_id)


def clear_all_files() -> int:
    return _get_store().clear_all_files()


def save_capsule(capsule: dict) -> dict:
    return _get_store().save_capsule(capsule)


def list_capsules(session_id: str) -> list[dict]:
    return _get_store().list_capsules(session_id)


def get_capsule(capsule_id: str) -> Optional[dict]:
    return _get_store().get_capsule(capsule_id)
