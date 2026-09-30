"""
CoreMind Backend — Unified Diff Engine.

Generates unified diffs and statistics for changes made by the AI agent.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Any


@dataclass
class FileDiff:
    """Represents a unified diff for a single file."""

    path: str
    diff: str
    status: str = "modified"  # "modified" | "created" | "deleted"
    additions: int = 0
    deletions: int = 0
    accepted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "diff": self.diff,
            "status": self.status,
            "additions": self.additions,
            "deletions": self.deletions,
            "accepted": self.accepted,
        }


def generate_diff(
    old_content: str,
    new_content: str,
    file_path: str = "file",
) -> str:
    """
    Generate a standard unified diff between old_content and new_content.
    """
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    # Ensure ending newline consistency for diff calculation
    if old_lines and not old_lines[-1].endswith("\n"):
        old_lines[-1] += "\n"
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        n=3,
    )
    return "".join(diff)


def compute_diff_stats(diff_text: str) -> tuple[int, int]:
    """Compute number of added and deleted lines from a unified diff."""
    additions = 0
    deletions = 0
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions


def create_file_diff(
    old_content: str,
    new_content: str,
    file_path: str,
    status: str | None = None,
) -> FileDiff:
    """Create a FileDiff with computed diff and statistics."""
    diff_text = generate_diff(old_content, new_content, file_path)
    additions, deletions = compute_diff_stats(diff_text)

    if status is None:
        if not old_content and new_content:
            derived_status = "created"
        elif old_content and not new_content:
            derived_status = "deleted"
        else:
            derived_status = "modified"
    else:
        derived_status = status

    return FileDiff(
        path=file_path,
        diff=diff_text,
        status=derived_status,
        additions=additions,
        deletions=deletions,
        accepted=False,
    )
