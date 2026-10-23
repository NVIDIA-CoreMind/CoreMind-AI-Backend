"""
CoreMind Backend — Google sign-in state storage.

A sign-in state is single-use and expires after 10 minutes. It is kept in the shared SQLite
database, not in process memory, so a backend restart between starting a sign-in and the Google
callback does not reject it. Any backend process that shares the database can complete it.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from src.config import settings

DEFAULT_TTL_SECONDS = 600


class OAuthStateStore:
    """Thread-safe store of issued, unused sign-in states."""

    def __init__(self, db_path: str | None = None, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self.db_path = db_path or settings.sqlite_db_path
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_states (
                    state TEXT PRIMARY KEY,
                    expires_at REAL NOT NULL
                )
                """
            )

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Open a connection, commit the transaction on success, and always close it."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def issue(self, state: str) -> None:
        """Record a state handed to the browser for a new sign-in."""
        with self._lock, self._get_connection() as conn:
            conn.execute("DELETE FROM oauth_states WHERE expires_at < ?", (time.time(),))
            conn.execute(
                "INSERT OR REPLACE INTO oauth_states (state, expires_at) VALUES (?, ?)",
                (state, time.time() + self.ttl_seconds),
            )

    def consume(self, state: str) -> bool:
        """Return True once for an issued, unexpired state. The state is removed on success."""
        with self._lock, self._get_connection() as conn:
            conn.execute("DELETE FROM oauth_states WHERE expires_at < ?", (time.time(),))
            cursor = conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
            return cursor.rowcount == 1
