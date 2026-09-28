import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load .env file
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


class NebiusConfig(BaseModel):
    api_key: str = Field(default_factory=lambda: os.getenv("NEBIUS_API_KEY", "dummy-key-for-dev"))
    base_url: str = Field(
        default_factory=lambda: os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1")
    )
    default_model: str = Field(
        default_factory=lambda: os.getenv("NEBIUS_MODEL", "nvidia/llama-3.1-nemotron-70b-instruct")
    )


class SandboxConfig(BaseModel):
    python_path: str = Field(default_factory=lambda: os.getenv("PYTHON_PATH", "python"))
    timeout_ms: int = Field(default_factory=lambda: int(os.getenv("SANDBOX_TIMEOUT_MS", "30000")))
    work_dir: Path = Field(
        default_factory=lambda: Path(os.getenv("SANDBOX_WORK_DIR", str(BASE_DIR / "workspace_sandbox"))).resolve()
    )


class AgentConfig(BaseModel):
    max_iterations: int = Field(default_factory=lambda: int(os.getenv("AGENT_MAX_ITERATIONS", "25")))
    max_debug_retries: int = Field(default_factory=lambda: int(os.getenv("AGENT_MAX_DEBUG_RETRIES", "5")))


class Settings(BaseModel):
    port: int = Field(default_factory=lambda: int(os.getenv("PORT", "4000")))
    host: str = Field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    environment: str = Field(default_factory=lambda: os.getenv("NODE_ENV", "development"))
    nebius: NebiusConfig = Field(default_factory=NebiusConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)


settings = Settings()
