"""
CoreMind Backend — Tool: read_file

Reads the contents of a file from the project.
Permission: READ
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tools.registry import PermissionLevel, ToolDefinition
from src.utils.errors import ErrorCode, ToolError

MAX_FILE_SIZE = 1_000_000  # 1 MB


async def execute_read_file(
    project_path: str,
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Read file contents, optionally a specific line range."""
    file_path = Path(project_path) / path

    if not file_path.exists():
        raise ToolError(ErrorCode.TOOL_FILE_NOT_FOUND, f"File not found: {path}")

    if not file_path.is_file():
        raise ToolError(ErrorCode.TOOL_INVALID_ARGS, f"Not a file: {path}")

    if file_path.stat().st_size > MAX_FILE_SIZE:
        raise ToolError(
            ErrorCode.TOOL_INVALID_ARGS,
            f"File too large ({file_path.stat().st_size} bytes). Max: {MAX_FILE_SIZE}",
        )

    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ToolError(ErrorCode.TOOL_INVALID_ARGS, f"Cannot read binary file: {path}")

    lines = content.splitlines()
    total_lines = len(lines)

    if start_line is not None or end_line is not None:
        start = (start_line or 1) - 1  # Convert to 0-indexed
        end = end_line or total_lines
        lines = lines[start:end]
        content = "\n".join(lines)

    return {
        "path": path,
        "content": content,
        "total_lines": total_lines,
        "lines_shown": len(lines),
    }


read_file_tool = ToolDefinition(
    name="read_file",
    description="Read the contents of a file from the project. Supports optional line range.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the file from project root",
            },
            "start_line": {
                "type": "integer",
                "description": "Optional start line (1-indexed)",
            },
            "end_line": {
                "type": "integer",
                "description": "Optional end line (1-indexed, inclusive)",
            },
        },
        "required": ["path"],
    },
    permission=PermissionLevel.READ,
    executor=execute_read_file,
    timeout_ms=10_000,
)
