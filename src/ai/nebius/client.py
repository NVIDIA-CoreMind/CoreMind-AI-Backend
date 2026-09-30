"""
CoreMind Backend — Nebius Provider.

Implements AIProvider using the OpenAI-compatible API exposed by
Nebius Token Factory to reach NVIDIA Nemotron models.

Uses the official `openai` Python SDK pointed at the Nebius base URL.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from src.ai.nebius.errors import handle_openai_error
from src.ai.nebius.streaming import stream_response
from src.ai.provider import AIProvider, AIResponse, AIStreamChunk
from src.ai.usage import UsageTracker
from src.config import settings
from src.utils.logger import logger


class NebiusProvider(AIProvider):
    """AI provider backed by Nebius Token Factory → NVIDIA Nemotron."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.nebius_api_key or "mock-nebius-key",
            base_url=settings.nebius_base_url,
        )
        self._model = settings.nebius_model
        self._usage = UsageTracker()

        logger.info(
            "ai.nebius.initialized",
            base_url=settings.nebius_base_url,
            model=self._model,
        )

    @property
    def name(self) -> str:
        return "nebius"

    @property
    def model(self) -> str:
        return self._model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AIResponse:
        """Send a chat completion to Nebius/Nemotron."""
        try:
            kwargs: dict[str, Any] = {
                "model": self._model,
                "messages": messages,
                "temperature": temperature,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            if max_tokens:
                kwargs["max_tokens"] = max_tokens

            response = await self._client.chat.completions.create(**kwargs)

            choice = response.choices[0]
            message = choice.message

            # Parse tool calls if present
            tool_calls: list[dict[str, Any]] = []
            if message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    })

            # Track usage
            usage: dict[str, int] = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
                self._usage.add(usage)

            logger.debug(
                "ai.nebius.chat_completed",
                model=self._model,
                finish_reason=choice.finish_reason or "",
                **usage,
            )

            return AIResponse(
                content=message.content or "",
                tool_calls=tool_calls,
                finish_reason=choice.finish_reason or "",
                usage=usage,
                model=response.model,
                raw=response.model_dump(),
            )

        except Exception as exc:
            handle_openai_error(exc)
            raise  # handle_openai_error always raises, but mypy needs this

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[AIStreamChunk]:
        """Stream a chat completion from Nebius/Nemotron."""
        try:
            kwargs: dict[str, Any] = {
                "model": self._model,
                "messages": messages,
                "temperature": temperature,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            if max_tokens:
                kwargs["max_tokens"] = max_tokens

            response_stream = await self._client.chat.completions.create(**kwargs)

            async for chunk in stream_response(response_stream, self._usage):
                yield chunk

        except Exception as exc:
            handle_openai_error(exc)
            raise

    async def list_models(self) -> list[dict[str, Any]]:
        """List available models from Nebius."""
        try:
            models = await self._client.models.list()
            return [
                {"id": m.id, "owned_by": m.owned_by, "created": m.created}
                for m in models.data
            ]
        except Exception as exc:
            logger.error("ai.nebius.list_models_error", error=str(exc))
            return []

    def get_usage(self) -> dict[str, Any]:
        """Get accumulated usage stats."""
        return self._usage.to_dict()
