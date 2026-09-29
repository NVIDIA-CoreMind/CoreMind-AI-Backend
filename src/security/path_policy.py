"""
CoreMind Backend — Path Policy.

Restricts all file operations to the active project directory.
Prevents directory traversal and access outside the project root.
"""

from __future__ import annotations

from pathlib import Path

from src.utils.errors import ErrorCode, ToolError
from src.utils.logger import logger

# Paths that are NEVER accessible regardless of project root
BLOCKED_PATHS = {
    ".env",
    ".env.local",
    ".git/config",
}

BLOCKED_EXTENSIONS = {
    ".pem", ".key", ".p12", ".pfx", ".jks",
}


def validate_path(file_path: str, project_path: str) -> None:
    """
    Validate that a file path is within the project root.

    Raises ToolError if the path escapes the project directory.
    """
    try:
        project_root = Path(project_path).resolve()
        target = (project_root / file_path).resolve()

        # Check directory traversal
        if not str(target).startswith(str(project_root)):
            logger.error(
                "security.path.traversal_blocked",
                path=file_path,
                project=project_path,
            )
            raise ToolError(
                ErrorCode.TOOL_INVALID_PATH,
                f"Path escapes project directory: {file_path}",
            )

        # Check blocked paths
        rel_path = str(target.relative_to(project_root))
        if rel_path in BLOCKED_PATHS:
            logger.error("security.path.blocked", path=rel_path)
            raise ToolError(
                ErrorCode.TOOL_PERMISSION_DENIED,
                f"Access to '{rel_path}' is blocked for security reasons",
            )

        # Check blocked extensions
        if target.suffix.lower() in BLOCKED_EXTENSIONS:
            logger.error("security.path.blocked_extension", path=rel_path, ext=target.suffix)
            raise ToolError(
                ErrorCode.TOOL_PERMISSION_DENIED,
                f"Access to files with extension '{target.suffix}' is blocked",
            )

    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(
            ErrorCode.TOOL_INVALID_PATH,
            f"Invalid path: {file_path} — {exc}",
        )
