"""
CoreMind Backend — Tool: terminal

Runs a shell command in the project directory.
Permission: EXECUTE
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.config import settings
from src.tools.registry import PermissionLevel, ToolDefinition
from src.utils.logger import logger

MAX_OUTPUT_SIZE = 50_000  # 50 KB


async def execute_terminal(
    project_path: str,
    command: str,
    timeout_ms: int | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Execute a shell command in the project directory."""
    timeout = (timeout_ms or settings.default_command_timeout_ms) / 1000

    logger.info("tools.terminal.execute", command=command[:200], cwd=project_path)

    process: asyncio.subprocess.Process | None = None
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )

        stdout = stdout_bytes.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE]
        stderr = stderr_bytes.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE]
        exit_code = process.returncode or 0

        logger.info("tools.terminal.completed", command=command[:100], exit_code=exit_code)

        return {
            "command": command,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "success": exit_code == 0,
        }

    except TimeoutError:
        logger.error("tools.terminal.timeout", command=command[:100], timeout_ms=timeout * 1000)
        if process is not None:
            try:
                process.kill()
            except Exception:
                pass
        return {
            "command": command,
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "success": False,
        }


terminal_tool = ToolDefinition(
    name="terminal",
    description=(
        "Execute a shell command in the project directory."
        " Use for running tests, build commands, etc."
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            },
            "timeout_ms": {
                "type": "integer",
                "description": "Optional timeout in milliseconds",
            },
        },
        "required": ["command"],
    },
    permission=PermissionLevel.EXECUTE,
    executor=execute_terminal,
    timeout_ms=120_000,
)
