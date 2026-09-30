"""
CoreMind Backend — Change Review API Routes.

GET  /v1/changes/{change_id}        — Preview change set diffs and files
POST /v1/changes/{change_id}/accept — Accept all changes in change set
POST /v1/changes/{change_id}/reject — Reject all changes and rollback
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.changes.review import change_review_manager

router = APIRouter(prefix="/v1/changes", tags=["changes"])


class FileActionRequest(BaseModel):
    file_path: str


@router.get("/{change_id}")
async def get_changes(change_id: str) -> dict[str, Any]:
    """Get the diff preview and files for a change set."""
    preview = change_review_manager.preview_changes(change_id)
    if preview is None:
        raise HTTPException(status_code=404, detail="Change set not found")
    return preview


@router.post("/{change_id}/accept")
async def accept_changes(change_id: str) -> dict[str, Any]:
    """Accept all changes in the change set."""
    success = change_review_manager.accept_changes(change_id)
    if not success:
        raise HTTPException(status_code=404, detail="Change set not found")
    return {"status": "accepted", "change_id": change_id}


@router.post("/{change_id}/reject")
async def reject_changes(change_id: str) -> dict[str, Any]:
    """Reject all changes in the change set and restore files."""
    success = change_review_manager.reject_changes(change_id)
    if not success:
        raise HTTPException(status_code=404, detail="Change set not found")
    return {"status": "rejected", "change_id": change_id}


@router.post("/{change_id}/accept_file")
async def accept_file(change_id: str, request: FileActionRequest) -> dict[str, Any]:
    """Accept a single file modification."""
    success = change_review_manager.accept_file(change_id, request.file_path)
    if not success:
        raise HTTPException(status_code=404, detail="File or change set not found")
    return {"status": "accepted", "change_id": change_id, "file_path": request.file_path}


@router.post("/{change_id}/reject_file")
async def reject_file(change_id: str, request: FileActionRequest) -> dict[str, Any]:
    """Reject and revert a single file modification."""
    success = change_review_manager.reject_file(change_id, request.file_path)
    if not success:
        raise HTTPException(status_code=404, detail="File or change set not found")
    return {"status": "rejected", "change_id": change_id, "file_path": request.file_path}
