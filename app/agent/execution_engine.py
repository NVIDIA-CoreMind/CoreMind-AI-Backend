import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from app.config import settings
from app.agent.state_machine import AgentPhase, AgentStateMachine
from app.agent.system_prompt import build_system_prompt
from app.providers.nebius_client import NebiusClient, default_nebius_client
from app.tools.registry import ToolRegistry, default_tool_registry

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Autonomous multi-turn engineering loop powered by Nebius and NVIDIA open-source models."""

    def __init__(
        self,
        nebius_client: NebiusClient = default_nebius_client,
        tool_registry: ToolRegistry = default_tool_registry,
    ):
        self.nebius_client = nebius_client
        self.tool_registry = tool_registry

    async def run_agent_loop(
        self,
        task: str,
        workspace_path: str | Path,
        model: Optional[str] = None,
        max_iterations: Optional[int] = None,
        max_debug_retries: Optional[int] = None,
        extra_context: Optional[str] = None,
        on_event: Optional[Callable[[str, Any], None]] = None,
    ) -> Dict[str, Any]:
        target_model = model or settings.nebius.default_model
        limit_iterations = max_iterations or settings.agent.max_iterations
        limit_debug_retries = max_debug_retries or settings.agent.max_debug_retries
        resolved_workspace = Path(workspace_path).resolve()

        def emit(event_type: str, payload: Any):
            if on_event:
                try:
                    on_event(event_type, payload)
                except Exception as e:
                    logger.error(f"[ExecutionEngine] Error in on_event handler: {e}")

        # Initialize State Machine
        state_machine = AgentStateMachine(
            max_debug_retries=limit_debug_retries,
            on_phase_change=lambda f, t, r: emit(
                "phase_change", {"from": f.value, "to": t.value, "reason": r}
            ),
        )

        # Emit initial TASK phase
        emit(
            "phase_change",
            {"from": "INITIALIZING", "to": AgentPhase.TASK.value, "reason": "Starting task evaluation"},
        )

        system_prompt = build_system_prompt(str(resolved_workspace), extra_context)
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Target Task:\n{task}\n\nPlease proceed following the 7-step loop: TASK -> PLAN -> CODE -> RUN -> TEST -> DEBUG / FIX -> VERIFY.",
            },
        ]

        iteration = 0
        final_summary = ""

        try:
            while iteration < limit_iterations:
                iteration += 1

                if state_machine.is_terminal():
                    break

                # Request completion from Nebius API with tools
                response = await self.nebius_client.create_chat_completion(
                    messages=messages,
                    tools=self.tool_registry.get_tools(),
                    model=target_model,
                )

                choice = response.choices[0]
                if not choice or not choice.message:
                    raise RuntimeError("Empty response received from Nebius API")

                assistant_msg = choice.message
                content = assistant_msg.content or ""

                if content:
                    state_machine.detect_and_transition_from_text(content)
                    emit(
                        "thought",
                        {
                            "content": content,
                            "phase": state_machine.get_current_phase().value,
                            "iteration": iteration,
                        },
                    )

                assistant_record: Dict[str, Any] = {
                    "role": "assistant",
                    "content": assistant_msg.content,
                }

                if assistant_msg.tool_calls:
                    assistant_record["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in assistant_msg.tool_calls
                    ]

                messages.append(assistant_record)

                # Check if turn contains no tool calls
                if not assistant_msg.tool_calls:
                    final_summary = content
                    current = state_machine.get_current_phase()
                    if (
                        current == AgentPhase.VERIFY
                        or "task completed" in content.lower()
                        or "verified successfully" in content.lower()
                    ):
                        state_machine.complete("Agent concluded task with verification")
                    break

                # Dispatch tool calls
                for tc in assistant_msg.tool_calls:
                    tool_name = tc.function.name
                    tool_args = tc.function.arguments

                    emit(
                        "tool_call",
                        {
                            "id": tc.id,
                            "name": tool_name,
                            "args": tool_args,
                            "phase": state_machine.get_current_phase().value,
                        },
                    )

                    result = await self.tool_registry.execute_tool(
                        tool_name, tool_args, resolved_workspace
                    )

                    emit(
                        "tool_result",
                        {
                            "id": tc.id,
                            "name": tool_name,
                            "success": result.success,
                            "data": result.data,
                            "error": result.error,
                        },
                    )

                    # Manage phase transitions based on tool outcomes
                    if tool_name in ("write_file", "apply_diff"):
                        if state_machine.get_current_phase() == AgentPhase.PLAN:
                            state_machine.transition_to(
                                AgentPhase.CODE, f"Modifying workspace: {tool_name}"
                            )
                        if tool_name == "apply_diff":
                            emit(
                                "diff_applied",
                                {
                                    "path": result.data.get("path") if result.data else None,
                                    "success": result.success,
                                },
                            )

                    elif tool_name == "run_sandbox_python":
                        sb_data = result.data or {}
                        emit("sandbox_output", sb_data)
                        if not result.success or sb_data.get("traceback"):
                            state_machine.transition_to(
                                AgentPhase.DEBUG, "Python execution error detected"
                            )
                        elif state_machine.get_current_phase() == AgentPhase.CODE:
                            state_machine.transition_to(
                                AgentPhase.RUN, "Script executed cleanly in sandbox"
                            )

                    elif tool_name == "run_sandbox_tests":
                        test_data = result.data or {}
                        emit("sandbox_output", test_data)
                        if (
                            not result.success
                            or test_data.get("traceback")
                            or test_data.get("exit_code") != 0
                        ):
                            state_machine.transition_to(
                                AgentPhase.DEBUG, "Test suite failures or tracebacks detected"
                            )
                        else:
                            state_machine.transition_to(
                                AgentPhase.VERIFY, "All tests passed cleanly with code 0"
                            )

                    # Append tool result back to history
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result.model_dump()),
                        }
                    )

            if iteration >= limit_iterations and not state_machine.is_terminal():
                state_machine.fail(f"Reached maximum execution limit of {limit_iterations} turns")

            final_phase = state_machine.get_current_phase()
            is_success = final_phase in (AgentPhase.COMPLETED, AgentPhase.VERIFY)

            res = {
                "success": is_success,
                "final_phase": final_phase.value,
                "iterations": iteration,
                "messages": messages,
                "summary": final_summary or f"Agent finished in phase: {final_phase.value}",
                "state_summary": state_machine.get_summary(),
            }

            emit(
                "verification",
                {
                    "success": is_success,
                    "final_phase": final_phase.value,
                    "summary": res["summary"],
                },
            )

            return res

        except Exception as exc:
            state_machine.fail(str(exc))
            emit("error", {"message": str(exc)})
            return {
                "success": False,
                "final_phase": state_machine.get_current_phase().value,
                "iterations": iteration,
                "messages": messages,
                "summary": "Agent loop aborted due to an unhandled exception",
                "state_summary": state_machine.get_summary(),
                "error": str(exc),
            }


default_execution_engine = ExecutionEngine()
