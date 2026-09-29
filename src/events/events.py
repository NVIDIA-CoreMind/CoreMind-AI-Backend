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
    AGENT_COMPLETED = "agent.completed"
    AGENT_ERROR = "agent.error"
    AGENT_STOPPED = "agent.stopped"

    # Tool events
    TOOL_STARTED = "agent.tool.started"
    TOOL_COMPLETED = "agent.tool.completed"

    # Approval events
    APPROVAL_REQUIRED = "agent.approval.required"
    APPROVAL_GRANTED = "agent.approval.granted"
    APPROVAL_DENIED = "agent.approval.denied"

    # File events
    FILE_CHANGED = "agent.file.changed"
    FILE_CREATED = "agent.file.created"
    FILE_DELETED = "agent.file.deleted"

    # Command/sandbox events
    COMMAND_STARTED = "agent.command.started"
    COMMAND_COMPLETED = "agent.command.completed"

    # Test events
    TEST_STARTED = "agent.test.started"
    TEST_PASSED = "agent.test.passed"
    TEST_FAILED = "agent.test.failed"

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
