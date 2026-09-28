import asyncio
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import List, Optional
from app.config import settings
from app.tools.types import SandboxExecutionResult


class PythonRunner:
    """Async execution runner for isolated Python code and pytest suites."""

    def __init__(
        self,
        python_path: Optional[str] = None,
        default_timeout_ms: Optional[int] = None,
        work_dir: Optional[Path] = None,
    ):
        self.python_path = python_path or settings.sandbox.python_path or sys.executable
        self.default_timeout_ms = default_timeout_ms or settings.sandbox.timeout_ms
        self.work_dir = work_dir or settings.sandbox.work_dir

    async def ensure_work_dir(self, dir_path: Optional[Path] = None) -> None:
        target = dir_path or self.work_dir
        target.mkdir(parents=True, exist_ok=True)

    def extract_traceback(self, output: str) -> Optional[str]:
        """Extract Python exception tracebacks or syntax errors."""
        tb_match = re.search(r"Traceback \(most recent call last\):[\s\S]+?(?=(\r?\n\r?\n|$))", output)
        if tb_match:
            return tb_match.group(0).strip()

        exc_match = re.search(r"(?:(\w+Error|\w+Exception|AssertionError):[^\r\n]+)", output)
        if exc_match:
            return exc_match.group(0).strip()

        return None

    async def run_code(
        self,
        code: Optional[str] = None,
        script_path: Optional[str] = None,
        args: Optional[List[str]] = None,
        cwd: Optional[Path] = None,
        timeout_ms: Optional[int] = None,
    ) -> SandboxExecutionResult:
        target_cwd = (cwd or self.work_dir).resolve()
        await self.ensure_work_dir(target_cwd)

        timeout_sec = (timeout_ms or self.default_timeout_ms) / 1000.0
        temp_file_created = False
        final_script_path: Path

        if code:
            temp_name = f"_temp_run_{int(time.time())}_{uuid.uuid4().hex[:8]}.py"
            final_script_path = target_cwd / temp_name
            final_script_path.write_text(code, encoding="utf-8")
            temp_file_created = True
        elif script_path:
            p = Path(script_path)
            final_script_path = p if p.is_absolute() else target_cwd / p
        else:
            return SandboxExecutionResult(
                success=False,
                stdout="",
                stderr="No code or script_path provided for execution.",
                exit_code=1,
                duration_ms=0,
                command="",
            )

        cmd_args = [str(final_script_path)] + (args or [])
        cmd_full = f"{self.python_path} {' '.join(cmd_args)}"
        start_time = time.time()

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONPATH"] = str(target_cwd)

        try:
            proc = await asyncio.create_subprocess_exec(
                self.python_path,
                *cmd_args,
                cwd=str(target_cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            try:
                stdout_data, stderr_data = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
                exit_code = proc.returncode if proc.returncode is not None else 0
                stdout = stdout_data.decode("utf-8", errors="replace")
                stderr = stderr_data.decode("utf-8", errors="replace")
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                stdout = ""
                stderr = f"[Sandbox Timeout] Execution killed after exceeding {timeout_ms or self.default_timeout_ms}ms limit."
                exit_code = 124

            duration_ms = int((time.time() - start_time) * 1000)
            combined = f"{stdout}\n{stderr}"
            tb = self.extract_traceback(combined)

            return SandboxExecutionResult(
                success=(exit_code == 0),
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                traceback=tb,
                duration_ms=duration_ms,
                command=cmd_full,
            )
        finally:
            if temp_file_created and final_script_path.exists():
                try:
                    final_script_path.unlink()
                except OSError:
                    pass

    async def run_tests(
        self,
        test_command: Optional[str] = None,
        test_path: Optional[str] = None,
        cwd: Optional[Path] = None,
        timeout_ms: Optional[int] = None,
    ) -> SandboxExecutionResult:
        target_cwd = (cwd or self.work_dir).resolve()
        await self.ensure_work_dir(target_cwd)

        timeout_sec = (timeout_ms or self.default_timeout_ms) / 1000.0

        if test_command:
            cmd = test_command
        else:
            target = f'"{test_path}"' if test_path else ""
            cmd = f"{self.python_path} -m pytest -v {target}".strip()

        start_time = time.time()
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONPATH"] = str(target_cwd)

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=str(target_cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            try:
                stdout_data, stderr_data = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
                exit_code = proc.returncode if proc.returncode is not None else 0
                stdout = stdout_data.decode("utf-8", errors="replace")
                stderr = stderr_data.decode("utf-8", errors="replace")
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                stdout = ""
                stderr = f"[Sandbox Timeout] Test suite killed after {timeout_ms or self.default_timeout_ms}ms."
                exit_code = 124

            duration_ms = int((time.time() - start_time) * 1000)
            combined = f"{stdout}\n{stderr}"
            tb = self.extract_traceback(combined)

            return SandboxExecutionResult(
                success=(exit_code == 0),
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                traceback=tb,
                duration_ms=duration_ms,
                command=cmd,
            )
        except Exception as exc:
            return SandboxExecutionResult(
                success=False,
                stdout="",
                stderr=str(exc),
                exit_code=1,
                traceback=None,
                duration_ms=int((time.time() - start_time) * 1000),
                command=cmd,
            )


default_python_runner = PythonRunner()
