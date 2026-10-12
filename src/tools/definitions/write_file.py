"""
CoreMind Backend — Tool: write_file

Creates or overwrites a file in the project.
Permission: WRITE
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tools.registry import PermissionLevel, ToolDefinition
from src.utils.errors import ErrorCode, ToolError
from src.utils.logger import logger


async def execute_write_file(
    project_path: str,
    path: str = "",
    content: str = "",
    file_path: str | None = None,
    create_directories: bool = True,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Write content to a file, creating parent directories if needed."""
    from src.changes.diff import create_file_diff
    from src.security.path_policy import validate_path

    target_rel_path = path or file_path
    if not target_rel_path:
        raise ToolError(ErrorCode.TOOL_INVALID_ARGS, "Missing required argument 'path' or 'file_path'")

    valid_rel_path = validate_path(target_rel_path, project_path)
    file_obj = Path(project_path) / valid_rel_path
    existed = file_obj.exists()
    old_content = ""
    if existed:
        try:
            old_content = file_obj.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if create_directories:
        file_obj.parent.mkdir(parents=True, exist_ok=True)

    file_obj.write_text(content, encoding="utf-8")

    file_diff = create_file_diff(old_content, content, valid_rel_path)
    action = "modified" if existed else "created"
    logger.info("tools.write_file", path=valid_rel_path, action=action, size=len(content))

    return {
        "path": valid_rel_path,
        "action": action,
        "size": len(content),
        "lines": content.count("\n") + 1,
        "diff": file_diff.diff,
        "additions": file_diff.additions,
        "deletions": file_diff.deletions,
    }


write_file_tool = ToolDefinition(
    name="write_file",
    description=(
        "Create or overwrite a file in the project."
        " Creates parent directories automatically."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the file from project root",
            },
            "content": {
                "type": "string",
                "description": "The full content to write to the file",
            },
            "create_directories": {
                "type": "boolean",
                "description": "Create parent directories if they don't exist (default: true)",
            },
        },
        "required": ["path", "content"],
    },
    permission=PermissionLevel.WRITE,
    executor=execute_write_file,
    timeout_ms=10_000,
)

create_file_tool = ToolDefinition(
    name="create_file",
    description="Create a new file or write file content with validated paths.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the file from workspace root",
            },
            "content": {
                "type": "string",
                "description": "The full text content to write to the file",
            },
            "create_directories": {
                "type": "boolean",
                "description": "Create parent directories if they don't exist (default: true)",
            },
        },
        "required": ["path", "content"],
    },
    permission=PermissionLevel.WRITE,
    executor=execute_write_file,
    timeout_ms=10_000,
)

