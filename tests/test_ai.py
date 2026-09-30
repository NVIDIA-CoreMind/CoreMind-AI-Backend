"""
Tests for AI Provider, Nebius Client, Models, and AI Endpoints.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.ai.nebius.models import KNOWN_MODELS, get_model_info
from src.ai.provider import AIProvider, AIResponse, AIStreamChunk, get_ai_provider
from src.app.application import create_app


def test_known_models_lookup() -> None:
    """Verify known Nemotron models are defined and retrievable."""
    assert len(KNOWN_MODELS) >= 4
    model_550b = get_model_info("nvidia/Nemotron-3-Ultra-550b-a55b")
    assert model_550b is not None
    assert model_550b.name == "Nemotron 3 Ultra 550B"
    assert model_550b.context_window == 131072

    assert get_model_info("nonexistent-model") is None


def test_ai_provider_singleton() -> None:
    """Verify get_ai_provider returns a subclass of AIProvider."""
    provider = get_ai_provider()
    assert isinstance(provider, AIProvider)
    assert provider.name == "nebius"
    assert "Nemotron" in provider.model


class TestAiApiEndpoints:
    """Test AI REST API routes."""

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(create_app())

    def test_ai_test_endpoint_success(self, client: TestClient) -> None:
        mock_response = AIResponse(content="CoreMind connected", model="test-model")
        with patch("src.api.routes.ai.get_ai_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.name = "nebius"
            mock_provider.model = "test-model"
            mock_provider.chat = AsyncMock(return_value=mock_response)
            mock_get_provider.return_value = mock_provider

            res = client.post("/v1/ai/test")
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "ok"
            assert data["response"] == "CoreMind connected"

    def test_ai_models_endpoint(self, client: TestClient) -> None:
        with patch("src.api.routes.ai.get_ai_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.name = "nebius"
            mock_provider.list_models = AsyncMock(return_value=[{"id": "test-model"}])
            mock_get_provider.return_value = mock_provider

            res = client.get("/v1/ai/models")
            assert res.status_code == 200
            data = res.json()
            assert data["provider"] == "nebius"
            assert len(data["models"]) == 1

    def test_ai_usage_endpoint(self, client: TestClient) -> None:
        with patch("src.api.routes.ai.get_ai_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.name = "nebius"
            mock_provider.get_usage.return_value = {"total_tokens": 100, "request_count": 2}
            mock_get_provider.return_value = mock_provider

            res = client.get("/v1/ai/usage")
            assert res.status_code == 200
            data = res.json()
            assert data["usage"]["total_tokens"] == 100
