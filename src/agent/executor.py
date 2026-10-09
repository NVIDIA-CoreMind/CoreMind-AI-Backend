"""
CoreMind Backend — Agent Executor.

Executes tool calls from AI responses, handling permissions,
approvals, checkpoints, change reviews, diff emission, and automatic post-edit validation.
"""

from __future__ import annotations

import json
from typing import Any

from src.agent.checkpoint import Checkpoint, checkpoint_manager
from src.agent.verifier import run_post_edit_validation
from src.changes.diff import FileDiff
from src.changes.review import change_review_manager
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

    def __init__(
        self,
        project_path: str,
        agent_id: str,
        checkpoint: Checkpoint | None = None,
        change_set_id: str | None = None,
    ) -> None:
        self._project_path = project_path
        self._agent_id = agent_id
        self._checkpoint = checkpoint
        self._change_set_id = change_set_id
        self._tool_executor = ToolExecutor()

    def set_checkpoint(self, checkpoint: Checkpoint) -> None:
        self._checkpoint = checkpoint

    def set_change_set_id(self, change_set_id: str) -> None:
        self._change_set_id = change_set_id

    async def execute_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Execute a batch of tool calls from the AI provider.
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
                raw_args = func.get("arguments", "{}")
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {}

                # Get tool definition and canonical name
                tool_def = tool_registry.get(tool_name)
                canonical_name = tool_def.name

                # Check command validation
                if canonical_name in ("terminal", "run_terminal", "sandbox_execute", "run_tests", "run_build"):
                    command = args.get("command") or args.get("test_command") or args.get("build_command") or ""
                    if command:
                        validate_command(command)
                        await event_bus.emit(CoreMindEvent(
                            type=EventType.COMMAND_STARTED,
                            agent_id=self._agent_id,
                            data={"command": command},
                        ))

                # Checkpoint backup before file modification
                if canonical_name in ("write_file", "create_file", "edit_file", "patch_file", "apply_diff", "delete_file") and self._checkpoint:
                    file_target = args.get("path", "")
                    if file_target:
                        checkpoint_manager.record_file_before_edit(self._checkpoint, file_target)

                # Check if tool requires approval
                needs_approval = requires_approval(tool_def.permission) or canonical_name == "delete_file"

                # Dynamically require approval for unsafe terminal commands
                if canonical_name in ("terminal", "run_terminal", "sandbox_execute"):
                    from src.security.command_policy import is_safe_command
                    command = args.get("command", "")
                    if command and not is_safe_command(command):
                        needs_approval = True

                is_approved = False
                if needs_approval:
                    approval = await approval_manager.request_approval(
                        agent_id=self._agent_id,
                        tool_name=tool_name,
                        args=args,
                        description=f"Execute {tool_name} with args: {json.dumps(args)[:200]}",
                    )
                    approved = await approval_manager.wait_for_decision(approval)
                    if not approved:
                        denied_msg = (
                            f"Tool '{tool_name}' was denied by user: {approval.deny_reason}"
                        )
                        results.append({
                            "tool_call_id": tool_call_id,
                            "content": denied_msg,
                            "tool_name": tool_name,
                        })
                        continue
                    is_approved = True

                # Execute the tool
                result = await self._tool_executor.execute_tool_call(
                    tool_call=tc,
                    project_path=self._project_path,
                    agent_id=self._agent_id,
                    is_approved=is_approved,
                )

                inner = result.get("result", {})

                # Event notifications for file read
                if canonical_name == "read_file":
                    path = inner.get("path", "")
                    await event_bus.emit(CoreMindEvent(
                        type=EventType.FILE_READ,
                        agent_id=self._agent_id,
                        data={"file": path, "total_lines": inner.get("total_lines", 0)},
                    ))

                # Track file changes and emit diffs
                if canonical_name in ("write_file", "create_file", "edit_file", "patch_file", "apply_diff"):
                    path = inner.get("path", "")
                    if path:
                        lines_cnt = inner.get("lines")
                        if lines_cnt is None:
                            lines_cnt = inner.get("additions", 0)
                        action = inner.get("action", "modified")

                        # If newly created, emit file.created immediately for snappy IDE response
                        if action == "created":
                            await event_bus.emit(CoreMindEvent(
                                 type=EventType.FILE_CREATED,
                                 agent_id=self._agent_id,
                                 data={
                                     "file": path,
                                     "path": path,
                                     "action": "created",
                                     "lines": lines_cnt,
                                     "size": inner.get("size", 0),
                                 },
                            ))

                        await event_bus.emit(CoreMindEvent(
                            type=EventType.FILE_CHANGED,
                            agent_id=self._agent_id,
                            data={
                                "file": path,
                                "path": path,
                                "action": action,
                                "lines": lines_cnt,
                                "additions": inner.get("additions", 0),
                                "deletions": inner.get("deletions", 0),
                                "size": inner.get("size", 0),
                            },
                        ))

                        diff_str = inner.get("diff", "")
                        if diff_str:
                            await event_bus.emit(CoreMindEvent(
                                type=EventType.DIFF_CREATED,
                                agent_id=self._agent_id,
                                data={
                                    "file": path,
                                    "diff": diff_str,
                                    "additions": inner.get("additions", 0),
                                    "deletions": inner.get("deletions", 0),
                                },
                            ))

                            if self._change_set_id:
                                fdiff = FileDiff(
                                    path=path,
                                    diff=diff_str,
                                    status=inner.get("action", "modified"),
                                    additions=inner.get("additions", 0),
                                    deletions=inner.get("deletions", 0),
                                )
                                orig_content = ""
                                if self._checkpoint and path in self._checkpoint.file_backups:
                                    orig_content = self._checkpoint.file_backups[path]
                                change_review_manager.record_change(
                                    self._change_set_id, path, fdiff, orig_content
                                )

                        # Automatic post-edit validation
                        valid, validation_err = await run_post_edit_validation(
                            self._project_path, path
                        )
                        if not valid:
                            inner["post_edit_validation_warning"] = (
                                f"Automatic validation detected an issue after edit: {validation_err}"
                            )

                elif canonical_name == "delete_file":
                    path = inner.get("path", "")
                    if path:
                        await event_bus.emit(CoreMindEvent(
                            type=EventType.FILE_DELETED,
                            agent_id=self._agent_id,
                            data={"file": path, "path": path, "action": "deleted"},
                        ))

                if canonical_name in ("terminal", "run_terminal", "sandbox_execute", "run_tests", "run_build"):
                    await event_bus.emit(CoreMindEvent(
                        type=EventType.COMMAND_COMPLETED,
                        agent_id=self._agent_id,
                        data={
                            "command": inner.get("command", ""),
                            "exit_code": inner.get("exit_code", 0),
                            "success": inner.get("success", True),
                        },
                    ))

                # Emit tool completed event
                await event_bus.emit(CoreMindEvent(
                    type=EventType.TOOL_COMPLETED,
                    agent_id=self._agent_id,
                    data={"tool": tool_name, "success": True, "result": inner},
                ))

                results.append({
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(inner),
                    "tool_name": tool_name,
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
                    "tool_name": tool_name,
                })

        return results
