"""
CoreMind Backend — Tool: list_directory

Lists files and folders in a directory.
Permission: READ
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tools.registry import PermissionLevel, ToolDefinition

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "coverage",
}

MAX_ENTRIES = 200


async def execute_list_directory(
    project_path: str,
    path: str = ".",
    max_depth: int = 3,
    **_kwargs: Any,
) -> dict[str, Any]:
    """List files and directories up to a given depth."""
    target = Path(project_path) / path
    root = Path(project_path)

    if not target.exists():
        return {"path": path, "entries": [], "error": f"Directory not found: {path}"}

    if not target.is_dir():
        return {"path": path, "entries": [], "error": f"Not a directory: {path}"}

    entries: list[dict[str, Any]] = []

    def _walk(current: Path, depth: int) -> None:
        if depth > max_depth or len(entries) >= MAX_ENTRIES:
            return

        try:
            items = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return

        for item in items:
            if item.name in SKIP_DIRS:
                continue
            if item.name.startswith(".") and item.name not in (".env.example", ".gitignore"):
                continue

            rel = str(item.relative_to(root))
            entry: dict[str, Any] = {
                "name": item.name,
                "path": rel,
                "type": "directory" if item.is_dir() else "file",
            }

            if item.is_file():
                try:
                    entry["size"] = item.stat().st_size
                except OSError:
                    entry["size"] = 0

            entries.append(entry)

            if item.is_dir() and len(entries) < MAX_ENTRIES:
                _walk(item, depth + 1)

    _walk(target, 1)

    return {
        "path": path,
        "entries": entries,
        "total": len(entries),
        "truncated": len(entries) >= MAX_ENTRIES,
    }


list_directory_tool = ToolDefinition(
    name="list_directory",
    description="List files and directories in the project. Supports depth control.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path from project root (default: '.')",
            },
            "max_depth": {
                "type": "integer",
                "description": "Maximum depth to recurse (default: 3)",
            },
        },
        "required": [],
    },
    permission=PermissionLevel.READ,
    executor=execute_list_directory,
    timeout_ms=10_000,
)
