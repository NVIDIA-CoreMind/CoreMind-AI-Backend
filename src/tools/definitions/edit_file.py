"""
CoreMind Backend — Tool: edit_file

Applies targeted edits to a file (search & replace).
Permission: WRITE
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tools.registry import PermissionLevel, ToolDefinition
from src.utils.errors import ErrorCode, ToolError
from src.utils.logger import logger


async def execute_edit_file(
    project_path: str,
    path: str,
    old_content: str,
    new_content: str,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Apply a search-and-replace edit to a file."""
    file_path = Path(project_path) / path

    if not file_path.exists():
        raise ToolError(ErrorCode.TOOL_FILE_NOT_FOUND, f"File not found: {path}")

    original = file_path.read_text(encoding="utf-8")

    if old_content not in original:
        raise ToolError(
            ErrorCode.TOOL_INVALID_ARGS,
            f"The specified old_content was not found in {path}. "
            "Read the file first to get the exact content.",
        )

    # Count occurrences
    count = original.count(old_content)

    updated = original.replace(old_content, new_content, 1)
    file_path.write_text(updated, encoding="utf-8")

    logger.info("tools.edit_file", path=path, occurrences=count)

    return {
        "path": path,
        "action": "edited",
        "occurrences_found": count,
        "replacements_made": 1,
        "old_content_preview": old_content[:100],
        "new_content_preview": new_content[:100],
    }


edit_file_tool = ToolDefinition(
    name="edit_file",
    description=(
        "Apply a targeted search-and-replace edit to a file."
        " Requires exact match of old_content."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the file from project root",
            },
            "old_content": {
                "type": "string",
                "description": "The exact content to find and replace",
            },
            "new_content": {
                "type": "string",
                "description": "The replacement content",
            },
        },
        "required": ["path", "old_content", "new_content"],
    },
    permission=PermissionLevel.WRITE,
    executor=execute_edit_file,
    timeout_ms=10_000,
)
