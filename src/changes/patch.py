"""
CoreMind Backend — Patch Engine.

Applies, validates, and rolls back unified diff patches on text content.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from src.utils.errors import ErrorCode, ToolError

HUNK_HEADER_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
)


class Hunk(NamedTuple):
    old_start: int
    old_len: int
    new_start: int
    new_len: int
    lines: list[str]


def parse_unified_diff(patch_text: str) -> list[Hunk]:
    """Parse unified diff text into individual Hunk instances."""
    hunks: list[Hunk] = []
    lines = patch_text.splitlines(keepends=True)
    i = 0

    while i < len(lines):
        line = lines[i]
        match = HUNK_HEADER_RE.match(line)
        if match:
            old_start = int(match.group(1))
            old_len = int(match.group(2)) if match.group(2) is not None else 1
            new_start = int(match.group(3))
            new_len = int(match.group(4)) if match.group(4) is not None else 1

            i += 1
            hunk_lines: list[str] = []
            while i < len(lines):
                cur = lines[i]
                if cur.startswith("@@ ") or cur.startswith("--- ") or cur.startswith("+++ "):
                    break
                if cur.startswith(("+", "-", " ", "\\")):
                    hunk_lines.append(cur)
                    i += 1
                else:
                    break

            hunks.append(
                Hunk(
                    old_start=old_start,
                    old_len=old_len,
                    new_start=new_start,
                    new_len=new_len,
                    lines=hunk_lines,
                )
            )
        else:
            i += 1

    return hunks


def apply_patch(original_content: str, patch_text: str) -> str:
    """
    Apply a unified diff patch to original_content and return the patched text.
    Raises ToolError if the patch cannot be applied cleanly.
    """
    hunks = parse_unified_diff(patch_text)
    if not hunks:
        # If no hunks found, return original
        return original_content

    orig_lines = original_content.splitlines(keepends=True)
    # Ensure all lines end with newline for clean matching
    normalized_orig = [
        ln if ln.endswith("\n") else ln + "\n"
        for ln in orig_lines
    ]

    result: list[str] = []
    orig_idx = 0  # 0-indexed cursor into normalized_orig

    for hunk in hunks:
        target_orig_line = hunk.old_start - 1  # convert 1-based to 0-based

        # Copy unchanged lines leading up to this hunk
        while orig_idx < target_orig_line and orig_idx < len(normalized_orig):
            result.append(normalized_orig[orig_idx])
            orig_idx += 1

        # Now apply the hunk lines
        for hline in hunk.lines:
            indicator = hline[0]
            content = hline[1:]
            if not content.endswith("\n"):
                content += "\n"

            if indicator == " ":
                # Context line: must match current orig_line (ignoring trailing whitespace)
                if orig_idx < len(normalized_orig):
                    cur_orig = normalized_orig[orig_idx]
                    if cur_orig.rstrip() != content.rstrip():
                        raise ToolError(
                            ErrorCode.TOOL_INVALID_ARGS,
                            f"Patch context mismatch at line {orig_idx + 1}:\n"
                            f"Expected: {repr(content)}\n"
                            f"Found:    {repr(cur_orig)}",
                        )
                    result.append(cur_orig)
                    orig_idx += 1
                else:
                    result.append(content)
            elif indicator == "-":
                # Deletion line: must match orig_line
                if orig_idx < len(normalized_orig):
                    cur_orig = normalized_orig[orig_idx]
                    if cur_orig.rstrip() != content.rstrip():
                        raise ToolError(
                            ErrorCode.TOOL_INVALID_ARGS,
                            f"Patch deletion mismatch at line {orig_idx + 1}:\n"
                            f"Expected to delete: {repr(content)}\n"
                            f"Found:             {repr(cur_orig)}",
                        )
                    orig_idx += 1
                else:
                    raise ToolError(
                        ErrorCode.TOOL_INVALID_ARGS,
                        f"Unexpected end of file while trying to delete: {repr(content)}",
                    )
            elif indicator == "+":
                # Addition line: add to output
                result.append(content)
            elif indicator == "\\":
                # "\ No newline at end of file" ignore
                continue

    # Append remaining lines
    while orig_idx < len(normalized_orig):
        result.append(normalized_orig[orig_idx])
        orig_idx += 1

    return "".join(result)


def validate_patch(original_content: str, patch_text: str) -> bool:
    """Check if patch can be applied cleanly without raising."""
    try:
        apply_patch(original_content, patch_text)
        return True
    except Exception:
        return False


def rollback_patch(patched_content: str, patch_text: str) -> str:
    """
    Reverse a unified diff patch and apply it to patched_content to restore original.
    """
    # Reverse diff by swapping '-' and '+'
    reversed_lines: list[str] = []
    for line in patch_text.splitlines(keepends=True):
        if line.startswith("--- "):
            reversed_lines.append("+++ " + line[4:])
        elif line.startswith("+++ "):
            reversed_lines.append("--- " + line[4:])
        elif line.startswith("@@ "):
            match = HUNK_HEADER_RE.match(line)
            if match:
                old_start = match.group(1)
                old_len = f",{match.group(2)}" if match.group(2) else ""
                new_start = match.group(3)
                new_len = f",{match.group(4)}" if match.group(4) else ""
                reversed_lines.append(f"@@ -{new_start}{new_len} +{old_start}{old_len} @@\n")
            else:
                reversed_lines.append(line)
        elif line.startswith("+"):
            reversed_lines.append("-" + line[1:])
        elif line.startswith("-"):
            reversed_lines.append("+" + line[1:])
        else:
            reversed_lines.append(line)

    reversed_patch = "".join(reversed_lines)
    return apply_patch(patched_content, reversed_patch)
