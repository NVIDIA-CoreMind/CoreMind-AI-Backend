"""
CoreMind Backend — Dynamic Task Graph.

Defines a structured, dependency-aware task graph for agentic planning
and execution, replacing static string plans with dynamic task states.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class TaskNodeStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskNode:
    """A single actionable task node within an execution plan."""

    id: str
    title: str
    description: str = ""
    status: TaskNodeStatus = TaskNodeStatus.PENDING
    dependencies: list[str] = field(default_factory=list)
    priority: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    result: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "dependencies": list(self.dependencies),
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskNode:
        status_val = data.get("status", TaskNodeStatus.PENDING)
        if isinstance(status_val, str):
            try:
                status = TaskNodeStatus(status_val.lower())
            except ValueError:
                status = TaskNodeStatus.PENDING
        else:
            status = status_val

        created_at_raw = data.get("created_at")
        created_at = (
            datetime.fromisoformat(created_at_raw)
            if isinstance(created_at_raw, str)
            else datetime.now(UTC)
        )

        completed_at_raw = data.get("completed_at")
        completed_at = (
            datetime.fromisoformat(completed_at_raw)
            if isinstance(completed_at_raw, str)
            else None
        )

        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            description=str(data.get("description", "")),
            status=status,
            dependencies=list(data.get("dependencies", [])),
            priority=int(data.get("priority", 0)),
            created_at=created_at,
            completed_at=completed_at,
            result=data.get("result"),
            error=data.get("error"),
        )


class TaskGraph:
    """A directed task graph managing task lifecycle and dependencies."""

    def __init__(self, goal: str = "") -> None:
        self.goal = goal
        self._tasks: dict[str, TaskNode] = {}
        self._order: list[str] = []

    def create_task(
        self,
        title: str,
        description: str = "",
        dependencies: list[str] | None = None,
        priority: int = 0,
        task_id: str | None = None,
    ) -> TaskNode:
        """Add a new task node to the graph."""
        tid = task_id or f"task_{len(self._tasks) + 1}"
        node = TaskNode(
            id=tid,
            title=title,
            description=description,
            dependencies=list(dependencies or []),
            priority=priority,
        )
        self._tasks[tid] = node
        if tid not in self._order:
            self._order.append(tid)
        return node

    def get_task(self, task_id: str) -> TaskNode | None:
        return self._tasks.get(task_id)

    def update_task(
        self,
        task_id: str,
        status: TaskNodeStatus | str | None = None,
        result: Any = None,
        error: str | None = None,
    ) -> TaskNode | None:
        """Update status or result of a task."""
        node = self._tasks.get(task_id)
        if not node:
            return None

        if status is not None:
            if isinstance(status, str):
                node.status = TaskNodeStatus(status.lower())
            else:
                node.status = status

            if node.status in (TaskNodeStatus.COMPLETED, TaskNodeStatus.FAILED, TaskNodeStatus.SKIPPED):
                node.completed_at = datetime.now(UTC)

        if result is not None:
            node.result = result
        if error is not None:
            node.error = error

        return node

    def complete_task(self, task_id: str, result: Any = None) -> TaskNode | None:
        return self.update_task(task_id, status=TaskNodeStatus.COMPLETED, result=result)

    def block_task(self, task_id: str, reason: str = "") -> TaskNode | None:
        return self.update_task(task_id, status=TaskNodeStatus.BLOCKED, error=reason)

    def fail_task(self, task_id: str, error: str = "") -> TaskNode | None:
        return self.update_task(task_id, status=TaskNodeStatus.FAILED, error=error)

    def get_runnable_tasks(self) -> list[TaskNode]:
        """Return all tasks whose dependencies are completed and are currently pending."""
        runnable: list[TaskNode] = []
        for tid in self._order:
            node = self._tasks[tid]
            if node.status != TaskNodeStatus.PENDING:
                continue

            deps_satisfied = True
            for dep_id in node.dependencies:
                dep_node = self._tasks.get(dep_id)
                if not dep_node or dep_node.status != TaskNodeStatus.COMPLETED:
                    deps_satisfied = False
                    break

            if deps_satisfied:
                runnable.append(node)

        # Sort by priority descending
        runnable.sort(key=lambda t: t.priority, reverse=True)
        return runnable

    def is_completed(self) -> bool:
        """Check if all tasks are completed or skipped."""
        if not self._tasks:
            return True
        return all(
            t.status in (TaskNodeStatus.COMPLETED, TaskNodeStatus.SKIPPED)
            for t in self._tasks.values()
        )

    def has_failures(self) -> bool:
        return any(t.status == TaskNodeStatus.FAILED for t in self._tasks.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "tasks": [self._tasks[tid].to_dict() for tid in self._order if tid in self._tasks],
            "is_completed": self.is_completed(),
            "has_failures": self.has_failures(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskGraph:
        graph = cls(goal=data.get("goal", ""))
        for task_raw in data.get("tasks", []):
            node = TaskNode.from_dict(task_raw)
            graph._tasks[node.id] = node
            if node.id not in graph._order:
                graph._order.append(node.id)
        return graph

    def summary(self) -> str:
        """Generate a concise string representation of task progress."""
        if not self._tasks:
            return "No tasks created."
        lines = [f"Goal: {self.goal}"] if self.goal else []
        for tid in self._order:
            node = self._tasks[tid]
            icon = {
                TaskNodeStatus.PENDING: "⏳",
                TaskNodeStatus.IN_PROGRESS: "🔄",
                TaskNodeStatus.COMPLETED: "✅",
                TaskNodeStatus.BLOCKED: "🚫",
                TaskNodeStatus.FAILED: "❌",
                TaskNodeStatus.SKIPPED: "⏭️",
            }.get(node.status, "•")
            lines.append(f"{icon} [{node.id}] {node.title} ({node.status.value})")
        return "\n".join(lines)
