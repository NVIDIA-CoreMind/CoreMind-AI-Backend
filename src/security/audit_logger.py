"""
CoreMind Backend — Audit Logger.

Provides a centralized audit log for all security-relevant actions,
permission grants, and tool executions.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from src.utils.logger import logger

class AuditLogEntry:
    def __init__(
        self,
        action: str,
        user_id: str = "system",
        agent_id: str | None = None,
        details: dict[str, Any] | None = None,
        status: str = "success",
    ) -> None:
        self.timestamp = datetime.now(UTC).isoformat()
        self.action = action
        self.user_id = user_id
        self.agent_id = agent_id
        self.details = details or {}
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "details": self.details,
            "status": self.status,
        }

class AuditLogger:
    def __init__(self) -> None:
        self.logs: list[AuditLogEntry] = []

    def log(self, entry: AuditLogEntry) -> None:
        self.logs.append(entry)
        logger.info(
            "security.audit",
            action=entry.action,
            user_id=entry.user_id,
            agent_id=entry.agent_id,
            status=entry.status,
        )
        
    def log_permission_grant(self, tool_name: str, mode: str, project: str | None = None) -> None:
        self.log(AuditLogEntry(
            action="permission_grant",
            details={"tool": tool_name, "mode": mode, "project": project}
        ))
        
    def log_tool_execution(self, tool_name: str, agent_id: str, success: bool, error: str | None = None) -> None:
        self.log(AuditLogEntry(
            action="tool_execution",
            agent_id=agent_id,
            status="success" if success else "failed",
            details={"tool": tool_name, "error": error}
        ))

    def get_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        return [log.to_dict() for log in self.logs[-limit:]]

audit_logger = AuditLogger()
