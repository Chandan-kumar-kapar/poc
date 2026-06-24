from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_success_and_me(app_client: AsyncClient):
    resp = await app_client.post(
        "/auth/login",
        json={"email": "admin@poc.local", "password": "Admin!Passw0rd123"},
    )
    assert resp.status_code == 200, resp.text
    tokens = resp.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    me = await app_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "admin@poc.local"
    assert "Admin" in me.json()["roles"]


@pytest.mark.asyncio
async def test_login_wrong_password_generic_error(app_client: AsyncClient):
    resp = await app_client.post(
        "/auth/login",
        json={"email": "admin@poc.local", "password": "WrongPassword!1"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_login_unknown_user_same_error(app_client: AsyncClient):
    resp = await app_client.post(
        "/auth/login",
        json={"email": "ghost@poc.local", "password": "WhateverPass!1"},
    )
    # Identical shape to wrong-password -> anti-enumeration.
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_register_does_not_reveal_existing(app_client: AsyncClient):
    # Registering an existing email must not confirm existence.
    resp = await app_client.post(
        "/auth/register",
        json={"email": "admin@poc.local", "password": "BrandNew!Pass123"},
    )
    assert resp.status_code in (200, 201)


@pytest.mark.asyncio
async def test_register_weak_password_rejected(app_client: AsyncClient):
    resp = await app_client.post(
        "/auth/register",
        json={"email": "new@poc.local", "password": "weak"},
    )
    assert resp.status_code == 422 or resp.status_code == 400


@pytest.mark.asyncio
async def test_refresh_rotation(app_client: AsyncClient):
    login = await app_client.post(
        "/auth/login",
        json={"email": "user@poc.local", "password": "User!Passw0rd123"},
    )
    refresh = login.json()["refresh_token"]
    r1 = await app_client.post("/auth/refresh", json={"refresh_token": refresh})
    assert r1.status_code == 200
    new_refresh = r1.json()["refresh_token"]
    assert new_refresh != refresh


@pytest.mark.asyncio
async def test_refresh_reuse_detection_revokes_family(app_client: AsyncClient):
    login = await app_client.post(
        "/auth/login",
        json={"email": "user@poc.local", "password": "User!Passw0rd123"},
    )
    refresh = login.json()["refresh_token"]

    # First rotation consumes the original.
    r1 = await app_client.post("/auth/refresh", json={"refresh_token": refresh})
    assert r1.status_code == 200
    new_refresh = r1.json()["refresh_token"]

    # Replaying the ORIGINAL (now consumed) triggers reuse detection.
    replay = await app_client.post("/auth/refresh", json={"refresh_token": refresh})
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "token_reuse"

    # The whole family is revoked: the rotated token is now invalid too.
    after = await app_client.post(
        "/auth/refresh", json={"refresh_token": new_refresh}
    )
    assert after.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_access_token(app_client: AsyncClient):
    login = await app_client.post(
        "/auth/login",
        json={"email": "user@poc.local", "password": "User!Passw0rd123"},
    )
    access = login.json()["access_token"]
    refresh = login.json()["refresh_token"]

    # Token works before logout.
    ok = await app_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {access}"}
    )
    assert ok.status_code == 200

    out = await app_client.post(
        "/auth/logout",
        json={"refresh_token": refresh},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert out.status_code == 200

    # Same access token is now denylisted.
    after = await app_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {access}"}
    )
    assert after.status_code == 401
