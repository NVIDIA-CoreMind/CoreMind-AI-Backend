"""
CoreMind Backend — Fast Intent Detector.

Instant keyword-based classifier that replaces the previous LLM-based
detection (~2-3s per query) with a microsecond-level check.
"""

from __future__ import annotations

import re

from src.utils.logger import logger

# Patterns that strongly indicate a FRIENDLY (non-coding) intent
_FRIENDLY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*(hi|hello|hey|howdy|greetings|yo|sup|hola|namaste)\s*[!.?]*\s*$", re.IGNORECASE),
    re.compile(r"^\s*(good\s+(morning|afternoon|evening|night))\s*[!.?]*\s*$", re.IGNORECASE),
    re.compile(r"^\s*(thank(s| you)|thx|cheers|appreciate it)\s*[!.?]*\s*$", re.IGNORECASE),
    re.compile(r"^\s*(bye|goodbye|see\s+you|take\s+care|later)\s*[!.?]*\s*$", re.IGNORECASE),
    re.compile(r"^\s*how\s+are\s+you\s*[?!.]*\s*$", re.IGNORECASE),
    re.compile(r"^\s*what'?s?\s+up\s*[?!.]*\s*$", re.IGNORECASE),
    re.compile(r"^\s*who\s+are\s+you\s*[?!.]*\s*$", re.IGNORECASE),
    re.compile(r"^\s*what\s+can\s+you\s+do\s*[?!.]*\s*$", re.IGNORECASE),
    re.compile(r"^\s*tell\s+me\s+(a\s+)?joke\s*[!.?]*\s*$", re.IGNORECASE),
]

# Patterns that strongly indicate an INFORMATIONAL / CONVERSATIONAL query (direct fast response)
_FAST_INFO_PREFIXES = (
    "what is", "what are", "what's", "how does", "how do i", "how to", "why is",
    "why does", "explain", "tell me about", "describe", "difference between",
    "can you explain", "give me an example", "who is", "who are", "define",
)

# Workspace action verbs that require the full AgentLoop (modifying project, running commands)
_ACTION_VERBS: set[str] = {
    "create", "build", "make", "implement", "refactor", "modify",
    "edit", "delete", "remove", "fix", "debug", "run", "execute",
    "install", "deploy", "commit", "push", "pull", "merge",
}

# Project workspace nouns that indicate direct manipulation of project
_PROJECT_TARGETS: set[str] = {
    "file", "files", "folder", "directory", "repo", "repository",
    "project", "test", "tests", "server", "package", "dependency",
    "script", "command", "terminal",
}


class IntentDetector:
    """Fast intent classification — no LLM call required."""

    @staticmethod
    async def is_friendly_chat(query: str) -> bool:
        """
        Determine if the user query is a conversational or informational prompt
        that can be answered instantly without needing workspace/terminal tools.

        Uses instant heuristic matching in microseconds instead of 2-3 seconds.
        """
        stripped = query.strip()

        # Very short greetings
        if len(stripped) < 3:
            logger.info("ai.intent_detector", query=stripped[:50], intent="FRIENDLY")
            return True

        # Check friendly patterns first (exact match on short inputs)
        for pattern in _FRIENDLY_PATTERNS:
            if pattern.match(stripped):
                logger.info("ai.intent_detector", query=stripped[:50], intent="FRIENDLY")
                return True

        query_lower = stripped.lower()
        words = set(re.findall(r'\b\w+\b', query_lower))

        # Check if query asks for project file/command actions
        has_action = bool(words & _ACTION_VERBS)
        has_project_target = bool(words & _PROJECT_TARGETS)

        # Explicit request to modify codebase or run commands -> WORKING
        if has_action and has_project_target:
            logger.info("ai.intent_detector", query=stripped[:50], intent="WORKING")
            return False

        # Informational question (e.g. "what is react", "how does async work", "explain docker") -> FAST DIRECT
        if any(query_lower.startswith(prefix) for prefix in _FAST_INFO_PREFIXES):
            logger.info("ai.intent_detector", query=stripped[:50], intent="FRIENDLY")
            return True

        # Short question without workspace mutations -> FAST DIRECT
        if len(stripped.split()) <= 10 and stripped.endswith("?") and not (has_action and has_project_target):
            logger.info("ai.intent_detector", query=stripped[:50], intent="FRIENDLY")
            return True

        # If it has action verbs like "fix", "create", "run" -> WORKING
        if has_action:
            logger.info("ai.intent_detector", query=stripped[:50], intent="WORKING")
            return False

        # Long multi-step tasks -> WORKING
        if len(stripped.split()) > 15:
            logger.info("ai.intent_detector", query=stripped[:50], intent="WORKING")
            return False

        # Default for short ambiguous queries without actions: FAST DIRECT
        logger.info("ai.intent_detector", query=stripped[:50], intent="FRIENDLY")
        return True


intent_detector = IntentDetector()
