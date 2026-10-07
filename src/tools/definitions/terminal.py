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
    **_kwargs: Any,
) -> dict[str, Any]:
    """Execute a shell command in the project directory with background server support."""
    timeout = (timeout_ms or settings.default_command_timeout_ms) / 1000

    cmd_stripped = command.strip()
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
