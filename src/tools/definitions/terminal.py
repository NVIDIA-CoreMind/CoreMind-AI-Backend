"""
CoreMind Backend — Tool: terminal

Runs a shell command in the project directory.
Permission: EXECUTE
"""

from __future__ import annotations

import asyncio
from typing import Any

import re
from src.config import settings
from src.terminal.process_manager import process_manager
from src.tools.registry import PermissionLevel, ToolDefinition
from src.utils.logger import logger

MAX_OUTPUT_SIZE = 50_000  # 50 KB

SERVER_COMMAND_PATTERNS = (
    "http.server",
    "live-server",
    "serve",
    "vite",
    "next dev",
    "npm run dev",
    "npm start",
    "yarn dev",
    "yarn start",
    "pnpm dev",
    "pnpm start",
    "uvicorn",
    "flask run",
    "fastapi dev",
)


async def execute_terminal(
    project_path: str,
    command: str,
    timeout_ms: int | None = None,
    is_background: bool = False,
    agent_id: str | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Execute a shell command in the project directory with live streaming and background support."""
    timeout = (timeout_ms or settings.default_command_timeout_ms) / 1000

    cmd_stripped = command.strip()
    from src.security.command_policy import validate_command
    validate_command(cmd_stripped)

    is_server = (
        is_background
        or cmd_stripped.endswith("&")
        or any(pat in cmd_stripped.lower() for pat in SERVER_COMMAND_PATTERNS)
    )

    if is_server:
        clean_cmd = cmd_stripped.rstrip("&").strip()
        logger.info("tools.terminal.execute_background", command=clean_cmd[:200], cwd=project_path)
        res = await process_manager.start_process(clean_cmd, cwd=project_path)
        if "error" in res:
            return {
                "command": command,
                "exit_code": 1,
                "stdout": "",
                "stderr": res["error"],
                "success": False,
            }

        # Wait briefly to let server initialize and emit port logs
        await asyncio.sleep(0.6)
        pid = res.get("process_id", "")
        logs = process_manager.read_process_logs(pid, tail_lines=20) or []
        stdout = "\n".join(logs)

        # Detect local URL/port
        url = None
        port_match = re.search(r"(?:http\.server|serve|port|-p)\s+(\d+)", clean_cmd)
        if not port_match:
            port_match = re.search(r"(?:localhost:|127\.0\.0\.1:|port\s+)(\d+)", stdout, re.IGNORECASE)
        if port_match:
            port = port_match.group(1)
            url = f"http://localhost:{port}"

        out_msg = stdout or f"Background process started (ID: {pid})"
        if url:
            out_msg += f"\nLocal web server running at: {url}"

        return {
            "command": command,
            "process_id": pid,
            "status": "running",
            "exit_code": 0,
            "stdout": out_msg,
            "stderr": "",
            "url": url,
            "success": True,
            "is_background": True,
        }

    logger.info("tools.terminal.execute", command=command[:200], cwd=project_path)
    from src.events.event_bus import event_bus
    from src.events.events import CoreMindEvent, EventType

    process: asyncio.subprocess.Process | None = None
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def _read_stream(reader: asyncio.StreamReader, is_err: bool) -> None:
            while True:
                chunk = await reader.read(1024)
                if not chunk:
                    break
                decoded = chunk.decode("utf-8", errors="replace")
                if is_err:
                    stderr_chunks.append(decoded)
                else:
                    stdout_chunks.append(decoded)
                await event_bus.emit(CoreMindEvent(
                    type=EventType.COMMAND_OUTPUT,
                    agent_id=agent_id,
                    task_id=task_id or agent_id,
                    session_id=session_id,
                    data={
                        "command": command,
                        "output": decoded,
                        "stream": "stderr" if is_err else "stdout",
                    },
                ))

        if process.stdout and process.stderr:
            await asyncio.wait_for(
                asyncio.gather(
                    _read_stream(process.stdout, False),
                    _read_stream(process.stderr, True),
                ),
                timeout=timeout,
            )
            await process.wait()

        stdout = "".join(stdout_chunks)[:MAX_OUTPUT_SIZE]
        stderr = "".join(stderr_chunks)[:MAX_OUTPUT_SIZE]
        exit_code = process.returncode if process.returncode is not None else 0

        logger.info("tools.terminal.completed", command=command[:100], exit_code=exit_code)

        return {
            "command": command,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "success": exit_code == 0,
        }

    except (TimeoutError, asyncio.CancelledError) as err:
        is_cancelled = isinstance(err, asyncio.CancelledError)
        logger.error("tools.terminal.interrupted", command=command[:100], cancelled=is_cancelled)
        if process is not None:
            try:
                process.terminate()
                await asyncio.sleep(0.1)
                if process.returncode is None:
                    process.kill()
            except Exception:
                pass
        if is_cancelled:
            raise
        return {
            "command": command,
            "exit_code": -1,
            "stdout": "".join(stdout_chunks)[:MAX_OUTPUT_SIZE],
            "stderr": f"Command timed out after {timeout}s",
            "success": False,
        }


terminal_tool = ToolDefinition(
    name="terminal",
    description=(
        "Execute a shell command in the project directory."
        " Use for running dev servers, tests, build commands, etc."
        " Dev servers (http.server, vite, npm run dev) automatically run in the background."
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute (e.g. 'python3 -m http.server 3000', 'npm test')",
            },
            "timeout_ms": {
                "type": "integer",
                "description": "Optional timeout in milliseconds",
            },
            "is_background": {
                "type": "boolean",
                "description": "Set to true for long-running servers or background processes so they don't block",
            },
        },
        "required": ["command"],
    },
    permission=PermissionLevel.EXECUTE,
    executor=execute_terminal,
    timeout_ms=120_000,
)

run_terminal_tool = ToolDefinition(
    name="run_terminal",
    description="Execute an approved shell command in the workspace directory.",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            },
            "timeout_ms": {
                "type": "integer",
                "description": "Optional command execution timeout in milliseconds (default: 120000)",
            },
            "is_background": {
                "type": "boolean",
                "description": "Whether command should run in the background (default: false)",
            },
        },
        "required": ["command"],
    },
    permission=PermissionLevel.EXECUTE,
    executor=execute_terminal,
    timeout_ms=120_000,
)

