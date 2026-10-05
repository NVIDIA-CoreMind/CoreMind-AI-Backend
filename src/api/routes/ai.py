"""
CoreMind Backend — AI API Routes.

POST /v1/ai/test   — Test AI connectivity
GET  /v1/ai/models — List available models
GET  /v1/ai/usage  — Get token usage stats
POST /v1/ai/chat   — Chat with tools
POST /v1/ai/plan   — AI workflow planning
POST /v1/ai/code   — High-quality code generation
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.ai.provider import get_ai_provider
from src.utils.logger import logger

router = APIRouter(prefix="/v1/ai", tags=["ai"])


@router.post("/test")
async def test_ai() -> dict[str, Any]:
    """Test connectivity to the AI provider."""
    logger.info("api.ai.test")
    provider = get_ai_provider()
    try:
        response = await provider.chat(
            messages=[{
                "role": "user",
                "content": "Say 'CoreMind connected' in two words.",
            }],
        )
        return {
            "status": "ok",
            "provider": provider.name,
            "model": provider.model,
            "response": response.content,
        }
    except Exception as exc:
        return {
            "status": "error",
            "provider": provider.name,
            "error": str(exc),
        }


@router.get("/models")
async def list_models() -> dict[str, Any]:
    """List available models from the AI provider."""
    provider = get_ai_provider()
    models = await provider.list_models()
    return {"provider": provider.name, "models": models}


@router.get("/usage")
async def get_usage() -> dict[str, Any]:
    """Get token usage statistics."""
    provider = get_ai_provider()
    return {"provider": provider.name, "usage": provider.get_usage()}


class ChatMessage(BaseModel):
    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class ChatRequest(BaseModel):
    query: str
    project_path: str = Field(default=".")
    history: list[ChatMessage] = Field(default_factory=list)


@router.post("/chat")
async def chat_with_tools(request: ChatRequest) -> dict[str, Any]:
    """Chat with the AI, using the full AgentLoop for the best workflow planning and coding."""
    from src.agent.agent_loop import AgentLoop
    from src.agent.task import AgentTask
    from src.project.project_manager import project_manager
    from src.utils.ids import agent_id as gen_agent_id
    from src.utils.ids import session_id as gen_session_id

    logger.info("api.ai.chat", query=request.query[:50])

    aid = gen_agent_id()
    sid = gen_session_id()

    # Ensure project is opened
    if project_manager.get_project(request.project_path) is None:
        await project_manager.open_project(request.project_path)

    agent_task = AgentTask(
        task_id=aid,
        session_id=sid,
        agent_id=aid,
        task=request.query,
        project_path=request.project_path,
    )

    loop = AgentLoop(agent_task)

    # Inject history into context manager
    for msg in request.history:
        if msg.role == "user":
            loop._context.add_user_message(msg.content)
        elif msg.role == "assistant":
            # Pydantic may have tool_calls as list of dicts, but it's safe to pass
            tool_calls = getattr(msg, "tool_calls", None)
            loop._context.add_assistant_message(msg.content, tool_calls)
        elif msg.role == "tool":
            loop._context.add_tool_result(msg.tool_call_id or "", msg.name or "tool", msg.content)

    try:
        # Run the full agent loop synchronously
        result = await loop.run()

        # Get final response from the conversation
        messages = loop._context.build_messages()

        # Find the last assistant message to return as response
        final_response = "Agent task completed."
        for m in reversed(messages):
            if m.get("role") == "assistant" and m.get("content"):
                final_response = m.get("content")
                break

        if result.error:
            final_response += f"\n\nError encountered: {result.error}"

        return {
            "status": "ok" if result.status.value == "completed" else "error",
            "response": final_response,
            "agent_id": aid,
            "files_changed": result.files_changed,
            "steps": result.steps_completed,
            "history": messages[1:],  # Exclude system prompt
        }
    except Exception as exc:
        logger.error("api.ai.chat_error", error=str(exc))
        return {
            "status": "error",
            "error": str(exc),
            "response": f"Agent loop failed: {exc}",
            "history": []
        }


class PlanRequest(BaseModel):
    objective: str
    project_path: str = Field(default=".")
    context: str | None = None


@router.post("/plan")
async def create_plan(request: PlanRequest) -> dict[str, Any]:
    """Create a step-by-step plan for a complex coding objective."""
    provider = get_ai_provider()
    logger.info("api.ai.plan", objective=request.objective[:50])
    
    system_prompt = (
        "You are an expert AI architect and staff software engineer. "
        "Your task is to create a detailed, step-by-step implementation plan for the user's objective. "
        "Focus on architecture, edge cases, best practices, modularity, and exact steps to achieve the goal. "
        "Provide your output as a structured markdown document with clear phases."
    )
    
    user_prompt = f"Objective: {request.objective}\n"
    if request.context:
        user_prompt += f"Context:\n{request.context}\n"
        
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    try:
        response = await provider.chat(messages=messages)
        return {
            "status": "ok",
            "plan": response.content
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc)
        }


class CodeRequest(BaseModel):
    task: str
    plan: str | None = None
    project_path: str = Field(default=".")


@router.post("/code")
async def generate_code(request: CodeRequest) -> dict[str, Any]:
    """Generate high-quality code based on a task and an optional plan."""
    provider = get_ai_provider()
    logger.info("api.ai.code", task=request.task[:50])
    
    system_prompt = (
        "You are an elite software developer. "
        "Your task is to write clean, efficient, robust, well-documented, and production-ready code. "
        "Follow industry best practices, include necessary type hints, and handle errors gracefully. "
        "Make sure the code matches any provided architectural plan."
    )
    
    user_prompt = f"Task: {request.task}\n"
    if request.plan:
        user_prompt += f"Plan to follow:\n{request.plan}\n"
        
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    try:
        response = await provider.chat(messages=messages)
        return {
            "status": "ok",
            "code": response.content
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc)
        }
