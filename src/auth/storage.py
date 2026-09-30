"""
CoreMind Backend — User Account Storage.

Persistent user data storage using SQLite with indexes on email and google_id.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from src.auth.models import User
from src.config import settings
from src.utils.logger import logger


class UserStorage:
    """Thread-safe SQLite storage for Google user accounts and profiles."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or settings.sqlite_db_path
        self._lock = threading.Lock()
        self._init_db()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Create a connection with row factory enabled, managing transaction and closing."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Ensure parent directories and tables exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    avatar_url TEXT,
                    provider TEXT NOT NULL DEFAULT 'google',
                    google_id TEXT,
                    role TEXT NOT NULL DEFAULT 'user',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_login_at TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id)")
            conn.commit()
            logger.info("auth.storage.initialized", db_path=self.db_path)

    def _row_to_user(self, row: sqlite3.Row | None) -> User | None:
        """Convert a SQLite row to a User model."""
        if row is None:
            return None
        return User(
            id=row["id"],
            email=row["email"],
            name=row["name"],
            avatar_url=row["avatar_url"],
            provider=row["provider"],
            google_id=row["google_id"],
            role=row["role"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_login_at=row["last_login_at"],
        )

    def get_by_id(self, user_id: str) -> User | None:
        """Fetch user by primary ID."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            return self._row_to_user(cursor.fetchone())

    def get_by_email(self, email: str) -> User | None:
        """Fetch user by email address (case-insensitive)."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email.strip(),)
            )
            return self._row_to_user(cursor.fetchone())

    def get_by_google_id(self, google_id: str) -> User | None:
        """Fetch user by Google account ID."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM users WHERE google_id = ?", (google_id,))
            return self._row_to_user(cursor.fetchone())

    def create_user(self, user: User) -> User:
        """Insert a new Google authenticated user into the database."""
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    id, email, name, avatar_url,
                    provider, google_id, role, is_active,
                    created_at, updated_at, last_login_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user.id,
                    user.email.lower().strip(),
                    user.name.strip(),
                    user.avatar_url,
                    user.provider,
                    user.google_id,
                    user.role,
                    1 if user.is_active else 0,
                    user.created_at,
                    user.updated_at,
                    user.last_login_at,
                ),
            )
            conn.commit()
            logger.info("auth.storage.user_created", user_id=user.id, email=user.email)
            return user

    def update_user(self, user: User) -> User:
        """Update existing user properties."""
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                UPDATE users SET
                    name = ?,
                    avatar_url = ?,
                    provider = ?,
                    google_id = ?,
                    role = ?,
                    is_active = ?,
                    updated_at = ?,
                    last_login_at = ?
                WHERE id = ?
                """,
                (
                    user.name.strip(),
                    user.avatar_url,
                    user.provider,
                    user.google_id,
                    user.role,
                    1 if user.is_active else 0,
                    user.updated_at,
                    user.last_login_at,
                    user.id,
                ),
            )
            conn.commit()
            logger.info("auth.storage.user_updated", user_id=user.id)
            return user

    def update_last_login(self, user_id: str, timestamp: str) -> None:
        """Update the last_login_at timestamp for a user."""
        with self._lock, self._get_connection() as conn:
            conn.execute(
                "UPDATE users SET last_login_at = ? WHERE id = ?",
                (timestamp, user_id),
            )
            conn.commit()

    def list_users(self, limit: int = 100) -> list[User]:
        """List registered users ordered by creation date."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM users ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            return [self._row_to_user(row) for row in cursor.fetchall() if row is not None]  # type: ignore[misc]


# Global singleton storage
user_storage = UserStorage()
