"""
CoreMind Backend — Agent Loop.

The main execution loop that orchestrates:
    Task → Analyze → Plan → Execute → Observe → Verify → Fix → Complete

This is the brain of CoreMind.
"""

from __future__ import annotations

import json
from typing import Any

from src.agent.executor import AgentExecutor
from src.agent.state_machine import AgentState, StateMachine
from src.agent.task import AgentTask, TaskStatus
from src.agent.verifier import VerificationResult, run_verification
from src.ai.prompts.coding import build_error_analysis
from src.ai.provider import get_ai_provider
from src.config import settings
from src.context.context_manager import ContextManager
from src.events.event_bus import event_bus
from src.events.events import CoreMindEvent, EventType
from src.tools.registry import tool_registry
from src.utils.logger import logger


class AgentLoop:
    """The main agent execution loop."""

    def __init__(self, task: AgentTask) -> None:
        self._task = task
        self._state = StateMachine(task.agent_id)
        self._context = ContextManager(task.project_path)
        self._executor = AgentExecutor(task.project_path, task.agent_id)
        self._provider = get_ai_provider()
        self._tools = tool_registry.to_openai_tools()
        self._stopped = False

    async def run(self) -> AgentTask:
        """
        Execute the full agent loop.

        Returns the completed task with all results.
        """
        try:
            await self._emit(EventType.AGENT_STARTED, {"task": self._task.task[:200]})
            self._task.status = TaskStatus.RUNNING

            # Step 1: Analyze
            self._state.transition(AgentState.ANALYZING)
            await self._emit(EventType.AGENT_THINKING, {"phase": "analyzing"})

            # Step 2: Plan + Execute loop
            self._state.transition(AgentState.PLANNING)
            await self._emit(EventType.AGENT_PLANNING, {"phase": "planning"})

            # Build initial context with user task
            messages = self._context.build_messages(user_task=self._task.task)

            # Step 3: Main loop — ask Nemotron, execute tools, repeat
            self._state.transition(AgentState.EXECUTING)
            step = 0

            while step < settings.max_agent_steps and not self._stopped:
                step += 1
                self._task.steps_completed = step

                logger.info(
                    "agent.loop.step",
                    agent_id=self._task.agent_id,
                    step=step,
                    max_steps=settings.max_agent_steps,
                )

                # Ask Nemotron for next action
                response = await self._provider.chat(
                    messages=messages,
                    tools=self._tools,
                    temperature=0.0,
                )

                # Add assistant message to context
                self._context.add_assistant_message(
                    content=response.content,
                    tool_calls=response.tool_calls if response.tool_calls else None,
                )

                # If Nemotron wants to call tools
                if response.tool_calls:
                    self._state.transition(AgentState.OBSERVING)

                    # Execute tool calls
                    results = await self._executor.execute_tool_calls(response.tool_calls)

                    # Add tool results to context
                    for result in results:
                        self._context.add_tool_result(
                            tool_call_id=result["tool_call_id"],
                            tool_name="tool",
                            result=result["content"],
                        )

                    # Track in task
                    self._task.tool_calls.extend(response.tool_calls)

                    # Track file changes
                    for tc in response.tool_calls:
                        func = tc.get("function", {})
                        name = func.get("name", "")
                        if name in ("write_file", "edit_file"):
                            try:
                                args = json.loads(func.get("arguments", "{}"))
                                path = args.get("path", "")
                                if path and path not in self._task.files_changed:
                                    self._task.files_changed.append(path)
                                    self._context.record_file_changed(path)
                            except json.JSONDecodeError:
                                pass

                    # Continue the loop
                    if self._state.can_transition(AgentState.EXECUTING):
                        self._state.transition(AgentState.EXECUTING)
                    messages = self._context.build_messages()
                    continue

                # If Nemotron responded with text only (no tool calls), it's done
                if response.finish_reason == "stop":
                    break

                messages = self._context.build_messages()

            # Step 4: Verification
            if self._task.files_changed and not self._stopped:
                verification = await self._run_verification_loop()

                if not verification.success:
                    self._state.transition(AgentState.FAILED)
                    self._task.status = TaskStatus.FAILED
                    self._task.error = f"Verification failed: {verification.error_summary[:500]}"
                    await self._emit(EventType.AGENT_ERROR, {"error": self._task.error})
                    return self._task

            # Complete
            if not self._stopped:
                self._state.transition(AgentState.VERIFYING)
                self._state.transition(AgentState.COMPLETED)
                self._task.status = TaskStatus.COMPLETED
                await self._emit(EventType.AGENT_COMPLETED, {
                    "files_changed": self._task.files_changed,
                    "steps": self._task.steps_completed,
                })
            else:
                self._task.status = TaskStatus.CANCELLED
                await self._emit(EventType.AGENT_STOPPED, {})

            return self._task

        except Exception as exc:
            logger.error("agent.loop.error", agent_id=self._task.agent_id, error=str(exc))
            self._task.status = TaskStatus.FAILED
            self._task.error = str(exc)
            await self._emit(EventType.AGENT_ERROR, {"error": str(exc)})
            return self._task

    async def _run_verification_loop(self, max_retries: int = 3) -> VerificationResult:
        """
        Run verification and attempt fixes if it fails.

        This is the error recovery loop:
        VERIFYING → ANALYZING_ERROR → FIXING → VERIFYING
        """
        for attempt in range(max_retries):
            if self._state.can_transition(AgentState.VERIFYING):
                self._state.transition(AgentState.VERIFYING)

            await self._emit(EventType.TEST_STARTED, {"attempt": attempt + 1})

            result = await run_verification(
                project_path=self._task.project_path,
                agent_id=self._task.agent_id,
            )

            self._task.execution_results.append({
                "attempt": attempt + 1,
                "success": result.success,
                "exit_code": result.exit_code,
                "command": result.command,
            })

            if result.success:
                await self._emit(EventType.TEST_PASSED, {"attempt": attempt + 1})
                return result

            await self._emit(EventType.TEST_FAILED, {
                "attempt": attempt + 1,
                "error_summary": result.error_summary[:500],
            })

            # Don't retry on the last attempt
            if attempt >= max_retries - 1:
                return result

            # Error recovery: ask Nemotron to fix
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

            # Ask Nemotron to fix the error
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
                        tool_name="fix",
                        result=r["content"],
                    )

        return result  # type: ignore[possibly-undefined]

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
