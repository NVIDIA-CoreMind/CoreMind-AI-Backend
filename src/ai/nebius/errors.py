"""
CoreMind Backend — Nebius Error Handling.

Maps OpenAI SDK exceptions to CoreMind AIError types.
"""

from __future__ import annotations

from typing import NoReturn

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)

from src.utils.errors import AIError, ErrorCode
from src.utils.logger import logger


def handle_openai_error(exc: Exception) -> NoReturn:
    """
    Convert an OpenAI SDK exception into a CoreMind AIError.

    Always raises — never returns.
    """
    if isinstance(exc, AuthenticationError):
        logger.error("ai.nebius.auth_failure", error=str(exc))
        raise AIError(
            ErrorCode.AI_AUTH_FAILURE,
            "Nebius authentication failed. Check your NEBIUS_API_KEY.",
        ) from exc

    if isinstance(exc, RateLimitError):
        logger.warn("ai.nebius.rate_limit", error=str(exc))
        raise AIError(
            ErrorCode.AI_RATE_LIMIT,
            "Nebius rate limit reached. Please wait and retry.",
        ) from exc

    if isinstance(exc, APITimeoutError):
        logger.error("ai.nebius.timeout", error=str(exc))
        raise AIError(
            ErrorCode.AI_TIMEOUT,
            "Nebius request timed out.",
        ) from exc

    if isinstance(exc, APIConnectionError):
        logger.error("ai.nebius.connection_error", error=str(exc))
        raise AIError(
            ErrorCode.AI_MODEL_UNAVAILABLE,
            "Could not connect to Nebius Token Factory.",
        ) from exc

    if isinstance(exc, APIStatusError):
        status = exc.status_code
        logger.error("ai.nebius.api_error", status=status, error=str(exc))
        if status == 404:
            raise AIError(
                ErrorCode.AI_MODEL_UNAVAILABLE,
                f"Model not found on Nebius: {exc}",
            ) from exc
        if status == 402:
            raise AIError(
                ErrorCode.AI_BUDGET_EXHAUSTED,
                "Payment Required: You have exhausted your budget. Please add funds to continue using the API.",
            ) from exc
        raise AIError(
            ErrorCode.AI_UNKNOWN,
            f"Nebius API error (HTTP {status}): {exc}",
        ) from exc

    # Unknown error
    logger.error("ai.nebius.unknown_error", error=str(exc), error_type=type(exc).__name__)
    raise AIError(
        ErrorCode.AI_UNKNOWN,
        f"Unexpected AI error: {exc}",
    ) from exc
