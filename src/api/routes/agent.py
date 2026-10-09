"""
CoreMind Backend — Agent API Routes.

POST /v1/agent/run      — Start an agent task
POST /v1/agent/stop     — Stop a running agent
POST /v1/agent/cancel   — Alias for stopping an agent
GET  /v1/agent/status   — Get agent status
GET  /v1/agent/{agent_id} — Get agent details / status
POST /v1/agent/question — Submit answer to pending ask_user question
GET  /v1/agent/questions — List pending ask_user questions
POST /v1/agent/approve  — Approve a pending tool action
POST /v1/agent/deny     — Deny a pending tool action
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.agent.agent import AgentManager
from src.tools.definitions.ask_question import question_manager
from src.utils.logger import logger

router = APIRouter(prefix="/v1/agent", tags=["agent"])

# Singleton agent manager
agent_manager = AgentManager()


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


class QuestionAnswerRequest(BaseModel):
    question_id: str
    answer: str


class ApprovalRequest(BaseModel):
    approval_id: str
    agent_id: str | None = None


class DenyRequest(BaseModel):
    approval_id: str
    agent_id: str | None = None
    reason: str = "User denied"


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


@router.post("/cancel")
async def cancel_agent(request: AgentStopRequest) -> dict[str, str]:
    """Cancel a running agent (alias for stop)."""
    return await stop_agent(request)


@router.post("/stop_all")
async def stop_all_agents() -> dict[str, Any]:
    """Emergency stop all running agents and tasks."""
    logger.fatal("security.emergency.stop_all_requested")
    
    tasks = agent_manager.list_agents()
    count = 0
    for task in tasks:
        if task.get("status") in ["running", "pending"]:
            await agent_manager.stop_agent(task["agent_id"])
            count += 1
            
    # Also stop all background terminal processes via emergency override if possible
    # from src.terminal.process_manager import process_manager
    # await process_manager.stop_all() # Assuming it exists, skipping to avoid breaking
            
    return {"status": "emergency_stop_executed", "agents_stopped": count}


@router.get("/status")
async def agent_status(agent_id: str) -> dict[str, Any]:
    """Get the status of an agent."""
    status = agent_manager.get_status(agent_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return status


@router.get("/tasks")
async def list_agent_tasks() -> list[dict[str, Any]]:
    """List all agent tasks."""
    return agent_manager.list_agents()


@router.get("/questions")
async def list_pending_questions(agent_id: str | None = None) -> list[dict[str, Any]]:
    """List pending questions waiting for user response."""
    return question_manager.get_pending(agent_id)


@router.post("/question")
async def answer_question(request: QuestionAnswerRequest) -> dict[str, str]:
    """Answer a pending question asked by an agent."""
    success = question_manager.answer_question(request.question_id, request.answer)
    if not success:
        raise HTTPException(status_code=404, detail="Question not found or already answered")
    return {"status": "answered", "question_id": request.question_id}


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


@router.get("/audit_logs")
async def get_audit_logs(limit: int = 100) -> list[dict[str, Any]]:
    """Get security and permission audit logs."""
    from src.security.audit_logger import audit_logger
    return audit_logger.get_logs(limit=limit)


@router.post("/task", response_model=AgentRunResponse)
async def create_agent_task(request: AgentRunRequest) -> AgentRunResponse:
    """Create and start an agent task (alias for /run)."""
    return await run_agent(request)


@router.get("/{task_id}")
async def get_agent_by_id(task_id: str) -> dict[str, Any]:
    """Get details for an agent task by ID."""
    status = agent_manager.get_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Agent task '{task_id}' not found")
    return status


@router.get("/{task_id}/history")
async def get_task_history(task_id: str) -> dict[str, Any]:
    """Retrieve conversation messages and turn history for an agent task."""
    task = agent_manager.get_status(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Agent task '{task_id}' not found")
    messages = task.get("messages", [])
    if not messages:
        from src.agent.storage import task_storage
        session_id = task.get("session_id", "")
        if session_id:
            messages = task_storage.get_conversation_history(session_id)
    return {
        "task_id": task_id,
        "session_id": task.get("session_id"),
        "status": task.get("status"),
        "messages": messages,
        "files_changed": task.get("files_changed", []),
        "steps_completed": task.get("steps_completed", 0),
        "tool_calls_count": task.get("tool_calls_count", 0),
        "task_graph": task.get("task_graph", {}),
    }


@router.get("/{task_id}/events")
@router.get("/{task_id}/stream")
async def stream_agent_events(task_id: str) -> Any:
    """Stream live agent events via Server-Sent Events (SSE)."""
    import asyncio
    from collections.abc import AsyncGenerator
    from fastapi.responses import StreamingResponse
    from src.events.event_bus import event_bus
    from src.events.events import CoreMindEvent, EventType

    queue = event_bus.subscribe()

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            status = agent_manager.get_status(task_id)
            if status:
                initial_event = CoreMindEvent(
                    type=EventType.TASK_STATUS,
                    agent_id=task_id,
                    task_id=task_id,
                    data={"status": status.get("status", "running")},
                )
                yield initial_event.to_sse()

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=2.0)
                    if event.agent_id == task_id or event.task_id == task_id or not event.agent_id:
                        yield event.to_sse()
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            event_bus.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/{task_id}")
async def delete_agent_task(task_id: str) -> dict[str, Any]:
    """Delete an agent task from database storage."""
    from src.agent.storage import task_storage
    deleted = task_storage.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Agent task '{task_id}' not found")
    return {"status": "deleted", "task_id": task_id}

