import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.config import settings
from app.sandbox.python_runner import default_python_runner
from app.api.routes import api_router

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("CoreMind")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure sandbox directory is ready
    await default_python_runner.ensure_work_dir()
    print(f"""
==============================================================
   CoreMind AI Backend - Autonomous Engineering Agent (FastAPI)
==============================================================
  Host:              {settings.host}
  Port:              {settings.port}
  Environment:       {settings.environment}
  Nebius Base URL:   {settings.nebius.base_url}
  Active NVIDIA LLM: {settings.nebius.default_model}
  Sandbox Directory: {settings.sandbox.work_dir}
  Python Path:       {settings.sandbox.python_path}
==============================================================
  Endpoints:
    - GET  /health            : Service & Nebius API connectivity
    - GET  /api/models        : List supported NVIDIA models
    - POST /api/agent/run     : Start agent loop (SSE Stream)
    - POST /api/sandbox/execute : Run isolated Python script
    - POST /api/sandbox/test    : Run test suite in sandbox
    - GET  /docs              : Interactive OpenAPI / Swagger UI
==============================================================
    """)
    yield
    logger.info("CoreMind AI Backend shutting down...")


app = FastAPI(
    title="CoreMind AI Backend",
    description="Autonomous software engineering agent powered by NVIDIA models on Nebius Token Factory",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routes
app.include_router(api_router)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=(settings.environment == "development"),
    )
