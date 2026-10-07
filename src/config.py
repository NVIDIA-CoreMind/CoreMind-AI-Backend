from __future__ import annotations
from pathlib import Path
"""
CoreMind Backend — Application Configuration.

Loads all settings from environment variables with Pydantic validation.
NEBIUS_API_KEY is never exposed to logs or API responses.
"""


from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All backend configuration — sourced from .env / environment."""

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
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
        default="nvidia/Nemotron-3_5-Lightning",
        description="Default NVIDIA Nemotron model ID",
    )

    # ── Backend Server ──────────────────────────────────────────────
    coremind_backend_host: str = Field(default="0.0.0.0")
    coremind_backend_port: int = Field(default=43110)

    # ── Agent Limits ────────────────────────────────────────────────
    max_agent_steps: int = Field(default=20, ge=1, le=100)
    default_command_timeout_ms: int = Field(default=120_000, ge=1000)

    # ── Limited Agent Memory ────────────────────────────────────────
    memory_max_items: int = Field(
        default=40,
        ge=1,
        le=200,
        description="Max durable memories stored per project",
    )
    memory_max_content_chars: int = Field(
        default=400,
        ge=50,
        le=2000,
        description="Max characters stored in a single memory",
    )
    memory_prompt_items: int = Field(
        default=8,
        ge=1,
        le=20,
        description="Max memories injected into each model request",
    )

    # ── Web Search ──────────────────────────────────────────────────
    web_search_max_results: int = Field(default=5, ge=1, le=10)
    web_search_timeout_s: int = Field(default=12, ge=3, le=30)
    tavily_api_key: str = Field(default="", description="Tavily API Key for web search")

    # ── Sandbox ─────────────────────────────────────────────────────
    sandbox_type: str = Field(default="local", pattern=r"^(local|nebius)$")
    sandbox_working_dir: str = Field(default="")

    # ── Authentication & JWT ────────────────────────────────────────
    jwt_secret_key: str = Field(
        default="coremind-super-secret-jwt-key-2026-production-ready",
        description="Secret key for signing CoreMind auth JWT tokens",
    )
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_token_expire_minutes: int = Field(default=60 * 24 * 7)  # 7 days
    jwt_refresh_token_expire_days: int = Field(default=30)

    # ── Google OAuth ────────────────────────────────────────────────
    google_client_id: str = Field(
        default="",
        description="Google OAuth Client ID",
    )
    google_client_secret: str = Field(
        default="",
        description="Google OAuth Client Secret",
    )
    google_redirect_uri: str = Field(
        default="http://localhost:43110/v1/auth/google/callback",
        description="Google OAuth Redirect URI callback",
    )

    # ── Database ────────────────────────────────────────────────────
    sqlite_db_path: str = Field(
        default="data/coremind.db",
        description="Path to local SQLite database for user accounts and state",
    )

    # ── Logging ─────────────────────────────────────────────────────
    log_level: str = Field(default="info", pattern=r"^(debug|info|warn|error|fatal)$")


# Singleton — import `settings` everywhere
settings = Settings()
