"""
CoreMind Backend — Typed Error Classes.

Each error domain has its own class for structured error handling.
All errors serialize to clean JSON for API responses.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """All known error codes grouped by domain."""

    # AI errors
    AI_AUTH_FAILURE = "AI_AUTH_FAILURE"
    AI_MODEL_UNAVAILABLE = "AI_MODEL_UNAVAILABLE"
    AI_RATE_LIMIT = "AI_RATE_LIMIT"
    AI_TIMEOUT = "AI_TIMEOUT"
    AI_INVALID_RESPONSE = "AI_INVALID_RESPONSE"
    AI_UNKNOWN = "AI_UNKNOWN"

    # Tool errors
    TOOL_FILE_NOT_FOUND = "TOOL_FILE_NOT_FOUND"
    TOOL_PERMISSION_DENIED = "TOOL_PERMISSION_DENIED"
    TOOL_INVALID_PATH = "TOOL_INVALID_PATH"
    TOOL_INVALID_ARGS = "TOOL_INVALID_ARGS"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"

    # Sandbox errors
    SANDBOX_TIMEOUT = "SANDBOX_TIMEOUT"
    SANDBOX_RUNTIME_ERROR = "SANDBOX_RUNTIME_ERROR"
    SANDBOX_COMPILATION_ERROR = "SANDBOX_COMPILATION_ERROR"
    SANDBOX_MEMORY_LIMIT = "SANDBOX_MEMORY_LIMIT"
    SANDBOX_PROCESS_KILLED = "SANDBOX_PROCESS_KILLED"
    SANDBOX_UNAVAILABLE = "SANDBOX_UNAVAILABLE"

    # Agent errors
    AGENT_STEP_LIMIT = "AGENT_STEP_LIMIT"
    AGENT_INVALID_STATE = "AGENT_INVALID_STATE"
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"

    # System errors
    CONFIG_INVALID = "CONFIG_INVALID"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_AI_STATUS_MAP: dict[ErrorCode, int] = {
    ErrorCode.AI_AUTH_FAILURE: 401,
    ErrorCode.AI_RATE_LIMIT: 429,
    ErrorCode.AI_TIMEOUT: 504,
    ErrorCode.AI_MODEL_UNAVAILABLE: 503,
}

_TOOL_STATUS_MAP: dict[ErrorCode, int] = {
    ErrorCode.TOOL_FILE_NOT_FOUND: 404,
    ErrorCode.TOOL_PERMISSION_DENIED: 403,
    ErrorCode.TOOL_INVALID_ARGS: 400,
    ErrorCode.TOOL_NOT_FOUND: 404,
}


class CoreMindError(Exception):
    """Base error for all CoreMind Backend errors."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {
            "code": self.code.value,
            "message": str(self),
        }
        if self.details:
            error["details"] = self.details
        return {"error": error}


class AIError(CoreMindError):
    """Errors from the AI provider layer."""

    def __init__(
        self, code: ErrorCode, message: str, details: dict[str, Any] | None = None
    ) -> None:
        status = _AI_STATUS_MAP.get(code, 502)
        super().__init__(code, message, status, details)


class ToolError(CoreMindError):
    """Errors from tool execution."""

    def __init__(
        self, code: ErrorCode, message: str, details: dict[str, Any] | None = None
    ) -> None:
        status = _TOOL_STATUS_MAP.get(code, 500)
        super().__init__(code, message, status, details)


class SandboxError(CoreMindError):
    """Errors from sandbox execution."""

    def __init__(
        self, code: ErrorCode, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(code, message, 500, details)


class AgentError(CoreMindError):
    """Errors from the agent engine."""

    def __init__(
        self, code: ErrorCode, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(code, message, 500, details)
