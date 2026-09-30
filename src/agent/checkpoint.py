"""
CoreMind Backend — Git Checkpoint Manager.

Creates lightweight checkpoints before AI modifications, distinguishing
pre-existing user changes from AI changes, and safely rolling back upon task failure.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from src.utils.ids import short_id
from src.utils.logger import logger


@dataclass
class Checkpoint:
    """A saved point in project state before AI edits begin."""

    checkpoint_id: str
    project_path: str
    initial_commit: str = ""
    is_git_repo: bool = False
    ai_modified_files: list[str] = field(default_factory=list)
    initial_untracked_files: set[str] = field(default_factory=set)
    file_backups: dict[str, str] = field(default_factory=dict)


class CheckpointManager:
    """Creates and manages rollback checkpoints using Git and file backup fallbacks."""

    async def _run_git(self, project_path: str, args: list[str]) -> tuple[int, str]:
        cmd = ["git"] + args
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            return (proc.returncode or 0, stdout.decode("utf-8", errors="ignore").strip())
        except Exception:
            return (-1, "")

    async def create_checkpoint(self, project_path: str) -> Checkpoint:
        """Create a checkpoint capturing current git status and existing uncommitted files."""
        cid = f"cp_{short_id()}"
        code, is_git = await self._run_git(project_path, ["rev-parse", "--is-inside-work-tree"])
        is_git_repo = (code == 0 and is_git == "true")

        initial_commit = ""
        untracked: set[str] = set()

        if is_git_repo:
            _, initial_commit = await self._run_git(project_path, ["rev-parse", "HEAD"])
            code, status_out = await self._run_git(project_path, ["status", "--porcelain"])
            if code == 0 and status_out:
                for line in status_out.splitlines():
                    if line.startswith("??"):
                        untracked.add(line[3:].strip())

        cp = Checkpoint(
            checkpoint_id=cid,
            project_path=project_path,
            initial_commit=initial_commit,
            is_git_repo=is_git_repo,
            initial_untracked_files=untracked,
        )
        logger.info("checkpoint.created", id=cid, git=is_git_repo)
        return cp

    def record_file_before_edit(self, checkpoint: Checkpoint, rel_path: str) -> None:
        """Backup file content before AI touches it."""
        if rel_path in checkpoint.file_backups:
            return

        full_path = Path(checkpoint.project_path) / rel_path
        if full_path.exists():
            try:
                checkpoint.file_backups[rel_path] = full_path.read_text(encoding="utf-8")
            except Exception:
                checkpoint.file_backups[rel_path] = ""
        else:
            checkpoint.file_backups[rel_path] = ""  # Sentinel for newly created file

        if rel_path not in checkpoint.ai_modified_files:
            checkpoint.ai_modified_files.append(rel_path)

    async def rollback(self, checkpoint: Checkpoint) -> bool:
        """
        Revert ONLY the files modified by the AI during this checkpoint.
        Unrelated user edits in other files are strictly preserved.
        """
        logger.info("checkpoint.rollback.start", id=checkpoint.checkpoint_id, files=checkpoint.ai_modified_files)
        root = Path(checkpoint.project_path)

        for rel_path in checkpoint.ai_modified_files:
            orig = checkpoint.file_backups.get(rel_path)
            full_path = root / rel_path

            if orig is not None:
                if orig == "":
                    # File was newly created by AI; delete it
                    if full_path.exists():
                        try:
                            full_path.unlink()
                        except Exception:
                            pass
                else:
                    # Restore previous content
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(orig, encoding="utf-8")

        # If in Git repo, reset git index for these files without wiping restored files
        if checkpoint.is_git_repo and checkpoint.ai_modified_files:
            for f in checkpoint.ai_modified_files:
                if f not in checkpoint.initial_untracked_files:
                    await self._run_git(checkpoint.project_path, ["reset", "HEAD", "--", f])

        logger.info("checkpoint.rollback.completed", id=checkpoint.checkpoint_id)
        return True


checkpoint_manager = CheckpointManager()
