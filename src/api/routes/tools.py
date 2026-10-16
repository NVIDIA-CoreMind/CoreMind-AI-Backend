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

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.auth.dependencies import require_direct_execution
from src.tools.executor import ToolExecutor
from src.utils.logger import logger

router = APIRouter(prefix="/v1/tools", tags=["tools"])

# Routes below run shell commands or project tooling on the host (see DIRECT_EXECUTION_ENABLED).
_EXECUTION_GATE = [Depends(require_direct_execution)]

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


@router.post("/diff")
async def apply_diff_endpoint(request: ToolRequest) -> dict[str, Any]:
    """Apply a unified diff directly to a file."""
    logger.info("api.tools.apply_diff", project=request.project_path)
    result = await tool_executor.execute(
        tool_name="apply_diff",
        args=request.args,
        project_path=request.project_path,
    )
    return result


@router.post("/tests", dependencies=_EXECUTION_GATE)
async def run_tests_endpoint(request: ToolRequest) -> dict[str, Any]:
    """Run tests for the project."""
    logger.info("api.tools.run_tests", project=request.project_path)
    result = await tool_executor.execute(
        tool_name="run_tests",
        args=request.args,
        project_path=request.project_path,
    )
    return result


@router.post("/build", dependencies=_EXECUTION_GATE)
async def run_build_endpoint(request: ToolRequest) -> dict[str, Any]:
    """Run project build command."""
    logger.info("api.tools.run_build", project=request.project_path)
    result = await tool_executor.execute(
        tool_name="run_build",
        args=request.args,
        project_path=request.project_path,
    )
    return result


@router.post("/diagnostics", dependencies=_EXECUTION_GATE)
async def get_diagnostics_endpoint(request: ToolRequest) -> dict[str, Any]:
    """Retrieve diagnostics for a file or workspace."""
    logger.info("api.tools.get_diagnostics", project=request.project_path)
    result = await tool_executor.execute(
        tool_name="get_diagnostics",
        args=request.args,
        project_path=request.project_path,
    )
    return result


@router.post("/execute", dependencies=_EXECUTION_GATE)
async def execute_tool_endpoint(request: ToolRequest) -> dict[str, Any]:
    """Execute any schema-validated tool by name."""
    logger.info("api.tools.execute", tool=request.tool, project=request.project_path)
    result = await tool_executor.execute(
        tool_name=request.tool,
        args=request.args,
        project_path=request.project_path,
    )
    return result


@router.get("/list")
async def list_available_tools() -> list[dict[str, Any]]:
    """List all registered tools with schemas and permissions."""
    from src.tools.registry import tool_registry
    return [
        {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
            "permission": t.permission.value,
            "timeout_ms": t.timeout_ms,
            "requires_approval": t.requires_approval,
        }
        for t in tool_registry.list_tools()
    ]

