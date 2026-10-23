"""
CoreMind Backend — Google sign-in state storage.

A sign-in state is single-use and expires after 30 minutes, long enough for the password, 2FA,
and account-picker steps on Google's consent page. Each state records the redirect URI it was
issued with, because Google only accepts a code exchanged with that same URI. The state is kept
in the shared SQLite database, not in process memory, so a backend restart between starting a
sign-in and the Google callback does not reject it.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from src.config import settings
from src.utils.logger import logger

DEFAULT_TTL_SECONDS = 30 * 60

_INSERT_STATE = (
    "INSERT OR REPLACE INTO oauth_states (state, expires_at, redirect_uri) VALUES (?, ?, ?)"
)


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
                    expires_at REAL NOT NULL,
                    redirect_uri TEXT NOT NULL DEFAULT ''
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(oauth_states)")}
            if "redirect_uri" not in columns:
                # Rows from before the redirect was stored have no known redirect.
                # consume() refuses them.
                conn.execute(
                    "ALTER TABLE oauth_states ADD COLUMN redirect_uri TEXT NOT NULL DEFAULT ''"
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

    def issue(self, state: str, redirect_uri: str) -> None:
        """Record a state for a new sign-in, with the redirect URI it was sent with."""
        now = time.time()
        with self._lock, self._get_connection() as conn:
            conn.execute("DELETE FROM oauth_states WHERE expires_at < ?", (now,))
            conn.execute(_INSERT_STATE, (state, now + self.ttl_seconds, redirect_uri))
        logger.info(
            "auth.google.state_issued",
            state_prefix=state[:8],
            redirect_uri=redirect_uri,
            db_path=self.db_path,
        )

    def consume(self, state: str) -> str | None:
        """Return the redirect URI a state was issued with, once. None refuses the state.

        The state is removed either way, so it cannot be replayed.
        """
        now = time.time()
        with self._lock, self._get_connection() as conn:
            # One atomic statement. When two backend processes race for the same state,
            # only one of them gets the row.
            row = conn.execute(
                "DELETE FROM oauth_states WHERE state = ? RETURNING expires_at, redirect_uri",
                (state,),
            ).fetchone()
            conn.execute("DELETE FROM oauth_states WHERE expires_at < ?", (now,))
        if row is None:
            logger.warning(
                "auth.google.state_unknown", state_prefix=state[:8], db_path=self.db_path
            )
            return None
        expires_at, redirect_uri = row
        if expires_at < now:
            logger.warning(
                "auth.google.state_expired",
                state_prefix=state[:8],
                seconds_late=round(now - expires_at),
            )
            return None
        if not redirect_uri:
            logger.warning("auth.google.state_without_redirect", state_prefix=state[:8])
            return None
        return redirect_uri
