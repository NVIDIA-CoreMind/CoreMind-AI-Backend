import asyncio
import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.agent.execution_engine import ExecutionEngine
from app.agent.state_machine import AgentPhase
from app.sandbox.python_runner import PythonRunner
from app.tools.registry import ToolRegistry

TEST_ENGINE_DIR = Path(__file__).resolve().parent / "engine_test_dir"


@pytest.fixture(autouse=True)
def setup_teardown():
    TEST_ENGINE_DIR.mkdir(parents=True, exist_ok=True)
    yield
    if TEST_ENGINE_DIR.exists():
        shutil.rmtree(TEST_ENGINE_DIR, ignore_errors=True)


def test_execution_engine_mock_loop():
    async def _test():
        call_count = 0

        async def mock_create_chat_completion(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            mock_resp = MagicMock()
            choice = MagicMock()
            msg = MagicMock()

            if call_count == 1:
                msg.content = "[PHASE: PLAN]\nI will write a Python script to compute factorial."
                tc = MagicMock()
                tc.id = "call_1"
                tc.function.name = "write_file"
                tc.function.arguments = json.dumps({
                    "path": "fact.py",
                    "content": "def fact(n):\n    return 1 if n <= 1 else n * fact(n-1)\nprint('FACT_RESULT:', fact(5))\n",
                })
                msg.tool_calls = [tc]
            elif call_count == 2:
                msg.content = "[PHASE: RUN]\nRunning fact.py in sandbox."
                tc = MagicMock()
                tc.id = "call_2"
                tc.function.name = "run_sandbox_python"
                tc.function.arguments = json.dumps({"script_path": "fact.py"})
                msg.tool_calls = [tc]
            else:
                msg.content = "[PHASE: VERIFY]\nFactorial computation verified. FACT_RESULT: 120."
                msg.tool_calls = None

            choice.message = msg
            mock_resp.choices = [choice]
            return mock_resp

        mock_nebius = MagicMock()
        mock_nebius.create_chat_completion = AsyncMock(side_effect=mock_create_chat_completion)

        runner = PythonRunner(work_dir=TEST_ENGINE_DIR)
        registry = ToolRegistry(runner)
        engine = ExecutionEngine(nebius_client=mock_nebius, tool_registry=registry)

        phases_seen = []
        result = await engine.run_agent_loop(
            task="Compute factorial of 5 in Python",
            workspace_path=TEST_ENGINE_DIR,
            on_event=lambda t, p: phases_seen.append(p["to"]) if t == "phase_change" else None,
        )

        assert result["success"] is True
        assert result["final_phase"] == AgentPhase.COMPLETED.value
        assert result["iterations"] == 3
        assert AgentPhase.TASK.value in phases_seen
        assert AgentPhase.PLAN.value in phases_seen
        assert AgentPhase.CODE.value in phases_seen
        assert AgentPhase.RUN.value in phases_seen
        assert AgentPhase.VERIFY.value in phases_seen
        assert AgentPhase.COMPLETED.value in phases_seen

        # Verify fact.py was created
        created_file = TEST_ENGINE_DIR / "fact.py"
        assert created_file.exists()
        assert "fact(5)" in created_file.read_text(encoding="utf-8")

    asyncio.run(_test())
