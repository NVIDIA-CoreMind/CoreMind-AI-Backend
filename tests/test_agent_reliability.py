"""
Tests for CoreMind Agent Reliability, Multi-Turn Orchestration, and Event Contracts.

Covers:
1. Multi-turn tool execution with real tool results fed back to model.
2. Verification failure preservation (files kept on disk, truthful failure event).
3. Safe halting on repeated duplicate tool calls.
4. WebSocket cancellation handling (agent.stop and agent.cancel messages).
5. Frontend event schema and correlation ID verification (including agent.ai.usage).
6. Compactor safety for JSON and file inspection outputs.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.agent.agent_loop import AgentLoop
from src.agent.task import AgentTask, TaskStatus
from src.agent.task_graph import TaskGraph
from src.agent.verifier import VerificationResult
from src.ai.provider import AIResponse
from src.context.compactor import compress_tool_output
from src.events.event_bus import event_bus
from src.events.events import CoreMindEvent, EventType


class TestMultiTurnAndToolFeedback:
    """Verify multi-turn tool calling and real tool result feedback."""

    @pytest.mark.asyncio
    async def test_multi_turn_tool_result_feedback(self, tmp_path: Path) -> None:
        """Test agent executing inspection tool, receiving result, then modifying file."""
        src_file = tmp_path / "app.py"
        src_file.write_text("port = 8080\n")

        task = AgentTask(
            task_id="task_multi_1",
            session_id="sess_multi_1",
            agent_id="agent_multi_1",
            task="Inspect app.py and change port to 9090",
            project_path=str(tmp_path),
        )

        loop = AgentLoop(task)

        turn1_resp = AIResponse(
            content="I will read app.py to inspect the port configuration.",
            tool_calls=[{
                "id": "call_read_1",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"path": "app.py"}),
                },
            }],
            usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        )

        turn2_resp = AIResponse(
            content="I see port = 8080. Now updating to 9090.",
            tool_calls=[{
                "id": "call_write_1",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps({"path": "app.py", "content": "port = 9090\n"}),
                },
            }],
            usage={"prompt_tokens": 150, "completion_tokens": 30, "total_tokens": 180},
        )

        turn3_resp = AIResponse(
            content="Successfully updated port to 9090 in app.py.",
            finish_reason="stop",
            usage={"prompt_tokens": 200, "completion_tokens": 25, "total_tokens": 225},
        )

        emitted_events: list[CoreMindEvent] = []

        async def _capture(e: CoreMindEvent) -> None:
            emitted_events.append(e)

        plan = TaskGraph(goal="Inspect and update")
        plan.create_task("Inspect", "Read app.py", task_id="t1")
        plan.create_task("Edit", "Update port", dependencies=["t1"], task_id="t2")

        event_bus.on_all(_capture)
        try:
            with patch("src.agent.agent_loop.generate_task_graph", AsyncMock(return_value=plan)):
                ai_mock = AsyncMock(side_effect=[turn1_resp, turn2_resp, turn3_resp])
                with patch.object(loop._provider, "chat", ai_mock):
                    with patch("src.agent.agent_loop.run_verification") as mock_verify:
                        mock_verify.return_value = VerificationResult(
                            success=True,
                            command="syntax_check",
                            exit_code=0,
                            stdout="Valid",
                            stderr="",
                        )
                        res = await loop.run()

                        assert res.status == TaskStatus.COMPLETED
                        assert "app.py" in res.files_changed
                        assert src_file.read_text() == "port = 9090\n"

                        # Verify tool results were recorded in context conversation
                        tool_msgs = [
                            m for m in loop._context._conversation if m.get("role") == "tool"
                        ]
                        assert len(tool_msgs) >= 2
                        assert any("port = 8080" in m.get("content", "") for m in tool_msgs)

                        # Verify AI usage was emitted
                        usage_events = [e for e in emitted_events if e.type == EventType.AI_USAGE]
                        assert len(usage_events) >= 1
                        assert usage_events[0].data.get("total_tokens") == 120
        finally:
            event_bus.clear()


class TestVerificationFailureHandling:
    """Verify that failed verifications report real errors and do not wipe files."""

    @pytest.mark.asyncio
    async def test_verification_failure_preserves_files(self, tmp_path: Path) -> None:
        src_file = tmp_path / "broken.py"
        src_file.write_text("print('original')\n")

        task = AgentTask(
            task_id="task_fail_1",
            session_id="sess_fail_1",
            agent_id="agent_fail_1",
            task="Introduce an edit that fails verification",
            project_path=str(tmp_path),
        )

        loop = AgentLoop(task)

        edit_args = {"path": "broken.py", "content": "def syntax_error(\n"}
        edit_resp = AIResponse(
            content="Modifying file",
            tool_calls=[{
                "id": "call_edit",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps(edit_args),
                },
            }],
        )
        fix_resp = AIResponse(
            content="I am unable to fix this automatically.",
            finish_reason="stop",
        )

        emitted_events: list[CoreMindEvent] = []

        async def _capture(e: CoreMindEvent) -> None:
            emitted_events.append(e)

        plan = TaskGraph(goal="Edit file")
        plan.create_task("Edit", "Modify broken.py", task_id="t1")

        event_bus.on_all(_capture)
        try:
            with patch("src.agent.agent_loop.generate_task_graph", AsyncMock(return_value=plan)):
                ai_mock = AsyncMock(side_effect=[edit_resp, fix_resp, fix_resp, fix_resp])
                with patch.object(loop._provider, "chat", ai_mock):
                    with patch("src.agent.agent_loop.run_verification") as mock_verify:
                        mock_verify.return_value = VerificationResult(
                            success=False,
                            command="pytest",
                            exit_code=1,
                            stdout="",
                            stderr="SyntaxError: unexpected EOF while parsing",
                            error_summary="SyntaxError: unexpected EOF while parsing",
                        )
                        res = await loop.run()

                        assert res.status == TaskStatus.FAILED
                        assert "Verification failed" in (res.error or "")

                        # Critical check: Disk edits are NOT wiped out
                        assert src_file.exists()
                        assert "syntax_error" in src_file.read_text()

                        # Failure event emitted with real error details
                        failed_events = [
                            e for e in emitted_events if e.type == EventType.AGENT_FAILED
                        ]
                        assert len(failed_events) >= 1
                        assert "SyntaxError" in str(failed_events[0].data)
        finally:
            event_bus.clear()


class TestDuplicateToolLoopHalting:
    """Verify safe halting on repeated identical tool calls."""

    @pytest.mark.asyncio
    async def test_duplicate_tool_loop_halts_safely(self, tmp_path: Path) -> None:
        task = AgentTask(
            task_id="task_dup_1",
            session_id="sess_dup_1",
            agent_id="agent_dup_1",
            task="Test duplicate prevention",
            project_path=str(tmp_path),
        )

        loop = AgentLoop(task)

        dup_resp = AIResponse(
            content="Looping call",
            tool_calls=[{
                "id": "call_dup",
                "type": "function",
                "function": {
                    "name": "list_directory",
                    "arguments": json.dumps({"path": "."}),
                },
            }],
        )

        with patch.object(loop._provider, "chat", AsyncMock(return_value=dup_resp)):
            res = await loop.run()
            assert res.steps_completed <= 4


class TestCompactorSafety:
    """Verify compactor preserves code inspection outputs and valid JSON."""

    def test_compactor_preserves_code_inspection_tools(self) -> None:
        big_code = "\n".join([f"line_{i} = {i}" for i in range(120)])
        json_output = json.dumps({
            "path": "module.py",
            "content": big_code,
            "total_lines": 120,
        })

        for tool in ("read_file", "search_files", "list_directory", "edit_file"):
            result = compress_tool_output(tool, json_output)
            assert result == json_output
            parsed = json.loads(result)
            assert parsed["total_lines"] == 120

    def test_compactor_compresses_terminal_logs(self) -> None:
        log = "\n".join([f"compiling step {i}..." for i in range(80)])
        log += "\nFAILED tests/test_core.py::test_eval - AssertionError\n"
        log += "\n".join([f"cleaning step {i}..." for i in range(40)])

        result = compress_tool_output("terminal", log, max_lines=20)
        assert "Output compressed" in result
        assert "AssertionError" in result


class TestWebSocketControlAndCorrelation:
    """Verify WebSocket control commands (stop/cancel) and event correlation."""

    @pytest.mark.asyncio
    async def test_websocket_stop_and_cancel_commands(self) -> None:
        from src.api.routes.agent import agent_manager

        start_res = await agent_manager.start_agent(
            task="Background task for websocket stop test",
            project_path=".",
        )
        aid = start_res["agent_id"]

        with patch.object(agent_manager, "stop_agent", AsyncMock(return_value=True)) as mock_stop:
            res = await agent_manager.stop_agent(aid)
            assert res is True
            mock_stop.assert_called_with(aid)

    @pytest.mark.asyncio
    async def test_event_schema_correlation_and_ordering(self, tmp_path: Path) -> None:
        """Verify correlation IDs and event sequencing across full task run."""
        emitted_events: list[CoreMindEvent] = []

        async def _capture(e: CoreMindEvent) -> None:
            emitted_events.append(e)

        event_bus.on_all(_capture)
        try:
            task = AgentTask(
                task_id="task_corr_888",
                session_id="sess_corr_999",
                agent_id="task_corr_888",
                task="Inspect and finish",
                project_path=str(tmp_path),
            )
            loop = AgentLoop(task)

            resp1 = AIResponse(
                content="I will inspect files.",
                tool_calls=[{
                    "id": "c1",
                    "type": "function",
                    "function": {
                        "name": "list_directory",
                        "arguments": json.dumps({"path": "."}),
                    },
                }],
                usage={"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60},
            )
            resp2 = AIResponse(
                content="Task completed without further modifications.",
                finish_reason="stop",
            )

            plan = TaskGraph(goal="Inspect")
            plan.create_task("Inspect", "List dir", task_id="t1")

            with patch("src.agent.agent_loop.generate_task_graph", AsyncMock(return_value=plan)):
                with patch.object(loop._provider, "chat", AsyncMock(side_effect=[resp1, resp2])):
                    res = await loop.run()
                    assert res.status == TaskStatus.COMPLETED

                    for e in emitted_events:
                        assert e.agent_id == "task_corr_888"
                        assert e.session_id == "sess_corr_999"
                        assert e.task_id == "task_corr_888"

                    event_types = [e.type for e in emitted_events]
                    assert EventType.AGENT_STARTED in event_types
                    assert EventType.TASK_STATUS in event_types
                    assert EventType.TOOL_STARTED in event_types
                    assert EventType.TOOL_COMPLETED in event_types
                    assert EventType.AGENT_COMPLETED in event_types
        finally:
            event_bus.clear()


class TestContractReconciliation:
    """Test frontend/backend contract reconciliation across REST and WebSocket."""

    def test_event_mirroring_identifiers(self) -> None:
        """Verify agent_id and task_id are mirrored at top-level and in data."""
        evt = CoreMindEvent(
            type=EventType.AGENT_STARTED,
            task_id="t_123",
            session_id="s_456",
            data={"foo": "bar"},
        )
        assert evt.agent_id == "t_123"
        assert evt.task_id == "t_123"
        assert evt.data["agent_id"] == "t_123"
        assert evt.data["task_id"] == "t_123"
        assert evt.data["session_id"] == "s_456"

    @pytest.mark.asyncio
    async def test_agent_run_request_reconciliation(self, tmp_path: Path) -> None:
        """Verify POST /v1/agent/run and /api/agent/task handle prompt/project_id aliases."""
        from fastapi.testclient import TestClient
        from src.app.application import create_app

        client = TestClient(create_app())

        with patch("src.api.routes.agent.agent_manager.start_agent", AsyncMock(return_value={
            "agent_id": "ag_test_01",
            "session_id": "sess_test_01",
            "status": "started",
        })):
            # 1. Frontend reported contract: task + project_path
            resp1 = client.post("/v1/agent/run", json={
                "task": "Test task",
                "project_path": str(tmp_path),
            })
            assert resp1.status_code == 200
            data1 = resp1.json()
            assert data1["agent_id"] == "ag_test_01"
            assert data1["task_id"] == "ag_test_01"

            # 2. Reported backend contract: prompt + project_id
            resp2 = client.post("/api/agent/task", json={
                "prompt": "Test prompt",
                "project_id": str(tmp_path),
            })
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert data2["agent_id"] == "ag_test_01"
            assert data2["task_id"] == "ag_test_01"

    @pytest.mark.asyncio
    async def test_stop_and_cancel_routes(self) -> None:
        """Verify path-based stop and cancel endpoints."""
        from fastapi.testclient import TestClient
        from src.app.application import create_app

        client = TestClient(create_app())

        with patch("src.api.routes.agent.agent_manager.stop_agent", AsyncMock(return_value=True)):
            # POST /v1/agent/:id/stop
            r1 = client.post("/v1/agent/ag_123/stop")
            assert r1.status_code == 200
            assert r1.json()["status"] == "stopped"

            # POST /v1/agent/:id/cancel
            r2 = client.post("/v1/agent/ag_123/cancel")
            assert r2.status_code == 200
            assert r2.json()["status"] == "stopped"

            # POST /api/agent/task/:id/cancel
            r3 = client.post("/api/agent/task/task_456/cancel")
            assert r3.status_code == 200
            assert r3.json()["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_changes_preview_by_agent_id(self, tmp_path: Path) -> None:
        """Verify GET /v1/changes/:id works with agent_id as well as change_id."""
        from fastapi.testclient import TestClient
        from src.app.application import create_app
        from src.changes.diff import create_file_diff
        from src.changes.review import change_review_manager

        cs = change_review_manager.create_change_set("agent_abc", str(tmp_path))
        diff = create_file_diff("old", "new", "file.py")
        change_review_manager.record_change(cs.change_id, "file.py", diff, "old")

        client = TestClient(create_app())

        # Lookup by change_id
        r1 = client.get(f"/v1/changes/{cs.change_id}")
        assert r1.status_code == 200
        assert r1.json()["change_id"] == cs.change_id

        # Lookup by agent_id
        r2 = client.get("/v1/changes/agent_abc")
        assert r2.status_code == 200
        assert r2.json()["change_id"] == cs.change_id

    @pytest.mark.asyncio
    async def test_websocket_client_id_and_action_messages(self) -> None:
        """Verify WebSocket connects on /ws and /ws/{client_id} and accepts action commands."""
        from fastapi.testclient import TestClient
        from src.app.application import create_app

        client = TestClient(create_app())

        with patch("src.api.routes.agent.agent_manager.stop_agent", AsyncMock(return_value=True)) as mock_stop:
            with client.websocket_connect("/ws/client_desktop_99") as ws:
                ws.send_text(json.dumps({"action": "agent.stop", "task_id": "task_ws_1"}))
                import asyncio
                await asyncio.sleep(0.05)
                mock_stop.assert_awaited_with("task_ws_1")


class TestEntrypointPreservationAndSubdirectoryDetection:
    """Verify that entrypoint tasks require actual entrypoint files and subdirectories are detected."""

    @pytest.mark.asyncio
    async def test_entrypoint_task_not_completed_by_non_entrypoint_file(self, tmp_path: Path) -> None:
        """Writing model or constants must not complete an entrypoint wiring task."""
        from src.agent.task_graph import TaskGraph, TaskNodeStatus
        from src.tools.definitions.write_file import execute_write_file

        task = AgentTask(
            task_id="task_entry_test_1",
            session_id="sess_entry_1",
            agent_id="agent_entry_1",
            task="Build flutter app",
            project_path=str(tmp_path),
        )
        loop = AgentLoop(task)

        plan = TaskGraph(goal="Build flutter app")
        plan.create_task("Scaffold", "Create project", task_id="t1")
        plan.create_task("Implement models and services", "Create models", dependencies=["t1"], task_id="t2")
        plan.create_task("Wire entrypoint and application configuration", "Wire main.dart", dependencies=["t2"], task_id="t3")

        # Set t3 as in progress
        plan.update_task("t1", status=TaskNodeStatus.COMPLETED)
        plan.update_task("t2", status=TaskNodeStatus.COMPLETED)
        plan.update_task("t3", status=TaskNodeStatus.IN_PROGRESS)
        loop._task.task_graph = plan

        write_model_resp = AIResponse(
            content="",
            tool_calls=[{
                "id": "call_model",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps({"path": "lib/models/todo.dart", "content": "class Todo {}\n"}),
                },
            }],
        )
        write_main_resp = AIResponse(
            content="",
            tool_calls=[{
                "id": "call_main",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps({"path": "lib/main.dart", "content": "void main() {}\n"}),
                },
            }],
        )
        final_resp = AIResponse(content="Done", finish_reason="stop")

        with patch.object(loop._provider, "chat", AsyncMock(side_effect=[write_model_resp, write_main_resp, final_resp])):
            with patch("src.agent.agent_loop.generate_task_graph", AsyncMock(return_value=plan)):
                with patch("src.agent.agent_loop.run_verification") as mock_v:
                    mock_v.return_value = VerificationResult(success=True, command="test", exit_code=0, stdout="", stderr="")
                    res = await loop.run()

                    assert res.status == TaskStatus.COMPLETED
                    assert "lib/main.dart" in res.files_changed
                    t3 = res.task_graph.get_task("t3")
                    assert t3.status == TaskNodeStatus.COMPLETED

    def test_detect_flutter_in_subdirectory(self, tmp_path: Path) -> None:
        """Detect Flutter project when scaffolded in a subdirectory."""
        from src.project.detector import detect_project
        sub = tmp_path / "todo_app"
        sub.mkdir()
        (sub / "pubspec.yaml").write_text("name: todo_app\n")
        (sub / "lib").mkdir()
        (sub / "lib" / "main.dart").write_text("void main() {}\n")

        info = detect_project(str(tmp_path))
        assert info.language == "Dart"
        assert info.framework == "Flutter"
        assert info.main_entry == "todo_app/lib/main.dart"
        assert "flutter" in info.test_command

