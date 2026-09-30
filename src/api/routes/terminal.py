"""
CoreMind Backend — Terminal API Routes.

POST   /v1/terminal/session              — Create persistent terminal session
POST   /v1/terminal/session/{id}/execute — Execute command in session
DELETE /v1/terminal/session/{id}         — Terminate session
GET    /v1/terminal/sessions             — List active sessions
POST   /v1/terminal/process/start        — Start background process
GET    /v1/terminal/process/{id}/status  — Background process status
GET    /v1/terminal/process/{id}/logs    — Read process logs
POST   /v1/terminal/process/{id}/stop    — Stop background process
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.terminal.process_manager import process_manager
from src.terminal.session import terminal_session_manager

router = APIRouter(prefix="/v1/terminal", tags=["terminal"])


class CreateSessionRequest(BaseModel):
    project_path: str = Field(..., min_length=1)
    session_id: str | None = None


class ExecuteCommandRequest(BaseModel):
    command: str = Field(..., min_length=1)
    timeout_seconds: float = 60.0


class StartProcessRequest(BaseModel):
    command: str = Field(..., min_length=1)
    cwd: str = Field(..., min_length=1)


@router.post("/session")
async def create_session(request: CreateSessionRequest) -> dict[str, Any]:
    """Create a new persistent terminal session."""
    session = terminal_session_manager.create_session(
        project_path=request.project_path,
        session_id=request.session_id,
    )
    return {
        "session_id": session.session_id,
        "project_path": session.project_path,
        "cwd": session.cwd,
        "is_active": session.is_active,
    }


@router.post("/session/{session_id}/execute")
async def execute_in_session(
    session_id: str,
    request: ExecuteCommandRequest,
) -> dict[str, Any]:
    """Execute a command inside a persistent terminal session."""
    session = terminal_session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Terminal session not found")

    result = await session.execute(
        command=request.command,
        timeout_seconds=request.timeout_seconds,
    )
    return result


@router.delete("/session/{session_id}")
async def delete_session(session_id: str) -> dict[str, Any]:
    """Terminate and remove a persistent terminal session."""
    success = terminal_session_manager.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Terminal session not found")
    return {"status": "deleted", "session_id": session_id}


@router.get("/sessions")
async def list_sessions() -> list[dict[str, Any]]:
    """List all active terminal sessions."""
    return terminal_session_manager.list_sessions()


@router.post("/process/start")
async def start_process(request: StartProcessRequest) -> dict[str, Any]:
    """Spawn a controlled background process."""
    res = await process_manager.start_process(request.command, request.cwd)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@router.get("/process/{process_id}/status")
async def process_status(process_id: str) -> dict[str, Any]:
    """Get status of a background process."""
    res = process_manager.get_process_status(process_id)
    if not res:
        raise HTTPException(status_code=404, detail="Background process not found")
    return res


@router.get("/process/{process_id}/logs")
async def process_logs(process_id: str, tail: int = 100) -> dict[str, Any]:
    """Read buffered logs of a background process."""
    logs = process_manager.read_process_logs(process_id, tail_lines=tail)
    if logs is None:
        raise HTTPException(status_code=404, detail="Background process not found")
    return {"process_id": process_id, "logs": logs}


@router.post("/process/{process_id}/stop")
async def stop_process(process_id: str) -> dict[str, Any]:
    """Stop a background process."""
    success = await process_manager.stop_process(process_id)
    if not success:
        raise HTTPException(status_code=404, detail="Background process not found or could not be stopped")
    return {"status": "stopped", "process_id": process_id}
