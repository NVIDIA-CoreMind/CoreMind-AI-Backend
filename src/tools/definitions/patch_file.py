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
    path: str = "",
    patch: str = "",
    diff: str = "",
    file_path: str | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Apply a unified diff patch to a file."""
    from src.security.path_policy import validate_path

    target_rel_path = path or file_path or ""
    diff_text = diff or patch

    if not target_rel_path:
        raise ToolError(ErrorCode.TOOL_INVALID_ARGS, "Missing required argument 'path'")
    if not diff_text:
        raise ToolError(ErrorCode.TOOL_INVALID_ARGS, "Missing required argument 'diff' or 'patch'")

    valid_rel_path = validate_path(target_rel_path, project_path)
    file_obj = Path(project_path) / valid_rel_path

    if not file_obj.exists():
        raise ToolError(ErrorCode.TOOL_FILE_NOT_FOUND, f"File not found: {valid_rel_path}")

    original_content = file_obj.read_text(encoding="utf-8")
    patched_content = apply_patch(original_content, diff_text)

    # Write patched content
    file_obj.write_text(patched_content, encoding="utf-8")
    file_diff = create_file_diff(original_content, patched_content, valid_rel_path)

    logger.info("tools.patch_file.applied", path=valid_rel_path, additions=file_diff.additions, deletions=file_diff.deletions)

    return {
        "path": valid_rel_path,
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

apply_diff_tool = ToolDefinition(
    name="apply_diff",
    description="Validate and apply code diff directly to a file.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the file from project root",
            },
            "diff": {
                "type": "string",
                "description": "Unified diff patch to apply to the file",
            },
        },
        "required": ["path", "diff"],
    },
    permission=PermissionLevel.WRITE,
    executor=execute_patch_file,
    timeout_ms=10_000,
)

