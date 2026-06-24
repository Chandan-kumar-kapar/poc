from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.middleware import (
    CorrelationIdMiddleware,
    SecurityHeadersMiddleware,
    configure_logging,
    log,
)
from app.modules.auth import api_local as auth_local
from app.modules.auth import api_sso as auth_sso
from app.modules.auth.keys import get_keyset
from app.modules.clients import api as clients
from app.modules.policies import api as policies

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    # Fail fast: ensure signing keys load for any mode that issues our JWTs.
    get_keyset()
    log.info("startup", auth_mode=settings.auth_mode.value)
    yield
    log.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Auth + Client & Policy POC",
        version="0.1.0",
        description=(
            "Proof-of-concept FastAPI backend with three-mode auth "
            "(NORMAL / SSO / BOTH), plus read-only Client and Policy search."
        ),
        openapi_version="3.1.0",
        lifespan=lifespan,
    )

    # Middleware (order: security headers outermost, then correlation id).
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    install_error_handlers(app)

    # Always-on routers.
    app.include_router(health.router)
    app.include_router(clients.router)
    app.include_router(policies.router)

    # Mode-gated auth routers.
    if settings.normal_enabled:
        app.include_router(auth_local.router)
    if settings.sso_enabled:
        app.include_router(auth_sso.router)
        # /auth/logout is provided by auth_local; in SSO-only mode expose it too.
        if not settings.normal_enabled:
            from fastapi import APIRouter

            sso_logout = APIRouter(prefix="/auth", tags=["auth-sso"])
            sso_logout.add_api_route(
                "/logout", auth_local.logout, methods=["POST"]
            )
            app.include_router(sso_logout)

    return app


app = create_app()
