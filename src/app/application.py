"""
CoreMind Backend — FastAPI Application Factory.

Creates and configures the FastAPI app with all routes, middleware,
WebSocket support, and error handlers.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response

from src.auth.dependencies import get_current_user, require_direct_execution
from src.config import settings
from src.utils.errors import CoreMindError
from src.utils.logger import logger


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup / shutdown lifecycle."""
    logger.info(
        "backend.starting",
        host=settings.coremind_backend_host,
        port=settings.coremind_backend_port,
        model=settings.nebius_model,
    )
    yield
    logger.info("backend.shutdown")


def create_app() -> FastAPI:
    """Build and return the fully-configured FastAPI application."""
    app = FastAPI(
        title="CoreMind Backend",
        description="AI/Agent orchestration backend for CoreMind IDE",
        version="1.0.0",
        lifespan=lifespan,
    )

    # ── CORS — allow Electron IDE renderer, local origins, and Chrome ───
    origins = [
        o.strip()
        for o in settings.frontend_origin.split(",")
        if o.strip()
    ]
    for o in ["null", "http://localhost:5173", "http://127.0.0.1:5173"]:
        if o not in origins:
            origins.append(o)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|null|app://.*|vscode-file://.*|file://.*)$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Global error handler ────────────────────────────────────────
    @app.exception_handler(CoreMindError)
    async def coremind_error_handler(_request: Request, exc: CoreMindError) -> JSONResponse:
        logger.error("api.error", code=exc.code.value, message=str(exc))
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.exception_handler(Exception)
    async def general_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.error("api.unhandled_error", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}},
        )

    # ── Root & Health check ─────────────────────────────────────────
    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "service": "CoreMind Backend",
            "version": "1.0.0",
            "status": "running",
            "docs": "/docs",
            "health": "/health",
            "auth": "/auth",
            "auth_api": "/v1/auth",
        }

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "coremind-backend", "version": "1.0.0"}

    # ── Interactive Antigravity Auth Portal ─────────────────────────
    @app.api_route("/auth", methods=["GET", "HEAD"], include_in_schema=False)
    async def auth_portal() -> HTMLResponse:
        from src.auth.portal import get_auth_portal_html

        return HTMLResponse(content=get_auth_portal_html(), status_code=200)

    # ── Register route modules ──────────────────────────────────────
    from src.api.routes.agent import router as agent_router, api_router as agent_api_router, bare_router as agent_bare_router
    from src.api.routes.ai import router as ai_router, bare_router as ai_bare_router
    from src.api.routes.auth import router as auth_router
    from src.api.routes.changes import router as changes_router
    from src.api.routes.project import router as project_router
    from src.api.routes.sandbox import router as sandbox_router
    from src.api.routes.settings import router as settings_router
    from src.api.routes.terminal import router as terminal_router
    from src.api.routes.tools import router as tools_router
    from src.api.websocket import router as ws_router

    # Every router except auth requires a valid Bearer token. The WebSocket checks its own token.
    gated = [Depends(get_current_user)]
    # Routes that run commands on the host also need DIRECT_EXECUTION_ENABLED (see config.py).
    executing = [*gated, Depends(require_direct_execution)]

    # Mount v1 API routes
    app.include_router(auth_router)
    app.include_router(agent_router, dependencies=gated)
    app.include_router(agent_api_router, dependencies=gated)
    app.include_router(agent_bare_router, include_in_schema=False, dependencies=gated)
    app.include_router(ai_router, dependencies=gated)
    app.include_router(ai_bare_router, include_in_schema=False, dependencies=gated)
    app.include_router(project_router, dependencies=gated)
    app.include_router(tools_router, dependencies=gated)
    app.include_router(sandbox_router, dependencies=executing)
    app.include_router(settings_router, dependencies=gated)
    app.include_router(changes_router, dependencies=gated)
    app.include_router(terminal_router, dependencies=executing)
    app.include_router(ws_router)
    app.include_router(ws_router, prefix="/v1", include_in_schema=False)

    # Mount convenient aliases without /v1 prefix for desktop client flexibility
    app.include_router(project_router, prefix="", include_in_schema=False, dependencies=gated)
    app.include_router(changes_router, prefix="", include_in_schema=False, dependencies=gated)
    app.include_router(terminal_router, prefix="", include_in_schema=False, dependencies=executing)

    return app
