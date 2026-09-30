"""
Tests for Phase 3: Ask User, Persistent Terminal, Background Processes, Git Checkpoints, Change Review.
"""

import asyncio
from pathlib import Path
import pytest

from src.agent.checkpoint import checkpoint_manager
from src.changes.diff import create_file_diff
from src.changes.review import change_review_manager
from src.terminal.process_manager import process_manager
from src.terminal.session import terminal_session_manager
from src.tools.definitions.ask_question import question_manager


class TestChangeReview:
    """Test change sets, preview, accept, and reject operations."""

    def test_change_set_lifecycle(self, tmp_path: Path) -> None:
        target = tmp_path / "main.py"
        target.write_text("print('version 1')\n")

        cs = change_review_manager.create_change_set("agent_1", str(tmp_path))
        diff = create_file_diff("print('version 1')\n", "print('version 2')\n", "main.py")
        change_review_manager.record_change(cs.change_id, "main.py", diff, "print('version 1')\n")

        # Apply edit to disk
        target.write_text("print('version 2')\n")

        # Preview
        preview = change_review_manager.preview_changes(cs.change_id)
        assert preview is not None
        assert len(preview["files"]) == 1
        assert preview["files"][0]["path"] == "main.py"

        # Rejection reverts disk content
        success = change_review_manager.reject_changes(cs.change_id)
        assert success
        assert target.read_text() == "print('version 1')\n"


class TestCheckpointManager:
    """Test checkpoint creation and isolated AI rollback."""

    @pytest.mark.asyncio
    async def test_checkpoint_and_rollback(self, tmp_path: Path) -> None:
        user_file = tmp_path / "user.txt"
        user_file.write_text("user content unchanged\n")

        ai_file = tmp_path / "feature.py"
        ai_file.write_text("original feature\n")

        cp = await checkpoint_manager.create_checkpoint(str(tmp_path))
        checkpoint_manager.record_file_before_edit(cp, "feature.py")

        # AI modifies feature.py
        ai_file.write_text("ai modified feature with bug\n")

        # Rollback
        await checkpoint_manager.rollback(cp)

        # ai_file restored, user_file preserved
        assert ai_file.read_text() == "original feature\n"
        assert user_file.read_text() == "user content unchanged\n"


class TestQuestionManager:
    """Test ask-user question pause and resume."""

    @pytest.mark.asyncio
    async def test_question_flow(self) -> None:
        async def answer_later(qid: str):
            await asyncio.sleep(0.05)
            question_manager.answer_question(qid, "Firebase Auth")

        loop = asyncio.get_running_loop()
        task = loop.create_task(question_manager.ask("agent_test", "Which auth to use?", ["Firebase Auth", "REST"]))

        await asyncio.sleep(0.01)
        # Check pending question exists
        pending = question_manager.get_pending("agent_test")

        assert len(pending) == 1
        qid = pending[0]["question_id"]

        loop.create_task(answer_later(qid))
        answer = await task
        assert answer == "Firebase Auth"


class TestTerminalSession:
    """Test persistent terminal session maintaining CWD."""

    @pytest.mark.asyncio
    async def test_session_maintains_cwd(self, tmp_path: Path) -> None:
        sub = tmp_path / "subfolder"
        sub.mkdir()

        session = terminal_session_manager.create_session(str(tmp_path))
        try:
            # Change directory
            res1 = await session.execute("cd subfolder")
            assert res1["success"]
            assert res1["cwd"].endswith("subfolder")

            # Check pwd in next command
            res2 = await session.execute("pwd")
            assert res2["success"]
            assert "subfolder" in res2["stdout"]
        finally:
            terminal_session_manager.delete_session(session.session_id)


class TestProcessManager:
    """Test background process lifecycle."""

    @pytest.mark.asyncio
    async def test_process_lifecycle(self, tmp_path: Path) -> None:
        res = await process_manager.start_process("sleep 10", str(tmp_path))
        pid = res.get("process_id")
        assert pid is not None

        status = process_manager.get_process_status(pid)
        assert status is not None
        assert status["status"] == "running"

        stopped = await process_manager.stop_process(pid)
        assert stopped
        status_after = process_manager.get_process_status(pid)
        assert status_after is not None
        assert status_after["status"] == "stopped"
