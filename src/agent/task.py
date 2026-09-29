"""
CoreMind Backend — Task Definition.

Defines the structure of an agent task and its lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class TaskStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentTask:
    """A single task submitted to the agent."""

    task_id: str
    session_id: str
    agent_id: str
    task: str
    project_path: str
    status: TaskStatus = TaskStatus.CREATED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    # Accumulated results
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    execution_results: list[dict[str, Any]] = field(default_factory=list)
    steps_completed: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "task": self.task,
            "project_path": self.project_path,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "steps_completed": self.steps_completed,
            "files_changed": self.files_changed,
            "tool_calls_count": len(self.tool_calls),
            "error": self.error,
        }
