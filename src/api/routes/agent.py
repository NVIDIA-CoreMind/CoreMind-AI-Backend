"""
CoreMind Backend — Agent API Routes.

POST /v1/agent/run     — Start an agent task
POST /v1/agent/stop    — Stop a running agent
GET  /v1/agent/status  — Get agent status
POST /v1/agent/approve — Approve a pending action
POST /v1/agent/deny    — Deny a pending action
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.agent.agent import AgentManager
from src.utils.logger import logger

router = APIRouter(prefix="/v1/agent", tags=["agent"])

# ── Singleton agent manager ─────────────────────────────────────────
agent_manager = AgentManager()


# ── Request / Response schemas ──────────────────────────────────────


class AgentRunRequest(BaseModel):
    task: str = Field(..., min_length=1, description="The coding task to execute")
    project_path: str = Field(..., min_length=1, description="Absolute path to the project")
    session_id: str | None = Field(default=None, description="Optional session ID to resume")


class AgentRunResponse(BaseModel):
    agent_id: str
    session_id: str
    status: str


class AgentStopRequest(BaseModel):
    agent_id: str


class ApprovalRequest(BaseModel):
    agent_id: str
    approval_id: str


class DenyRequest(BaseModel):
    agent_id: str
    approval_id: str
    reason: str = "User denied"


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/run", response_model=AgentRunResponse)
async def run_agent(request: AgentRunRequest) -> AgentRunResponse:
    """Start an agent to execute a coding task."""
    logger.info("api.agent.run", task=request.task[:100], project=request.project_path)

    result = await agent_manager.start_agent(
        task=request.task,
        project_path=request.project_path,
        session_id=request.session_id,
    )
    return AgentRunResponse(**result)


@router.post("/stop")
async def stop_agent(request: AgentStopRequest) -> dict[str, str]:
    """Stop a running agent."""
    logger.info("api.agent.stop", agent_id=request.agent_id)

    success = await agent_manager.stop_agent(request.agent_id)
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "stopped", "agent_id": request.agent_id}


@router.get("/status")
async def agent_status(agent_id: str) -> dict[str, Any]:
    """Get the status of an agent."""
    status = agent_manager.get_status(agent_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return status


@router.post("/approve")
async def approve_action(request: ApprovalRequest) -> dict[str, str]:
    """Approve a pending agent action."""
    from src.security.approval_manager import approval_manager

    logger.info("api.agent.approve", agent_id=request.agent_id, approval_id=request.approval_id)
    await approval_manager.approve(request.approval_id)
    return {"status": "approved"}


@router.post("/deny")
async def deny_action(request: DenyRequest) -> dict[str, str]:
    """Deny a pending agent action."""
    from src.security.approval_manager import approval_manager

    logger.info("api.agent.deny", agent_id=request.agent_id, approval_id=request.approval_id)
    await approval_manager.deny(request.approval_id, request.reason)
    return {"status": "denied"}
