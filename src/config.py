"""
CoreMind Backend — Application Configuration.

Loads all settings from environment variables with Pydantic validation.
NEBIUS_API_KEY is never exposed to logs or API responses.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All backend configuration — sourced from .env / environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Nebius / NVIDIA Nemotron ────────────────────────────────────
    nebius_api_key: str = Field(
        default="",
        description="Nebius Token Factory API key (NEVER expose to renderer)",
    )
    nebius_base_url: str = Field(
        default="https://api.studio.nebius.com/v1",
        description="Nebius Token Factory base URL",
    )
    nebius_model: str = Field(
        default="nvidia/llama-3.3-nemotron-super-49b-v1",
        description="Default NVIDIA Nemotron model ID",
    )

    # ── Backend Server ──────────────────────────────────────────────
    coremind_backend_host: str = Field(default="127.0.0.1")
    coremind_backend_port: int = Field(default=43110)

    # ── Agent Limits ────────────────────────────────────────────────
    max_agent_steps: int = Field(default=20, ge=1, le=100)
    default_command_timeout_ms: int = Field(default=120_000, ge=1000)

    # ── Sandbox ─────────────────────────────────────────────────────
    sandbox_type: str = Field(default="local", pattern=r"^(local|nebius)$")
    sandbox_working_dir: str = Field(default="")

    # ── Logging ─────────────────────────────────────────────────────
    log_level: str = Field(default="info", pattern=r"^(debug|info|warn|error|fatal)$")


# Singleton — import `settings` everywhere
settings = Settings()
