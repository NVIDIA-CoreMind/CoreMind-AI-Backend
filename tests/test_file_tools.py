import asyncio
import shutil
from pathlib import Path
import pytest
from app.tools.file_tools import (
    execute_read_file,
    execute_write_file,
    execute_apply_diff,
    resolve_safe_path,
)

TEST_WORKSPACE = Path(__file__).resolve().parent / "workspace_test_dir"


@pytest.fixture(autouse=True)
def setup_teardown_workspace():
    TEST_WORKSPACE.mkdir(parents=True, exist_ok=True)
    yield
    if TEST_WORKSPACE.exists():
        shutil.rmtree(TEST_WORKSPACE, ignore_errors=True)


def test_reject_path_traversal():
    with pytest.raises(PermissionError):
        resolve_safe_path(TEST_WORKSPACE, "../../outside_secret.txt")


def test_write_and_read_file_with_range():
    async def _test():
        lines = ["first line", "second line", "third line", "fourth line", "fifth line"]
        content = "\n".join(lines)

        write_res = await execute_write_file(TEST_WORKSPACE, "nested/sample.txt", content)
        assert write_res.success is True
        assert write_res.data["bytes_written"] > 0

        # Full read
        full_read = await execute_read_file(TEST_WORKSPACE, "nested/sample.txt")
        assert full_read.success is True
        assert full_read.data["content"] == content
        assert full_read.data["total_lines"] == 5

        # Range read lines 2 to 4
        range_read = await execute_read_file(TEST_WORKSPACE, "nested/sample.txt", start_line=2, end_line=4)
        assert range_read.success is True
        assert "2: second line" in range_read.data["content"]
        assert "4: fourth line" in range_read.data["content"]
        assert "1: first line" not in range_read.data["content"]

    asyncio.run(_test())


def test_apply_search_replace_diff():
    async def _test():
        original_code = "def subtract(a, b):\n    return a - b\n"
        await execute_write_file(TEST_WORKSPACE, "math_ops.py", original_code)

        patch = """<<<<<<< SEARCH
def subtract(a, b):
    return a - b
=======
def subtract(a, b):
    return a + b
>>>>>>>"""

        diff_res = await execute_apply_diff(TEST_WORKSPACE, "math_ops.py", patch)
        assert diff_res.success is True

        updated_file = await execute_read_file(TEST_WORKSPACE, "math_ops.py")
        assert "return a + b" in updated_file.data["content"]

    asyncio.run(_test())
