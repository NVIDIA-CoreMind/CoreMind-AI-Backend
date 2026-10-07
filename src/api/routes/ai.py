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

    # Detect if it's a friendly chat — now instant (no LLM call)
    from src.ai.intent import intent_detector
    from src.ai.provider import get_ai_provider

    if await intent_detector.is_friendly_chat(request.query):
        provider = get_ai_provider()
        chat_messages = [
            {
                "role": "system",
                "content": "You are CoreMind AI, an ultra-fast, intelligent coding assistant. Provide clear, direct, and concise answers.",
            }
        ]
        for msg in request.history:
            chat_messages.append({"role": msg.role, "content": msg.content})
        chat_messages.append({"role": "user", "content": request.query})
        
        try:
            response = await provider.chat(messages=chat_messages, max_tokens=1024)
            
            # Format as expected by the chat endpoint
            history_out = [{"role": msg.role, "content": msg.content} for msg in request.history]
            history_out.append({"role": "user", "content": request.query})
            history_out.append({"role": "assistant", "content": response.content})
            
            return {
                "status": "ok",
                "response": response.content,
                "agent_id": aid,
                "files_changed": [],
                "steps": 1,
                "history": history_out,
            }
        except Exception as exc:
            logger.error("api.ai.chat.friendly_error", error=str(exc))
            # Fallback to normal flow if it fails


    # Ensure project is opened
    if project_manager.get_project(request.project_path) is None:
        await project_manager.open_project(request.project_path)

    # --- AUTO-SEARCH: Run concurrently (non-blocking) ---
    import asyncio

    query_lower = request.query.lower()
    search_task = None
    if any(kw in query_lower for kw in ("search", "trending", "latest", "look up", "current", "github")):
        from src.tools.definitions.web_search import execute_web_search

        async def _do_search() -> str | None:
            try:
                logger.info("api.ai.chat.auto_search", query=request.query)
                search_res = await execute_web_search(request.query, max_results=3)
                if search_res and search_res.get("results"):
                    extra = "\n\n[System Auto-Search Results Provided for Context]:\n"
                    for r in search_res["results"]:
                        extra += f"- {r.get('title')}: {r.get('snippet')} ({r.get('url')})\n"
                    return extra
            except Exception as e:
                logger.warn("api.ai.chat.auto_search_failed", error=str(e))
            return None

        search_task = asyncio.create_task(_do_search())

    # If search was started, await it (with a short timeout so it doesn't block forever)
    if search_task is not None:
        try:
            search_extra = await asyncio.wait_for(search_task, timeout=5.0)
            if search_extra:
                request.query += search_extra
        except asyncio.TimeoutError:
            logger.warn("api.ai.chat.auto_search_timeout")
    # --------------------------

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
