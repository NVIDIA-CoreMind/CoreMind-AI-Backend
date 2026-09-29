"""
CoreMind Backend — Project Indexer.

Builds a searchable index of project files for fast lookups.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", "coverage",
}

CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".dart", ".java", ".kt",
    ".rs", ".go", ".c", ".cpp", ".h", ".hpp", ".cs", ".rb",
    ".swift", ".vue", ".svelte", ".html", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml", ".xml", ".md", ".txt",
    ".sh", ".bash", ".zsh", ".sql", ".graphql",
}


class ProjectIndex:
    """In-memory index of project files."""

    def __init__(self) -> None:
        self.files: list[str] = []
        self.file_count: int = 0
        self.total_size: int = 0

    async def build(self, project_path: str) -> None:
        """Build the index from the project directory."""
        root = Path(project_path)
        self.files = []
        self.file_count = 0
        self.total_size = 0

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

            for filename in filenames:
                file_path = Path(dirpath) / filename
                if file_path.suffix.lower() in CODE_EXTENSIONS:
                    rel = str(file_path.relative_to(root))
                    self.files.append(rel)
                    try:
                        self.total_size += file_path.stat().st_size
                    except OSError:
                        pass

        self.file_count = len(self.files)

    def search(self, query: str) -> list[str]:
        """Search file paths matching a query."""
        query_lower = query.lower()
        return [f for f in self.files if query_lower in f.lower()]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_count": self.file_count,
            "total_size": self.total_size,
            "files": self.files[:100],  # Cap for context window
        }
