"""
CoreMind Backend — Structured JSON Logger.

Never logs secrets: API keys, tokens, passwords, SSH keys, .env secrets.
All log output is machine-parseable JSON to stdout/stderr.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from typing import Any

# ── Secret Detection ────────────────────────────────────────────────

_REDACTED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"api[_\-]?key", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"authorization", re.IGNORECASE),
    re.compile(r"ssh[_\-]?key", re.IGNORECASE),
    re.compile(r"private[_\-]?key", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
]

_SECRET_ENV_KEYS: set[str] = {"NEBIUS_API_KEY"}

_LOG_LEVELS: dict[str, int] = {
    "debug": 0,
    "info": 1,
    "warn": 2,
    "error": 3,
    "fatal": 4,
}


def _is_secret_key(key: str) -> bool:
    if key.upper() in _SECRET_ENV_KEYS:
        return True
    return any(p.search(key) for p in _REDACTED_PATTERNS)


def _redact(obj: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in obj.items():
        if _is_secret_key(key):
            cleaned[key] = "[REDACTED]"
        elif isinstance(value, dict):
            cleaned[key] = _redact(value)
        else:
            cleaned[key] = value
    return cleaned


# ── Logger ──────────────────────────────────────────────────────────


class Logger:
    """Structured JSON logger with automatic secret redaction."""

    def __init__(self, level: str = "info", context: dict[str, Any] | None = None) -> None:
        self._min_level = _LOG_LEVELS.get(level, 1)
        self._context: dict[str, Any] = context or {}

    def set_level(self, level: str) -> None:
        self._min_level = _LOG_LEVELS.get(level, 1)

    def _write(self, level: str, event: str, data: dict[str, Any] | None = None) -> None:
        if _LOG_LEVELS.get(level, 1) < self._min_level:
            return

        entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": level,
            "event": event,
            **self._context,
        }
        if data:
            entry.update(_redact(data))

        line = json.dumps(entry, default=str)

        if level in ("error", "fatal"):
            sys.stderr.write(line + "\n")
            sys.stderr.flush()
        else:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()

    def debug(self, event: str, **data: Any) -> None:
        self._write("debug", event, data if data else None)

    def info(self, event: str, **data: Any) -> None:
        self._write("info", event, data if data else None)

    def warn(self, event: str, **data: Any) -> None:
        self._write("warn", event, data if data else None)

    def warning(self, event: str, **data: Any) -> None:
        self._write("warn", event, data if data else None)

    def error(self, event: str, **data: Any) -> None:
        self._write("error", event, data if data else None)

    def fatal(self, event: str, **data: Any) -> None:
        self._write("fatal", event, data if data else None)

    def child(self, **context: Any) -> Logger:
        """Create a child logger with inherited + additional context fields."""
        merged = {**self._context, **context}
        child = Logger.__new__(Logger)
        child._min_level = self._min_level
        child._context = merged
        return child


# ── Module-level singleton ──────────────────────────────────────────

import os  # noqa: E402

logger = Logger(level=os.environ.get("LOG_LEVEL", "info"))
