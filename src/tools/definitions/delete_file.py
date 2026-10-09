"""
CoreMind Backend — Tool: delete_file

Deletes a file or directory from the workspace.
Requires explicit authorization / approval.
Permission: HIGH_RISK
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from src.events.event_bus import event_bus
from src.events.events import CoreMindEvent, EventType
from src.security.path_policy import validate_path
from src.tools.registry import PermissionLevel, ToolDefinition
from src.utils.errors import ErrorCode, ToolError
from src.utils.logger import logger


async def execute_delete_file(
    project_path: str,
    path: str = "",
    file_path: str | None = None,
    recursive: bool = False,
    agent_id: str | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Delete a file or empty directory in the workspace with safety checks."""
    target_rel_path = path or file_path
    if not target_rel_path:
        raise ToolError(ErrorCode.TOOL_INVALID_ARGS, "Missing required argument 'path'")

    # Validate path within project root
    valid_rel_path = validate_path(target_rel_path, project_path)
    if not valid_rel_path or valid_rel_path in (".", "/", ""):
        raise ToolError(ErrorCode.TOOL_PERMISSION_DENIED, "Cannot delete the project root directory")

    file_obj = Path(project_path) / valid_rel_path

    if not file_obj.exists():
        raise ToolError(ErrorCode.TOOL_FILE_NOT_FOUND, f"File or directory not found: {valid_rel_path}")

    is_dir = file_obj.is_dir()

    if is_dir:
        if not recursive:
            # Check if directory is empty
            if any(file_obj.iterdir()):
                raise ToolError(
                    ErrorCode.TOOL_PERMISSION_DENIED,
                    f"Directory '{valid_rel_path}' is not empty. Set recursive=true to delete non-empty directory.",
                )
            file_obj.rmdir()
        else:
            shutil.rmtree(file_obj)
    else:
        file_obj.unlink()

    logger.info("tools.delete_file", path=valid_rel_path, is_dir=is_dir)

    # Emit file deleted event
    await event_bus.emit(CoreMindEvent(
        type=EventType.FILE_DELETED,
        agent_id=agent_id,
        data={"path": valid_rel_path, "file": valid_rel_path, "is_dir": is_dir},
    ))

    return {
        "path": valid_rel_path,
        "action": "deleted",
        "is_dir": is_dir,
        "success": True,
    }


delete_file_tool = ToolDefinition(
    name="delete_file",
    description="Delete a file or directory from the workspace. Requires user approval.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the file or directory to delete",
            },
            "recursive": {
                "type": "boolean",
                "description": "If deleting a non-empty directory, set to true (default: false)",
            },
        },
        "required": ["path"],
    },
    permission=PermissionLevel.HIGH_RISK,
    requires_approval=True,
    executor=execute_delete_file,
    timeout_ms=10_000,
)
