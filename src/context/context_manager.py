"""
CoreMind Backend — Context Manager.

Assembles prioritized, layered context for AI requests:

    System Prompt (AI Coding Agent instructions)
          +
    Project Rules (.coremindrules, AGENTS.md, .cursorrules)
          +
    Project Context (language, framework, test command)
          +
    Repository Map (compact structure and symbols)
          +
    Limited Durable Memory
          +
    User Request & Task State
          +
    Conversation History (with compressed tool results)
          ↓
    AI Provider

Never sends the entire repository. Uses compaction and output compression
when context approaches token limits.
"""

from __future__ import annotations

from typing import Any

from src.ai.prompts.coding import build_coding_context
from src.ai.prompts.system import get_system_prompt
from src.config import settings
from src.context.compactor import compress_tool_output, store_raw_output
from src.context.compaction import compact_messages
from src.context.rules import load_project_rules
from src.memory.store import agent_memory
from src.project.project_manager import project_manager
from src.project.repo_map import RepoMap
from src.utils.logger import logger

MAX_CONTEXT_TOKENS = 100_000
CHARS_PER_TOKEN = 4


class ContextManager:
    """Assembles and manages prioritized layered context for AI requests."""

    def __init__(self, project_path: str) -> None:
        self._project_path = project_path
        self._conversation: list[dict[str, Any]] = []
        self._tool_results: list[dict[str, Any]] = []
        self._files_read: dict[str, str] = {}
        self._files_changed: list[str] = []
        self._repo_map = RepoMap(project_path)
        self._user_task: str | None = None

    def build_messages(self, user_task: str | None = None) -> list[dict[str, Any]]:
        """
        Build the full prioritized message list for an AI request.
        """
        messages: list[dict[str, Any]] = []

        # Layer 1: Core System Prompt
        messages.append({
            "role": "system",
            "content": get_system_prompt(max_steps=settings.max_agent_steps),
        })

        # Layer 2: Project Rules (.coremindrules, AGENTS.md, .cursorrules)
        rules_text = load_project_rules(self._project_path)
        if rules_text:
            messages.append({"role": "system", "content": rules_text})

        # Layer 3: Project Architecture & Environment Context
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

        # Layer 4: Compact Repository Map & Symbol Outline
        try:
            repo_summary = self._repo_map.build_compact_summary(max_chars=3500)
            if repo_summary and len(repo_summary) > 50:
                messages.append({"role": "system", "content": repo_summary})
        except Exception as e:
            logger.warn("context.repo_map.failed", error=str(e))

        # Layer 5: Limited Project Memory
        memory_query = user_task or ""
        if not memory_query:
            for msg in reversed(self._conversation):
                if msg.get("role") == "user":
                    memory_query = str(msg.get("content") or "")
                    break
        digest = agent_memory.build_prompt_digest(self._project_path, query=memory_query)
        if digest:
            messages.append({"role": "system", "content": digest})

        if user_task:
            self._user_task = user_task
            # Ensure the user prompt is present in the conversation history
            if not self._conversation or self._conversation[-1].get("content") != user_task:
                self.add_user_message(user_task)

        # Layer 6: Active Conversation & Tool Execution
        messages.extend(self._conversation)

        # Compaction if token threshold reached
        estimated_tokens = sum(len(m.get("content") or "") for m in messages) // CHARS_PER_TOKEN
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
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        """Add an assistant message to the conversation."""
        msg: dict[str, Any] = {"role": "assistant", "content": content or ""}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self._conversation.append(msg)

    def add_tool_result(
        self,
        tool_call_id: str,
        tool_name: str,
        result: str,
    ) -> None:
        """Add a tool result to the conversation, applying output compression if verbose."""
        # Store full raw result
        store_raw_output(tool_call_id, result)

        # Compress if too large
        compressed = compress_tool_output(tool_name, result)

        self._conversation.append({
            "role": "tool",
            "content": compressed,
            "tool_call_id": tool_call_id,
        })
        self._tool_results.append({
            "tool": tool_name,
            "result_preview": result[:200],
        })

    def record_file_read(self, path: str, content: str) -> None:
        """Record a file that was read (for context tracking)."""
        self._files_read[path] = content[:5000]

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
        self._user_task = None
