"""
CoreMind Backend — Project Manager.

Opens, tracks, and manages project state including detection,
scanning, and indexing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.project.detector import detect_project
from src.project.indexer import ProjectIndex
from src.project.scanner import scan_project
from src.utils.logger import logger


class ProjectManager:
    """Manages open projects and their metadata."""

    def __init__(self) -> None:
        self._projects: dict[str, dict[str, Any]] = {}
        self._indexes: dict[str, ProjectIndex] = {}

    async def open_project(self, path: str) -> dict[str, Any]:
        """Open a project, detect its type, and build the index."""
        root = Path(path)
        if not root.exists():
            return {"error": f"Project path does not exist: {path}"}

        if not root.is_dir():
            return {"error": f"Not a directory: {path}"}

        # Detect project type
        info = detect_project(path)
        logger.info(
            "project.opened",
            path=path,
            language=info.language,
            framework=info.framework,
        )

        # Build index
        index = ProjectIndex()
        await index.build(path)

        project_data: dict[str, Any] = {
            "path": path,
            "name": root.name,
            "language": info.language,
            "framework": info.framework,
            "package_manager": info.package_manager,
            "main_entry": info.main_entry,
            "test_command": info.test_command,
            "config_file": info.config_file,
            "file_count": index.file_count,
            "total_size": index.total_size,
        }

        self._projects[path] = project_data
        self._indexes[path] = index

        return project_data

    def get_project(self, path: str) -> dict[str, Any] | None:
        """Get project info by path."""
        return self._projects.get(path)

    def get_index(self, path: str) -> ProjectIndex | None:
        """Get the project file index."""
        return self._indexes.get(path)

    async def get_tree(self, path: str) -> list[dict[str, Any]]:
        """Get the file tree for a project."""
        return await scan_project(path)

    def close_project(self, path: str) -> bool:
        """Close/remove a project."""
        if path in self._projects:
            del self._projects[path]
            self._indexes.pop(path, None)
            logger.info("project.closed", path=path)
            return True
        return False


# Module-level singleton
project_manager = ProjectManager()
