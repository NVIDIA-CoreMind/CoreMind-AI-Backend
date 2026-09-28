from pathlib import Path
from app.sandbox.python_runner import PythonRunner, default_python_runner
from app.tools.types import RunSandboxPythonArgs, RunSandboxTestsArgs, ToolResult


async def execute_run_sandbox_python(
    runner: PythonRunner = default_python_runner,
    args: RunSandboxPythonArgs = RunSandboxPythonArgs(),
    workspace_root: str | Path = "",
) -> ToolResult:
    try:
        target_cwd = Path(workspace_root) if workspace_root else runner.work_dir
        result = await runner.run_code(
            code=args.code,
            script_path=args.script_path,
            args=args.args,
            cwd=target_cwd,
            timeout_ms=args.timeout,
        )

        msg = (
            f"Python execution completed successfully in {result.duration_ms}ms."
            if result.success
            else f"Python execution failed with exit code {result.exit_code}. Stderr: {result.stderr}"
        )

        return ToolResult(
            success=result.success,
            data=result.model_dump(),
            message=msg,
        )
    except Exception as exc:
        return ToolResult(success=False, error=f"Sandbox execution error: {exc}")


async def execute_run_sandbox_tests(
    runner: PythonRunner = default_python_runner,
    args: RunSandboxTestsArgs = RunSandboxTestsArgs(),
    workspace_root: str | Path = "",
) -> ToolResult:
    try:
        target_cwd = Path(workspace_root) if workspace_root else runner.work_dir
        result = await runner.run_tests(
            test_command=args.test_command,
            test_path=args.test_path,
            cwd=target_cwd,
            timeout_ms=args.timeout,
        )

        msg = (
            f"All tests passed cleanly in {result.duration_ms}ms."
            if result.success
            else f"Tests failed with exit code {result.exit_code}.\nTraceback/Error: {result.traceback or result.stderr or 'No explicit traceback'}"
        )

        return ToolResult(
            success=result.success,
            data=result.model_dump(),
            message=msg,
        )
    except Exception as exc:
        return ToolResult(success=False, error=f"Sandbox test execution error: {exc}")
