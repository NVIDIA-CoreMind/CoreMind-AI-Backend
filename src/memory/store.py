"""
CoreMind Backend — Limited Agent Memory.

Durable, project-scoped notes the coding agent can save and recall.
Capacity is hard-capped so memory cannot grow without bound.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config import settings
from src.utils.ids import memory_id
from src.utils.logger import logger

ALLOWED_CATEGORIES = frozenset({"fact", "preference", "decision", "lesson", "convention"})
_TOKEN_RE = re.compile(r"[a-z0-9_]{3,}")


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _normalize_project(project_path: str) -> str:
    try:
        return str(Path(project_path).expanduser().resolve())
    except OSError:
        return project_path.rstrip("/")


def _clip(text: str, limit: int) -> str:
    cleaned = " ".join(text.strip().split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


@dataclass(frozen=True)
class MemoryItem:
    id: str
    project_path: str
    category: str
    content: str
    importance: int
    created_at: str
    updated_at: str
    last_accessed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "content": self.content,
            "importance": self.importance,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class AgentMemoryStore:
    """Thread-safe SQLite store for a small set of project memories."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or settings.sqlite_db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_memories (
                    id TEXT PRIMARY KEY,
                    project_path TEXT NOT NULL,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance INTEGER NOT NULL DEFAULT 3,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_accessed_at TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_memories_project "
                "ON agent_memories(project_path)"
            )
            conn.commit()

    def _row_to_item(self, row: sqlite3.Row | None) -> MemoryItem | None:
        if row is None:
            return None
        return MemoryItem(
            id=row["id"],
            project_path=row["project_path"],
            category=row["category"],
            content=row["content"],
            importance=int(row["importance"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_accessed_at=row["last_accessed_at"],
        )

    def save(
        self,
        project_path: str,
        content: str,
        category: str = "fact",
        importance: int = 3,
    ) -> MemoryItem:
        """Store a memory, evicting the weakest entries if the project is at capacity."""
        project = _normalize_project(project_path)
        category = category.lower().strip()
        if category not in ALLOWED_CATEGORIES:
            category = "fact"
        importance = max(1, min(5, int(importance)))
        content = _clip(content, settings.memory_max_content_chars)
        if not content:
            raise ValueError("Memory content cannot be empty")

        now = _utc_now()
        item_id = memory_id()

        with self._lock, self._get_connection() as conn:
            existing = conn.execute(
                "SELECT id FROM agent_memories WHERE project_path = ? AND content = ?",
                (project, content),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE agent_memories
                    SET category = ?, importance = ?, updated_at = ?, last_accessed_at = ?
                    WHERE id = ?
                    """,
                    (category, importance, now, now, existing["id"]),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM agent_memories WHERE id = ?",
                    (existing["id"],),
                ).fetchone()
                item = self._row_to_item(row)
                assert item is not None
                return item

            conn.execute(
                """
                INSERT INTO agent_memories
                    (id, project_path, category, content, importance, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (item_id, project, category, content, importance, now, now),
            )
            self._evict_locked(conn, project, keep_id=item_id)
            conn.commit()
            row = conn.execute(
                "SELECT * FROM agent_memories WHERE id = ?",
                (item_id,),
            ).fetchone()

        item = self._row_to_item(row)
        assert item is not None
        logger.info(
            "memory.saved",
            memory_id=item.id,
            category=item.category,
            importance=item.importance,
        )
        return item

    def _evict_locked(
        self,
        conn: sqlite3.Connection,
        project: str,
        keep_id: str | None = None,
    ) -> None:
        limit = settings.memory_max_items
        rows = conn.execute(
            """
            SELECT id FROM agent_memories
            WHERE project_path = ?
            ORDER BY importance ASC, updated_at ASC
            """,
            (project,),
        ).fetchall()
        overflow = len(rows) - limit
        if overflow <= 0:
            return
        drop_ids = [
            row["id"] for row in rows
            if keep_id is None or row["id"] != keep_id
        ][:overflow]
        if not drop_ids:
            return
        conn.executemany(
            "DELETE FROM agent_memories WHERE id = ?",
            [(mid,) for mid in drop_ids],
        )
        logger.info("memory.evicted", project=project, count=len(drop_ids))

    def recall(
        self,
        project_path: str,
        query: str = "",
        limit: int | None = None,
    ) -> list[MemoryItem]:
        """Return the most relevant memories for a query, capped for prompt use."""
        project = _normalize_project(project_path)
        cap = limit or settings.memory_prompt_items
        with self._lock, self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_memories WHERE project_path = ?",
                (project,),
            ).fetchall()

        items = [item for row in rows if (item := self._row_to_item(row))]
        if not items:
            return []

        scored = sorted(
            items,
            key=lambda item: (
                self._score(item, query),
                item.importance,
                item.updated_at,
            ),
            reverse=True,
        )
        selected = scored[:cap]
        self._touch([item.id for item in selected])
        return selected

    def forget(self, project_path: str, item_id: str) -> bool:
        project = _normalize_project(project_path)
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM agent_memories WHERE id = ? AND project_path = ?",
                (item_id, project),
            )
            conn.commit()
            deleted = cursor.rowcount > 0
        if deleted:
            logger.info("memory.forgotten", memory_id=item_id)
        return deleted

    def count(self, project_path: str) -> int:
        project = _normalize_project(project_path)
        with self._lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM agent_memories WHERE project_path = ?",
                (project,),
            ).fetchone()
        return int(row["n"]) if row else 0

    def build_prompt_digest(self, project_path: str, query: str = "") -> str:
        """Compact memory block injected into the model context."""
        items = self.recall(project_path, query=query)
        if not items:
            return ""
        used = self.count(project_path)
        lines = [
            "## Agent Memory (limited, project-scoped)",
            "",
            f"You may keep at most {settings.memory_max_items} notes for this project "
            f"({used} in use). Each note is capped at {settings.memory_max_content_chars} "
            "characters. Save only durable facts — not the current file contents.",
            "",
        ]
        for item in items:
            lines.append(f"- [{item.category}|{item.id}|p{item.importance}] {item.content}")
        return "\n".join(lines)

    def _touch(self, ids: list[str]) -> None:
        if not ids:
            return
        now = _utc_now()
        with self._lock, self._get_connection() as conn:
            conn.executemany(
                "UPDATE agent_memories SET last_accessed_at = ? WHERE id = ?",
                [(now, mid) for mid in ids],
            )
            conn.commit()

    @staticmethod
    def _score(item: MemoryItem, query: str) -> int:
        if not query:
            return item.importance
        q_tokens = set(_TOKEN_RE.findall(query.lower()))
        m_tokens = set(_TOKEN_RE.findall(item.content.lower()))
        overlap = len(q_tokens & m_tokens)
        return overlap * 3 + item.importance


agent_memory = AgentMemoryStore()
