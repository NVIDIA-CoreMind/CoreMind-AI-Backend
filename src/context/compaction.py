"""
CoreMind Backend — Context Compaction.

When the conversation grows too large for the model's context window,
we compact older messages to preserve the most important context.
"""

from __future__ import annotations

from typing import Any

from src.utils.logger import logger

CHARS_PER_TOKEN = 4


def compact_messages(
    messages: list[dict[str, Any]],
    max_tokens: int,
) -> list[dict[str, Any]]:
    """
    Compact messages to fit within the token limit.

    Strategy:
    1. Always keep system messages
    2. Always keep the first user message (the task)
    3. Always keep the last N messages
    4. Summarize/truncate tool results in the middle
    5. Drop older conversation turns if still too large
    """
    if not messages:
        return messages

    estimated_tokens = sum(len(m.get("content") or "") for m in messages) // CHARS_PER_TOKEN
    if estimated_tokens <= max_tokens:
        return messages

    logger.info(
        "context.compaction.start",
        message_count=len(messages),
        estimated_tokens=estimated_tokens,
        target_tokens=max_tokens,
    )

    # Split into sections
    system_msgs = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]

    if not non_system:
        return messages

    # Keep first user message and last 10 messages
    keep_first = non_system[:1]
    keep_last = non_system[-10:] if len(non_system) > 10 else non_system
    middle = non_system[1:-10] if len(non_system) > 11 else []

    # Truncate tool results in middle messages
    compacted_middle: list[dict[str, Any]] = []
    for msg in middle:
        if msg.get("role") == "tool":
            content = msg.get("content") or ""
            if len(content) > 500:
                msg = {**msg, "content": content[:500] + "\n... [truncated]"}
        compacted_middle.append(msg)

    # Reassemble
    result = system_msgs + keep_first + compacted_middle + keep_last

    # If still too large, drop middle messages
    result_tokens = sum(len(m.get("content") or "") for m in result) // CHARS_PER_TOKEN
    while result_tokens > max_tokens and compacted_middle:
        compacted_middle.pop(0)
        result = system_msgs + keep_first + compacted_middle + keep_last
        result_tokens = sum(len(m.get("content") or "") for m in result) // CHARS_PER_TOKEN

    logger.info(
        "context.compaction.done",
        original_count=len(messages),
        compacted_count=len(result),
        estimated_tokens=result_tokens,
    )

    return result
