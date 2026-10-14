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

    def test_ai_chat_stream_endpoint(self, client: TestClient) -> None:
        async def mock_stream_gen(*args: Any, **kwargs: Any):
            yield AIStreamChunk(content="Hello ")
            yield AIStreamChunk(content="from ")
            yield AIStreamChunk(content="CoreMind!")

        with patch("src.api.routes.ai.get_ai_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.name = "nebius"
            mock_provider.stream = mock_stream_gen
            mock_get_provider.return_value = mock_provider

            res = client.post(
                "/v1/ai/chat/stream",
                json={"query": "Hello", "project_path": "."},
            )
            assert res.status_code == 200
            assert "text/event-stream" in res.headers["content-type"]
            body = res.text
            assert "Hello " in body
            assert "CoreMind!" in body
            assert "[DONE]" in body

    def test_friendly_chat_endpoint_success(self, client: TestClient) -> None:
        """Test dedicated friendly chat endpoint returns provider response."""
        mock_response = AIResponse(content="Hi there! How can I help you today?", model="test-model")
        with patch("src.api.routes.ai.get_ai_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.name = "nebius"
            mock_provider.chat = AsyncMock(return_value=mock_response)
            mock_get_provider.return_value = mock_provider

            res = client.post(
                "/v1/ai/chat/friendly",
                json={"query": "Hello", "history": []},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "ok"
            assert data["response"] == "Hi there! How can I help you today?"
            assert len(data["history"]) >= 2
            assert data["history"][-1]["role"] == "assistant"

    def test_friendly_chat_empty_query_rejected(self, client: TestClient) -> None:
        """Test empty query is rejected with 422."""
        res = client.post("/v1/ai/chat/friendly", json={"query": "   "})
        assert res.status_code == 422

    def test_friendly_chat_field_aliases(self, client: TestClient) -> None:
        """Test accepting prompt alias instead of query."""
        mock_response = AIResponse(content="I am doing great!", model="test-model")
        with patch("src.api.routes.ai.get_ai_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.name = "nebius"
            mock_provider.chat = AsyncMock(return_value=mock_response)
            mock_get_provider.return_value = mock_provider

            res = client.post(
                "/v1/ai/chat",
                json={"prompt": "how are you?", "messages": []},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "ok"
            assert data["response"] == "I am doing great!"

    def test_friendly_chat_provider_error_handling(self, client: TestClient) -> None:
        """Test provider error returns 502 with structured error."""
        with patch("src.api.routes.ai.get_ai_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.name = "nebius"
            mock_provider.chat = AsyncMock(side_effect=RuntimeError("Rate limit exceeded"))
            mock_get_provider.return_value = mock_provider

            res = client.post(
                "/v1/ai/chat/friendly",
                json={"query": "hello"},
            )
            assert res.status_code == 502
            assert "Rate limit exceeded" in res.json()["detail"]

    def test_friendly_chat_unprefixed_endpoint(self, client: TestClient) -> None:
        """Test /ai/chat and /ai/chat/friendly without /v1 prefix work."""
        mock_response = AIResponse(content="Greetings!", model="test-model")
        with patch("src.api.routes.ai.get_ai_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.name = "nebius"
            mock_provider.chat = AsyncMock(return_value=mock_response)
            mock_get_provider.return_value = mock_provider

            res = client.post("/ai/chat/friendly", json={"query": "hi"})
            assert res.status_code == 200
            assert res.json()["response"] == "Greetings!"

    def test_friendly_chat_via_agent_run(self, client: TestClient) -> None:
        """Test /v1/agent/run with friendly query returns response in payload."""
        mock_response = AIResponse(content="Hello from agent friendly handler!", model="test-model")
        with patch("src.ai.provider.get_ai_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.chat = AsyncMock(return_value=mock_response)
            mock_get_provider.return_value = mock_provider

            res = client.post(
                "/v1/agent/run",
                json={"task": "hello", "project_path": "."},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "completed"
            assert data["response"] == "Hello from agent friendly handler!"

