"""
CoreMind Backend — Agent Loop.

The main execution loop that orchestrates:
    Understand → Inspect Context → Create Plan → Execute Task →
    Observe Result → Verify → Fix → Re-verify → Complete

This is the brain of CoreMind.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from src.agent.checkpoint import Checkpoint, checkpoint_manager
from src.agent.executor import AgentExecutor
from src.agent.planner import generate_task_graph
from src.agent.state_machine import AgentState, StateMachine
from src.agent.task import AgentTask, TaskStatus
from src.agent.task_graph import TaskNodeStatus
from src.agent.verifier import VerificationResult, run_verification
from src.ai.prompts.coding import build_error_analysis
from src.ai.provider import get_ai_provider
from src.changes.review import ChangeSet, change_review_manager
from src.config import settings
from src.context.context_manager import ContextManager
from src.events.event_bus import event_bus
from src.events.events import CoreMindEvent, EventType
from src.tools.definitions.tasks import clear_active_task_graph, set_active_task_graph
from src.tools.registry import tool_registry
from src.utils.logger import logger

MAX_REPAIR_ATTEMPTS = 3


class AgentLoop:
    """The main agent execution engine."""

    def __init__(self, task: AgentTask) -> None:
        self._task = task
        self._state = StateMachine(task.agent_id)
        self._context = ContextManager(task.project_path)
        self._executor = AgentExecutor(task.project_path, task.agent_id)
        self._provider = get_ai_provider()
        self._tools = tool_registry.to_openai_tools()
        self._stopped = False
        self._checkpoint: Checkpoint | None = None
        self._change_set: ChangeSet | None = None

    @property
    def state(self) -> AgentState:
        return self._state.state

    async def run(self) -> AgentTask:
        """
        Execute the full agent loop.
        Returns the completed task with all results.
        """
        set_active_task_graph(self._task.agent_id, self._task.task_graph)
        try:
            await self._emit(EventType.AGENT_STARTED, {"task": self._task.task[:200]})
            self._task.status = TaskStatus.RUNNING

            # Step 1: Understand & Analyze Context
            self._state.transition(AgentState.ANALYZING)
            await self._emit(EventType.AGENT_THINKING, {"phase": "analyzing"})

            # Step 2: Create Structured Plan
            self._state.transition(AgentState.PLANNING)
            await self._emit(EventType.AGENT_PLANNING, {"phase": "planning"})

            # Generate structured task graph
            try:
                task_graph = await generate_task_graph(
                    task=self._task.task,
                    project_context=f"Project root: {self._task.project_path}",
                )
                self._task.task_graph = task_graph
                set_active_task_graph(self._task.agent_id, self._task.task_graph)
                await self._emit(
                    EventType.PLAN_CREATED,
                    {"goal": task_graph.goal, "tasks": task_graph.to_dict()["tasks"]},
                )
            except Exception as plan_err:
                logger.warn("agent.loop.plan_generation_warn", error=str(plan_err))

            # Build initial context with user task and task summary
            user_prompt = self._task.task
            if self._task.task_graph and self._task.task_graph._tasks:
                user_prompt += f"\n\nPlanned Task Roadmap:\n{self._task.task_graph.summary()}"

            messages = self._context.build_messages(user_task=user_prompt)

            # Step 3: Main loop — Execute → Observe → Act
            # Create Git Checkpoint & Change Set before AI modifications begin
            self._checkpoint = await checkpoint_manager.create_checkpoint(self._task.project_path)
            self._change_set = change_review_manager.create_change_set(
                self._task.agent_id, self._task.project_path
            )
            self._executor.set_checkpoint(self._checkpoint)
            self._executor.set_change_set_id(self._change_set.change_id)

            self._state.transition(AgentState.EXECUTING)
            step = 0


            while step < settings.max_agent_steps and not self._stopped:
                step += 1
                self._task.steps_completed = step

                # Mark next runnable subtask in progress if available
                runnable_tasks = self._task.task_graph.get_runnable_tasks()
                current_subtask_id = ""
                if runnable_tasks:
                    current_task_node = runnable_tasks[0]
                    current_subtask_id = current_task_node.id
                    self._task.task_graph.update_task(
                        current_task_node.id, status=TaskNodeStatus.IN_PROGRESS
                    )
                    await self._emit(
                        EventType.TASK_STARTED,
                        {"task_id": current_task_node.id, "title": current_task_node.title},
                    )

                logger.info(
                    "agent.loop.step",
                    agent_id=self._task.agent_id,
                    step=step,
                    max_steps=settings.max_agent_steps,
                )

                # Ask AI Provider for next action
                response = await self._provider.chat(
                    messages=messages,
                    tools=self._tools,
                    temperature=0.0,
                )

                # Stream AI message/token to frontend
                if response.content:
                    await self._emit(EventType.AI_TOKEN, {"token": response.content})

                # Add assistant message to context
                self._context.add_assistant_message(
                    content=response.content,
                    tool_calls=response.tool_calls if response.tool_calls else None,
                )

                # If AI wants to call tools
                if response.tool_calls:
                    self._state.transition(AgentState.OBSERVING)

                    # Execute tool calls
                    results = await self._executor.execute_tool_calls(response.tool_calls)

                    # Add tool results to context
                    for result in results:
                        self._context.add_tool_result(
                            tool_call_id=result["tool_call_id"],
                            tool_name=result.get("tool_name", "tool"),
                            result=result["content"],
                        )

                    # Track in task
                    self._task.tool_calls.extend(response.tool_calls)

                    # Track file changes and tool types
                    called_edit_tool = False
                    called_inspection_tool = False
                    called_execution_tool = False

                    for tc in response.tool_calls:
                        func = tc.get("function", {})
                        name = func.get("name", "")
                        if name in ("write_file", "edit_file", "patch_file"):
                            called_edit_tool = True
                            try:
                                args = json.loads(func.get("arguments", "{}"))
                                path = args.get("path") or args.get("file_path") or ""
                                if path and path not in self._task.files_changed:
                                    self._task.files_changed.append(path)
                                    self._context.record_file_changed(path)
                            except json.JSONDecodeError:
                                pass
                        elif name in ("list_directory", "read_file", "search_files", "git_status", "git_log"):
                            called_inspection_tool = True
                        elif name in ("terminal", "sandbox_execute"):
                            called_execution_tool = True

                    # Progress task graph based on actions taken
                    if current_subtask_id:
                        node = self._task.task_graph.get_task(current_subtask_id)
                        title_lower = (node.title if node else "").lower()
                        should_complete = False

                        if called_edit_tool:
                            should_complete = True
                        elif called_inspection_tool and any(
                            kw in title_lower for kw in ("inspect", "read", "locate", "search", "analyze", "explore")
                        ):
                            should_complete = True
                        elif called_execution_tool and any(
                            kw in title_lower for kw in ("verify", "test", "run", "check")
                        ):
                            should_complete = True

                        if should_complete:
                            self._task.task_graph.complete_task(
                                current_subtask_id, result="Action executed successfully"
                            )
                            await self._emit(
                                EventType.TASK_COMPLETED,
                                {"task_id": current_subtask_id, "title": node.title if node else "", "status": "completed"},
                            )

                    # Continue the loop
                    if self._state.can_transition(AgentState.EXECUTING):
                        self._state.transition(AgentState.EXECUTING)
                    messages = self._context.build_messages()
                    continue

                # If AI responded with text only (no tool calls):
                # If changes have already been made or no file-oriented tasks remain, complete
                has_pending_creation = not self._task.files_changed and any(
                    any(kw in t.title.lower() for kw in ("create", "edit", "write", "make", "implement", "code", "file", "build"))
                    for t in self._task.task_graph._tasks.values()
                    if t.status in (TaskNodeStatus.PENDING, TaskNodeStatus.IN_PROGRESS)
                )
                if not has_pending_creation:
                    if current_subtask_id:
                        node = self._task.task_graph.get_task(current_subtask_id)
                        self._task.task_graph.complete_task(
                            current_subtask_id, result="Finished without additional tool calls"
                        )
                        await self._emit(
                            EventType.TASK_COMPLETED,
                            {"task_id": current_subtask_id, "title": node.title if node else "", "status": "completed"},
                        )
                    break

                # AI chatted without executing pending creation/edit task — nudge it to create the file
                logger.info("agent.loop.nudge_action", agent_id=self._task.agent_id)
                self._context.add_user_message(
                    "You responded with text, but the task requires creating or modifying code. "
                    "Please proceed now to create or edit the necessary file(s) using the `write_file` or `edit_file` tool. "
                    "If a filename or details were not specified, use standard conventions (e.g. create `main.py`)."
                )
                if current_subtask_id:
                    node = self._task.task_graph.get_task(current_subtask_id)
                    title_lower = (node.title if node else "").lower()
                    if any(kw in title_lower for kw in ("inspect", "read", "locate", "search", "analyze")):
                        self._task.task_graph.complete_task(current_subtask_id, result="Inspection completed")
                        await self._emit(
                            EventType.TASK_COMPLETED,
                            {"task_id": current_subtask_id, "title": node.title if node else "", "status": "completed"},
                        )
                messages = self._context.build_messages()

            # Mark all remaining tasks completed if not failed, and emit TASK_COMPLETED so UI updates
            for t in self._task.task_graph._tasks.values():
                if t.status in (TaskNodeStatus.PENDING, TaskNodeStatus.IN_PROGRESS):
                    t.status = TaskNodeStatus.COMPLETED
                    t.completed_at = datetime.now(UTC)
                    await self._emit(
                        EventType.TASK_COMPLETED,
                        {"task_id": t.id, "title": t.title, "status": "completed"},
                    )

            # Step 4: Verification Loop
            if self._task.files_changed and not self._stopped:
                verification = await self._run_verification_loop(max_retries=MAX_REPAIR_ATTEMPTS)

                if not verification.success:
                    self._state.transition(AgentState.FAILED)
                    self._task.status = TaskStatus.FAILED
                    self._task.error = f"Verification failed: {verification.error_summary[:500]}"
                    if self._checkpoint:
                        await checkpoint_manager.rollback(self._checkpoint)
                    await self._emit(EventType.AGENT_FAILED, {"error": self._task.error})
                    await self._emit(EventType.AGENT_ERROR, {"error": self._task.error})
                    return self._task

            # Complete or Cancelled
            if not self._stopped:
                if self._state.can_transition(AgentState.VERIFYING):
                    self._state.transition(AgentState.VERIFYING)
                self._state.transition(AgentState.COMPLETED)
                self._task.status = TaskStatus.COMPLETED
                local_url = None
                try:
                    from src.terminal.web_server import ensure_project_web_server
                    server_info = await ensure_project_web_server(self._task.project_path)
                    if server_info:
                        local_url = server_info.get("url")
                except Exception:
                    pass

                await self._emit(EventType.AGENT_COMPLETED, {
                    "files_changed": self._task.files_changed,
                    "steps": self._task.steps_completed,
                    "task_graph": self._task.task_graph.to_dict(),
                    "change_id": self._change_set.change_id if self._change_set else None,
                    "local_url": local_url,
                })
            else:
                if self._state.can_transition(AgentState.CANCELLED):
                    self._state.transition(AgentState.CANCELLED)
                elif self._state.can_transition(AgentState.STOPPED):
                    self._state.transition(AgentState.STOPPED)
                self._task.status = TaskStatus.CANCELLED
                self._task.completed_at = datetime.now(UTC)
                await self._emit(EventType.AGENT_STOPPED, {})

            return self._task

        except Exception as exc:
            logger.error("agent.loop.error", agent_id=self._task.agent_id, error=str(exc))
            self._task.status = TaskStatus.FAILED
            self._task.error = str(exc)
            self._task.completed_at = datetime.now(UTC)
            if self._checkpoint:
                try:
                    await checkpoint_manager.rollback(self._checkpoint)
                except Exception:
                    pass
            await self._emit(EventType.AGENT_FAILED, {"error": str(exc)})
            await self._emit(EventType.AGENT_ERROR, {"error": str(exc)})
            return self._task

        finally:
            clear_active_task_graph(self._task.agent_id)

    async def _run_verification_loop(self, max_retries: int = MAX_REPAIR_ATTEMPTS) -> VerificationResult:
        """
        Run verification and attempt fixes if it fails.
        Error recovery loop: VERIFYING → ANALYZING_ERROR → FIXING → VERIFYING
        """
        last_result = VerificationResult(
            success=False,
            command="",
            exit_code=-1,
            stdout="",
            stderr="No verification executed",
        )

        for attempt in range(max_retries):
            if self._state.can_transition(AgentState.VERIFYING):
                self._state.transition(AgentState.VERIFYING)

            await self._emit(EventType.VERIFICATION_STARTED, {"attempt": attempt + 1})

            result = await run_verification(
                project_path=self._task.project_path,
                agent_id=self._task.agent_id,
            )
            last_result = result

            self._task.execution_results.append({
                "attempt": attempt + 1,
                "success": result.success,
                "exit_code": result.exit_code,
                "command": result.command,
            })

            if result.success:
                await self._emit(EventType.VERIFICATION_PASSED, {"attempt": attempt + 1})
                return result

            await self._emit(EventType.VERIFICATION_FAILED, {
                "attempt": attempt + 1,
                "error_summary": result.error_summary[:500],
            })

            # Don't retry on the last attempt
            if attempt >= max_retries - 1:
                return result

            # Error recovery: ask AI provider to fix
            logger.info(
                "agent.loop.fixing",
                agent_id=self._task.agent_id,
                attempt=attempt + 1,
            )

            if self._state.can_transition(AgentState.ANALYZING_ERROR):
                self._state.transition(AgentState.ANALYZING_ERROR)

            error_prompt = build_error_analysis(
                error_output=result.error_summary,
                command=result.command,
                exit_code=result.exit_code,
            )
            self._context.add_user_message(error_prompt)

            if self._state.can_transition(AgentState.FIXING):
                self._state.transition(AgentState.FIXING)

            messages = self._context.build_messages()
            fix_response = await self._provider.chat(
                messages=messages,
                tools=self._tools,
                temperature=0.0,
            )

            self._context.add_assistant_message(
                content=fix_response.content,
                tool_calls=fix_response.tool_calls if fix_response.tool_calls else None,
            )

            # Execute fix tool calls
            if fix_response.tool_calls:
                results = await self._executor.execute_tool_calls(fix_response.tool_calls)
                for r in results:
                    self._context.add_tool_result(
                        tool_call_id=r["tool_call_id"],
                        tool_name=r.get("tool_name", "fix"),
                        result=r["content"],
                    )

        return last_result

    def stop(self) -> None:
        """Signal the agent to stop."""
        self._stopped = True

    async def _emit(self, event_type: EventType, data: dict[str, Any]) -> None:
        """Emit an event to the IDE."""
        await event_bus.emit(CoreMindEvent(
            type=event_type,
            agent_id=self._task.agent_id,
            session_id=self._task.session_id,
            data=data,
        ))
