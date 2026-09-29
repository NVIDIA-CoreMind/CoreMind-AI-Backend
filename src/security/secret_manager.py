"""
CoreMind Backend — Secret Manager.

Ensures secrets are never exposed to logs, API responses,
or the AI model.
"""

from __future__ import annotations

import re
from typing import Any

from src.config import settings

# Keys that contain secrets
SECRET_KEYS = {"nebius_api_key", "api_key", "secret", "password", "token", "authorization"}

# Patterns to detect secrets in strings
SECRET_PATTERNS = [
    re.compile(r"(sk-[a-zA-Z0-9]{20,})", re.IGNORECASE),        # API keys
    re.compile(r"(eyJ[a-zA-Z0-9_-]{20,})", re.IGNORECASE),       # JWTs
    re.compile(r"(ghp_[a-zA-Z0-9]{36})", re.IGNORECASE),          # GitHub PATs
    re.compile(r"(-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----)", re.IGNORECASE),  # Private keys
]


def get_api_key() -> str:
    """Get the Nebius API key securely (only from env, never logged)."""
    key = settings.nebius_api_key
    if not key or key == "your_api_key_here":
        raise ValueError(
            "NEBIUS_API_KEY is not configured. "
            "Copy .env.example to .env and set your API key."
        )
    return key


def redact_secrets(text: str) -> str:
    """Redact any detected secrets from a text string."""
    result = text
    for pattern in SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def sanitize_for_model(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Sanitize messages before sending to the AI model.

    Removes any accidentally included secrets from message content.
    """
    sanitized: list[dict[str, Any]] = []
    for msg in messages:
        clean = dict(msg)
        if "content" in clean and isinstance(clean["content"], str):
            clean["content"] = redact_secrets(clean["content"])
        sanitized.append(clean)
    return sanitized


def is_secret_key(key: str) -> bool:
    """Check if a dictionary key likely holds a secret value."""
    return key.lower() in SECRET_KEYS
