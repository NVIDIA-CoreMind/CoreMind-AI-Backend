"""
CoreMind Backend — Agent Loop.

The main execution loop that orchestrates:
    Understand → Inspect Context → Create Plan → Execute Task →
    Observe Result → Verify → Fix → Re-verify → Complete

This is the brain of CoreMind.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from src.agent.checkpoint import Checkpoint, checkpoint_manager
from src.agent.executor import AgentExecutor
from src.agent.planner import generate_task_graph
from src.project.project_manager import project_manager
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

ENTRYPOINT_KEYWORDS = ("entrypoint", "wire", "connect", "main")
ENTRYPOINT_FILENAMES = (
    "main.dart", "main.py", "app.py", "App.tsx", "App.jsx",
    "main.tsx", "main.jsx", "index.ts", "index.js", "index.html",
    "main.go", "main.rs", "page.tsx",
)


class AgentLoop:
    """The main agent execution engine."""

    def __init__(self, task: AgentTask) -> None:
        self._task = task
        self._state = StateMachine(task.agent_id)
        self._context = ContextManager(task.project_path)
        self._executor = AgentExecutor(
            task.project_path,
            task.agent_id,
            session_id=task.session_id,
            task_id=task.task_id,
        )
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
            await self._set_task_status(TaskStatus.ANALYZING)

            # Step 1: Understand & Analyze Context
            self._state.transition(AgentState.ANALYZING)
            await self._emit(EventType.AGENT_THINKING, {"phase": "analyzing"})

            # Load conversation history from prior tasks in same session if available
            try:
                from src.agent.storage import task_storage
                prior_history = task_storage.get_conversation_history(self._task.session_id)
                if prior_history:
                    for msg in prior_history:
                        if msg.get("role") == "user":
                            self._context.add_user_message(msg.get("content", ""))
                        elif msg.get("role") == "assistant":
                            self._context.add_assistant_message(msg.get("content"), msg.get("tool_calls"))
            except Exception as hist_err:
                logger.debug("agent.loop.prior_history_load_err", error=str(hist_err))

            # Step 2: Create Structured Plan
            await self._set_task_status(TaskStatus.PLANNING)
            self._state.transition(AgentState.PLANNING)
            await self._emit(EventType.AGENT_PLANNING, {"phase": "planning"})

            # Generate structured task graph
            try:
                project_info = project_manager.get_project(self._task.project_path) or {}
                repo_summary = ""
                try:
                    repo_summary = self._context._repo_map.build_compact_summary(max_chars=2000)
                except Exception:
                    pass
                proj_ctx = (
                    f"Project root: {self._task.project_path}\n"
                    f"Language: {project_info.get('language', 'unknown')}\n"
                    f"Framework: {project_info.get('framework', 'unknown')}\n"
                    f"{repo_summary}"
                )
                task_graph = await generate_task_graph(
                    task=self._task.task,
                    project_context=proj_ctx,
                )
                self._task.task_graph = task_graph
                set_active_task_graph(self._task.agent_id, self._task.task_graph)
                task_nodes = task_graph.to_dict()["tasks"]
                await self._emit(
                    EventType.PLAN_CREATED,
                    {
                        "goal": task_graph.goal,
                        "nodes": task_nodes,
                        "tasks": task_nodes,
                        "task_graph": task_graph.to_dict(),
                    },
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

            await self._set_task_status(TaskStatus.EXECUTING)
            self._state.transition(AgentState.EXECUTING)
            step = 0
            nudge_count = 0
            last_tool_signatures: list[str] = []
            consecutive_duplicate_turns = 0

            while step < settings.max_agent_steps and not self._stopped:
                step += 1
                self._task.steps_completed = step

                # Track active subtask: prioritize existing in_progress, else next runnable
                in_progress_nodes = [
                    t for t in self._task.task_graph._tasks.values()
                    if t.status == TaskNodeStatus.IN_PROGRESS
                ]
                current_task_node = in_progress_nodes[0] if in_progress_nodes else None
                if not current_task_node:
                    runnable_tasks = self._task.task_graph.get_runnable_tasks()
                    if runnable_tasks:
                        current_task_node = runnable_tasks[0]
                        self._task.task_graph.update_task(
                            current_task_node.id, status=TaskNodeStatus.IN_PROGRESS
                        )
                        await self._emit(
                            EventType.TASK_STARTED,
                            {"task_id": current_task_node.id, "title": current_task_node.title},
                        )

                current_subtask_id = current_task_node.id if current_task_node else ""

                logger.info(
                    "agent.loop.step",
                    agent_id=self._task.agent_id,
                    step=step,
                    max_steps=settings.max_agent_steps,
                )

                # Emit real thinking event before consulting model
                await self._emit(
                    EventType.AGENT_THINKING,
                    {"phase": "inference", "step": step, "max_steps": settings.max_agent_steps},
                )

                if self._stopped:
                    break

                # Ask AI Provider for next action
                response = await self._provider.chat(
                    messages=messages,
                    tools=self._tools,
                    temperature=0.0,
                )

                if self._stopped:
                    break

                # Emit token streaming / usage events to frontend
                if response.usage:
                    await self._emit(EventType.AI_USAGE, response.usage)

                if response.content or response.usage:
                    token_payload: dict[str, Any] = {"token": response.content or ""}
                    if response.usage:
                        token_payload.update(response.usage)
                    await self._emit(EventType.AI_TOKEN, token_payload)

                if response.content:
                    self._task.response = response.content

                # Add assistant message to context
                self._context.add_assistant_message(
                    content=response.content,
                    tool_calls=response.tool_calls if response.tool_calls else None,
                )

                # If AI wants to call tools
                if response.tool_calls:
                    # Prevent duplicate tool execution loops
                    current_signatures = [
                        f"{tc.get('function', {}).get('name', '')}:{tc.get('function', {}).get('arguments', '')}"
                        for tc in response.tool_calls
                    ]
                    if current_signatures == last_tool_signatures:
                        consecutive_duplicate_turns += 1
                    else:
                        consecutive_duplicate_turns = 0
                        last_tool_signatures = current_signatures

                    if consecutive_duplicate_turns >= 1:
                        logger.warn(
                            "agent.loop.duplicate_tool_loop_prevented",
                            agent_id=self._task.agent_id,
                            tools=current_signatures,
                            turns=consecutive_duplicate_turns,
                        )
                        if consecutive_duplicate_turns >= 3:
                            logger.warn(
                                "agent.loop.duplicate_tool_loop_halting",
                                agent_id=self._task.agent_id,
                            )
                            break

                        for tc in response.tool_calls:
                            self._context.add_tool_result(
                                tool_call_id=tc.get("id") or "call_dup",
                                tool_name=tc.get("function", {}).get("name", "tool"),
                                result=json.dumps({
                                    "notice": "Duplicate tool call detected with identical arguments. This action was already completed. Do NOT repeat it or re-read it. Proceed to create the next file, write the main entrypoint (e.g. main.dart), or run verification."
                                }),
                            )
                        messages = self._context.build_messages()
                        continue

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

                    # Track file changes ONLY when tool execution confirms disk modification
                    called_edit_tool = False
                    called_inspection_tool = False
                    called_execution_tool = False

                    for res in results:
                        tool_nm = res.get("tool_name", "")
                        try:
                            inner_res = json.loads(res.get("content", "{}"))
                        except Exception:
                            inner_res = {}

                        if "error" not in inner_res and inner_res.get("verified_on_disk", False):
                            f_path = inner_res.get("path") or inner_res.get("project_dir") or ""
                            if f_path and f_path not in self._task.files_changed:
                                self._task.files_changed.append(f_path)
                                self._context.record_file_changed(f_path)
                                called_edit_tool = True

                        if tool_nm in ("list_directory", "list_files", "read_file", "search_files", "search_code", "git_status", "git_log", "inspect_git", "get_diagnostics", "web_search", "flutter_check_env"):
                            called_inspection_tool = True
                        elif tool_nm in ("terminal", "run_terminal", "sandbox_execute", "run_tests", "run_build", "flutter_create_project"):
                            called_execution_tool = True

                    # Check whether an entrypoint file was modified/created on disk
                    has_entrypoint_edited = any(
                        any(f.endswith(ep) for ep in ENTRYPOINT_FILENAMES)
                        for f in self._task.files_changed
                    )

                    # Progress task graph based on actions taken
                    if current_subtask_id:
                        node = self._task.task_graph.get_task(current_subtask_id)
                        title_lower = (node.title if node else "").lower()
                        should_complete = False

                        is_entrypoint_node = any(kw in title_lower for kw in ENTRYPOINT_KEYWORDS)
                        is_scaffold_node = any(kw in title_lower for kw in ("scaffold", "architecture", "directory", "structure", "folder", "manifest"))
                        is_inspect_node = any(kw in title_lower for kw in ("inspect", "read", "locate", "search", "explore", "examine", "find", "check")) or ("analyze" in title_lower and not any(kw in title_lower for kw in ("verify", "test", "lint")))
                        is_verify_node = any(kw in title_lower for kw in ("verify", "test", "lint")) and not is_inspect_node

                        if is_entrypoint_node:
                            # Entrypoint task ONLY completes if an actual entrypoint file was modified/created
                            if has_entrypoint_edited:
                                should_complete = True
                        elif is_scaffold_node:
                            if called_execution_tool or called_edit_tool:
                                should_complete = True
                        elif is_inspect_node:
                            if called_inspection_tool or called_edit_tool:
                                should_complete = True
                        elif is_verify_node:
                            if called_execution_tool:
                                should_complete = True
                        elif called_edit_tool:
                            # Complete active component/model/service task on code edit
                            should_complete = True
                        elif called_execution_tool and any(
                            kw in title_lower for kw in ("run", "build", "setup", "create", "init", "install", "command", "exec", "start", "config")
                        ):
                            should_complete = True

                        if should_complete and node and node.status == TaskNodeStatus.IN_PROGRESS:
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
                if response.content:
                    self._task.response = response.content

                has_entrypoint_edited = any(
                    any(f.endswith(ep) for ep in ENTRYPOINT_FILENAMES)
                    for f in self._task.files_changed
                )

                # Complete current subtask if in progress (unless it is an unwritten entrypoint task)
                if current_subtask_id:
                    node = self._task.task_graph.get_task(current_subtask_id)
                    is_entry_node = any(kw in (node.title if node else "").lower() for kw in ENTRYPOINT_KEYWORDS)
                    if node and node.status == TaskNodeStatus.IN_PROGRESS:
                        if not (is_entry_node and not has_entrypoint_edited):
                            self._task.task_graph.complete_task(
                                current_subtask_id, result=response.content or "Completed subtask"
                            )
                            await self._emit(
                                EventType.TASK_COMPLETED,
                                {"task_id": current_subtask_id, "title": node.title if node else "", "status": "completed"},
                            )

                pending_subtasks = [
                    t for t in self._task.task_graph._tasks.values()
                    if t.status in (TaskNodeStatus.PENDING, TaskNodeStatus.IN_PROGRESS)
                ]

                # Check if there are remaining pending action/implementation subtasks
                action_kws = (
                    "create", "edit", "write", "modify", "implement", "build", "patch", "fix", "add", "scaffold", "wire", "setup", "connect", "entrypoint"
                )
                pending_action_tasks = [
                    t for t in pending_subtasks
                    if any(kw in t.title.lower() for kw in action_kws)
                ]

                # Check if an entrypoint task was planned in the graph but has not yet been edited on disk
                entrypoint_tasks_planned = [
                    t for t in self._task.task_graph._tasks.values()
                    if any(kw in t.title.lower() for kw in ENTRYPOINT_KEYWORDS)
                ]
                needs_entrypoint_write = bool(entrypoint_tasks_planned) and not has_entrypoint_edited

                # If all action tasks are completed AND entrypoint requirement is satisfied, proceed to verification loop
                if not pending_action_tasks and not needs_entrypoint_write:
                    break

                # If there are still pending action tasks or missing entrypoint, guide the agent to proceed
                if nudge_count < 8:
                    nudge_count += 1
                    if needs_entrypoint_write:
                        entry_node = entrypoint_tasks_planned[0]
                        if entry_node.status != TaskNodeStatus.IN_PROGRESS:
                            self._task.task_graph.update_task(entry_node.id, status=TaskNodeStatus.IN_PROGRESS)
                        logger.info(
                            "agent.loop.nudge_missing_entrypoint",
                            agent_id=self._task.agent_id,
                            nudge_count=nudge_count,
                            entrypoint_task=entry_node.title,
                        )
                        self._context.add_user_message(
                            "CRITICAL STEP: The primary application entrypoint (e.g. `lib/main.dart`, `src/App.tsx`, or `main.py`) "
                            "has NOT been written or replaced yet. CLI tools only generate placeholder templates. "
                            "You MUST use `write_file` to write the complete application entrypoint file connecting your models, "
                            "services, and screens into a working application now before proceeding."
                        )
                    else:
                        next_node = pending_action_tasks[0]
                        logger.info(
                            "agent.loop.nudge_next_subtask",
                            agent_id=self._task.agent_id,
                            nudge_count=nudge_count,
                            next_subtask=next_node.title,
                        )
                        self._context.add_user_message(
                            f"Great progress. Now please proceed to the next planned task:\n"
                            f"- Task [{next_node.id}]: {next_node.title}\n"
                            f"{f'- Details: {next_node.description}' if next_node.description else ''}\n"
                            f"Please execute the necessary actions now using tools (`write_file`, `create_file`, `edit_file`, or `terminal`). Continue until all tasks are fully accomplished."
                        )
                    messages = self._context.build_messages()
                    continue

                # If maximum nudges reached, exit execution loop
                break

            # Mark all remaining tasks completed if not failed, and emit TASK_COMPLETED so UI updates
            if not self._stopped:
                has_entrypoint_edited = any(
                    any(f.endswith(ep) for ep in ENTRYPOINT_FILENAMES)
                    for f in self._task.files_changed
                )
                for t in self._task.task_graph._tasks.values():
                    if t.status in (TaskNodeStatus.PENDING, TaskNodeStatus.IN_PROGRESS):
                        is_entry = any(kw in t.title.lower() for kw in ENTRYPOINT_KEYWORDS)
                        if is_entry and not has_entrypoint_edited:
                            t.status = TaskNodeStatus.FAILED
                            t.error = "Entrypoint file was not created or modified before agent terminated"
                            await self._emit(
                                EventType.TASK_FAILED,
                                {"task_id": t.id, "title": t.title, "error": t.error},
                            )
                        else:
                            t.status = TaskNodeStatus.COMPLETED
                            t.completed_at = datetime.now(UTC)
                            await self._emit(
                                EventType.TASK_COMPLETED,
                                {"task_id": t.id, "title": t.title, "status": "completed"},
                            )

            # Step 4: Verification Loop
            if self._task.files_changed and not self._stopped:
                await self._set_task_status(TaskStatus.TESTING)
                verification = await self._run_verification_loop(max_retries=MAX_REPAIR_ATTEMPTS)

                if not verification.success:
                    self._state.transition(AgentState.FAILED)
                    self._task.error = f"Verification failed: {verification.error_summary[:500]}"
                    # Do not rollback files: preserve disk modifications for review
                    await self._set_task_status(TaskStatus.FAILED)
                    await self._emit(EventType.AGENT_FAILED, {
                        "error": self._task.error,
                        "files_changed": self._task.files_changed,
                        "verification": {
                            "command": verification.command,
                            "exit_code": verification.exit_code,
                            "error_summary": verification.error_summary,
                        },
                    })
                    await self._emit(EventType.AGENT_ERROR, {"error": self._task.error})
                    return self._task

            # Complete or Cancelled
            self._task.messages = list(self._context._conversation)
            if not self._stopped:
                if self._state.can_transition(AgentState.VERIFYING):
                    self._state.transition(AgentState.VERIFYING)
                self._state.transition(AgentState.COMPLETED)
                await self._set_task_status(TaskStatus.COMPLETED)
                local_url = None
                try:
                    from src.terminal.web_server import ensure_project_web_server
                    server_info = await ensure_project_web_server(self._task.project_path)
                    if server_info:
                        local_url = server_info.get("url")
                except Exception:
                    pass

                # Populate truthful final response
                clean_done = "Agent task completed successfully."
                if not self._task.response or self._task.response.strip() == clean_done:
                    for m in reversed(self._context._conversation):
                        if m.get("role") == "assistant" and m.get("content"):
                            self._task.response = m.get("content")
                            break

                actions_summary: list[str] = []
                if self._task.files_changed:
                    chg_str = ", ".join(self._task.files_changed)
                    actions_summary.append(f"Modified files ({len(self._task.files_changed)}): {chg_str}")
                if self._task.tool_calls:
                    actions_summary.append(f"Tool operations: {len(self._task.tool_calls)}")
                if self._task.execution_results:
                    last_exec = self._task.execution_results[-1]
                    if last_exec.get("success"):
                        actions_summary.append(f"Verification passed: `{last_exec.get('command')}`")

                if not self._task.response:
                    if actions_summary:
                        formatted = "\n".join(f"- {a}" for a in actions_summary)
                        self._task.response = f"Task execution completed:\n{formatted}"
                    else:
                        self._task.response = "Agent task completed successfully."

                await self._emit(EventType.AGENT_COMPLETED, {
                    "files_changed": self._task.files_changed,
                    "steps": self._task.steps_completed,
                    "task_graph": self._task.task_graph.to_dict(),
                    "change_id": self._change_set.change_id if self._change_set else None,
                    "local_url": local_url,
                    "response": self._task.response,
                })
            else:
                if self._state.can_transition(AgentState.CANCELLED):
                    self._state.transition(AgentState.CANCELLED)
                elif self._state.can_transition(AgentState.STOPPED):
                    self._state.transition(AgentState.STOPPED)
                self._task.completed_at = datetime.now(UTC)
                await self._set_task_status(TaskStatus.CANCELLED)
                await self._emit(EventType.AGENT_STOPPED, {
                    "reason": "Task was stopped by user request",
                    "files_changed": self._task.files_changed,
                })

            return self._task

        except asyncio.CancelledError:
            logger.info("agent.loop.cancelled", agent_id=self._task.agent_id)
            self._stopped = True
            if self._state.can_transition(AgentState.CANCELLED):
                self._state.transition(AgentState.CANCELLED)
            elif self._state.can_transition(AgentState.STOPPED):
                self._state.transition(AgentState.STOPPED)
            self._task.completed_at = datetime.now(UTC)
            await self._set_task_status(TaskStatus.CANCELLED)
            await self._emit(EventType.AGENT_STOPPED, {
                "reason": "Task was cancelled",
                "files_changed": self._task.files_changed,
            })
            return self._task

        except Exception as exc:
            logger.error("agent.loop.error", agent_id=self._task.agent_id, error=str(exc))
            self._task.error = str(exc)
            self._task.completed_at = datetime.now(UTC)
            self._task.messages = list(self._context._conversation)
            if self._checkpoint:
                try:
                    await checkpoint_manager.rollback(self._checkpoint)
                except Exception:
                    pass
            if self._state.can_transition(AgentState.FAILED):
                self._state.transition(AgentState.FAILED)
            await self._set_task_status(TaskStatus.FAILED)
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

                # Track any files changed during repair that are confirmed on disk
                for r in results:
                    try:
                        inner_r = json.loads(r.get("content", "{}"))
                    except Exception:
                        inner_r = {}
                    if "error" not in inner_r and inner_r.get("verified_on_disk", False):
                        f_path = inner_r.get("path") or ""
                        if f_path and f_path not in self._task.files_changed:
                            self._task.files_changed.append(f_path)
                            self._context.record_file_changed(f_path)

        return last_result

    async def _set_task_status(self, new_status: TaskStatus) -> None:
        """Update task status, emit event, and persist to SQLite."""
        self._task.status = new_status
        await self._emit(EventType.TASK_STATUS, {
            "status": new_status.value,
            "task_id": self._task.task_id,
            "agent_id": self._task.agent_id,
        })
        try:
            from src.agent.storage import task_storage
            task_storage.save_task(self._task.to_dict())
        except Exception as e:
            logger.warn("agent.loop.save_task_warn", error=str(e))

    def stop(self) -> None:
        """Signal the agent to stop."""
        self._stopped = True

    async def _emit(self, event_type: EventType, data: dict[str, Any]) -> None:
        """Emit an event to the IDE."""
        await event_bus.emit(CoreMindEvent(
            type=event_type,
            agent_id=self._task.agent_id,
            task_id=self._task.task_id,
            session_id=self._task.session_id,
            data=data,
        ))
