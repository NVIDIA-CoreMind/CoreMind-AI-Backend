"""
CoreMind Backend — Structured Tool Call Parser.

Extracts structured tool calls from model content when the model does not support
native function calling or outputs tool invocations in text/JSON/XML format.
Never fabricates responses or results.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from src.utils.logger import logger


def extract_structured_tool_calls(
    content: str,
    known_tools: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Parse text for structured tool calls emitted by models without native tool calling.
    Supports:
      1. XML tags: <tool_call>{...}</tool_call> or <tool>{...}</tool>
      2. Markdown JSON blocks: ```json { "name": "...", "arguments": {...} } ```
      3. Raw JSON objects: { "name": "...", "arguments": {...} } or { "tool": "...", "args": {...} }
    """
    if not content or not content.strip():
        return []

    tool_calls: list[dict[str, Any]] = []

    # 1. XML style tags: <tool_call> ... </tool_call> or <tool> ... </tool>
    xml_matches = re.findall(r"<tool(?:_call)?>(.*?)</tool(?:_call)?>", content, re.DOTALL | re.IGNORECASE)
    for block in xml_matches:
        tc = _try_parse_tool_call_json(block.strip(), known_tools)
        if tc:
            tool_calls.append(tc)

    if tool_calls:
        logger.debug("ai.parser.extracted_xml_tool_calls", count=len(tool_calls))
        return tool_calls

    # 2. Markdown fenced code blocks: ```json ... ``` or ``` ... ```
    code_blocks = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)
    for block in code_blocks:
        tc = _try_parse_tool_call_json(block.strip(), known_tools)
        if tc:
            tool_calls.append(tc)

    if tool_calls:
        logger.debug("ai.parser.extracted_markdown_tool_calls", count=len(tool_calls))
        return tool_calls

    # 3. Direct JSON object if content is primarily JSON
    trimmed = content.strip()
    if trimmed.startswith("{") and trimmed.endswith("}"):
        tc = _try_parse_tool_call_json(trimmed, known_tools)
        if tc:
            tool_calls.append(tc)

    return tool_calls


def _try_parse_tool_call_json(
    raw_text: str,
    known_tools: set[str] | None = None,
) -> dict[str, Any] | None:
    """Attempt to parse a single JSON block into an OpenAI-compatible tool call."""
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    # Handle various schema conventions
    name = (
        data.get("name")
        or data.get("tool")
        or data.get("function")
        or data.get("tool_name")
        or data.get("action")
    )
    if not name or not isinstance(name, str):
        return None

    args = (
        data.get("arguments")
        or data.get("args")
        or data.get("parameters")
        or data.get("params")
        or data.get("input")
        or {}
    )

    if known_tools and name not in known_tools:
        # Check if known with alias
        from src.tools.registry import TOOL_ALIASES
        if name not in TOOL_ALIASES and TOOL_ALIASES.get(name) not in known_tools:
            return None

    args_str = json.dumps(args) if isinstance(args, dict) else str(args)
    call_id = f"call_{uuid.uuid4().hex[:12]}"

    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": args_str,
        },
    }
