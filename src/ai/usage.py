"""
CoreMind Backend — Token Usage Tracker.

Accumulates token usage across all AI requests for a session.
"""

from __future__ import annotations

from typing import Any


class UsageTracker:
    """Tracks cumulative token usage."""

    def __init__(self) -> None:
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_tokens: int = 0
        self.request_count: int = 0

    def add(self, usage: dict[str, int]) -> None:
        """Add usage from a single request."""
        self.total_prompt_tokens += usage.get("prompt_tokens", 0)
        self.total_completion_tokens += usage.get("completion_tokens", 0)
        self.total_tokens += usage.get("total_tokens", 0)
        self.request_count += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "request_count": self.request_count,
        }

    def reset(self) -> None:
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.request_count = 0
