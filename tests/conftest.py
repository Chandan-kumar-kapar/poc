from __future__ import annotations

import os

# Configure environment BEFORE importing app modules.
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("AUTH_MODE", "NORMAL")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("POC_INMEMORY_KEYS", "1")
os.environ.setdefault("JWT_ISSUER", "https://api.poc.local")
os.environ.setdefault("JWT_AUDIENCE", "poc-api")
os.environ.setdefault("JWT_ACTIVE_KID", "test-key")
os.environ.setdefault("SEED_ADMIN_PASSWORD", "Admin!Passw0rd123")
os.environ.setdefault("SEED_USER_PASSWORD", "User!Passw0rd123")

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool



@pytest_asyncio.fixture
async def app_client() -> AsyncGenerator[AsyncClient, None]:
    # Build a fresh in-memory DB shared across the test's connections.
    import app.db.session as session_mod
    from app.db.session import Base

    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)

    # Patch the global session factory used by get_session().
    session_mod.engine = test_engine
    session_mod.AsyncSessionLocal = TestSessionLocal

    import app.models  # noqa: F401  ensure metadata is populated

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Fake redis: force fallback to Postgres/DB path by raising on use.
    import app.db.redis_client as redis_mod

    class _FakeRedis:
        async def ping(self):
            return True

        async def get(self, *a, **k):
            return None

        async def set(self, *a, **k):
            return True

    # Force the fake on the module so token.py (which calls
    # redis_client.get_redis()) uses it instead of a real connection.
    redis_mod.get_redis = lambda: _FakeRedis()  # type: ignore

    # Seed RBAC + users.
    from app.db.seed import seed_rbac, seed_users

    async with TestSessionLocal() as db:
        roles = await seed_rbac(db)
        await seed_users(db, roles)
        await db.commit()

    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client._test_session = TestSessionLocal  # type: ignore
        yield client

    await test_engine.dispose()


@pytest_asyncio.fixture
async def admin_token(app_client: AsyncClient) -> str:
    resp = await app_client.post(
        "/auth/login",
        json={"email": "admin@poc.local", "password": "Admin!Passw0rd123"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def user_token(app_client: AsyncClient) -> str:
    resp = await app_client.post(
        "/auth/login",
        json={"email": "user@poc.local", "password": "User!Passw0rd123"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]
