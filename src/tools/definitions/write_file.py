"""
CoreMind Backend — Tool: write_file

Creates or overwrites a file in the project.
Permission: WRITE
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tools.registry import PermissionLevel, ToolDefinition
from src.utils.logger import logger


async def execute_write_file(
    project_path: str,
    path: str,
    content: str,
    create_directories: bool = True,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Write content to a file, creating parent directories if needed."""
    file_path = Path(project_path) / path
    existed = file_path.exists()

    if create_directories:
        file_path.parent.mkdir(parents=True, exist_ok=True)

    file_path.write_text(content, encoding="utf-8")

    action = "modified" if existed else "created"
    logger.info("tools.write_file", path=path, action=action, size=len(content))

    return {
        "path": path,
        "action": action,
        "size": len(content),
        "lines": content.count("\n") + 1,
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
