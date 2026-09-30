"""
CoreMind Backend — Local Sandbox Provider.

Executes commands as local subprocesses with timeout and output limits.
For MVP, this is the primary sandbox provider.
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.config import settings
from src.sandbox.provider import SandboxProvider
from src.utils.errors import ErrorCode, SandboxError
from src.utils.ids import sandbox_id as gen_sandbox_id
from src.utils.logger import logger

MAX_OUTPUT = 100_000  # 100 KB


class LocalSandboxProvider(SandboxProvider):
    """Local process-based sandbox provider."""

    def __init__(self) -> None:
        self._sandboxes: dict[str, dict[str, Any]] = {}
        logger.info("sandbox.local.initialized")

    @property
    def name(self) -> str:
        return "local"

    async def create(self, project_path: str) -> dict[str, Any]:
        """Create a local sandbox (just tracks the project path)."""
        sid = gen_sandbox_id()

        self._sandboxes[sid] = {
            "sandbox_id": sid,
            "project_path": project_path,
            "status": "active",
        }

        logger.info("sandbox.local.created", sandbox_id=sid, project=project_path)

        return {"sandbox_id": sid, "status": "active", "provider": "local"}

    async def execute(
        self,
        sandbox_id: str,
        command: str,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        """Execute a command in the local sandbox."""
        sandbox = self._sandboxes.get(sandbox_id)
        if sandbox is None:
            raise SandboxError(ErrorCode.SANDBOX_UNAVAILABLE, f"Sandbox not found: {sandbox_id}")

        project_path = sandbox["project_path"]
        timeout = (timeout_ms or settings.default_command_timeout_ms) / 1000

        logger.info(
            "sandbox.local.execute",
            sandbox_id=sandbox_id,
            command=command[:200],
        )

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

            stdout = stdout_bytes.decode("utf-8", errors="replace")[:MAX_OUTPUT]
            stderr = stderr_bytes.decode("utf-8", errors="replace")[:MAX_OUTPUT]
            exit_code = process.returncode or 0

            logger.info(
                "sandbox.local.completed",
                sandbox_id=sandbox_id,
                exit_code=exit_code,
                stdout_len=len(stdout),
                stderr_len=len(stderr),
            )

            return {
                "sandbox_id": sandbox_id,
                "command": command,
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "success": exit_code == 0,
            }

        except TimeoutError:
            logger.error("sandbox.local.timeout", sandbox_id=sandbox_id, command=command[:100])
            if process is not None:
                try:
                    process.kill()
                except Exception:
                    pass
            raise SandboxError(
                ErrorCode.SANDBOX_TIMEOUT,
                f"Command timed out after {timeout}s: {command[:100]}",
            )

    async def destroy(self, sandbox_id: str) -> bool:
        """Destroy a local sandbox."""
        if sandbox_id in self._sandboxes:
            del self._sandboxes[sandbox_id]
            logger.info("sandbox.local.destroyed", sandbox_id=sandbox_id)
            return True
        return False
