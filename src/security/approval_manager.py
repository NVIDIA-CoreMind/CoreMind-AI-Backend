"""
CoreMind Backend — Approval Manager.

Handles the approval flow for high-risk operations.
The agent pauses and waits for user approval via WebSocket/API.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from src.events.event_bus import event_bus
from src.events.events import CoreMindEvent, EventType
from src.utils.ids import request_id
from src.utils.logger import logger


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


@dataclass
class ApprovalRequest:
    """A pending approval request."""

    approval_id: str
    agent_id: str
    tool_name: str
    args: dict[str, Any]
    description: str
    session_id: str | None = None
    task_id: str | None = None
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    deny_reason: str | None = None
    _event: asyncio.Event = field(default_factory=asyncio.Event)


class ApprovalManager:
    """Manages the approval lifecycle for high-risk agent actions."""

    def __init__(self) -> None:
        self._pending: dict[str, ApprovalRequest] = {}

    async def request_approval(
        self,
        agent_id: str,
        tool_name: str,
        args: dict[str, Any],
        description: str,
        session_id: str | None = None,
        task_id: str | None = None,
    ) -> ApprovalRequest:
        """
        Create an approval request and notify the IDE.

        The agent will await the returned request's event.
        """
        approval = ApprovalRequest(
            approval_id=request_id(),
            agent_id=agent_id,
            tool_name=tool_name,
            args=args,
            description=description,
            session_id=session_id,
            task_id=task_id,
        )

        self._pending[approval.approval_id] = approval

        logger.info(
            "security.approval.requested",
            approval_id=approval.approval_id,
            agent_id=agent_id,
            tool=tool_name,
        )

        # Emit event to IDE
        await event_bus.emit(CoreMindEvent(
            type=EventType.APPROVAL_REQUIRED,
            agent_id=agent_id,
            session_id=session_id,
            task_id=task_id,
            data={
                "approval_id": approval.approval_id,
                "tool": tool_name,
                "args": args,
                "description": description,
            },
        ))

        return approval

    async def wait_for_decision(self, approval: ApprovalRequest, timeout: float = 30) -> bool:
        """Wait for the user to approve or deny. Returns True if approved."""
        try:
            await asyncio.wait_for(approval._event.wait(), timeout=timeout)
            return approval.status == ApprovalStatus.APPROVED
        except TimeoutError:
            approval.status = ApprovalStatus.EXPIRED
            logger.warn("security.approval.expired", approval_id=approval.approval_id)
            return False

    async def approve(self, approval_id: str) -> bool:
        """Approve a pending request."""
        req = self._pending.get(approval_id)
        if req is None or req.status != ApprovalStatus.PENDING:
            return False

        req.status = ApprovalStatus.APPROVED
        req.resolved_at = datetime.now(UTC)
        req._event.set()

        logger.info("security.approval.approved", approval_id=approval_id)

        await event_bus.emit(CoreMindEvent(
            type=EventType.APPROVAL_GRANTED,
            agent_id=req.agent_id,
            session_id=req.session_id,
            task_id=req.task_id,
            data={"approval_id": approval_id, "tool": req.tool_name},
        ))

        return True

    async def deny(self, approval_id: str, reason: str = "User denied") -> bool:
        """Deny a pending request."""
        req = self._pending.get(approval_id)
        if req is None or req.status != ApprovalStatus.PENDING:
            return False

        req.status = ApprovalStatus.DENIED
        req.deny_reason = reason
        req.resolved_at = datetime.now(UTC)
        req._event.set()

        logger.info("security.approval.denied", approval_id=approval_id, reason=reason)

        await event_bus.emit(CoreMindEvent(
            type=EventType.APPROVAL_DENIED,
            agent_id=req.agent_id,
            session_id=req.session_id,
            task_id=req.task_id,
            data={"approval_id": approval_id, "reason": reason},
        ))

        return True

    def get_pending(self, agent_id: str | None = None) -> list[ApprovalRequest]:
        """Get all pending approval requests, optionally filtered by agent."""
        reqs = [r for r in self._pending.values() if r.status == ApprovalStatus.PENDING]
        if agent_id:
            reqs = [r for r in reqs if r.agent_id == agent_id]
        return reqs


# Module-level singleton
approval_manager = ApprovalManager()
