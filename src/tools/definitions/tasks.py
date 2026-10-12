"""
CoreMind Backend — Tool: task management

Allows the AI agent to explicitly create, update, and track dynamic tasks
in the execution graph.
Permission: READ
"""

from __future__ import annotations

from typing import Any

from src.agent.task_graph import TaskNodeStatus
from src.events.event_bus import event_bus
from src.events.events import CoreMindEvent, EventType
from src.tools.registry import PermissionLevel, ToolDefinition
from src.utils.errors import ErrorCode, ToolError

# Global or thread-local task graph context reference
_active_task_graphs: dict[str, Any] = {}


def set_active_task_graph(agent_id: str, graph: Any) -> None:
    _active_task_graphs[agent_id] = graph


def get_active_task_graph(agent_id: str) -> Any:
    return _active_task_graphs.get(agent_id)


def clear_active_task_graph(agent_id: str) -> None:
    _active_task_graphs.pop(agent_id, None)


async def execute_create_task(
    project_path: str,
    title: str,
    description: str = "",
    dependencies: list[str] | None = None,
    priority: int = 0,
    agent_id: str = "",
    **_kwargs: Any,
) -> dict[str, Any]:
    """Create a task in the dynamic task graph."""
    graph = get_active_task_graph(agent_id)
    if not graph:
        return {"status": "ok", "task_id": "task_1", "title": title}

    node = graph.create_task(
        title=title,
        description=description,
        dependencies=dependencies or [],
        priority=priority,
    )
    if agent_id:
        sess_id = _kwargs.get("session_id")
        t_id = _kwargs.get("agent_task_id") or agent_id
        await event_bus.emit(CoreMindEvent(
            type=EventType.PLAN_CREATED,
            agent_id=agent_id,
            session_id=sess_id,
            task_id=t_id,
            data={"goal": graph.goal, "tasks": graph.to_dict()["tasks"]},
        ))
    return {"status": "created", "task": node.to_dict()}


async def execute_update_task(
    project_path: str,
    task_id: str,
    status: str,
    result: str | None = None,
    error: str | None = None,
    agent_id: str = "",
    **_kwargs: Any,
) -> dict[str, Any]:
    """Update task status in the dynamic task graph."""
    graph = get_active_task_graph(agent_id)
    if not graph:
        return {"status": "ok", "task_id": task_id, "new_status": status}

    try:
        node_status = TaskNodeStatus(status.lower())
    except ValueError:
        raise ToolError(
            ErrorCode.TOOL_INVALID_ARGS,
            f"Invalid status '{status}'. Valid statuses: {[s.value for s in TaskNodeStatus]}",
        )

    node = graph.update_task(task_id, status=node_status, result=result, error=error)
    if not node:
        raise ToolError(ErrorCode.TOOL_INVALID_ARGS, f"Task '{task_id}' not found in task graph.")

    if agent_id:
        sess_id = _kwargs.get("session_id")
        t_id = _kwargs.get("agent_task_id") or agent_id
        if node_status == TaskNodeStatus.COMPLETED:
            await event_bus.emit(CoreMindEvent(
                type=EventType.TASK_COMPLETED,
                agent_id=agent_id,
                session_id=sess_id,
                task_id=t_id,
                data={"task_id": task_id, "title": node.title, "status": "completed", "result": result},
            ))
        elif node_status == TaskNodeStatus.IN_PROGRESS:
            await event_bus.emit(CoreMindEvent(
                type=EventType.TASK_STARTED,
                agent_id=agent_id,
                session_id=sess_id,
                task_id=t_id,
                data={"task_id": task_id, "title": node.title},
            ))

    return {"status": "updated", "task": node.to_dict()}


create_task_tool = ToolDefinition(
    name="create_task",
    description="Create a subtask in the execution plan with optional dependencies and priority.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short title of the task"},
            "description": {"type": "string", "description": "Detailed description of the task"},
            "dependencies": {
                "type": "array",
                "items": {"type": "string"},
                "description": "IDs of tasks that must be completed before this task (e.g. ['task_1'])",
            },
            "priority": {"type": "integer", "description": "Priority (higher runs first, default 0)"},
        },
        "required": ["title"],
    },
    permission=PermissionLevel.READ,
    executor=execute_create_task,
)

update_task_tool = ToolDefinition(
    name="update_task",
    description="Update a subtask's status (pending, in_progress, completed, blocked, failed, skipped).",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "ID of the task to update (e.g. 'task_1')"},
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "completed", "blocked", "failed", "skipped"],
                "description": "New status for the task",
            },
            "result": {"type": "string", "description": "Optional summary of what was accomplished"},
            "error": {"type": "string", "description": "Optional error explanation if blocked/failed"},
        },
        "required": ["task_id", "status"],
    },
    permission=PermissionLevel.READ,
    executor=execute_update_task,
)
