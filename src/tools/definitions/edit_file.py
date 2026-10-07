"""
CoreMind Backend — Tool: edit_file

Applies safe, multi-strategy edits to a file:
  Strategy 1: Exact search-and-replace
  Strategy 2: Multi-chunk replacement
  Strategy 3: Line-range replacement
  Strategy 4: Whitespace-tolerant fuzzy fallback
Includes pre-write syntax validation and generates unified diffs.
Permission: WRITE
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.agent.verifier import validate_syntax
from src.changes.diff import create_file_diff
from src.tools.registry import PermissionLevel, ToolDefinition
from src.utils.errors import ErrorCode, ToolError
from src.utils.logger import logger


def _fuzzy_find_and_replace(original: str, old_content: str, new_content: str) -> str:
    """
    Attempt whitespace-tolerant matching if exact match fails.
    Matches lines by stripping trailing whitespace and normalizing line breaks.
    """
    orig_lines = original.splitlines(keepends=True)
    target_lines = old_content.splitlines()

    if not target_lines:
        raise ToolError(ErrorCode.TOOL_INVALID_ARGS, "old_content cannot be empty for fuzzy match")

    target_stripped = [ln.strip() for ln in target_lines if ln.strip()]
    if not target_stripped:
        raise ToolError(ErrorCode.TOOL_INVALID_ARGS, "old_content contains only whitespace")

    n_target = len(target_stripped)

    # Search for matching line sequence
    match_start: int | None = None
    match_end: int | None = None

    for i in range(len(orig_lines)):
        # Collect non-empty stripped lines starting at i
        candidate: list[str] = []
        end_idx = i
        while end_idx < len(orig_lines) and len(candidate) < n_target:
            stripped = orig_lines[end_idx].strip()
            if stripped:
                candidate.append(stripped)
            end_idx += 1

        if candidate == target_stripped:
            if match_start is not None:
                raise ToolError(
                    ErrorCode.TOOL_INVALID_ARGS,
                    "Multiple fuzzy matches found for old_content. "
                    "Please provide more surrounding context lines or use line-range editing.",
                )
            match_start = i
            match_end = end_idx

    if match_start is None or match_end is None:
        raise ToolError(
            ErrorCode.TOOL_INVALID_ARGS,
            "The specified old_content was not found even with whitespace-tolerant matching. "
            "Please read the file again to get the exact lines.",
        )

    # Replace range [match_start:match_end] with new_content
    replacement_lines = new_content.splitlines(keepends=True)
    if replacement_lines and not replacement_lines[-1].endswith("\n"):
        replacement_lines[-1] += "\n"

    new_file_lines = orig_lines[:match_start] + replacement_lines + orig_lines[match_end:]
    return "".join(new_file_lines)


def _apply_line_range_edit(original: str, start_line: int, end_line: int, new_content: str) -> str:
    """Replace lines [start_line..end_line] (1-indexed, inclusive) with new_content."""
    lines = original.splitlines(keepends=True)
    total_lines = len(lines)

    if start_line < 1 or start_line > max(1, total_lines):
        raise ToolError(
            ErrorCode.TOOL_INVALID_ARGS,
            f"start_line ({start_line}) is out of range [1..{max(1, total_lines)}]",
        )
    if end_line < start_line or end_line > total_lines:
        raise ToolError(
            ErrorCode.TOOL_INVALID_ARGS,
            f"end_line ({end_line}) is out of range [{start_line}..{total_lines}]",
        )

    repl_lines = new_content.splitlines(keepends=True)
    if repl_lines and not repl_lines[-1].endswith("\n"):
        repl_lines[-1] += "\n"

    prefix = lines[: start_line - 1]
    suffix = lines[end_line:]
    return "".join(prefix + repl_lines + suffix)


async def execute_edit_file(
    project_path: str,
    path: str = "",
    old_content: str | None = None,
    new_content: str | None = None,
    chunks: list[dict[str, str]] | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    file_path: str | None = None,
    target_content: str | None = None,
    replacement_content: str | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Apply safe multi-strategy edit to a file."""
    target_rel_path = path or file_path
    if not target_rel_path:
        raise ToolError(ErrorCode.TOOL_INVALID_ARGS, "Missing required argument 'path' or 'file_path'")

    old_content = old_content if old_content is not None else target_content
    new_content = new_content if new_content is not None else replacement_content

    file_obj = Path(project_path) / target_rel_path

    if not file_obj.exists():
        raise ToolError(ErrorCode.TOOL_FILE_NOT_FOUND, f"File not found: {target_rel_path}")

    if not file_obj.is_file():
        raise ToolError(ErrorCode.TOOL_INVALID_ARGS, f"Not a file: {target_rel_path}")

    try:
        original = file_obj.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ToolError(ErrorCode.TOOL_INVALID_ARGS, f"Cannot edit binary file: {target_rel_path}")

    updated = original
    strategy_used = "none"

    # Strategy 2: Multi-chunk replacement
    if chunks:
        strategy_used = "multi_chunk"
        for idx, chunk in enumerate(chunks, start=1):
            c_old = chunk.get("old_content", "")
            c_new = chunk.get("new_content", "")
            if not c_old:
                raise ToolError(ErrorCode.TOOL_INVALID_ARGS, f"Chunk #{idx} missing old_content")

            if c_old in updated:
                count = updated.count(c_old)
                if count > 1:
                    raise ToolError(
                        ErrorCode.TOOL_INVALID_ARGS,
                        f"Chunk #{idx} old_content appears {count} times in {path}. "
                        "Include more context to make the chunk unique.",
                    )
                updated = updated.replace(c_old, c_new, 1)
            else:
                # Try fuzzy fallback for this chunk
                updated = _fuzzy_find_and_replace(updated, c_old, c_new)

    # Strategy 3: Line-range editing
    elif start_line is not None and end_line is not None and new_content is not None:
        strategy_used = "line_range"
        updated = _apply_line_range_edit(original, start_line, end_line, new_content)

    # Strategy 1 & 4: Exact replacement with fuzzy fallback
    elif old_content is not None and new_content is not None:
        if old_content in original:
            count = original.count(old_content)
            if count > 1:
                raise ToolError(
                    ErrorCode.TOOL_INVALID_ARGS,
                    f"old_content appears {count} times in {path}. "
                    "Include more surrounding lines to uniquely identify the edit target.",
                )
            strategy_used = "exact"
            updated = original.replace(old_content, new_content, 1)
        else:
            strategy_used = "fuzzy_fallback"
            updated = _fuzzy_find_and_replace(original, old_content, new_content)

    else:
        raise ToolError(
            ErrorCode.TOOL_INVALID_ARGS,
            "Must provide either (old_content, new_content), or (chunks), or (start_line, end_line, new_content)",
        )

    # Post-edit syntax validation before writing
    valid, syntax_err = validate_syntax(file_obj, updated)
    if not valid:
        raise ToolError(
            ErrorCode.TOOL_INVALID_ARGS,
            f"Edit would cause syntax error in {target_rel_path}:\n{syntax_err}\n"
            "File was NOT modified. Please check your replacement content.",
        )

    # Generate unified diff
    file_diff = create_file_diff(original, updated, target_rel_path)

    # Write file
    file_obj.write_text(updated, encoding="utf-8")

    logger.info(
        "tools.edit_file",
        path=target_rel_path,
        strategy=strategy_used,
        additions=file_diff.additions,
        deletions=file_diff.deletions,
    )

    return {
        "path": target_rel_path,
        "action": "edited",
        "strategy": strategy_used,
        "diff": file_diff.diff,
        "additions": file_diff.additions,
        "deletions": file_diff.deletions,
        "lines": updated.count("\n") + 1,
    }


