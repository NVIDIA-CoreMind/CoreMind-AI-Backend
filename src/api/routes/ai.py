"""
CoreMind Backend — AI API Routes.

POST /v1/ai/test   — Test AI connectivity
GET  /v1/ai/models — List available models
GET  /v1/ai/usage  — Get token usage stats
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.ai.provider import get_ai_provider
from src.utils.logger import logger

router = APIRouter(prefix="/v1/ai", tags=["ai"])


@router.post("/test")
async def test_ai() -> dict[str, Any]:
    """Test connectivity to the AI provider."""
    logger.info("api.ai.test")
    provider = get_ai_provider()
    try:
        response = await provider.chat(
            messages=[{
                "role": "user",
                "content": "Say 'CoreMind connected' in two words.",
            }],
        )
        return {
            "status": "ok",
            "provider": provider.name,
            "model": provider.model,
            "response": response.content,
        }
    except Exception as exc:
        return {
            "status": "error",
            "provider": provider.name,
            "error": str(exc),
        }


@router.get("/models")
async def list_models() -> dict[str, Any]:
    """List available models from the AI provider."""
    provider = get_ai_provider()
    models = await provider.list_models()
    return {"provider": provider.name, "models": models}


@router.get("/usage")
async def get_usage() -> dict[str, Any]:
    """Get token usage statistics."""
    provider = get_ai_provider()
    return {"provider": provider.name, "usage": provider.get_usage()}
