"""
CoreMind Backend — Session Types & Manager.

Tracks agent sessions with full lifecycle metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from src.utils.ids import session_id as gen_session_id
from src.utils.logger import logger


class SessionStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Session:
    """An agent session."""

    session_id: str
    project_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: SessionStatus = SessionStatus.CREATED
    agent_ids: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project_id": self.project_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "agent_ids": self.agent_ids,
            "tasks": self.tasks,
            "files_changed": self.files_changed,
        }


class SessionManager:
    """Manages agent sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create_session(self, project_id: str) -> Session:
        """Create a new session."""
        sid = gen_session_id()
        session = Session(session_id=sid, project_id=project_id)
        self._sessions[sid] = session
        logger.info("session.created", session_id=sid, project=project_id)
        return session

    def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def update_status(self, session_id: str, status: SessionStatus) -> None:
        """Update session status."""
        session = self._sessions.get(session_id)
        if session:
            session.status = status

    def add_agent(self, session_id: str, agent_id: str) -> None:
        """Add an agent to a session."""
        session = self._sessions.get(session_id)
        if session:
            session.agent_ids.append(agent_id)

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions."""
        return [s.to_dict() for s in self._sessions.values()]


# Module-level singleton
session_manager = SessionManager()