edit_file_tool = ToolDefinition(
    name="edit_file",
    description=(
        "Safely edit a file using one of several strategies: "
        "1) Exact replacement (old_content, new_content), "
        "2) Multi-chunk replacement (chunks=[{old_content, new_content}, ...]), "
        "3) Line-range replacement (start_line, end_line, new_content). "
        "Includes whitespace-tolerant fuzzy fallback and pre-write syntax validation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the file from project root",
            },
            "old_content": {
                "type": "string",
                "description": "The target content to find and replace (for single edit)",
            },
            "new_content": {
                "type": "string",
                "description": "The replacement content",
            },
            "chunks": {
                "type": "array",
                "description": "Optional list of multiple edits: [{'old_content': str, 'new_content': str}]",
                "items": {
                    "type": "object",
                    "properties": {
                        "old_content": {"type": "string"},
                        "new_content": {"type": "string"},
                    },
                    "required": ["old_content", "new_content"],
                },
            },
            "start_line": {
                "type": "integer",
                "description": "Optional start line (1-indexed) for line-range replacement",
            },
            "end_line": {
                "type": "integer",
                "description": "Optional end line (1-indexed) for line-range replacement",
            },
        },
        "required": ["path"],
    },
    permission=PermissionLevel.WRITE,
    executor=execute_edit_file,
    timeout_ms=15_000,
)
