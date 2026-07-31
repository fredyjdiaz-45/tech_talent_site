"""SQLite connection management.

Plain ``sqlite3`` rather than an async driver or an ORM: the dataset is small
(tens of thousands of rows), and keeping it dependency-free makes the project
easy to run anywhere. Blocking calls are pushed to a thread with
``asyncio.to_thread`` so FastAPI's event loop is never held up.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from state_parks.config import settings

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

T = TypeVar("T")

#: ``run_db`` hands work to a thread pool, so the connection is shared across
#: threads (``check_same_thread=False``) and every access is serialized through
#: this lock. Serializing is not a bottleneck here -- the queries are small and
#: SQLite writes are single-writer anyway -- and it rules out both cross-thread
#: misuse and two threads interleaving each other's transactions.
_db_lock = threading.RLock()


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open a connection with sane defaults and the schema applied."""
    db_path = Path(path) if path is not None else settings.database_path
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        db_path, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Apply the schema. Safe to call repeatedly (all DDL is IF NOT EXISTS)."""
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()


async def run_db(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a blocking DB callable off the event loop, one at a time."""

    def _locked() -> T:
        with _db_lock:
            return fn(*args, **kwargs)

    return await asyncio.to_thread(_locked)


class Database:
    """Small holder so the API and scheduler share one connection lifecycle."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = path
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = connect(self.path)
            init_db(self._conn)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
