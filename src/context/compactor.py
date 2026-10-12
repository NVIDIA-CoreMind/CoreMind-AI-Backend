"""
CoreMind Backend — Tool Output Compactor & Context Optimizer.

Compresses verbose command and tool outputs down to essential error signals,
stack traces, and diagnostics so large logs do not swamp LLM context.
"""

from __future__ import annotations

import re


# In-memory storage for full raw outputs
_raw_output_store: dict[str, str] = {}


def store_raw_output(output_id: str, raw_output: str) -> None:
    _raw_output_store[output_id] = raw_output
    # Prune if too large
    if len(_raw_output_store) > 100:
        oldest_key = next(iter(_raw_output_store))
        _raw_output_store.pop(oldest_key, None)


def get_raw_output(output_id: str) -> str | None:
    return _raw_output_store.get(output_id)


def compress_tool_output(
    tool_name: str,
    raw_output: str,
    max_lines: int = 50,
    max_chars: int = 2500,
) -> str:
    """
    Compress large outputs (such as build or test logs) to focus on errors,
    failures, and critical summary lines.

    Preserves code inspection tools (read_file, search_files, list_directory, edit_file)
    intact so syntax and JSON structures are never corrupted.
    """
    # Do not mangle file reading, directory listing, or file editing outputs
    file_inspection_tools = {
        "read_file",
        "search_files",
        "search_code",
        "list_directory",
        "list_files",
        "edit_file",
        "write_file",
        "create_file",
        "patch_file",
        "apply_diff",
        "get_diagnostics",
    }
    if tool_name in file_inspection_tools:
        return raw_output

    if len(raw_output) <= max_chars and raw_output.count("\n") <= max_lines:
        return raw_output

    lines = raw_output.splitlines()
    total_lines = len(lines)

    # Patterns indicating significant errors or summaries
    error_patterns = [
        re.compile(r"error|failed|failure|exception|traceback|syntaxerror", re.IGNORECASE),
        re.compile(r"^\s*•\s+.*•"),  # Dart analyzer style
        re.compile(r"^.*?:\d+:\d+:\s+error:", re.IGNORECASE),  # C/Rust/TS style
        re.compile(r"^FAILED\s+", re.IGNORECASE),  # Pytest style
        re.compile(r"===\s*FAILURES\s*===", re.IGNORECASE),
        re.compile(r"===+.*===+"),
    ]

    important_indices: set[int] = set()

    for idx, line in enumerate(lines):
        for pattern in error_patterns:
            if pattern.search(line):
                # Include context around error (2 lines before, 3 lines after)
                for c in range(max(0, idx - 2), min(total_lines, idx + 4)):
                    important_indices.add(c)
                break

    if not important_indices:
        # If no explicit error patterns matched, keep head and tail
        head = lines[:20]
        tail = lines[-20:]
        omitted = total_lines - len(head) - len(tail)
        return (
            "\n".join(head)
            + f"\n\n... [{omitted} lines omitted] ...\n\n"
            + "\n".join(tail)
        )

    # Collect and sort important lines
    sorted_indices = sorted(important_indices)
    extracted: list[str] = []
    prev_idx = -1

    for idx in sorted_indices:
        if prev_idx != -1 and idx > prev_idx + 1:
            omitted = idx - prev_idx - 1
            extracted.append(f"... [{omitted} lines omitted] ...")
        extracted.append(lines[idx])
        prev_idx = idx
        if len(extracted) >= max_lines:
            extracted.append(f"... [remaining {total_lines - idx} lines omitted] ...")
            break

    summary = "\n".join(extracted)
    if len(summary) > max_chars:
        summary = summary[:max_chars] + "\n... [truncated]"

    return (
        f"[Output compressed from {total_lines} lines / {len(raw_output)} chars]\n\n"
        + summary
    )
