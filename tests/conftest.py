"""Shared test setup.

Routes are protected in create_app(). Most tests exercise feature behavior, so they run
with a stub user. Tests marked ``real_auth`` run against the real token checks.
"""

import os

# Settings require a signing key. This value only exists inside the test process.
os.environ.setdefault("JWT_SECRET_KEY", "test-only-signing-key-do-not-use-in-production-0123456789")

import pytest  # noqa: E402

from src.auth.models import User  # noqa: E402

_STUB_USER = User(
    id="test-user",
    email="test@example.com",
    name="Test User",
    created_at="2026-01-01T00:00:00+00:00",
    updated_at="2026-01-01T00:00:00+00:00",
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "real_auth: run with the real token checks instead of the stub user")


@pytest.fixture(autouse=True)
def stub_route_auth(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("real_auth"):
        return
    monkeypatch.setattr("src.app.application.get_current_user", lambda: _STUB_USER)
    monkeypatch.setattr("src.api.websocket._websocket_authorized", lambda websocket: True)
