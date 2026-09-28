import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.providers.nebius_client import default_nebius_client, SUPPORTED_NVIDIA_MODELS
from app.sandbox.python_runner import default_python_runner
from app.agent.execution_engine import default_execution_engine
from app.api.sse_handler import SSEEventStream

api_router = APIRouter()


class RunAgentRequest(BaseModel):
    task: str = Field(description="The software engineering task to execute")
    workspace_path: Optional[str] = Field(default=None, alias="workspacePath")
    model: Optional[str] = Field(default=None)
    extra_context: Optional[str] = Field(default=None, alias="extraContext")
    max_iterations: Optional[int] = Field(default=None, alias="maxIterations")
    max_debug_retries: Optional[int] = Field(default=None, alias="maxDebugRetries")

    class Config:
        populate_by_name = True


class ExecutePythonRequest(BaseModel):
    code: Optional[str] = None
    script_path: Optional[str] = Field(default=None, alias="scriptPath")
    args: Optional[List[str]] = None
    cwd: Optional[str] = None
    timeout: Optional[int] = None

    class Config:
        populate_by_name = True


class RunTestsRequest(BaseModel):
    test_command: Optional[str] = Field(default=None, alias="testCommand")
    test_path: Optional[str] = Field(default=None, alias="testPath")
    cwd: Optional[str] = None
    timeout: Optional[int] = None

    class Config:
        populate_by_name = True


@api_router.get("/health")
async def health_check():
    nebius_health = await default_nebius_client.check_health()
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nebius": nebius_health,
        "environment": settings.environment,
        "active_model": settings.nebius.default_model,
    }


@api_router.get("/api/models")
async def list_models():
    return {
        "default_model": settings.nebius.default_model,
        "supported_models": SUPPORTED_NVIDIA_MODELS,
        "base_url": default_nebius_client.base_url,
    }


@api_router.post("/api/agent/run")
async def run_agent(request: RunAgentRequest):
    if not request.task.strip():
        raise HTTPException(status_code=400, detail="Field 'task' is required.")

    target_workspace = (
        Path(request.workspace_path).resolve()
        if request.workspace_path
        else settings.sandbox.work_dir
    )

    sse = SSEEventStream()

    async def execute_task_background():
        try:
            result = await default_execution_engine.run_agent_loop(
                task=request.task,
                workspace_path=target_workspace,
                model=request.model,
                max_iterations=request.max_iterations,
                max_debug_retries=request.max_debug_retries,
                extra_context=request.extra_context,
                on_event=lambda ev_type, data: sse.emit(ev_type, data),
            )
            sse.close(final_payload=result)
        except Exception as exc:
            sse.emit("error", {"message": str(exc)})
            sse.close(final_payload={"success": False, "error": str(exc)})

        # Fire and forget background worker connected to queue
    asyncio.create_task(execute_task_background())

    return StreamingResponse(
        sse.stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@api_router.post("/api/sandbox/execute")
async def execute_sandbox_code(request: ExecutePythonRequest):
    if not request.code and not request.script_path:
        raise HTTPException(status_code=400, detail="Either 'code' or 'scriptPath' must be provided.")

    target_cwd = Path(request.cwd).resolve() if request.cwd else settings.sandbox.work_dir
    result = await default_python_runner.run_code(
        code=request.code,
        script_path=request.script_path,
        args=request.args,
        cwd=target_cwd,
        timeout_ms=request.timeout,
    )
    return result.model_dump()


@api_router.post("/api/sandbox/test")
async def execute_sandbox_tests(request: RunTestsRequest):
    target_cwd = Path(request.cwd).resolve() if request.cwd else settings.sandbox.work_dir
    result = await default_python_runner.run_tests(
        test_command=request.test_command,
        test_path=request.test_path,
        cwd=target_cwd,
        timeout_ms=request.timeout,
    )
    return result.model_dump()
