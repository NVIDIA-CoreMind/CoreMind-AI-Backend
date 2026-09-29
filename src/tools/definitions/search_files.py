"""
CoreMind Backend — Tool: search_files

Searches for a pattern across project files (grep-like).
Permission: READ
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.tools.registry import PermissionLevel, ToolDefinition

# Directories to skip during search
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "coverage",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "env",
}

# Binary extensions to skip
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".svg",
    ".woff", ".woff2", ".ttf", ".eot",
    ".pdf", ".zip", ".tar", ".gz",
    ".exe", ".dll", ".so", ".dylib",
    ".pyc", ".pyo", ".class",
}

MAX_RESULTS = 50
MAX_FILE_SIZE = 500_000  # 500 KB


async def execute_search_files(
    project_path: str,
    pattern: str,
    file_pattern: str | None = None,
    max_results: int = MAX_RESULTS,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Search for a text pattern across project files."""
    results: list[dict[str, Any]] = []
    files_searched = 0
    root = Path(project_path)

    for dirpath, dirnames, filenames in os.walk(root):
        # Skip unwanted directories
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for filename in filenames:
            if len(results) >= max_results:
                break

            file_path = Path(dirpath) / filename

            # Skip binary files
            if file_path.suffix.lower() in BINARY_EXTENSIONS:
                continue

            # Optional file pattern filter (e.g., "*.py")
            if file_pattern and not file_path.match(file_pattern):
                continue

            # Skip large files
            try:
                if file_path.stat().st_size > MAX_FILE_SIZE:
                    continue
            except OSError:
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                files_searched += 1
            except (OSError, UnicodeDecodeError):
                continue

            for line_num, line in enumerate(content.splitlines(), start=1):
                if pattern.lower() in line.lower():
                    rel_path = str(file_path.relative_to(root))
                    results.append({
                        "file": rel_path,
                        "line": line_num,
                        "content": line.strip()[:200],
                    })
                    if len(results) >= max_results:
                        break

    return {
        "pattern": pattern,
        "matches": results,
        "total_matches": len(results),
        "files_searched": files_searched,
        "truncated": len(results) >= max_results,
    }


search_files_tool = ToolDefinition(
    name="search_files",
    description=(
        "Search for a text pattern across project files."
        " Returns matching lines with file paths and line numbers."
    ),
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Text pattern to search for (case-insensitive)",
            },
            "file_pattern": {
                "type": "string",
                "description": "Optional glob pattern to filter files (e.g., '*.py')",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results (default 50)",
            },
        },
        "required": ["pattern"],
    },
    permission=PermissionLevel.READ,
    executor=execute_search_files,
    timeout_ms=30_000,
)
