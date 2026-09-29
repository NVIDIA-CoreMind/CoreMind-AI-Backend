"""
CoreMind Backend — Sandbox Client.

HTTP client for future remote sandbox providers (e.g., Nebius Sandbox).
Placeholder for when the Nebius Sandbox API is verified.
"""

from __future__ import annotations

from typing import Any

import httpx


class SandboxClient:
    """HTTP client for remote sandbox APIs."""

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def create_sandbox(self, project_path: str) -> dict[str, Any]:
        """Create a remote sandbox instance."""
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/sandbox/create",
                json={"project_path": project_path},
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]

    async def execute(
        self,
        sandbox_id: str,
        command: str,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        """Execute a command in a remote sandbox."""
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/sandbox/execute",
                json={
                    "sandbox_id": sandbox_id,
                    "command": command,
                    "timeout_ms": timeout_ms,
                },
                headers=headers,
                timeout=(timeout_ms or 120_000) / 1000,
            )
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]

    async def destroy(self, sandbox_id: str) -> bool:
        """Destroy a remote sandbox."""
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/sandbox/destroy",
                json={"sandbox_id": sandbox_id},
                headers=headers,
                timeout=15,
            )
            return response.status_code == 200
