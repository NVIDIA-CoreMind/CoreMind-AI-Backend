"""
CoreMind Backend — Tool Registry.

Central registry for all tools the agent can call.
Each tool has a name, description, input schema (OpenAI function format),
permission level, and executor function.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from src.utils.errors import ErrorCode, ToolError
from src.utils.logger import logger


class PermissionLevel(StrEnum):
    """Tool permission levels from the PRD."""

    READ = "READ"
    WRITE = "WRITE"
    EXECUTE = "EXECUTE"
    HIGH_RISK = "HIGH_RISK"


# Type alias for tool executor functions
ToolFunction = Callable[..., Coroutine[Any, Any, dict[str, Any]]]


@dataclass
class ToolDefinition:
    """A registered tool that the agent can invoke."""

    name: str
    description: str
    parameters: dict[str, Any]  # OpenAI function calling JSON schema
    permission: PermissionLevel
    executor: ToolFunction
    timeout_ms: int = 30_000
    requires_approval: bool = False
    tags: list[str] = field(default_factory=list)

    def to_openai_tool(self) -> dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Central registry for all available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition."""
        if tool.name in self._tools:
            logger.warn("tools.registry.duplicate", tool=tool.name)
        self._tools[tool.name] = tool
        logger.debug("tools.registry.registered", tool=tool.name, permission=tool.permission.value)

    def get(self, name: str) -> ToolDefinition:
        """Get a tool by name. Raises ToolError if not found."""
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(ErrorCode.TOOL_NOT_FOUND, f"Tool not found: {name}")
        return tool

    def list_tools(self) -> list[ToolDefinition]:
        """List all registered tools."""
        return list(self._tools.values())

    def to_openai_tools(self) -> list[dict[str, Any]]:
        """Convert all tools to OpenAI function calling format."""
        return [tool.to_openai_tool() for tool in self._tools.values()]

    def get_by_permission(self, level: PermissionLevel) -> list[ToolDefinition]:
        """Get all tools at a specific permission level."""
        return [t for t in self._tools.values() if t.permission == level]

    @property
    def count(self) -> int:
        return len(self._tools)


# ── Module-level singleton ──────────────────────────────────────────

tool_registry = ToolRegistry()


def _register_all_tools() -> None:
    """Register all built-in tool definitions."""
    from src.tools.definitions.edit_file import edit_file_tool
    from src.tools.definitions.git import git_diff_tool, git_log_tool, git_status_tool
    from src.tools.definitions.list_directory import list_directory_tool
    from src.tools.definitions.read_file import read_file_tool
    from src.tools.definitions.sandbox import sandbox_execute_tool
    from src.tools.definitions.search_files import search_files_tool
    from src.tools.definitions.terminal import terminal_tool
    from src.tools.definitions.write_file import write_file_tool

    for tool in [
        read_file_tool,
        search_files_tool,
        list_directory_tool,
        write_file_tool,
        edit_file_tool,
        terminal_tool,
        git_status_tool,
        git_diff_tool,
        git_log_tool,
        sandbox_execute_tool,
    ]:
        tool_registry.register(tool)

    logger.info("tools.registry.initialized", count=tool_registry.count)


# Auto-register on import
_register_all_tools()
