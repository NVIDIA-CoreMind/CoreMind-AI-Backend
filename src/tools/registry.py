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


TOOL_ALIASES: dict[str, str] = {
    "execute_command": "terminal",
    "run_command": "terminal",
    "bash": "terminal",
    "sh": "terminal",
    "shell": "terminal",
    "terminal_run": "terminal",
    "list_files": "list_directory",
    "list_dir": "list_directory",
    "view_file": "read_file",
    "create_file": "write_file",
    "modify_file": "edit_file",
    "apply_patch": "patch_file",
    "search": "search_files",
    "grep": "search_files",
    "find_files": "search_files",
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
        """Get a tool by name. Supports aliases. Raises ToolError if not found."""
        canonical = TOOL_ALIASES.get(name, name)
        tool = self._tools.get(canonical)
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


class DefaultToolRegistry(ToolRegistry):
    """The default system singleton tool registry with lazy built-in loading."""

    def __init__(self) -> None:
        super().__init__()
        self._registered = False

    def _ensure_registered(self) -> None:
        if not self._registered:
            self._registered = True
            _register_all_tools(self)

    def get(self, name: str) -> ToolDefinition:
        self._ensure_registered()
        return super().get(name)

    def list_tools(self) -> list[ToolDefinition]:
        self._ensure_registered()
        return super().list_tools()

    def to_openai_tools(self) -> list[dict[str, Any]]:
        self._ensure_registered()
        return super().to_openai_tools()

    def get_by_permission(self, level: PermissionLevel) -> list[ToolDefinition]:
        self._ensure_registered()
        return super().get_by_permission(level)

    @property
    def count(self) -> int:
        self._ensure_registered()
        return super().count


# ── Module-level singleton ──────────────────────────────────────────

tool_registry = DefaultToolRegistry()


def _register_all_tools(target: ToolRegistry) -> None:
    """Register all built-in tool definitions."""
    from src.tools.definitions.ask_question import ask_question_tool
    from src.tools.definitions.edit_file import edit_file_tool

    from src.tools.definitions.git import git_diff_tool, git_log_tool, git_status_tool
    from src.tools.definitions.list_directory import list_directory_tool
    from src.tools.definitions.memory import (
        memory_forget_tool,
        memory_recall_tool,
        memory_save_tool,
    )
    from src.tools.definitions.patch_file import patch_file_tool
    from src.tools.definitions.read_file import read_file_tool
    from src.tools.definitions.sandbox import sandbox_execute_tool
    from src.tools.definitions.search_files import search_files_tool
    from src.tools.definitions.tasks import create_task_tool, update_task_tool
    from src.tools.definitions.terminal import terminal_tool
    from src.tools.definitions.web_search import web_search_tool
    from src.tools.definitions.write_file import write_file_tool

    for tool in [
        read_file_tool,
        search_files_tool,
        list_directory_tool,
        write_file_tool,
        edit_file_tool,
        patch_file_tool,
        create_task_tool,
        update_task_tool,
        ask_question_tool,
        terminal_tool,
        git_status_tool,
        git_diff_tool,
        git_log_tool,
        sandbox_execute_tool,
        web_search_tool,
        memory_save_tool,
        memory_recall_tool,
        memory_forget_tool,
    ]:
        target.register(tool)

    logger.info("tools.registry.initialized", count=len(target._tools))

