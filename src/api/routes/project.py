"""
CoreMind Backend — Project API Routes.

POST /v1/project/open     — Open/register a project
GET  /v1/project/tree     — Get project file tree
GET  /v1/project/search   — Hybrid search in project files
GET  /v1/project/repo_map — Compact repository map with symbols
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.project.project_manager import project_manager
from src.project.repo_map import RepoMap
from src.project.search import HybridCodeSearcher
from src.utils.logger import logger

router = APIRouter(prefix="/v1/project", tags=["project"])


class ProjectOpenRequest(BaseModel):
    path: str = Field(..., min_length=1, description="Absolute path to project root")


@router.post("/open")
async def open_project(request: ProjectOpenRequest) -> dict[str, Any]:
    """Open a project and detect its framework/language."""
    logger.info("api.project.open", path=request.path)
    info = await project_manager.open_project(request.path)
    return info


@router.get("/tree")
async def project_tree(path: str) -> dict[str, Any]:
    """Get the file tree of an opened project."""
    info = project_manager.get_project(path)
    if info is None:
        raise HTTPException(status_code=404, detail="Project not opened")
    tree = await project_manager.get_tree(path)
    return {"project_path": path, "tree": tree}


@router.get("/search")
async def search_project(
    path: str,
    query: str,
    file_pattern: str | None = None,
    is_regex: bool = False,
    max_results: int = 30,
) -> dict[str, Any]:
    """Perform hybrid search across the project."""
    searcher = HybridCodeSearcher(path)
    matches = searcher.search(
        query=query,
        file_pattern=file_pattern,
        is_regex=is_regex,
        max_results=max_results,
    )
    return {
        "project_path": path,
        "query": query,
        "matches": [m.to_dict() for m in matches],
        "total": len(matches),
    }


@router.get("/repo_map")
async def get_repo_map(path: str) -> dict[str, Any]:
    """Get the symbol outline and compact repo map."""
    repo_map = RepoMap(path)
    summary = repo_map.build_compact_summary()
    return {
        "project_path": path,
        "summary": summary,
        "details": repo_map.to_dict(),
    }
