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
    """Chat with the AI, allowing it to use tools (like web search) before answering."""
    from src.tools.registry import tool_registry
    from src.tools.executor import ToolExecutor
    import json

    logger.info("api.ai.chat", query=request.query[:50])
    provider = get_ai_provider()
    executor = ToolExecutor(tool_registry)

    tools = tool_registry.to_openai_tools()

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": "You are CoreMind AI. Use the web_search tool to find current facts and docs. "
            "Use search_files, read_file to inspect the project. Combine internal and web data to answer."
        }
    ]

    for msg in request.history:
        m: dict[str, Any] = {"role": msg.role, "content": msg.content or ""}
        if msg.tool_calls:
            m["tool_calls"] = msg.tool_calls
        if msg.tool_call_id:
            m["tool_call_id"] = msg.tool_call_id
        if msg.name:
            m["name"] = msg.name
        messages.append(m)

    messages.append({"role": "user", "content": request.query})

    max_turns = 5
    for _ in range(max_turns):
        response = await provider.chat(messages=messages, tools=tools)

        ast_msg: dict[str, Any] = {"role": "assistant", "content": response.content or ""}
        if response.tool_calls:
            ast_msg["tool_calls"] = response.tool_calls
        messages.append(ast_msg)

        if not response.tool_calls:
            return {
                "status": "ok",
                "response": response.content,
                "history": messages[1:],
            }

        for tc in response.tool_calls:
            try:
                res = await executor.execute_tool_call(tc, project_path=request.project_path)
                result_str = json.dumps(res.get("result", res))
            except Exception as e:
                result_str = f"Error: {e}"

            messages.append({
                "role": "tool",
                "content": result_str,
                "tool_call_id": tc["id"],
                "name": tc["function"]["name"]
            })

    return {
        "status": "error",
        "error": "Max tool turns exceeded",
        "response": messages[-1].get("content", ""),
        "history": messages[1:]
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
