"""
CoreMind Backend — AI API Routes.

POST /v1/ai/test   — Test AI connectivity
GET  /v1/ai/models — List available models
GET  /v1/ai/usage  — Get token usage stats
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
            tool_calls = msg.tool_calls if hasattr(msg, "tool_calls") else msg.get("tool_calls")
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
