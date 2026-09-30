"""
CoreMind Backend — Tools API Routes.

POST /v1/tools/search — Search files in project
POST /v1/tools/web-search — Search the public web
POST /v1/tools/read   — Read a file
POST /v1/tools/write  — Write a file
POST /v1/tools/edit   — Edit a file
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.tools.executor import ToolExecutor
from src.utils.logger import logger

router = APIRouter(prefix="/v1/tools", tags=["tools"])

tool_executor = ToolExecutor()


class ToolRequest(BaseModel):
    tool: str = Field(..., description="Tool name")
    args: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    project_path: str = Field(..., description="Active project path")


@router.post("/search")
async def search_files(request: ToolRequest) -> dict[str, Any]:
    """Search files in the project."""
    logger.info("api.tools.search", project=request.project_path)
    result = await tool_executor.execute(
        tool_name="search_files",
        args=request.args,
        project_path=request.project_path,
    )
    return result


@router.post("/web-search")
async def web_search(request: ToolRequest) -> dict[str, Any]:
    """Search the public web."""
    logger.info("api.tools.web_search", project=request.project_path)
    result = await tool_executor.execute(
        tool_name="web_search",
        args=request.args,
        project_path=request.project_path,
    )
    return result


@router.post("/read")
async def read_file(request: ToolRequest) -> dict[str, Any]:
    """Read a file from the project."""
    logger.info("api.tools.read", project=request.project_path)
    result = await tool_executor.execute(
        tool_name="read_file",
        args=request.args,
        project_path=request.project_path,
    )
    return result


@router.post("/write")
async def write_file(request: ToolRequest) -> dict[str, Any]:
    """Write/create a file in the project."""
    logger.info("api.tools.write", project=request.project_path)
    result = await tool_executor.execute(
        tool_name="write_file",
        args=request.args,
        project_path=request.project_path,
    )
    return result


@router.post("/edit")
async def edit_file(request: ToolRequest) -> dict[str, Any]:
    """Edit/patch a file in the project."""
    logger.info("api.tools.edit", project=request.project_path)
    result = await tool_executor.execute(
        tool_name="edit_file",
        args=request.args,
        project_path=request.project_path,
    )
    return result
