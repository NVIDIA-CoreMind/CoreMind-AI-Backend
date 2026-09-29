"""
CoreMind Backend — Project API Routes.

POST /v1/project/open — Open/register a project
GET  /v1/project/tree — Get project file tree
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.project.project_manager import project_manager
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
