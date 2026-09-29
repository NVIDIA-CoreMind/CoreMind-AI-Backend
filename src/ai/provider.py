"""
CoreMind Backend — AI Provider Abstraction.

The agent engine talks to AIProvider, NOT directly to Nebius.
This allows future providers (local models, other APIs) without
changing the agent code.

    AIProvider
        ├── NebiusProvider
        ├── LocalProvider  (future)
        └── OtherProvider  (future)
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AIMessage:
    """A single message in a conversation."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class AIResponse:
    """Normalized response from any AI provider."""

    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class AIStreamChunk:
    """A single chunk from a streaming response."""

    content: str = ""
    tool_calls_delta: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class ModelInfo:
    """Information about an available model."""

    id: str
    name: str
    provider: str
    context_window: int | None = None


class AIProvider(abc.ABC):
    """Abstract base class for AI providers."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'nebius')."""
        ...

    @property
    @abc.abstractmethod
    def model(self) -> str:
        """Currently configured model ID."""
        ...

    @abc.abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AIResponse:
        """Send a chat completion request and return the full response."""
        ...

    @abc.abstractmethod
    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[AIStreamChunk]:
        """Stream a chat completion response chunk by chunk."""
        ...

    @abc.abstractmethod
    async def list_models(self) -> list[dict[str, Any]]:
        """List available models from this provider."""
        ...

    @abc.abstractmethod
    def get_usage(self) -> dict[str, Any]:
        """Get accumulated token usage statistics."""
        ...


# ── Provider Factory ────────────────────────────────────────────────

_provider_instance: AIProvider | None = None


def get_ai_provider() -> AIProvider:
    """Get the singleton AI provider instance."""
    global _provider_instance
    if _provider_instance is None:
        from src.ai.nebius.client import NebiusProvider

        _provider_instance = NebiusProvider()
    return _provider_instance
