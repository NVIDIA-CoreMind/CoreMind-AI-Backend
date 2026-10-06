"""
CoreMind Backend — Permission Manager.

Handles granular permission checks, approval modes, and safety controls
across different tools and contexts (Work vs Friend mode).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from src.security.command_policy import CommandClassification, classify_command
from src.security.permissions import requires_approval
from src.tools.registry import PermissionLevel, ToolDefinition, tool_registry
from src.utils.errors import ErrorCode, ToolError
from src.utils.logger import logger

class ApprovalMode(StrEnum):
    ASK_EVERY_TIME = "ask_every_time"
    APPROVE_ONCE = "approve_once"
    APPROVE_FOR_PROJECT = "approve_for_project"
    ALWAYS_ALLOW = "always_allow"


class AgentMode(StrEnum):
    WORK = "work"
    FRIEND = "friend"


class PermissionManager:
    """Centralized security layer for tool execution."""

    def __init__(self) -> None:
        # tool_name -> ApprovalMode
        self.tool_approvals: dict[str, ApprovalMode] = {}
        # project_path -> set of approved tools
        self.project_approved: dict[str, set[str]] = {}
        # current session approved tools
        self.session_approved: set[str] = set()

    def set_approval_mode(self, tool_name: str, mode: ApprovalMode) -> None:
        self.tool_approvals[tool_name] = mode

    def approve_for_session(self, tool_name: str) -> None:
        self.session_approved.add(tool_name)

    def approve_for_project(self, project_path: str, tool_name: str) -> None:
        if project_path not in self.project_approved:
            self.project_approved[project_path] = set()
        self.project_approved[project_path].add(tool_name)

    def check_execution_permission(
        self,
        tool: ToolDefinition,
        args: dict[str, Any],
        project_path: str,
        agent_mode: AgentMode = AgentMode.WORK,
        network_enabled: bool = True,
    ) -> bool:
        """
        Check if a tool can be executed without explicit interactive approval.
        Returns True if allowed automatically, False if approval is needed.
        Raises ToolError if explicitly blocked.
        """
        tool_name = tool.name

        # 1. Friend Chat Safety
        if agent_mode == AgentMode.FRIEND:
            if tool.permission in {PermissionLevel.WRITE, PermissionLevel.EXECUTE, PermissionLevel.HIGH_RISK}:
                logger.warning("security.permission.friend_mode_blocked", tool=tool_name)
                raise ToolError(
                    ErrorCode.TOOL_PERMISSION_DENIED,
                    f"Tool '{tool_name}' cannot be used in Friend mode. Switch to Work mode for actions."
                )

        # 2. Network & Web Permissions
        network_tools = {"web_search", "curl", "wget"} # simplified
        if not network_enabled and tool_name in network_tools:
             raise ToolError(
                ErrorCode.TOOL_PERMISSION_DENIED,
                f"Network access is disabled for this session/project."
            )
             
        # 3. Terminal Safety (specific checks for terminal command)
        if tool_name == "terminal" and "command" in args:
            classification = classify_command(args["command"])
            if classification == CommandClassification.DESTRUCTIVE:
                # Always ask for destructive commands
                return False
            if classification == CommandClassification.RISKY:
                # Needs approval unless overridden by always allow
                if self.tool_approvals.get("terminal") != ApprovalMode.ALWAYS_ALLOW:
                    return False
        
        # 4. Check global tool approval modes
        mode = self.tool_approvals.get(tool_name, ApprovalMode.ASK_EVERY_TIME)
        if mode == ApprovalMode.ALWAYS_ALLOW:
            return True
            
        # 5. Check project approvals
        if mode == ApprovalMode.APPROVE_FOR_PROJECT and tool_name in self.project_approved.get(project_path, set()):
            return True
            
        # 6. Check session/once approvals
        if mode == ApprovalMode.APPROVE_ONCE and tool_name in self.session_approved:
            self.session_approved.remove(tool_name) # Consume it
            return True

        # 7. Fallback to basic permission levels
        if tool.permission == PermissionLevel.READ:
            return True

        # If it reaches here, we need interactive approval
        return False

permission_manager = PermissionManager()
