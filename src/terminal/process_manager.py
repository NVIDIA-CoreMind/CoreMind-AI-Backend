"""
CoreMind Backend — Controlled Background Process Manager.

Manages long-running support processes (dev servers, file watchers, test runners)
with log buffering, status reporting, and safe lifecycle controls.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.security.command_policy import validate_command
from src.utils.ids import short_id
from src.utils.logger import logger


@dataclass
class BackgroundProcess:
    """A managed background process."""

    process_id: str
    command: str
    cwd: str
    status: str  # "running", "completed", "failed", "stopped"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    exit_code: int | None = None
    proc: asyncio.subprocess.Process | None = None
    logs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "process_id": self.process_id,
            "command": self.command,
            "cwd": self.cwd,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "exit_code": self.exit_code,
            "log_lines_count": len(self.logs),
        }


class ProcessManager:
    """Manages controlled background processes."""

    def __init__(self, max_processes: int = 5) -> None:
        self._processes: dict[str, BackgroundProcess] = {}
        self._max_processes = max_processes

    async def start_process(self, command: str, cwd: str) -> dict[str, Any]:
        """Start a background process with output logging."""
        # Enforce command policy
        validate_command(command)

        # Enforce concurrent background process limit
        running = [p for p in self._processes.values() if p.status == "running"]
        if len(running) >= self._max_processes:
            return {
                "error": f"Maximum background processes limit reached ({self._max_processes}). Stop an existing process first.",
            }

        pid = f"proc_{short_id()}"

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception as e:
            return {"error": f"Failed to spawn background process: {e}"}

        bg_proc = BackgroundProcess(
            process_id=pid,
            command=command,
            cwd=cwd,
            status="running",
            proc=proc,
        )
        self._processes[pid] = bg_proc

        # Start background task to consume and buffer logs
        asyncio.create_task(self._monitor_process(bg_proc))

        logger.info("process.started", pid=pid, command=command[:100], cwd=cwd)
        return bg_proc.to_dict()

    async def _monitor_process(self, bg_proc: BackgroundProcess) -> None:
        """Read stdout lines and update status on process termination."""
        if not bg_proc.proc or not bg_proc.proc.stdout:
            return

        try:
            while True:
                line = await bg_proc.proc.stdout.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                bg_proc.logs.append(decoded)
                # Keep last 500 lines
                if len(bg_proc.logs) > 500:
                    bg_proc.logs.pop(0)

            await bg_proc.proc.wait()
            bg_proc.exit_code = bg_proc.proc.returncode
            bg_proc.status = "completed" if bg_proc.exit_code == 0 else "failed"
            logger.info("process.exited", pid=bg_proc.process_id, exit_code=bg_proc.exit_code)
        except Exception as e:
            bg_proc.status = "failed"
            logger.error("process.monitor_error", pid=bg_proc.process_id, error=str(e))

    def get_process_status(self, process_id: str) -> dict[str, Any] | None:
        bp = self._processes.get(process_id)
        return bp.to_dict() if bp else None

    def read_process_logs(self, process_id: str, tail_lines: int = 100) -> list[str] | None:
        bp = self._processes.get(process_id)
        if not bp:
            return None
        return bp.logs[-tail_lines:]

    async def stop_process(self, process_id: str) -> bool:
        bp = self._processes.get(process_id)
        if not bp or bp.status != "running" or not bp.proc:
            return False

        try:
            bp.proc.terminate()
            try:
                await asyncio.wait_for(bp.proc.wait(), timeout=3.0)
            except TimeoutError:
                bp.proc.kill()
            bp.status = "stopped"
            logger.info("process.stopped", pid=process_id)
            return True
        except Exception as e:
            logger.error("process.stop_error", pid=process_id, error=str(e))
            return False

    def list_processes(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self._processes.values()]


process_manager = ProcessManager()
