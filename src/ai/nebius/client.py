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


def _create_openai_client(api_key: str, base_url: str) -> AsyncOpenAI:
    import httpx
    try:
        import ssl
        import certifi
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        http_client = httpx.AsyncClient(verify=ssl_ctx)
    except Exception:
        http_client = None

    return AsyncOpenAI(
        api_key=api_key or "mock-nebius-key",
        base_url=base_url,
        http_client=http_client,
    )


class NebiusProvider(AIProvider):
    """AI provider backed by Nebius Token Factory → NVIDIA Nemotron."""

    def __init__(self) -> None:
        self._base_url = settings.nebius_base_url
        self._client: AsyncOpenAI | None = None
        self._loop: Any = None
        self._model = settings.nebius_model
        self._usage = UsageTracker()

        logger.info(
            "ai.nebius.initialized",
            base_url=self._base_url,
            model=self._model,
        )

    def _get_client(self) -> AsyncOpenAI:
        import asyncio
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._client is None or self._loop is None or self._loop != current_loop or self._loop.is_closed():
            self._loop = current_loop
            self._client = _create_openai_client(
                api_key=settings.nebius_api_key,
                base_url=self._base_url,
            )
        return self._client

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
            # Sanitize messages: ensure assistant messages with tool_calls have content: None when empty
            sanitized_messages: list[dict[str, Any]] = []
            for msg in messages:
                m = dict(msg)
                if m.get("role") == "assistant" and m.get("tool_calls") and not m.get("content"):
                    m["content"] = None
                sanitized_messages.append(m)

            kwargs: dict[str, Any] = {
                "model": self._model,
                "messages": sanitized_messages,
                "temperature": temperature,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            if max_tokens:
                kwargs["max_tokens"] = max_tokens

            client = self._get_client()
            response = await client.chat.completions.create(**kwargs)

            if not response.choices:
                return AIResponse(
                    content="",
                    tool_calls=[],
                    finish_reason="stop",
                    usage={},
                    model=response.model or self._model,
                    raw=response.model_dump() if hasattr(response, "model_dump") else {},
                )

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
            elif message.content and tools:
                # Fallback structured parsing for models without native tool calling
                from src.ai.parser import extract_structured_tool_calls
                known = {t.get("function", {}).get("name") for t in tools if isinstance(t, dict)}
                tool_calls = extract_structured_tool_calls(message.content, known_tools=known)

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
                tool_calls_count=len(tool_calls),
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
            sanitized_messages: list[dict[str, Any]] = []
            for msg in messages:
                m = dict(msg)
                if m.get("role") == "assistant" and m.get("tool_calls") and not m.get("content"):
                    m["content"] = None
                sanitized_messages.append(m)

            kwargs: dict[str, Any] = {
                "model": self._model,
                "messages": sanitized_messages,
                "temperature": temperature,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            if max_tokens:
                kwargs["max_tokens"] = max_tokens

            client = self._get_client()
            try:
                response_stream = await client.chat.completions.create(**kwargs)
            except Exception:
                # If stream_options is not supported, retry without it
                if "stream_options" in kwargs:
                    kwargs.pop("stream_options", None)
                    response_stream = await client.chat.completions.create(**kwargs)
                else:
                    raise

            async for chunk in stream_response(response_stream, self._usage):
                yield chunk

        except Exception as exc:
            handle_openai_error(exc)
            raise

    async def list_models(self) -> list[dict[str, Any]]:
        """List available models from Nebius."""
        try:
            client = self._get_client()
            models = await client.models.list()
            return [
                {"id": m.id, "owned_by": m.owned_by, "created": m.created}
                for m in models.data
            ]
        except Exception as exc:
            logger.error("ai.nebius.list_models_error", error=str(exc))
            return []

    def set_model(self, model: str) -> None:
        """Dynamically configure the active model name."""
        self._model = model
        logger.info("ai.nebius.model_updated", model=model)

    def set_base_url(self, base_url: str) -> None:
        """Dynamically configure the provider base URL endpoint."""
        self._base_url = base_url
        self._client = None
        logger.info("ai.nebius.base_url_updated", base_url=base_url)

    def get_usage(self) -> dict[str, Any]:
        """Get accumulated usage stats."""
        return self._usage.to_dict()

