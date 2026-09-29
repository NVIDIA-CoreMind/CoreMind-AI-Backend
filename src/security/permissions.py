"""
CoreMind Backend — Permission System.

Four permission levels: READ, WRITE, EXECUTE, HIGH_RISK.
HIGH_RISK operations must NEVER be auto-executed by the agent.
"""

from __future__ import annotations

from src.tools.registry import PermissionLevel
from src.utils.errors import ErrorCode, ToolError
from src.utils.logger import logger

# Permissions that require user approval before execution
APPROVAL_REQUIRED: set[PermissionLevel] = {PermissionLevel.HIGH_RISK}

# Permissions that are always allowed (no approval needed)
ALWAYS_ALLOWED: set[PermissionLevel] = {PermissionLevel.READ}


def check_permission(level: PermissionLevel, tool_name: str) -> None:
    """
    Check if a tool can be executed at the given permission level.

    READ tools are always allowed.
    WRITE and EXECUTE tools are allowed but logged.
    HIGH_RISK tools raise an error (must go through approval flow).
    """
    if level in ALWAYS_ALLOWED:
        return

    if level in APPROVAL_REQUIRED:
        logger.warn(
            "security.permission.approval_required",
            tool=tool_name,
            permission=level.value,
        )
        raise ToolError(
            ErrorCode.TOOL_PERMISSION_DENIED,
            f"Tool '{tool_name}' requires approval (permission: {level.value})",
            details={"permission": level.value, "requires_approval": True},
        )

    # WRITE and EXECUTE — allowed but logged
    logger.debug(
        "security.permission.allowed",
        tool=tool_name,
        permission=level.value,
    )


def requires_approval(level: PermissionLevel) -> bool:
    """Check if a permission level requires user approval."""
    return level in APPROVAL_REQUIRED
