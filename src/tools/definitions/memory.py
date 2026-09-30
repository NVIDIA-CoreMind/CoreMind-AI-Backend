"""
CoreMind Backend — Tools: memory_save, memory_recall, memory_forget

Limited durable memory for the coding agent. Permission: WRITE / READ.
"""

from __future__ import annotations

from typing import Any

from src.config import settings
from src.memory.store import ALLOWED_CATEGORIES, agent_memory
from src.tools.registry import PermissionLevel, ToolDefinition


async def execute_memory_save(
    project_path: str,
    content: str,
    category: str = "fact",
    importance: int = 3,
    **_kwargs: Any,
) -> dict[str, Any]:
    item = agent_memory.save(
        project_path=project_path,
        content=content,
        category=category,
        importance=importance,
    )
    return {
        "saved": True,
        "memory": item.to_dict(),
        "project_count": agent_memory.count(project_path),
        "max_items": settings.memory_max_items,
    }


async def execute_memory_recall(
    project_path: str,
    query: str = "",
    **_kwargs: Any,
) -> dict[str, Any]:
    items = agent_memory.recall(project_path, query=query)
    return {
        "query": query,
        "memories": [item.to_dict() for item in items],
        "returned": len(items),
        "project_count": agent_memory.count(project_path),
        "max_items": settings.memory_max_items,
    }


async def execute_memory_forget(
    project_path: str,
    memory_id: str,
    **_kwargs: Any,
) -> dict[str, Any]:
    deleted = agent_memory.forget(project_path, memory_id)
    return {
        "forgotten": deleted,
        "memory_id": memory_id,
        "project_count": agent_memory.count(project_path),
    }


memory_save_tool = ToolDefinition(
    name="memory_save",
    description=(
        "Save a short durable note about this project (conventions, user preferences, "
        "decisions, lessons). Capacity is limited — do not store file contents or "
        "ephemeral task details."
    ),
    parameters={
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The note to remember (short, durable)",
            },
            "category": {
                "type": "string",
                "description": (
                    "One of: fact, preference, decision, lesson, convention"
                ),
                "enum": sorted(ALLOWED_CATEGORIES),
            },
            "importance": {
                "type": "integer",
                "description": "1 (low) to 5 (must keep). Weak notes are evicted first.",
            },
        },
        "required": ["content"],
    },
    permission=PermissionLevel.WRITE,
    executor=execute_memory_save,
    timeout_ms=5_000,
)

memory_recall_tool = ToolDefinition(
    name="memory_recall",
    description=(
        "Search this project's limited durable memories. Use when you need a stored "
        "convention, preference, or past decision."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to look up in memory",
            },
        },
        "required": [],
    },
    permission=PermissionLevel.READ,
    executor=execute_memory_recall,
    timeout_ms=5_000,
)

memory_forget_tool = ToolDefinition(
    name="memory_forget",
    description="Delete a stored memory by id when it is wrong or obsolete.",
    parameters={
        "type": "object",
        "properties": {
            "memory_id": {
                "type": "string",
                "description": "Memory id returned by memory_save or memory_recall",
            },
        },
        "required": ["memory_id"],
    },
    permission=PermissionLevel.WRITE,
    executor=execute_memory_forget,
    timeout_ms=5_000,
)
