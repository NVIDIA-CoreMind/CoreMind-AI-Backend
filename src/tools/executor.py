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

        # Permission check (bypass if explicitly approved by user)
        if not is_approved:
            check_permission(tool.permission, tool_name)

        # Path validation for file tools
        if "path" in args:
            validate_path(args["path"], project_path)
        if "file_path" in args:
            validate_path(args["file_path"], project_path)

        logger.info(
            "tools.execute.start",
            tool=tool_name,
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
        )
