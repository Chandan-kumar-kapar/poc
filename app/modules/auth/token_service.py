from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import redis_client
from app.modules.auth.token_models import RefreshToken, RevokedToken

settings = get_settings()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_refresh(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_raw_refresh() -> str:
    return secrets.token_urlsafe(48)


async def issue_refresh_token(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    family_id: uuid.UUID | None = None,
) -> str:
    """Create a new refresh token row and return the raw (unhashed) value."""
    raw = generate_raw_refresh()
    rt = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh(raw),
        family_id=family_id or uuid.uuid4(),
        expires_at=_now() + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(rt)
    await db.flush()
    return raw


class RefreshReuseError(Exception):
    pass


class RefreshInvalidError(Exception):
    pass


async def rotate_refresh_token(db: AsyncSession, raw: str) -> tuple[uuid.UUID, str]:
    """Validate + rotate. On reuse of a consumed token, revoke the whole family.
    Returns (user_id, new_raw_refresh)."""
    token_hash = hash_refresh(raw)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    rt = result.scalar_one_or_none()

    if rt is None:
        raise RefreshInvalidError("Unknown refresh token.")

    if rt.revoked:
        raise RefreshInvalidError("Refresh token revoked.")

    expires_at = rt.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= _now():
        raise RefreshInvalidError("Refresh token expired.")

    if rt.consumed:
        # Reuse detected: nuke the entire family.
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == rt.family_id)
            .values(revoked=True)
        )
        await db.flush()
        raise RefreshReuseError("Refresh token reuse detected; family revoked.")

    # Consume current and mint a replacement within the same family.
    new_raw = generate_raw_refresh()
    new_rt = RefreshToken(
        user_id=rt.user_id,
        token_hash=hash_refresh(new_raw),
        family_id=rt.family_id,
        expires_at=_now() + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(new_rt)
    await db.flush()

    rt.consumed = True
    rt.replaced_by = new_rt.id
    await db.flush()

    return rt.user_id, new_raw


async def revoke_refresh_family(db: AsyncSession, raw: str) -> None:
    token_hash = hash_refresh(raw)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    rt = result.scalar_one_or_none()
    if rt is not None:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == rt.family_id)
            .values(revoked=True)
        )
        await db.flush()


# --- Access token denylist (jti) ---

def _redis_key(jti: str) -> str:
    return f"denylist:jti:{jti}"


async def revoke_access_jti(db: AsyncSession, jti: str, expires_at: datetime) -> None:
    """Mirror to Redis (fast path) and Postgres (durable record)."""
    db.add(RevokedToken(jti=jti, expires_at=expires_at))
    await db.flush()
    ttl = max(1, int((expires_at - _now()).total_seconds()))
    try:
        await redis_client.get_redis().set(_redis_key(jti), "1", ex=ttl)
    except Exception:
        # Redis unavailable: Postgres remains the source of truth.
        pass


async def is_access_jti_revoked(db: AsyncSession, jti: str) -> bool:
    try:
        if await redis_client.get_redis().get(_redis_key(jti)) is not None:
            return True
    except Exception:
        pass
    # Fallback to Postgres if Redis missed or is down.
    result = await db.execute(
        select(RevokedToken).where(RevokedToken.jti == jti)
    )
    return result.scalar_one_or_none() is not None
