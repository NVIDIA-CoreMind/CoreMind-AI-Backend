"""
CoreMind Backend — Event Type Definitions.

All streaming events the IDE can receive from the backend.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventType(StrEnum):
    """All agent/system event types streamed to the IDE."""

    # Agent lifecycle
    AGENT_STARTED = "agent.started"
    AGENT_PLANNING = "agent.planning"
    AGENT_THINKING = "agent.thinking"
    AGENT_WAITING_FOR_USER = "agent.waiting_for_user"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    AGENT_ERROR = "agent.error"
    AGENT_STOPPED = "agent.stopped"

    # Plan and task progress
    PLAN_CREATED = "plan.created"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"

    # Tool events
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"

    # Approval events
    APPROVAL_REQUIRED = "agent.approval.required"
    APPROVAL_GRANTED = "agent.approval.granted"
    APPROVAL_DENIED = "agent.approval.denied"

    # File & Diff events
    FILE_READ = "file.read"
    FILE_CHANGED = "file.changed"
    FILE_CREATED = "file.created"
    FILE_DELETED = "file.deleted"
    DIFF_CREATED = "diff.created"

    # Command/sandbox events
    COMMAND_STARTED = "command.started"
    COMMAND_OUTPUT = "command.output"
    COMMAND_COMPLETED = "command.completed"

    # Verification events
    VERIFICATION_STARTED = "verification.started"
    VERIFICATION_PASSED = "verification.passed"
    VERIFICATION_FAILED = "verification.failed"
    TEST_STARTED = "verification.started"
    TEST_PASSED = "verification.passed"
    TEST_FAILED = "verification.failed"

    # AI streaming
    AI_TOKEN = "agent.ai.token"
    AI_USAGE = "agent.ai.usage"

    # System
    SYSTEM_HEALTH = "system.health"
    SYSTEM_ERROR = "system.error"


class CoreMindEvent(BaseModel):
    """A single event to stream to the IDE."""

    type: EventType
    agent_id: str | None = None
    session_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data: dict[str, Any] = Field(default_factory=dict)

    def to_sse(self) -> str:
        """Serialize to Server-Sent Events format."""
        payload = self.model_dump_json()
        return f"data: {payload}\n\n"
