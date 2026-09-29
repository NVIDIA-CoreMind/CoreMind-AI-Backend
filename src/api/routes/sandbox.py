"""
CoreMind Backend — Sandbox API Routes.

POST /v1/sandbox/create  — Create a sandbox instance
POST /v1/sandbox/execute — Execute code in sandbox
POST /v1/sandbox/destroy — Destroy a sandbox instance
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.sandbox.provider import get_sandbox_provider
from src.utils.logger import logger

router = APIRouter(prefix="/v1/sandbox", tags=["sandbox"])


class SandboxCreateRequest(BaseModel):
    project_path: str = Field(..., description="Project path for the sandbox")


class SandboxExecuteRequest(BaseModel):
    sandbox_id: str = Field(..., description="Sandbox instance ID")
    command: str = Field(..., description="Command to execute")
    timeout_ms: int | None = Field(default=None, description="Optional timeout override")


class SandboxDestroyRequest(BaseModel):
    sandbox_id: str = Field(..., description="Sandbox instance ID")


@router.post("/create")
async def create_sandbox(request: SandboxCreateRequest) -> dict[str, Any]:
    """Create a new sandbox instance."""
    logger.info("api.sandbox.create", project=request.project_path)
    provider = get_sandbox_provider()
    result = await provider.create(request.project_path)
    return result


@router.post("/execute")
async def execute_in_sandbox(request: SandboxExecuteRequest) -> dict[str, Any]:
    """Execute a command in a sandbox."""
    logger.info("api.sandbox.execute", sandbox_id=request.sandbox_id, command=request.command[:100])
    provider = get_sandbox_provider()
    result = await provider.execute(
        sandbox_id=request.sandbox_id,
        command=request.command,
        timeout_ms=request.timeout_ms,
    )
    return result


@router.post("/destroy")
async def destroy_sandbox(request: SandboxDestroyRequest) -> dict[str, str]:
    """Destroy a sandbox instance."""
    logger.info("api.sandbox.destroy", sandbox_id=request.sandbox_id)
    provider = get_sandbox_provider()
    success = await provider.destroy(request.sandbox_id)
    if not success:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    return {"status": "destroyed", "sandbox_id": request.sandbox_id}
