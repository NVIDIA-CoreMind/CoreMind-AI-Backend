"""
CoreMind Backend — Nebius Streaming Adapter.

Converts the OpenAI streaming response into CoreMind AIStreamChunk objects.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from src.ai.provider import AIStreamChunk
from src.ai.usage import UsageTracker
from src.utils.logger import logger


async def stream_response(
    response_stream: Any,
    usage_tracker: UsageTracker,
) -> AsyncIterator[AIStreamChunk]:
    """
    Consume an OpenAI-compatible streaming response and yield AIStreamChunks.

    Handles content deltas, tool call deltas, and usage reporting.
    """
    async for chunk in response_stream:
        if not chunk.choices and hasattr(chunk, "usage") and chunk.usage:
            # Final usage-only chunk
            usage = {
                "prompt_tokens": chunk.usage.prompt_tokens,
                "completion_tokens": chunk.usage.completion_tokens,
                "total_tokens": chunk.usage.total_tokens,
            }
            usage_tracker.add(usage)
            yield AIStreamChunk(usage=usage)
            continue

        if not chunk.choices:
            continue

        choice = chunk.choices[0]
        delta = choice.delta

        content = ""
        if delta and delta.content:
            content = delta.content

        tool_calls_delta: list[dict[str, Any]] = []
        if delta and delta.tool_calls:
            for tc in delta.tool_calls:
                tc_dict: dict[str, Any] = {"index": tc.index}
                if tc.id:
                    tc_dict["id"] = tc.id
                if tc.type:
                    tc_dict["type"] = tc.type
                if tc.function:
                    func: dict[str, str] = {}
                    if tc.function.name:
                        func["name"] = tc.function.name
                    if tc.function.arguments:
                        func["arguments"] = tc.function.arguments
                    tc_dict["function"] = func
                tool_calls_delta.append(tc_dict)

        finish_reason = choice.finish_reason if choice.finish_reason else None

        if finish_reason:
            logger.debug("ai.stream.finished", finish_reason=finish_reason)

        chunk_usage: dict[str, int] = {}
        if hasattr(chunk, "usage") and chunk.usage:
            chunk_usage = {
                "prompt_tokens": chunk.usage.prompt_tokens,
                "completion_tokens": chunk.usage.completion_tokens,
                "total_tokens": chunk.usage.total_tokens,
            }
            usage_tracker.add(chunk_usage)

        yield AIStreamChunk(
            content=content,
            tool_calls_delta=tool_calls_delta,
            finish_reason=finish_reason,
            usage=chunk_usage,
        )
