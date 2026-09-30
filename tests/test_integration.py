"""
End-to-End Integration Tests for CoreMind Backend.

Tests complete agent lifecycle and all REST API endpoints.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from src.agent.agent_loop import AgentLoop
from src.agent.task import AgentTask, TaskStatus
from src.ai.provider import AIResponse
from src.app.application import create_app


@pytest.fixture
def api_client():
    app = create_app()
    return TestClient(app)


class TestApiEndpoints:
    """Test REST API routes."""

    def test_health_check(self, api_client: TestClient) -> None:
        response = api_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "coremind-backend"

    def test_project_endpoints(self, api_client: TestClient, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("print('hello world')\n")

        # Open project
        res_open = api_client.post("/v1/project/open", json={"path": str(tmp_path)})
        assert res_open.status_code == 200
        assert res_open.json()["name"] == tmp_path.name

        # Tree
        res_tree = api_client.get(f"/v1/project/tree?path={tmp_path}")
        assert res_tree.status_code == 200
        assert "tree" in res_tree.json()

        # Search
        res_search = api_client.get(f"/v1/project/search?path={tmp_path}&query=hello")
        assert res_search.status_code == 200
        assert res_search.json()["total"] > 0

        # Repo Map
        res_map = api_client.get(f"/v1/project/repo_map?path={tmp_path}")
        assert res_map.status_code == 200
        assert "summary" in res_map.json()

    def test_terminal_session_api(self, api_client: TestClient, tmp_path: Path) -> None:
        # Create session
        res = api_client.post("/v1/terminal/session", json={"project_path": str(tmp_path)})
        assert res.status_code == 200
        sid = res.json()["session_id"]

        # Execute
        res_exec = api_client.post(f"/v1/terminal/session/{sid}/execute", json={"command": "echo test_terminal_api"})
        assert res_exec.status_code == 200
        assert "test_terminal_api" in res_exec.json()["stdout"]

        # Delete session
        res_del = api_client.delete(f"/v1/terminal/session/{sid}")
        assert res_del.status_code == 200


class TestAgentCompleteLifecycle:
    """Test full Understand -> Plan -> Search -> Edit -> Verify -> Complete workflow."""

    @pytest.mark.asyncio
    async def test_end_to_end_agent_workflow(self, tmp_path: Path) -> None:
        # Setup initial project file
        code_file = tmp_path / "calculator.py"
        code_file.write_text("def add(a, b):\n    return a - b  # Bug: minus instead of plus\n")

        test_file = tmp_path / "test_calc.py"
        test_file.write_text("from calculator import add\ndef test_add():\n    assert add(2, 3) == 5\n")

        task = AgentTask(
            task_id="task_int_1",
            session_id="session_int_1",
            agent_id="agent_int_1",
            task="Fix the addition bug in calculator.py so that test_calc passes.",
            project_path=str(tmp_path),
        )

        agent_loop = AgentLoop(task)

        # Mock AI responses to simulate:
        # 1. read_file calculator.py
        # 2. edit_file calculator.py
        # 3. completion

        responses = [
            # Step 1: Tool call read_file
            AIResponse(
                content="I will read calculator.py first.",
                tool_calls=[{
                    "id": "tc_1",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "calculator.py"}',
                    },
                }],
            ),
            # Step 2: Tool call edit_file
            AIResponse(
                content="I will fix the bug in calculator.py.",
                tool_calls=[{
                    "id": "tc_2",
                    "type": "function",
                    "function": {
                        "name": "edit_file",
                        "arguments": '{"path": "calculator.py", "old_content": "return a - b", "new_content": "return a + b"}',
                    },
                }],
            ),
            # Step 3: Complete
            AIResponse(
                content="I have fixed the addition logic in calculator.py.",
                finish_reason="stop",
            ),
        ]

        with patch.object(agent_loop._provider, "chat", AsyncMock(side_effect=responses)):
            with patch("src.agent.agent_loop.run_verification") as mock_verify:
                from src.agent.verifier import VerificationResult
                mock_verify.return_value = VerificationResult(
                    success=True,
                    command="pytest",
                    exit_code=0,
                    stdout="1 passed in 0.01s",
                    stderr="",
                )

                completed_task = await agent_loop.run()

                assert completed_task.status == TaskStatus.COMPLETED
                assert "calculator.py" in completed_task.files_changed
                assert "return a + b" in code_file.read_text()
                assert completed_task.task_graph.is_completed()
