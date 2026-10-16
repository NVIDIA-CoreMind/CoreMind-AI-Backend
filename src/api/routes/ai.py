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

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.ai.provider import get_ai_provider
from src.utils.logger import logger

core_router = APIRouter()


@core_router.post("/test")
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


@core_router.get("/models")
async def list_models() -> dict[str, Any]:
    """List available models from the AI provider."""
    provider = get_ai_provider()
    models = await provider.list_models()
    return {"provider": provider.name, "models": models}


@core_router.get("/usage")
async def get_usage() -> dict[str, Any]:
    """Get token usage statistics."""
    provider = get_ai_provider()
    return {"provider": provider.name, "usage": provider.get_usage()}


class ChatMessage(BaseModel):
    role: str = Field(default="user")
    content: str = Field(default="")
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class ChatRequest(BaseModel):
    query: str | None = Field(default=None, description="User prompt or chat query")
    prompt: str | None = Field(default=None, description="Alias for query")
    message: str | None = Field(default=None, description="Alias for query")
    task: str | None = Field(default=None, description="Alias for query")
    project_path: str = Field(default=".", description="Project path")
    workspace_path: str | None = Field(default=None, description="Alias for project_path")
    history: list[ChatMessage] = Field(default_factory=list, description="Prior conversation messages")
    messages: list[ChatMessage] | None = Field(default=None, description="Alias for history")

    @property
    def effective_query(self) -> str:
        q = self.query or self.prompt or self.message or self.task
        if not q or not q.strip():
            raise HTTPException(status_code=422, detail="Missing query or prompt text in request")
        return q.strip()

    @property
    def effective_history(self) -> list[ChatMessage]:
        return self.messages if self.messages is not None else self.history

    @property
    def effective_project_path(self) -> str:
        return self.workspace_path or self.project_path or "."


def _build_sanitized_messages(
    query_text: str,
    history: list[ChatMessage],
    system_prompt: str | None = None,
) -> list[dict[str, Any]]:
    """Build conversation message list, eliminating duplicate trailing user prompt."""
    default_system = (
        "You are CoreMind AI, an ultra-fast, intelligent coding assistant and staff software engineer. "
        "Provide direct, high-quality answers and clear explanations."
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt or default_system}
    ]

    for i, msg in enumerate(history):
        # Prevent duplicate if history already ended with the current query
        if i == len(history) - 1 and msg.role == "user" and msg.content.strip() == query_text.strip():
            continue
        messages.append({"role": msg.role, "content": msg.content or ""})

    messages.append({"role": "user", "content": query_text})
    return messages


async def _execute_live_search_context(query: str) -> str:
    """Run live web search via Tavily/DDG and format results as prompt context."""
    from src.config import settings
    from src.tools.definitions.web_search import execute_web_search

    try:
        logger.info("api.ai.chat.live_search", query=query[:80])
        search_res = await execute_web_search(query, max_results=settings.web_search_max_results)
        if search_res and search_res.get("results"):
            extra = "\n\n[Live Web Search Results (Tavily/DDG)]:\n"
            for r in search_res["results"]:
                extra += f"- {r.get('title')}: {r.get('snippet')} ({r.get('url')})\n"
            extra += (
                "\nINSTRUCTIONS: Answer the user's question accurately using the live web search results above. "
                "Always provide markdown links to the sources. Never claim you cannot browse the web."
            )
            return extra
    except Exception as e:
        logger.warn("api.ai.chat.live_search_failed", error=str(e))
    return ""


@core_router.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """
    Stream AI code generation and assistant responses via Server-Sent Events (SSE).
    Unthrottled token streaming without artificial delays or rate limiting.
    """
    from src.ai.intent import intent_detector

    query_text = request.effective_query
    history = request.effective_history
    provider = get_ai_provider()

    logger.info("api.ai.chat.stream", query=query_text[:50], history_len=len(history))

    if intent_detector.is_search_query(query_text):
        search_extra = await _execute_live_search_context(query_text)
        if search_extra:
            query_text += search_extra

    messages = _build_sanitized_messages(query_text, history)

    async def _event_generator() -> AsyncIterator[str]:
        try:
            from src.events.event_bus import event_bus
            from src.events.events import CoreMindEvent, EventType

            async for chunk in provider.stream(messages=messages):
                if chunk.content:
                    # Broadcast immediately via event bus for WebSocket subscribers
                    await event_bus.emit(
                        CoreMindEvent(
                            type=EventType.AI_TOKEN,
                            data={"token": chunk.content},
                        )
                    )
                    # Yield unthrottled SSE chunk
                    payload = json.dumps({
                        "type": "token",
                        "token": chunk.content,
                        "content": chunk.content,
                    })
                    yield f"data: {payload}\n\n"

            done_payload = json.dumps({"type": "done", "status": "completed"})
            yield f"data: {done_payload}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            logger.error("api.ai.chat.stream_error", error=str(exc))
            err_payload = json.dumps({"type": "error", "error": str(exc)})
            yield f"data: {err_payload}\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@core_router.post("/chat/friendly")
