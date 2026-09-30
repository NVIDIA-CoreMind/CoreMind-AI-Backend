"""
CoreMind Backend — Tool: patch_file

Applies a unified diff patch directly to a file.
Permission: WRITE
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.changes.diff import create_file_diff
from src.changes.patch import apply_patch
from src.tools.registry import PermissionLevel, ToolDefinition
from src.utils.errors import ErrorCode, ToolError
from src.utils.logger import logger


async def execute_patch_file(
    project_path: str,
    path: str,
    patch: str,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Apply a unified diff patch to a file."""
    file_path = Path(project_path) / path

    if not file_path.exists():
        raise ToolError(ErrorCode.TOOL_FILE_NOT_FOUND, f"File not found: {path}")

    original_content = file_path.read_text(encoding="utf-8")
    patched_content = apply_patch(original_content, patch)

    # Write patched content
    file_path.write_text(patched_content, encoding="utf-8")
    file_diff = create_file_diff(original_content, patched_content, path)

    logger.info("tools.patch_file.applied", path=path, additions=file_diff.additions, deletions=file_diff.deletions)

    return {
        "path": path,
        "action": "patched",
        "diff": file_diff.diff,
        "additions": file_diff.additions,
        "deletions": file_diff.deletions,
    }


patch_file_tool = ToolDefinition(
    name="patch_file",
    description="Apply a unified diff patch directly to a file.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the file from project root",
            },
            "patch": {
                "type": "string",
                "description": "Unified diff patch text to apply",
            },
        },
        "required": ["path", "patch"],
    },
    permission=PermissionLevel.WRITE,
    executor=execute_patch_file,
    timeout_ms=10_000,
)
