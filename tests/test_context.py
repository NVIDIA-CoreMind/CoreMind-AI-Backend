"""
Tests for the Context Manager and Compaction.
"""

from src.context.compaction import compact_messages
from src.context.context_manager import ContextManager


class TestCompaction:
    """Test context compaction."""

    def test_no_compaction_when_under_limit(self) -> None:
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        result = compact_messages(messages, max_tokens=1000)
        assert len(result) == 3

    def test_compaction_truncates_tool_results(self) -> None:
        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Task"},
        ]
        # Add many large tool results
        for i in range(20):
            messages.append({"role": "tool", "content": "X" * 2000, "tool_call_id": f"tc_{i}"})
            messages.append({"role": "assistant", "content": f"Response {i}"})

        result = compact_messages(messages, max_tokens=500)
        # Should be smaller than the original
        assert len(result) < len(messages)

    def test_empty_messages_handled(self) -> None:
        result = compact_messages([], max_tokens=1000)
        assert result == []

    def test_compaction_handles_none_content(self) -> None:
        from typing import Any
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Task"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1"}]},
        ]
        result = compact_messages(messages, max_tokens=1000)
        assert len(result) == 3


class TestContextManager:
    """Test context manager functionality."""

    def test_add_messages(self) -> None:
        cm = ContextManager("/fake/project")
        cm.add_user_message("Hello")
        cm.add_assistant_message("Hi there")
        assert cm.message_count == 2

    def test_build_messages_with_none_assistant_content(self) -> None:
        cm = ContextManager("/fake/project")
        cm.add_assistant_message(None, tool_calls=[{"id": "c1"}])
        messages = cm.build_messages("test task")
        assert len(messages) >= 2

    def test_record_file_changed(self) -> None:
        cm = ContextManager("/fake/project")
        cm.record_file_changed("src/main.py")
        cm.record_file_changed("src/utils.py")
        cm.record_file_changed("src/main.py")  # Duplicate
        assert len(cm.files_changed) == 2

    def test_clear(self) -> None:
        cm = ContextManager("/fake/project")
        cm.add_user_message("Hello")
        cm.record_file_changed("test.py")
        cm.clear()
        assert cm.message_count == 0
        assert len(cm.files_changed) == 0
