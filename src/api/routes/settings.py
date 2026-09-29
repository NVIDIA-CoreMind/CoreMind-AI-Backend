"""
CoreMind Backend — Settings API Routes.

GET  /v1/settings — Get current (safe) settings
"""

from __future__ import annotations

from fastapi import APIRouter

from src.config import settings

router = APIRouter(prefix="/v1/settings", tags=["settings"])


@router.get("")
async def get_settings() -> dict[str, object]:
    """Return safe (non-secret) settings for the IDE."""
    return {
        "model": settings.nebius_model,
        "max_agent_steps": settings.max_agent_steps,
        "command_timeout_ms": settings.default_command_timeout_ms,
        "sandbox_type": settings.sandbox_type,
        "host": settings.coremind_backend_host,
        "port": settings.coremind_backend_port,
        # NEVER expose: nebius_api_key
    }
