"""
CoreMind Backend — Context Manager.

Assembles layered context for Nemotron requests:

    System Context
          +
    Project Context
          +
    Task Context
          +
    Conversation Context
          +
    Relevant File Context
          +
    Tool Results
          ↓
    Nemotron

Never sends the entire repository. Uses compaction when context grows too large.
"""

from __future__ import annotations

from typing import Any

from src.ai.prompts.coding import build_coding_context
from src.ai.prompts.system import get_system_prompt
from src.config import settings
from src.context.compaction import compact_messages
from src.project.project_manager import project_manager
from src.utils.logger import logger

# Approximate token limit for context (conservative estimate)
MAX_CONTEXT_TOKENS = 100_000
# Characters-to-tokens ratio (rough estimate)
CHARS_PER_TOKEN = 4


class ContextManager:
    """Assembles and manages layered context for AI requests."""

    def __init__(self, project_path: str) -> None:
        self._project_path = project_path
        self._conversation: list[dict[str, Any]] = []
        self._tool_results: list[dict[str, Any]] = []
        self._files_read: dict[str, str] = {}
        self._files_changed: list[str] = []

    def build_messages(self, user_task: str | None = None) -> list[dict[str, Any]]:
        """
        Build the full message list for a Nemotron request.

        Layers:
        1. System prompt
        2. Project context (as a system message)
        3. User task
        4. Conversation history + tool results
        """
        messages: list[dict[str, Any]] = []

        # Layer 1: System prompt
        messages.append({
            "role": "system",
            "content": get_system_prompt(max_steps=settings.max_agent_steps),
        })

        # Layer 2: Project context
        project_info = project_manager.get_project(self._project_path)
        if project_info:
            ctx = build_coding_context(
                project_name=project_info.get("name", "Unknown"),
                language=project_info.get("language", "Unknown"),
                framework=project_info.get("framework", "Unknown"),
                package_manager=project_info.get("package_manager", "Unknown"),
                main_entry=project_info.get("main_entry", ""),
                test_command=project_info.get("test_command", ""),
                files_changed=self._files_changed,
            )
            messages.append({"role": "system", "content": ctx})

        # Layer 3: User task (if first message)
        if user_task and not self._conversation:
            messages.append({"role": "user", "content": user_task})

        # Layer 4: Conversation history
        messages.extend(self._conversation)

        # Compact if too large
        estimated_tokens = sum(len(m.get("content", "")) for m in messages) // CHARS_PER_TOKEN
        if estimated_tokens > MAX_CONTEXT_TOKENS:
            logger.warn(
                "context.compacting",
                estimated_tokens=estimated_tokens,
                max_tokens=MAX_CONTEXT_TOKENS,
            )
            messages = compact_messages(messages, MAX_CONTEXT_TOKENS)

        return messages

    def add_user_message(self, content: str) -> None:
        """Add a user message to the conversation."""
        self._conversation.append({"role": "user", "content": content})

    def add_assistant_message(
        self,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        """Add an assistant message to the conversation."""
        msg: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self._conversation.append(msg)

    def add_tool_result(
        self,
        tool_call_id: str,
        tool_name: str,
        result: str,
    ) -> None:
        """Add a tool result to the conversation."""
        self._conversation.append({
            "role": "tool",
            "content": result,
            "tool_call_id": tool_call_id,
        })
        self._tool_results.append({
            "tool": tool_name,
            "result_preview": result[:200],
        })

    def record_file_read(self, path: str, content: str) -> None:
        """Record a file that was read (for context tracking)."""
        self._files_read[path] = content[:5000]  # Keep first 5K chars

    def record_file_changed(self, path: str) -> None:
        """Record a file that was modified."""
        if path not in self._files_changed:
            self._files_changed.append(path)

    @property
    def files_changed(self) -> list[str]:
        return list(self._files_changed)

    @property
    def message_count(self) -> int:
        return len(self._conversation)

    def clear(self) -> None:
        """Reset all context."""
        self._conversation.clear()
        self._tool_results.clear()
        self._files_read.clear()
        self._files_changed.clear()
