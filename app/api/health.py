from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis_client import redis_ping
from app.db.session import get_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def ready(
    db: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
) -> dict:
    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    redis_ok = await redis_ping()

    # DB is required; Redis degradation is tolerated (denylist falls back to PG).
    ready_state = db_ok
    if not ready_state:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if ready_state else "not_ready",
        "checks": {"database": db_ok, "redis": redis_ok},
    }


@router.get("/metrics")
async def metrics() -> Response:
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
    except Exception:
        return Response("metrics unavailable", status_code=200)
