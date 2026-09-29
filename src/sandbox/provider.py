"""
CoreMind Backend — Sandbox Provider Abstraction.

    SandboxProvider
        ├── LocalSandboxProvider
        └── NebiusSandboxProvider  (future)
"""

from __future__ import annotations

import abc
from typing import Any

from src.config import settings


class SandboxProvider(abc.ABC):
    """Abstract interface for sandbox execution providers."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Provider name."""
        ...

    @abc.abstractmethod
    async def create(self, project_path: str) -> dict[str, Any]:
        """Create a sandbox instance for the given project."""
        ...

    @abc.abstractmethod
    async def execute(
        self,
        sandbox_id: str,
        command: str,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        """Execute a command in the sandbox."""
        ...

    @abc.abstractmethod
    async def destroy(self, sandbox_id: str) -> bool:
        """Destroy a sandbox instance."""
        ...


# ── Provider Factory ────────────────────────────────────────────────

_provider_instance: SandboxProvider | None = None


def get_sandbox_provider() -> SandboxProvider:
    """Get the singleton sandbox provider."""
    global _provider_instance
    if _provider_instance is None:
        if settings.sandbox_type == "local":
            from src.sandbox.local import LocalSandboxProvider
            _provider_instance = LocalSandboxProvider()
        else:
            # Future: NebiusSandboxProvider
            from src.sandbox.local import LocalSandboxProvider
            _provider_instance = LocalSandboxProvider()
    return _provider_instance
