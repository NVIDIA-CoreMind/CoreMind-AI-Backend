"""
CoreMind Backend — Change Review Manager.

Maintains structured AI change sets and allows the user or frontend
to review, accept, or reject file changes individually or as a batch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.changes.diff import FileDiff
from src.changes.patch import rollback_patch
from src.utils.ids import short_id
from src.utils.logger import logger


@dataclass
class ChangeSet:
    """A collection of file diffs produced by an agent session or task."""

    change_id: str
    agent_id: str
    project_path: str
    files: dict[str, FileDiff] = field(default_factory=dict)
    original_contents: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_id": self.change_id,
            "agent_id": self.agent_id,
            "project_path": self.project_path,
            "files": [f.to_dict() for f in self.files.values()],
            "created_at": self.created_at.isoformat(),
        }


class ChangeReviewManager:
    """Manages active change sets and handles accept/reject operations."""

    def __init__(self) -> None:
        self._change_sets: dict[str, ChangeSet] = {}

    def create_change_set(self, agent_id: str, project_path: str) -> ChangeSet:
        cid = f"chg_{short_id()}"
        cs = ChangeSet(change_id=cid, agent_id=agent_id, project_path=project_path)
        self._change_sets[cid] = cs
        return cs

    def record_change(
        self,
        change_id: str,
        file_path: str,
        file_diff: FileDiff,
        original_content: str,
    ) -> None:
        cs = self._change_sets.get(change_id)
        if cs:
            cs.files[file_path] = file_diff
            if file_path not in cs.original_contents:
                cs.original_contents[file_path] = original_content

    def get_change_set(self, change_id: str) -> ChangeSet | None:
        return self._change_sets.get(change_id)

    def preview_changes(self, change_id: str) -> dict[str, Any] | None:
        cs = self._change_sets.get(change_id)
        return cs.to_dict() if cs else None

    def accept_changes(self, change_id: str) -> bool:
        """Mark all files in the change set as accepted."""
        cs = self._change_sets.get(change_id)
        if not cs:
            return False
        for f in cs.files.values():
            f.accepted = True
        logger.info("changes.accepted_all", change_id=change_id)
        return True

    def reject_changes(self, change_id: str) -> bool:
        """Reject all changes and revert files back to original contents."""
        cs = self._change_sets.get(change_id)
        if not cs:
            return False

        root = Path(cs.project_path)
        for rel_path, orig in cs.original_contents.items():
            full_path = root / rel_path
            if orig == "":
                # File was created by AI; delete it
                if full_path.exists():
                    full_path.unlink()
            else:
                full_path.write_text(orig, encoding="utf-8")

        for f in cs.files.values():
            f.accepted = False

        logger.info("changes.rejected_all", change_id=change_id)
        return True

    def accept_file(self, change_id: str, file_path: str) -> bool:
        cs = self._change_sets.get(change_id)
        if not cs or file_path not in cs.files:
            return False
        cs.files[file_path].accepted = True
        return True

    def reject_file(self, change_id: str, file_path: str) -> bool:
        """Reject a single file change and revert it."""
        cs = self._change_sets.get(change_id)
        if not cs or file_path not in cs.files:
            return False

        orig = cs.original_contents.get(file_path)
        if orig is not None:
            full_path = Path(cs.project_path) / file_path
            if orig == "":
                if full_path.exists():
                    full_path.unlink()
            else:
                full_path.write_text(orig, encoding="utf-8")

        cs.files[file_path].accepted = False
        return True


change_review_manager = ChangeReviewManager()
