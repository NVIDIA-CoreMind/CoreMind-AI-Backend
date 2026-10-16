"""Route protection checked against the real token checks (no stub user)."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.api.websocket import WS_AUTH_PROTOCOL
from src.app.application import create_app
from src.auth.models import User
from src.auth.security import create_access_token

pytestmark = pytest.mark.real_auth

# One representative endpoint from each protected router.
GATED_REQUESTS = [
    ("post", "/v1/terminal/session", {"project_path": "/tmp"}),
    ("post", "/v1/tools/read", {"path": "README.md"}),
    ("get", "/v1/project/tree?path=/tmp", None),
    ("post", "/v1/sandbox/execute", {"command": "echo hi"}),
    ("post", "/v1/agent/run", {"prompt": "hello"}),
    ("post", "/v1/ai/chat/stream", {"query": "hello"}),
    ("get", "/v1/settings", None),
]


@pytest.mark.parametrize(("method", "path", "body"), GATED_REQUESTS)
def test_gated_routes_reject_requests_without_a_token(method: str, path: str, body: dict | None) -> None:
    client = TestClient(create_app())
    send = getattr(client, method)
    response = send(path, json=body) if body is not None else send(path)
    assert response.status_code == 401


def test_health_check_stays_public() -> None:
    client = TestClient(create_app())
    assert client.get("/health").status_code == 200


def test_websocket_refuses_connection_without_a_token() -> None:
    client = TestClient(create_app())
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws"):
            pass
    assert excinfo.value.code == 1008


def test_websocket_refuses_an_invalid_token() -> None:
    client = TestClient(create_app())
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws", subprotocols=[WS_AUTH_PROTOCOL, "not-a-real-token"]):
            pass
    assert excinfo.value.code == 1008


def test_websocket_accepts_a_valid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    user = User(
        id="ws-user",
        email="ws@example.com",
        name="WebSocket User",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    monkeypatch.setattr("src.auth.dependencies.user_storage.get_by_id", lambda user_id: user)
    token, _ = create_access_token(user_id=user.id, email=user.email)

    client = TestClient(create_app())
    with client.websocket_connect("/ws", subprotocols=[WS_AUTH_PROTOCOL, token]):
        pass
