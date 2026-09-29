"""
CoreMind Backend — Tool: git (status, diff, log)

Git awareness tools for the agent.
Permission: READ
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.tools.registry import PermissionLevel, ToolDefinition


async def _run_git(project_path: str, args: list[str]) -> dict[str, Any]:
    """Run a git command and return structured output."""
    cmd = ["git"] + args
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=15,
        )

        return {
            "command": f"git {' '.join(args)}",
            "output": stdout_bytes.decode("utf-8", errors="replace")[:30_000],
            "error": stderr_bytes.decode("utf-8", errors="replace")[:5_000],
            "exit_code": process.returncode or 0,
        }
    except TimeoutError:
        cmd_str = f"git {' '.join(args)}"
        return {
            "command": cmd_str, "output": "",
            "error": "Timed out", "exit_code": -1,
        }
    except FileNotFoundError:
        cmd_str = f"git {' '.join(args)}"
        return {
            "command": cmd_str, "output": "",
            "error": "git not found", "exit_code": -1,
        }


async def execute_git_status(
    project_path: str, **_kwargs: Any,
) -> dict[str, Any]:
    """Get git status."""
    return await _run_git(project_path, ["status", "--porcelain"])


async def execute_git_diff(
    project_path: str, staged: bool = False, **_kwargs: Any,
) -> dict[str, Any]:
    """Get git diff."""
    args = ["diff"]
    if staged:
        args.append("--staged")
    return await _run_git(project_path, args)


async def execute_git_log(project_path: str, count: int = 10, **_kwargs: Any) -> dict[str, Any]:
    """Get recent git commits."""
    return await _run_git(project_path, ["log", f"-{count}", "--oneline", "--no-decorate"])


git_status_tool = ToolDefinition(
    name="git_status",
    description="Get the current git status of the project (changed, added, deleted files).",
    parameters={"type": "object", "properties": {}, "required": []},
    permission=PermissionLevel.READ,
    executor=execute_git_status,
    timeout_ms=15_000,
)

git_diff_tool = ToolDefinition(
    name="git_diff",
    description="Get the git diff showing code changes.",
    parameters={
        "type": "object",
        "properties": {
            "staged": {
                "type": "boolean",
                "description": "Show staged changes only (default: false)",
            },
        },
        "required": [],
    },
    permission=PermissionLevel.READ,
    executor=execute_git_diff,
    timeout_ms=15_000,
)

git_log_tool = ToolDefinition(
    name="git_log",
    description="Get recent git commit history.",
    parameters={
        "type": "object",
        "properties": {
            "count": {
                "type": "integer",
                "description": "Number of commits to show (default: 10)",
            },
        },
        "required": [],
    },
    permission=PermissionLevel.READ,
    executor=execute_git_log,
    timeout_ms=15_000,
)
