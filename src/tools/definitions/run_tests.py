"""
CoreMind Backend — Tool: run_tests

Runs project unit or integration tests and returns structured results.
Permission: EXECUTE
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from src.events.event_bus import event_bus
from src.events.events import CoreMindEvent, EventType
from src.project.project_manager import project_manager
from src.security.command_policy import validate_command
from src.tools.registry import PermissionLevel, ToolDefinition
from src.utils.errors import ErrorCode, ToolError
from src.utils.logger import logger


def _detect_test_command(project_path: str, test_path: str | None = None) -> str:
    """Detect the appropriate test command for the project."""
    root = Path(project_path)
    info = project_manager.get_project(project_path) or {}
    configured_cmd = info.get("test_command", "")

    if (root / "pytest.ini").exists() or (root / "tests").is_dir() or (root / "pyproject.toml").exists():
        cmd = "pytest"
        if test_path:
            cmd = f"pytest {test_path}"
        return cmd
    elif (root / "pubspec.yaml").exists():
        cmd = "flutter test"
        if test_path:
            cmd = f"flutter test {test_path}"
        return cmd
    elif (root / "package.json").exists():
        if test_path:
            return f"npm test -- {test_path}"
        return "npm test"
    elif (root / "Cargo.toml").exists():
        return "cargo test"
    elif (root / "go.mod").exists():
        return "go test ./..."

    return configured_cmd or "pytest"


async def execute_run_tests(
    project_path: str,
    test_command: str | None = None,
    test_path: str | None = None,
    timeout_ms: int = 120_000,
    agent_id: str | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Execute tests in the workspace and report structured results."""
    cmd = test_command or _detect_test_command(project_path, test_path)
    validate_command(cmd)

    sess_id = _kwargs.get("session_id")
    t_id = _kwargs.get("task_id") or agent_id
    await event_bus.emit(CoreMindEvent(
        type=EventType.VERIFICATION_STARTED,
        agent_id=agent_id,
        session_id=sess_id,
        task_id=t_id,
        data={"command": cmd, "attempt": 1},
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

        # Pytest exit code 5 means 0 items collected (empty or no tests yet)
        is_no_tests = "pytest" in cmd and (exit_code == 5 or "collected 0 items" in stdout.lower())
        success = exit_code == 0 or is_no_tests

        # Extract last lines as summary
        output = stdout if stdout else stderr
        summary_lines = [l for l in output.strip().splitlines() if l.strip()]
        summary = "\n".join(summary_lines[-10:]) if summary_lines else ("Tests passed" if success else "Tests failed")

        event_type = EventType.VERIFICATION_PASSED if success else EventType.VERIFICATION_FAILED
        await event_bus.emit(CoreMindEvent(
            type=event_type,
            agent_id=agent_id,
            data={"command": cmd, "exit_code": exit_code, "error_summary": summary[:500]},
        ))

        logger.info("tools.run_tests.completed", command=cmd, exit_code=exit_code, success=success)

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
        await event_bus.emit(CoreMindEvent(
            type=EventType.VERIFICATION_FAILED,
            agent_id=agent_id,
            data={"command": cmd, "error_summary": f"Tests timed out after {timeout_s}s"},
        ))
        raise ToolError(
            ErrorCode.TOOL_TIMEOUT,
            f"Test execution timed out after {timeout_s}s for command '{cmd}'",
        )
    except Exception as exc:
        raise ToolError(
            ErrorCode.TOOL_EXECUTION_FAILED,
            f"Failed to execute tests: {exc}",
        ) from exc


run_tests_tool = ToolDefinition(
    name="run_tests",
    description=(
        "Run the project's test suite or a targeted test file."
        " Automatically detects pytest, npm test, flutter test, cargo test, etc."
    ),
    parameters={
        "type": "object",
        "properties": {
            "test_command": {
                "type": "string",
                "description": "Optional explicit test command to run (e.g. 'pytest tests/test_auth.py')",
            },
            "test_path": {
                "type": "string",
                "description": "Optional specific test file or directory path to run",
            },
            "timeout_ms": {
                "type": "integer",
                "description": "Maximum execution timeout in milliseconds (default: 120000)",
            },
        },
    },
    permission=PermissionLevel.EXECUTE,
    executor=execute_run_tests,
    timeout_ms=130_000,
)
