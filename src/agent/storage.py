"""
CoreMind Backend — Agent Task & Conversation Storage.

Persistent storage for agent tasks, conversation history, and plans using SQLite.
Thread-safe and shared with the main application SQLite database.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config import settings
from src.utils.logger import logger


class TaskStorage:
    """Thread-safe SQLite storage for agent tasks and conversation history."""

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
                CREATE TABLE IF NOT EXISTS agent_tasks (
                    task_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    user_id TEXT,
                    project_path TEXT NOT NULL,
                    task TEXT NOT NULL,
                    status TEXT NOT NULL,
                    steps_completed INTEGER NOT NULL DEFAULT 0,
                    files_changed TEXT NOT NULL DEFAULT '[]',
                    tool_calls_count INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    response TEXT,
                    task_graph_json TEXT,
                    messages_json TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_tasks_session ON agent_tasks(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_tasks_status ON agent_tasks(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_tasks_project ON agent_tasks(project_path)")
            conn.commit()
            logger.info("agent.storage.initialized", db_path=self.db_path)

    def save_task(self, task_data: dict[str, Any], user_id: str | None = None) -> None:
        """Insert or update an agent task."""
        task_id = task_data.get("task_id") or task_data.get("agent_id", "")
        session_id = task_data.get("session_id", "")
        agent_id = task_data.get("agent_id") or task_id
        project_path = task_data.get("project_path", "")
        task_prompt = task_data.get("task", "")
        status = task_data.get("status", "created")
        steps = task_data.get("steps_completed", 0)
        files = json.dumps(task_data.get("files_changed", []))
        tool_count = task_data.get("tool_calls_count", 0)
        error = task_data.get("error")
        response = task_data.get("response")
        task_graph = json.dumps(task_data.get("task_graph", {}))
        messages = json.dumps(task_data.get("messages", []))
        created_at = task_data.get("created_at") or datetime.now(UTC).isoformat()
        completed_at = task_data.get("completed_at")
        updated_at = datetime.now(UTC).isoformat()

        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_tasks (
                    task_id, session_id, agent_id, user_id, project_path, task,
                    status, steps_completed, files_changed, tool_calls_count,
                    error, response, task_graph_json, messages_json,
                    created_at, completed_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status = excluded.status,
                    steps_completed = excluded.steps_completed,
                    files_changed = excluded.files_changed,
                    tool_calls_count = excluded.tool_calls_count,
                    error = excluded.error,
                    response = excluded.response,
                    task_graph_json = excluded.task_graph_json,
                    messages_json = excluded.messages_json,
                    completed_at = excluded.completed_at,
                    updated_at = excluded.updated_at
                """,
                (
                    task_id, session_id, agent_id, user_id, project_path, task_prompt,
                    status, steps, files, tool_count,
                    error, response, task_graph, messages,
                    created_at, completed_at, updated_at,
                ),
            )
            conn.commit()

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """Fetch task by ID."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM agent_tasks WHERE task_id = ? OR agent_id = ?", (task_id, task_id))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_dict(row)

    def list_tasks(
        self,
        session_id: str | None = None,
        project_path: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List recent tasks, optionally filtered by session or project."""
        query = "SELECT * FROM agent_tasks"
        params: list[Any] = []
        clauses: list[str] = []

        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if project_path:
            clauses.append("project_path = ?")
            params.append(project_path)

        if clauses:
            query += " WHERE " + " AND ".join(clauses)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(query, tuple(params))
            return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_conversation_history(self, session_id: str) -> list[dict[str, Any]]:
        """Retrieve conversation history for a session across all its tasks."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT messages_json FROM agent_tasks WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            )
            all_messages: list[dict[str, Any]] = []
            for row in cursor.fetchall():
                raw = row["messages_json"]
                if raw:
                    try:
                        msgs = json.loads(raw)
                        if isinstance(msgs, list):
                            all_messages.extend(msgs)
                    except Exception:
                        pass
            return all_messages

    def delete_task(self, task_id: str) -> bool:
        """Delete a task by ID."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM agent_tasks WHERE task_id = ? OR agent_id = ?", (task_id, task_id))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert a SQLite row to a task dictionary."""
        files = []
        task_graph = {}
        messages = []

        if row["files_changed"]:
            try:
                files = json.loads(row["files_changed"])
            except Exception:
                files = []

        if row["task_graph_json"]:
            try:
                task_graph = json.loads(row["task_graph_json"])
            except Exception:
                task_graph = {}

        if row["messages_json"]:
            try:
                messages = json.loads(row["messages_json"])
            except Exception:
                messages = []

        return {
            "task_id": row["task_id"],
            "session_id": row["session_id"],
            "agent_id": row["agent_id"],
            "user_id": row["user_id"],
            "project_path": row["project_path"],
            "task": row["task"],
            "status": row["status"],
            "steps_completed": row["steps_completed"],
            "files_changed": files,
            "tool_calls_count": row["tool_calls_count"],
            "error": row["error"],
            "response": row["response"],
            "task_graph": task_graph,
            "messages": messages,
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
            "updated_at": row["updated_at"],
        }


# Singleton task storage instance
task_storage = TaskStorage()
