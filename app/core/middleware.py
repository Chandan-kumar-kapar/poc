from __future__ import annotations

import json
import logging
import os
import sys
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.errors import correlation_id_ctx

# Field names redacted from logged payloads, regardless of nesting.
_REDACTED_FIELDS = {
    "password",
    "new_password",
    "current_password",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "client_secret",
    "secret",
    "authorization",
}


def _redact(value: object) -> object:
    if isinstance(value, dict):
        return {
            k: ("***" if k.lower() in _REDACTED_FIELDS else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _safe_payload(raw_body: bytes) -> object:
    if not raw_body:
        return None
    try:
        return _redact(json.loads(raw_body))
    except (UnicodeDecodeError, ValueError):
        # Non-JSON body (e.g. form data or binary): log size only.
        return f"<{len(raw_body)} bytes, non-JSON>"


class _HealthCheckFilter(logging.Filter):
    """Drops uvicorn access-log noise for the liveness probe."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "/health" not in record.getMessage()


def configure_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    # Optional: also write structured logs to a file when LOG_FILE is set.
    # In dev (docker-compose.override.yml) this maps to ./logs/app.log on the
    # host so logs are easy to tail and keep.
    log_file = os.getenv("LOG_FILE")
    if log_file:
        try:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
        except OSError:
            # Never let logging setup crash the app.
            pass

    logging.basicConfig(format="%(message)s", level=logging.INFO, handlers=handlers)

    # uvicorn configures its own loggers (with propagate=False) before this
    # runs, so access/error logs never reach the root handlers above unless
    # we attach the same handlers here directly.
    for name in ("uvicorn.access", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = handlers
        uv_logger.propagate = False

    logging.getLogger("uvicorn.access").addFilter(_HealthCheckFilter())

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        # Route through stdlib logging so both stdout and the file handler get
        # every line.
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


log = structlog.get_logger()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        cid = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        correlation_id_ctx.set(cid)
        structlog.contextvars.bind_contextvars(correlation_id=cid)
        # Cache the body up front so it can still be read by the route
        # handler below — Starlette memoizes Request.body() either way.
        raw_body = await request.body()
        try:
            response = await call_next(request)
        except Exception:
            log.error(
                "request_failed",
                path=str(request.url.path),
                method=request.method,
                payload=_safe_payload(raw_body),
            )
            raise
        else:
            if response.status_code >= 400:
                log.warning(
                    "request_failed",
                    path=str(request.url.path),
                    method=request.method,
                    status_code=response.status_code,
                    payload=_safe_payload(raw_body),
                )
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["X-Correlation-ID"] = cid
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
        return response
