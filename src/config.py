from __future__ import annotations
from pathlib import Path
"""
CoreMind Backend — Application Configuration.

Loads all settings from environment variables with Pydantic validation.
NEBIUS_API_KEY is never exposed to logs or API responses.
"""


from pydantic import Field, field_validator
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
        default="nvidia/Nemotron-3-Ultra-550b-a55b",
        description="Default NVIDIA Nemotron model ID",
    )

    # ── Backend Server ──────────────────────────────────────────────
    # Loopback by default. Container deployments bind 0.0.0.0 explicitly (see Dockerfile).
    coremind_backend_host: str = Field(default="127.0.0.1")
    coremind_backend_port: int = Field(default=43110)

    # ── Agent Limits ────────────────────────────────────────────────
    max_agent_steps: int = Field(default=50, ge=1, le=100)
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
    # Direct execution endpoints (/v1/terminal/*, /v1/sandbox/*, and the tool execute, tests, build,
    # and diagnostics routes) run commands on the host. They stay off unless this is set.
    direct_execution_enabled: bool = Field(
        default=False,
        description="Enable direct command execution endpoints. Off by default.",
    )

    # ── Authentication & JWT ────────────────────────────────────────
    # Required. There is deliberately no default: a published default would let anyone forge tokens.
    jwt_secret_key: str = Field(
        ...,
        min_length=32,
        description="Secret key for signing CoreMind auth JWT tokens. Set JWT_SECRET_KEY (32+ characters).",
    )
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_token_expire_minutes: int = Field(default=60 * 24 * 7)  # 7 days
    jwt_refresh_token_expire_days: int = Field(default=30)

    @field_validator("jwt_secret_key")
    @classmethod
    def _reject_placeholder_secret(cls, value: str) -> str:
        if value.startswith("change-this"):
            raise ValueError("JWT_SECRET_KEY is still the .env.example placeholder. Set a random value.")
        return value

    # ── Google OAuth ────────────────────────────────────────────────
    google_client_id: str = Field(
        default="",
        description="Google OAuth Client ID",
    )
    google_client_secret: str = Field(
        default="",
        description="Google OAuth Client Secret",
    )
    google_redirect_uri: str | None = Field(
        default=None,
        description=(
            "Google OAuth redirect URI. Leave unset to use this backend's own address, "
            "/v1/auth/google/callback. The URI must be registered on the Google OAuth client."
        ),
    )
    frontend_origin: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        description="Allowed frontend origins for CORS",
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
