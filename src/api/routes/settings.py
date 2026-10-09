"""
CoreMind Backend — Settings API Routes.

GET  /v1/settings — Get current (safe) settings
"""

from __future__ import annotations

from fastapi import APIRouter

from src.config import settings

from pydantic import BaseModel, Field
from src.ai.provider import get_ai_provider

router = APIRouter(prefix="/v1/settings", tags=["settings"])


class SettingsUpdateRequest(BaseModel):
    model: str | None = Field(default=None, description="Model ID to configure")
    max_agent_steps: int | None = Field(default=None, ge=1, le=100)
    command_timeout_ms: int | None = Field(default=None, ge=1000)


@router.get("")
async def get_settings() -> dict[str, object]:
    """Return safe (non-secret) settings for the IDE."""
    provider = get_ai_provider()
    return {
        "model": provider.model,
        "max_agent_steps": settings.max_agent_steps,
        "command_timeout_ms": settings.default_command_timeout_ms,
        "sandbox_type": settings.sandbox_type,
        "host": settings.coremind_backend_host,
        "port": settings.coremind_backend_port,
        # NEVER expose: nebius_api_key
    }


@router.patch("")
async def update_settings(update: SettingsUpdateRequest) -> dict[str, object]:
    """Update active model and agent settings."""
    provider = get_ai_provider()
    if update.model:
        settings.nebius_model = update.model
        provider.set_model(update.model)
    if update.max_agent_steps is not None:
        settings.max_agent_steps = update.max_agent_steps
    if update.command_timeout_ms is not None:
        settings.default_command_timeout_ms = update.command_timeout_ms

    return await get_settings()

