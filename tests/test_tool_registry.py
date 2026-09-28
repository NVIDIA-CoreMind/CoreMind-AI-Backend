import asyncio
import shutil
from pathlib import Path
import pytest
from app.tools.registry import ToolRegistry, CORE_MIND_TOOLS

TEST_DIR = Path(__file__).resolve().parent / "reg_test_dir"


@pytest.fixture(autouse=True)
def setup_teardown():
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    yield
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR, ignore_errors=True)


def test_tools_schema_definitions():
    registry = ToolRegistry()
    tools = registry.get_tools()

    assert len(tools) == 5
    names = [t["function"]["name"] for t in tools]
    assert "read_file" in names
    assert "write_file" in names
    assert "apply_diff" in names
    assert "run_sandbox_python" in names
    assert "run_sandbox_tests" in names


def test_unknown_tool_rejection():
    async def _test():
        registry = ToolRegistry()
        res = await registry.execute_tool("invalid_tool_name", {}, TEST_DIR)
        assert res.success is False
        assert "Unsupported tool" in res.error

    asyncio.run(_test())
