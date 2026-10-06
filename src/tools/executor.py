"""
CoreMind Backend — Tool Executor.

Dispatches tool calls with permission checks, path validation,
timeout enforcement, and structured result collection.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from src.security.path_policy import validate_path
from src.security.permissions import check_permission
from src.tools.registry import ToolRegistry, tool_registry
from src.utils.errors import ErrorCode, ToolError
from src.utils.logger import logger


from src.security.permission_manager import permission_manager, AgentMode

class ToolExecutor:
    """Executes tool calls with security checks and timeouts."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self._registry = registry or tool_registry

    async def execute(
        self,
        tool_name: str,
        args: dict[str, Any],
        project_path: str,
        agent_id: str | None = None,
        is_approved: bool = False,
        agent_mode: AgentMode = AgentMode.WORK,
        network_enabled: bool = True,
    ) -> dict[str, Any]:
        """
        Execute a tool by name with the given arguments.

        1. Look up the tool
        2. Check permissions
        3. Validate paths
        4. Execute with timeout
        5. Return structured result
        """
        tool = self._registry.get(tool_name)
        clean_name = tool.name

        # Map common argument aliases
        if clean_name == "terminal":
            if "command" not in args and "cmd" in args:
                args["command"] = args["cmd"]
        elif clean_name == "list_directory":
            if "path" not in args:
                args["path"] = args.get("directory") or args.get("dir") or args.get("folder") or "."

        # Permission check via centralized PermissionManager
        if not is_approved:
            # check_execution_permission will raise ToolError if strictly blocked (e.g. friend mode)
            # and will return False if explicit approval is needed.
            is_auto_allowed = permission_manager.check_execution_permission(
                tool=tool,
                args=args,
                project_path=project_path,
                agent_mode=agent_mode,
                network_enabled=network_enabled,
            )
            
            if not is_auto_allowed:
                logger.warn(
                    "security.permission.approval_required",
                    tool=clean_name,
                    permission=tool.permission.value,
                )
                raise ToolError(
                    ErrorCode.TOOL_PERMISSION_DENIED,
                    f"Tool '{clean_name}' requires approval.",
                    details={"permission": tool.permission.value, "requires_approval": True},
                )

        # Path validation and normalization for file tools
        if "path" in args:
            args["path"] = validate_path(args["path"], project_path)
        if "file_path" in args:
            args["file_path"] = validate_path(args["file_path"], project_path)

        logger.info(
            "tools.execute.start",
            tool=clean_name,
            agent_id=agent_id or "",
            permission=tool.permission.value,
        )

        try:
            result = await asyncio.wait_for(
                tool.executor(project_path=project_path, agent_id=agent_id or "", **args),
                timeout=tool.timeout_ms / 1000,
            )

            logger.info(
                "tools.execute.completed",
                tool=tool_name,
                agent_id=agent_id or "",
                success=True,
            )

            return {"tool": tool_name, "success": True, "result": result}

        except TimeoutError as err:
            logger.error("tools.execute.timeout", tool=tool_name, timeout_ms=tool.timeout_ms)
            raise ToolError(
                ErrorCode.TOOL_TIMEOUT,
                f"Tool '{tool_name}' timed out after {tool.timeout_ms}ms",
            ) from err
        except ToolError:
            raise
        except Exception as exc:
            logger.error("tools.execute.failed", tool=tool_name, error=str(exc))
            raise ToolError(
                ErrorCode.TOOL_EXECUTION_FAILED,
                f"Tool '{tool_name}' failed: {exc}",
            ) from exc

    async def execute_tool_call(
        self,
        tool_call: dict[str, Any],
        project_path: str,
        agent_id: str | None = None,
        is_approved: bool = False,
        agent_mode: AgentMode = AgentMode.WORK,
        network_enabled: bool = True,
    ) -> dict[str, Any]:
        """
        Execute an OpenAI-format tool call (from Nemotron's response).

        Parses the function name and JSON arguments, then delegates to execute().
        """
        func = tool_call.get("function", {})
        name = func.get("name", "")
        args_str = func.get("arguments", "{}")

        try:
            args = json.loads(args_str)
        except json.JSONDecodeError as err:
            raise ToolError(
                ErrorCode.TOOL_INVALID_ARGS,
                f"Invalid JSON arguments for tool '{name}': {args_str}",
            ) from err

        return await self.execute(
            tool_name=name,
            args=args,
            project_path=project_path,
            agent_id=agent_id,
            is_approved=is_approved,
            agent_mode=agent_mode,
            network_enabled=network_enabled,
        )
