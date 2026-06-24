from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Optional

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Correlation id is set per-request by middleware.
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="-")

log = structlog.get_logger()


class AppError(Exception):
    """Application error mapped to the standard envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _envelope(code: str, message: str, correlation_id: str) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "correlation_id": correlation_id,
        }
    }


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        cid = correlation_id_ctx.get()
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, cid),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        cid = correlation_id_ctx.get()
        code = _status_to_code(exc.status_code)
        detail = exc.detail if isinstance(exc.detail, str) else code
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, detail, cid),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        cid = correlation_id_ctx.get()
        # Log field/location and error type ONLY — never the submitted values,
        # which may contain passwords or PII.
        safe_fields = [
            {"loc": e.get("loc"), "type": e.get("type"), "msg": e.get("msg")}
            for e in exc.errors()
        ]
        log.warning(
            "request_validation_failed",
            path=str(request.url.path),
            method=request.method,
            errors=safe_fields,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope("validation_error", "Request validation failed.", cid)
            | {"detail": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        cid = correlation_id_ctx.get()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("internal_error", "An unexpected error occurred.", cid),
        )


def _status_to_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        429: "rate_limited",
        500: "internal_error",
        503: "unavailable",
    }.get(status_code, "error")
