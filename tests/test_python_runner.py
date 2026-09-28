import asyncio
import shutil
from pathlib import Path
import pytest
from app.sandbox.python_runner import PythonRunner

TEST_SANDBOX_DIR = Path(__file__).resolve().parent / "sandbox_test_dir"


@pytest.fixture(autouse=True)
def setup_teardown_sandbox():
    TEST_SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    yield
    if TEST_SANDBOX_DIR.exists():
        shutil.rmtree(TEST_SANDBOX_DIR, ignore_errors=True)


def test_run_valid_python_code():
    async def _test():
        runner = PythonRunner(work_dir=TEST_SANDBOX_DIR)
        code = 'print("CoreMind Python Sandbox Active")\nprint(20 + 22)'
        result = await runner.run_code(code=code)

        assert result.success is True
        assert result.exit_code == 0
        assert "CoreMind Python Sandbox Active" in result.stdout
        assert "42" in result.stdout
        assert result.traceback is None

    asyncio.run(_test())


def test_capture_traceback_on_error():
    async def _test():
        runner = PythonRunner(work_dir=TEST_SANDBOX_DIR)
        code = "def divide(a, b):\n    return a / b\n\ndivide(10, 0)"
        result = await runner.run_code(code=code)

        assert result.success is False
        assert result.exit_code != 0
        assert result.traceback is not None
        assert "ZeroDivisionError" in result.traceback

    asyncio.run(_test())


def test_execution_timeout():
    async def _test():
        runner = PythonRunner(work_dir=TEST_SANDBOX_DIR)
        code = "import time\ntime.sleep(5)"
        result = await runner.run_code(code=code, timeout_ms=800)

        assert result.success is False
        assert result.exit_code == 124
        assert "[Sandbox Timeout]" in result.stderr

    asyncio.run(_test())
