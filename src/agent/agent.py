"""
CoreMind Backend — Agent Manager.

Top-level manager that creates, runs, and tracks agents.
The API routes delegate to this class.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from src.agent.agent_loop import AgentLoop
from src.agent.task import AgentTask, TaskStatus
from src.project.project_manager import project_manager
from src.utils.ids import agent_id as gen_agent_id
from src.utils.ids import session_id as gen_session_id
from src.utils.logger import logger


class AgentManager:
    """Manages the lifecycle of all agents."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentLoop] = {}
        self._tasks: dict[str, AgentTask] = {}
        self._running_tasks: dict[str, asyncio.Task[AgentTask]] = {}

    async def start_agent(
        self,
        task: str,
        project_path: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Create and start a new agent for a task."""
        aid = gen_agent_id()
        sid = session_id or gen_session_id()

        # Ensure project is opened
        if project_manager.get_project(project_path) is None:
            await project_manager.open_project(project_path)

        agent_task = AgentTask(
            task_id=aid,
            session_id=sid,
            agent_id=aid,
            task=task,
            project_path=project_path,
        )

        agent_loop = AgentLoop(agent_task)
        self._agents[aid] = agent_loop
        self._tasks[aid] = agent_task

        # Run the agent loop in the background
        bg_task = asyncio.create_task(self._run_agent(aid, agent_loop))
        self._running_tasks[aid] = bg_task

        logger.info("agent.manager.started", agent_id=aid, session_id=sid, task=task[:100])

        return {
            "agent_id": aid,
            "session_id": sid,
            "status": "started",
        }

    async def _run_agent(self, agent_id: str, loop: AgentLoop) -> AgentTask:
        """Run the agent loop and handle completion."""
        try:
            result = await loop.run()
            logger.info(
                "agent.manager.completed",
                agent_id=agent_id,
                status=result.status.value,
                steps=result.steps_completed,
            )
            return result
        except Exception as exc:
            logger.error("agent.manager.error", agent_id=agent_id, error=str(exc))
            task = self._tasks.get(agent_id)
            if task:
                task.status = TaskStatus.FAILED
                task.error = str(exc)
                task.completed_at = datetime.now(UTC)
            raise
        finally:
            self._running_tasks.pop(agent_id, None)

    async def stop_agent(self, agent_id: str) -> bool:
        """Stop a running agent."""
        loop = self._agents.get(agent_id)
        if loop is None:
            return False

        loop.stop()

        # Cancel the background task
        bg_task = self._running_tasks.get(agent_id)
        if bg_task and not bg_task.done():
            bg_task.cancel()

        task = self._tasks.get(agent_id)
        if task:
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now(UTC)

        logger.info("agent.manager.stopped", agent_id=agent_id)
        return True

    def get_status(self, agent_id: str) -> dict[str, Any] | None:
        """Get the status of an agent."""
        task = self._tasks.get(agent_id)
        if task is None:
            return None
        return task.to_dict()

    def list_agents(self) -> list[dict[str, Any]]:
        """List all agents and their statuses."""
        return [task.to_dict() for task in self._tasks.values()]
