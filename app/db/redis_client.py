from __future__ import annotations

from functools import lru_cache
from typing import Optional

import redis.asyncio as aioredis

from app.core.config import get_settings


@lru_cache
def get_redis() -> aioredis.Redis:
    settings = get_settings()
    return aioredis.from_url(
        settings.redis_url, encoding="utf-8", decode_responses=True
    )


async def redis_ping() -> bool:
    try:
        return bool(await get_redis().ping())
    except Exception:
        return False
