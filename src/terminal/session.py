"""
CoreMind Backend — Persistent Terminal Session.

Maintains stateful terminal sessions (working directory, environment variables,
virtual environments) across consecutive command executions.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.security.command_policy import validate_command
from src.utils.errors import ErrorCode, ToolError
from src.utils.ids import short_id
from src.utils.logger import logger


def _get_shell() -> str:
    if os.name == "nt":
        git_bash = r"C:\Program Files\Git\bin\bash.exe"
        if os.path.exists(git_bash):
            return git_bash
        git_bash_86 = r"C:\Program Files (x86)\Git\bin\bash.exe"
        if os.path.exists(git_bash_86):
            return git_bash_86
        for cand in ["bash", "zsh"]:
            found = shutil.which(cand)
            if found and "WindowsApps" not in found:
                return found
        return shutil.which("powershell") or "cmd.exe"
    return shutil.which("bash") or shutil.which("zsh") or "/bin/sh"


@dataclass
class TerminalSession:
    """A persistent terminal session maintaining working directory and environment."""

    session_id: str
    project_path: str
    cwd: str
    env: dict[str, str] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    is_active: bool = True

    async def execute(self, command: str, timeout_seconds: float = 60.0) -> dict[str, Any]:
        """
        Execute command preserving environment and current working directory.
        """
        if not self.is_active:
            raise ToolError(ErrorCode.TOOL_EXECUTION_FAILED, f"Terminal session {self.session_id} is closed.")

        # Security policy validation
        validate_command(command)

        # We execute through a subshell that sources accumulated env, sets cwd,
        # executes command, and outputs the updated cwd and environment variables.
        delimiter = f"__CM_DELIM_{short_id()}__"
        pwd_cmd = "pwd -W 2>/dev/null || pwd" if os.name == "nt" else "pwd"
        wrapper = (
            f"{command}\n"
            f"__CM_EXIT__=$?\n"
            f"echo \"{delimiter}\"\n"
            f"echo \"EXIT:$__CM_EXIT__\"\n"
            f"echo \"PWD:$({pwd_cmd})\"\n"
            f"echo \"{delimiter}\"\n"
        )

        shell_bin = _get_shell()
        cmd_env = {**os.environ, **self.env}

        logger.info("terminal.session.exec", session_id=self.session_id, command=command[:150], cwd=self.cwd)

        try:
            proc = await asyncio.create_subprocess_exec(
                shell_bin,
                "-c",
                wrapper,
                cwd=self.cwd,
                env=cmd_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_seconds,
            )

            raw_stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            # Parse sentinel blocks
            exit_code = proc.returncode or 0
            stdout = raw_stdout

            if delimiter in raw_stdout:
                parts = raw_stdout.split(delimiter)
                stdout = parts[0]
                if len(parts) >= 2:
                    control_block = parts[1].strip()
                    for line in control_block.splitlines():
                        if line.startswith("EXIT:"):
                            try:
                                exit_code = int(line[5:])
                            except ValueError:
                                pass
                        elif line.startswith("PWD:"):
                            new_pwd = line[4:].strip()
                            if os.name == "nt":
                                import re
                                m_wsl = re.match(r"^/mnt/([a-zA-Z])/(.*)", new_pwd)
                                if m_wsl:
                                    candidate = f"{m_wsl.group(1).upper()}:\\{m_wsl.group(2).replace('/', '\\')}"
                                    if os.path.isdir(candidate):
                                        new_pwd = candidate
                                else:
                                    m_msys = re.match(r"^/([a-zA-Z])/(.*)", new_pwd)
                                    if m_msys:
                                        candidate = f"{m_msys.group(1).upper()}:\\{m_msys.group(2).replace('/', '\\')}"
                                        if os.path.isdir(candidate):
                                            new_pwd = candidate
                            if os.path.isdir(new_pwd):
                                self.cwd = new_pwd

            res = {
                "session_id": self.session_id,
                "command": command,
                "cwd": self.cwd,
                "exit_code": exit_code,
                "stdout": stdout[:50_000],
                "stderr": stderr[:20_000],
                "success": exit_code == 0,
            }
            self.history.append(res)
            return res

        except TimeoutError:
            try:
                proc.kill()  # type: ignore[possibly-undefined]
            except Exception:
                pass
            return {
                "session_id": self.session_id,
                "command": command,
                "cwd": self.cwd,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout_seconds}s",
                "success": False,
            }

    def close(self) -> None:
        self.is_active = False


class TerminalSessionManager:
    """Manages active persistent terminal sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, TerminalSession] = {}

    def create_session(self, project_path: str, session_id: str | None = None) -> TerminalSession:
        sid = session_id or f"term_{short_id()}"
        session = TerminalSession(
            session_id=sid,
            project_path=project_path,
            cwd=project_path,
        )
        self._sessions[sid] = session
        logger.info("terminal.session.created", session_id=sid, cwd=project_path)
        return session

    def get_session(self, session_id: str) -> TerminalSession | None:
        return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        session = self._sessions.pop(session_id, None)
        if session:
            session.close()
            logger.info("terminal.session.deleted", session_id=session_id)
            return True
        return False

    def list_sessions(self) -> list[dict[str, Any]]:
        return [
            {
                "session_id": s.session_id,
                "project_path": s.project_path,
                "cwd": s.cwd,
                "is_active": s.is_active,
                "created_at": s.created_at.isoformat(),
            }
            for s in self._sessions.values()
        ]


terminal_session_manager = TerminalSessionManager()
