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
from src.security.command_policy import (
    SHELL_TOOLS,
    CommandClassification,
    extract_commands,
    validate_command,
    worst_classification,
)
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
        session_id: str | None = None,
        task_id: str | None = None,
    ) -> None:
        self._project_path = project_path
        self._agent_id = agent_id
        self._checkpoint = checkpoint
        self._change_set_id = change_set_id
        self._session_id = session_id
        self._task_id = task_id or agent_id
        self._tool_executor = ToolExecutor()

    def set_checkpoint(self, checkpoint: Checkpoint) -> None:
        self._checkpoint = checkpoint

    def set_change_set_id(self, change_set_id: str) -> None:
        self._change_set_id = change_set_id

    async def _emit(self, event_type: EventType, data: dict[str, Any]) -> None:
        """Emit an event with full correlation identifiers."""
        await event_bus.emit(CoreMindEvent(
            type=event_type,
            agent_id=self._agent_id,
            task_id=self._task_id,
            session_id=self._session_id,
            data=data,
        ))

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
            tool_call_id = tc.get("id") or f"call_{tool_name}"

            raw_args = func.get("arguments", "{}")
            if isinstance(raw_args, dict):
                args = raw_args
            elif isinstance(raw_args, str):
                try:
                    clean_str = raw_args.strip()
                    if clean_str.startswith("```json") and clean_str.endswith("```"):
                        clean_str = clean_str[7:-3].strip()
                    elif clean_str.startswith("```") and clean_str.endswith("```"):
                        clean_str = clean_str[3:-3].strip()
                    args = json.loads(clean_str)
                except Exception:
                    args = {}
            else:
                args = {}

            # Emit tool started event with tool args for UI transparency
            await self._emit(EventType.TOOL_STARTED, {
                "tool": tool_name,
                "tool_call_id": tool_call_id,
                "args": args,
            })

            try:
                # Get tool definition and canonical name
                tool_def = tool_registry.get(tool_name)
                canonical_name = tool_def.name

                # Check command validation on every command-like argument (SEC-04)
                shell_commands = extract_commands(args) if canonical_name in SHELL_TOOLS else []
                for command in shell_commands:
                    validate_command(command)
                    await self._emit(EventType.COMMAND_STARTED, {
                        "command": command,
                        "cwd": self._project_path,
                    })

                # Checkpoint backup before file modification
                if canonical_name in ("write_file", "create_file", "edit_file", "patch_file", "apply_diff", "delete_file") and self._checkpoint:
                    file_target = args.get("path", "")
                    if file_target:
                        checkpoint_manager.record_file_before_edit(self._checkpoint, file_target)

                # Check if tool requires approval
                needs_approval = requires_approval(tool_def.permission) or canonical_name == "delete_file"

                # Shell tools need approval when any command they carry is not clearly safe
                if shell_commands and worst_classification(shell_commands) != CommandClassification.SAFE:
                    needs_approval = True

                is_approved = False
                if needs_approval:
                    approval = await approval_manager.request_approval(
                        agent_id=self._agent_id,
                        tool_name=tool_name,
                        args=args,
                        description=f"Execute {tool_name} with args: {json.dumps(args)[:200]}",
                        session_id=self._session_id,
                        task_id=self._task_id,
                    )
                    approved = await approval_manager.wait_for_decision(approval)
                    if not approved:
                        denied_msg = (
                            f"Tool '{tool_name}' was denied by user: {approval.deny_reason}"
                        )
                        await self._emit(EventType.TOOL_FAILED, {
                            "tool": tool_name,
                            "tool_call_id": tool_call_id,
                            "error": denied_msg,
                        })
                        await self._emit(EventType.TOOL_COMPLETED, {
                            "tool": tool_name,
                            "tool_call_id": tool_call_id,
                            "success": False,
                            "error": denied_msg,
                        })
                        results.append({
                            "tool_call_id": tool_call_id,
                            "content": json.dumps({"error": denied_msg}),
                            "tool_name": tool_name,
                        })
                        continue
                    is_approved = True
                else:
                    is_approved = True

                # Execute the tool
                result = await self._tool_executor.execute_tool_call(
                    tool_call=tc,
                    project_path=self._project_path,
                    agent_id=self._agent_id,
                    is_approved=is_approved,
                    session_id=self._session_id,
                    task_id=self._task_id,
                )

                inner = result.get("result", {})

                # Event notifications for file read
                if canonical_name == "read_file":
                    path = inner.get("path", "")
                    await self._emit(EventType.FILE_READ, {
                        "file": path,
                        "path": path,
                        "total_lines": inner.get("total_lines", 0),
                    })

                # Track file changes and emit diffs
                if canonical_name in ("write_file", "create_file", "edit_file", "patch_file", "apply_diff"):
                    path = inner.get("path", "")
                    if path:
                        # Verify change on disk
                        from pathlib import Path
                        on_disk = (Path(self._project_path) / path).exists()
                        inner["verified_on_disk"] = on_disk

                        lines_cnt = inner.get("lines")
                        if lines_cnt is None:
                            lines_cnt = inner.get("additions", 0)
                        action = inner.get("action", "modified")

                        # If newly created, emit file.created immediately for snappy IDE response
                        if action == "created":
                            await self._emit(EventType.FILE_CREATED, {
                                "file": path,
                                "path": path,
                                "action": "created",
                                "lines": lines_cnt,
                                "size": inner.get("size", 0),
                            })

                        await self._emit(EventType.FILE_CHANGED, {
                            "file": path,
                            "path": path,
                            "action": action,
                            "lines": lines_cnt,
                            "additions": inner.get("additions", 0),
                            "deletions": inner.get("deletions", 0),
                            "size": inner.get("size", 0),
                        })

                        diff_str = inner.get("diff", "")
                        if diff_str:
                            await self._emit(EventType.DIFF_CREATED, {
                                "file": path,
                                "diff": diff_str,
                                "additions": inner.get("additions", 0),
                                "deletions": inner.get("deletions", 0),
                            })

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
                        from pathlib import Path
                        deleted_on_disk = not (Path(self._project_path) / path).exists()
                        inner["verified_on_disk"] = deleted_on_disk
                        await self._emit(EventType.FILE_DELETED, {
                            "file": path,
                            "path": path,
                            "action": "deleted",
                        })

                if canonical_name in ("terminal", "run_terminal", "sandbox_execute", "run_tests", "run_build"):
                    stdout_str = inner.get("stdout") or inner.get("output") or ""
                    stderr_str = inner.get("stderr") or ""
                    full_out = f"{stdout_str}\n{stderr_str}".strip() if stderr_str else stdout_str
                    cmd_str = inner.get("command", "") or args.get("command") or args.get("test_command") or args.get("build_command") or ""
                    await self._emit(EventType.COMMAND_COMPLETED, {
                        "command": cmd_str,
                        "exit_code": inner.get("exit_code", 0),
                        "success": inner.get("success", True),
                        "output": full_out,
                    })

                # Emit tool completed event
                await self._emit(EventType.TOOL_COMPLETED, {
                    "tool": tool_name,
                    "tool_call_id": tool_call_id,
                    "success": True,
                    "result": inner,
                })

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

                await self._emit(EventType.TOOL_FAILED, {
                    "tool": tool_name,
                    "tool_call_id": tool_call_id,
                    "error": str(exc),
                })

                await self._emit(EventType.TOOL_COMPLETED, {
                    "tool": tool_name,
                    "tool_call_id": tool_call_id,
                    "success": False,
                    "error": str(exc),
                })

                results.append({
                    "tool_call_id": tool_call_id,
                    "content": json.dumps({"error": str(exc)}),
                    "tool_name": tool_name,
                })

        return results
