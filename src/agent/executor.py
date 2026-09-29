"""
CoreMind Backend — Agent Executor.

Executes tool calls from Nemotron's responses, handling permissions,
approvals, and result collection.
"""

from __future__ import annotations

import json
from typing import Any

from src.events.event_bus import event_bus
from src.events.events import CoreMindEvent, EventType
from src.security.approval_manager import approval_manager
from src.security.command_policy import validate_command
from src.security.permissions import requires_approval
from src.tools.executor import ToolExecutor
from src.tools.registry import tool_registry
from src.utils.logger import logger


class AgentExecutor:
    """Executes tool calls on behalf of the agent."""

    def __init__(self, project_path: str, agent_id: str) -> None:
        self._project_path = project_path
        self._agent_id = agent_id
        self._tool_executor = ToolExecutor()

    async def execute_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Execute a batch of tool calls from Nemotron.

        Returns a list of tool results (one per call).
        """
        results: list[dict[str, Any]] = []

        for tc in tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            tool_call_id = tc.get("id", "")

            # Emit tool started event
            await event_bus.emit(CoreMindEvent(
                type=EventType.TOOL_STARTED,
                agent_id=self._agent_id,
                data={"tool": tool_name, "tool_call_id": tool_call_id},
            ))

            try:
                # Check if command tools need validation
                if tool_name in ("terminal", "sandbox_execute"):
                    args = json.loads(func.get("arguments", "{}"))
                    command = args.get("command", "")
                    validate_command(command)

                # Check if tool requires approval
                tool_def = tool_registry.get(tool_name)
                if requires_approval(tool_def.permission):
                    args = json.loads(func.get("arguments", "{}"))
                    approval = await approval_manager.request_approval(
                        agent_id=self._agent_id,
                        tool_name=tool_name,
                        args=args,
                        description=f"Execute {tool_name} with args: {json.dumps(args)[:200]}",
                    )
                    approved = await approval_manager.wait_for_decision(approval)
                    if not approved:
                        denied_msg = (
                            f"Tool '{tool_name}' was denied"
                            f" by user: {approval.deny_reason}"
                        )
                        results.append({
                            "tool_call_id": tool_call_id,
                            "content": denied_msg,
                        })
                        continue

                # Execute the tool
                result = await self._tool_executor.execute_tool_call(
                    tool_call=tc,
                    project_path=self._project_path,
                    agent_id=self._agent_id,
                )

                # Track file changes
                if tool_name in ("write_file", "edit_file"):
                    inner = result.get("result", {})
                    path = inner.get("path", "")
                    if path:
                        await event_bus.emit(CoreMindEvent(
                            type=EventType.FILE_CHANGED,
                            agent_id=self._agent_id,
                            data={"file": path, "action": inner.get("action", "modified")},
                        ))

                # Emit tool completed event
                await event_bus.emit(CoreMindEvent(
                    type=EventType.TOOL_COMPLETED,
                    agent_id=self._agent_id,
                    data={"tool": tool_name, "success": True},
                ))

                results.append({
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(result.get("result", {})),
                })

            except Exception as exc:
                logger.error(
                    "agent.executor.tool_error",
                    tool=tool_name,
                    error=str(exc),
                )

                await event_bus.emit(CoreMindEvent(
                    type=EventType.TOOL_COMPLETED,
                    agent_id=self._agent_id,
                    data={"tool": tool_name, "success": False, "error": str(exc)},
                ))

                results.append({
                    "tool_call_id": tool_call_id,
                    "content": json.dumps({"error": str(exc)}),
                })

        return results
