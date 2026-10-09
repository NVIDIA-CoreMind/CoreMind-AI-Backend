"""
CoreMind Backend — Tool: run_build

Executes project compilation or bundling build command.
Permission: EXECUTE
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from src.events.event_bus import event_bus
from src.events.events import CoreMindEvent, EventType
from src.security.command_policy import validate_command
from src.tools.registry import PermissionLevel, ToolDefinition
from src.utils.errors import ErrorCode, ToolError
from src.utils.logger import logger


def _detect_build_command(project_path: str) -> str:
    """Detect the appropriate build command for the project."""
    root = Path(project_path)
    if (root / "package.json").exists():
        import json
        try:
            pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
            scripts = pkg.get("scripts", {})
            if "build" in scripts:
                return "npm run build"
        except Exception:
            return "npm run build"
    if (root / "pubspec.yaml").exists():
        return "flutter build bundle"
    if (root / "Cargo.toml").exists():
        return "cargo build"
    if (root / "go.mod").exists():
        return "go build ./..."
    if (root / "pyproject.toml").exists():
        return "python -m py_compile"
    return "npm run build"


async def execute_run_build(
    project_path: str,
    build_command: str | None = None,
    timeout_ms: int = 120_000,
    agent_id: str | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Execute project build and report structured results."""
    cmd = build_command or _detect_build_command(project_path)
    validate_command(cmd)

    logger.info("tools.run_build.start", command=cmd, cwd=project_path)
    await event_bus.emit(CoreMindEvent(
        type=EventType.COMMAND_STARTED,
        agent_id=agent_id,
        data={"command": cmd, "type": "build"},
    ))

    timeout_s = timeout_ms / 1000.0
    process: asyncio.subprocess.Process | None = None

    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_s,
        )

        stdout = stdout_bytes.decode("utf-8", errors="replace")[:50_000]
        stderr = stderr_bytes.decode("utf-8", errors="replace")[:50_000]
        exit_code = process.returncode or 0
        success = exit_code == 0

        output = stdout if stdout else stderr
        summary_lines = [l for l in output.strip().splitlines() if l.strip()]
        summary = "\n".join(summary_lines[-10:]) if summary_lines else ("Build succeeded" if success else "Build failed")

        await event_bus.emit(CoreMindEvent(
            type=EventType.COMMAND_COMPLETED,
            agent_id=agent_id,
            data={"command": cmd, "exit_code": exit_code, "success": success, "type": "build"},
        ))

        logger.info("tools.run_build.completed", command=cmd, exit_code=exit_code, success=success)

        return {
            "command": cmd,
            "exit_code": exit_code,
            "success": success,
            "stdout": stdout,
            "stderr": stderr,
            "summary": summary,
        }

    except TimeoutError:
        if process:
            try:
                process.kill()
            except Exception:
                pass
        raise ToolError(
            ErrorCode.TOOL_TIMEOUT,
            f"Build command timed out after {timeout_s}s: {cmd}",
        )
    except Exception as exc:
        raise ToolError(
            ErrorCode.TOOL_EXECUTION_FAILED,
            f"Failed to execute build: {exc}",
        ) from exc


run_build_tool = ToolDefinition(
    name="run_build",
    description="Run the appropriate build command for the project (e.g. 'npm run build', 'tsc', 'cargo build').",
    parameters={
        "type": "object",
        "properties": {
            "build_command": {
                "type": "string",
                "description": "Optional explicit build command to execute",
            },
            "timeout_ms": {
                "type": "integer",
                "description": "Build timeout in milliseconds (default: 120000)",
            },
        },
    },
    permission=PermissionLevel.EXECUTE,
    executor=execute_run_build,
    timeout_ms=130_000,
)