@core_router.post("/friendly")
async def friendly_chat(request: ChatRequest) -> dict[str, Any]:
    """Dedicated endpoint for fast, conversational AI chat without workspace mutations."""
    from src.ai.intent import intent_detector
    from src.utils.ids import agent_id as gen_agent_id

    query_text = request.effective_query
    history = request.effective_history
    logger.info("api.ai.chat.friendly", query=query_text[:50])

    system_prompt = (
        "You are CoreMind AI, an ultra-fast, intelligent coding assistant. "
        "Provide clear, direct, and concise answers."
    )

    if intent_detector.is_search_query(query_text):
        search_extra = await _execute_live_search_context(query_text)
        if search_extra:
            query_text += search_extra
            system_prompt = (
                "You are CoreMind AI, an intelligent coding assistant with live web search capabilities. "
                "Answer the user accurately using the provided live search results. "
                "Provide markdown links to sources. Never claim you cannot browse the web."
            )

    provider = get_ai_provider()
    chat_messages = _build_sanitized_messages(
        query_text,
        history,
        system_prompt=system_prompt,
    )

    try:
        response = await provider.chat(messages=chat_messages, max_tokens=1024)
    except Exception as exc:
        logger.error("api.ai.chat.friendly_error", error=str(exc))
        raise HTTPException(
            status_code=502,
            detail=f"AI Provider error during chat completion: {str(exc)}",
        )

    history_out = [{"role": m["role"], "content": m["content"]} for m in chat_messages if m["role"] != "system"]
    history_out.append({"role": "assistant", "content": response.content})

    return {
        "status": "ok",
        "response": response.content,
        "agent_id": gen_agent_id(),
        "files_changed": [],
        "files_details": [],
        "steps": 1,
        "history": history_out,
    }


@core_router.post("/chat")
async def chat_with_tools(request: ChatRequest) -> dict[str, Any]:
    """Chat with the AI, using the full AgentLoop for the best workflow planning and coding."""
    from src.agent.agent_loop import AgentLoop
    from src.agent.task import AgentTask
    from src.project.project_manager import project_manager
    from src.utils.ids import agent_id as gen_agent_id
    from src.utils.ids import session_id as gen_session_id
    from src.ai.intent import intent_detector

    query_text = request.effective_query
    history = request.effective_history
    proj_path = request.effective_project_path

    logger.info("api.ai.chat", query=query_text[:50])

    aid = gen_agent_id()
    sid = gen_session_id()

    # If it's a live search query, fetch live web search results immediately
    is_search = intent_detector.is_search_query(query_text)
    if is_search:
        search_extra = await _execute_live_search_context(query_text)
        if search_extra:
            query_text += search_extra

    # Detect if it's a friendly chat — now instant (no LLM call)
    if not is_search and await intent_detector.is_friendly_chat(query_text):
        provider = get_ai_provider()
        chat_messages = _build_sanitized_messages(
            query_text,
            history,
            system_prompt=(
                "You are CoreMind AI, an ultra-fast, intelligent coding assistant. "
                "Provide clear, direct, and concise answers."
            ),
        )

        try:
            response = await provider.chat(messages=chat_messages, max_tokens=1024)

            history_out = [{"role": m["role"], "content": m["content"]} for m in chat_messages if m["role"] != "system"]
            history_out.append({"role": "assistant", "content": response.content})

            return {
                "status": "ok",
                "response": response.content,
                "agent_id": aid,
                "files_changed": [],
                "files_details": [],
                "steps": 1,
                "history": history_out,
            }
        except Exception as exc:
            logger.error("api.ai.chat.friendly_error", error=str(exc))
            raise HTTPException(
                status_code=502,
                detail=f"AI Provider error during chat completion: {str(exc)}",
            )

    # Ensure project is opened
    if project_manager.get_project(proj_path) is None:
        await project_manager.open_project(proj_path)

    agent_task = AgentTask(
        task_id=aid,
        session_id=sid,
        agent_id=aid,
        task=query_text,
        project_path=proj_path,
    )

    loop = AgentLoop(agent_task)

    # Inject history into context manager
    for msg in history:
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

        files_details = []
        for p_rel in result.files_changed:
            target_f = Path(request.project_path) / p_rel
            line_cnt = 0
            if target_f.exists() and target_f.is_file():
                try:
                    line_cnt = len(target_f.read_text(encoding="utf-8", errors="ignore").splitlines())
                except Exception:
                    pass
            files_details.append({
                "file": p_rel,
                "lines": line_cnt,
                "action": "created" if line_cnt > 0 else "modified",
            })

        # Check if project has a web entrypoint and ensure web server is running
        local_url = None
        try:
            from src.terminal.web_server import ensure_project_web_server
            server_info = await ensure_project_web_server(request.project_path)
            if server_info:
                local_url = server_info.get("url")
        except Exception as ws_err:
            logger.warn("api.ai.chat.web_server_warn", error=str(ws_err))

        if local_url and local_url not in final_response:
            final_response += (
                f"\n\n---\n"
                f"🌐 **Local Website Preview:** [{local_url}]({local_url})\n\n"
                f"Your website is running live on local host and ready to view in your browser!"
            )

        return {
            "status": "ok" if result.status.value == "completed" else "error",
            "response": final_response,
            "agent_id": aid,
            "files_changed": result.files_changed,
            "files_details": files_details,
            "steps": result.steps_completed,
            "local_url": local_url,
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


@core_router.post("/plan")
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


@core_router.post("/code")
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


# ── Mount prefixes: /v1/ai and /ai ─────────────────────────────────
router = APIRouter(prefix="/v1/ai", tags=["ai"])
router.include_router(core_router)

bare_router = APIRouter(prefix="/ai", tags=["ai"])
bare_router.include_router(core_router)
