"""
CoreMind Backend — Project Scanner.

Walks the project file tree to build a structured view,
skipping irrelevant directories and binary files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "coverage", ".dart_tool",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "env",
    ".gradle", ".idea", ".vs",
}

MAX_FILES = 500


async def scan_project(project_path: str, max_depth: int = 4) -> list[dict[str, Any]]:
    """Scan the project and return a structured file tree."""
    root = Path(project_path)
    entries: list[dict[str, Any]] = []

    def _walk(current: Path, depth: int) -> None:
        if depth > max_depth or len(entries) >= MAX_FILES:
            return

        try:
            items = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return

        for item in items:
            if item.name.startswith(".") and item.name not in (".gitignore", ".env.example"):
                continue
            if item.name in SKIP_DIRS:
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

            if item.is_dir():
                children: list[dict[str, Any]] = []
                entry["children"] = children
                _walk(item, depth + 1)

    _walk(root, 0)
    return entries
