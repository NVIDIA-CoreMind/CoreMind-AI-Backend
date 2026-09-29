"""
CoreMind Backend — Bootstrap Entry Point.

Loads config, creates the FastAPI app, and starts uvicorn.
"""

from __future__ import annotations

import uvicorn
from dotenv import load_dotenv

# Load .env BEFORE importing anything that reads settings
load_dotenv()

from src.app.application import create_app  # noqa: E402
from src.config import settings  # noqa: E402
from src.utils.logger import logger  # noqa: E402


def main() -> None:
    """Start the CoreMind Backend server."""
    app = create_app()

    logger.info(
        "backend.bootstrap",
        host=settings.coremind_backend_host,
        port=settings.coremind_backend_port,
        model=settings.nebius_model,
        max_steps=settings.max_agent_steps,
    )

    uvicorn.run(
        app,
        host=settings.coremind_backend_host,
        port=settings.coremind_backend_port,
        log_level="warning",  # We use our own structured logger
    )


if __name__ == "__main__":
    main()
