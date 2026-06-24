from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


async def _seed_domain(app_client: AsyncClient):
    from app.db.seed import seed_domain

    TestSessionLocal = app_client._test_session  # type: ignore
    async with TestSessionLocal() as db:
        await seed_domain(db)
        await db.commit()


@pytest.mark.asyncio
async def test_clients_requires_auth(app_client: AsyncClient):
    resp = await app_client.get("/clients")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_clients_list_and_pagination(app_client: AsyncClient, user_token: str):
    await _seed_domain(app_client)
    resp = await app_client.get(
        "/clients?page=1&page_size=5",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["page"] == 1
    assert body["page_size"] == 5
    assert body["total"] >= 20
    assert len(body["items"]) == 5


@pytest.mark.asyncio
async def test_clients_search_by_code(app_client: AsyncClient, user_token: str):
    await _seed_domain(app_client)
    resp = await app_client.get(
        "/clients?q=CLT-0001",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(i["client_code"] == "CLT-0001" for i in items)


@pytest.mark.asyncio
async def test_client_detail_and_404(app_client: AsyncClient, user_token: str):
    await _seed_domain(app_client)
    lst = await app_client.get(
        "/clients?page_size=1",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    cid = lst.json()["items"][0]["id"]
    detail = await app_client.get(
        f"/clients/{cid}", headers={"Authorization": f"Bearer {user_token}"}
    )
    assert detail.status_code == 200
    assert detail.json()["id"] == cid

    missing = await app_client.get(
        f"/clients/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_policies_list_filters(app_client: AsyncClient, user_token: str):
    await _seed_domain(app_client)
    resp = await app_client.get(
        "/policies?status=ACTIVE&product_type=AUTO",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 200, resp.text
    for item in resp.json()["items"]:
        assert item["status"] == "ACTIVE"
        assert item["product_type"] == "AUTO"


@pytest.mark.asyncio
async def test_policy_detail_includes_client_summary(
    app_client: AsyncClient, user_token: str
):
    await _seed_domain(app_client)
    lst = await app_client.get(
        "/policies?page_size=1",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    pid = lst.json()["items"][0]["id"]
    detail = await app_client.get(
        f"/policies/{pid}", headers={"Authorization": f"Bearer {user_token}"}
    )
    assert detail.status_code == 200
    body = detail.json()
    assert "client" in body
    assert set(body["client"].keys()) == {"id", "client_code", "full_name"}


@pytest.mark.asyncio
async def test_policy_404(app_client: AsyncClient, user_token: str):
    resp = await app_client.get(
        f"/policies/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_forbidden_when_permission_missing(app_client: AsyncClient):
    """A user whose role lacks client:view gets 403 (not 401)."""
    # Create a role-less user directly, mint a token for them.
    from app.core.jwt import mint_access_token
    from app.models.auth import User
    from app.core.passwords import hash_password

    TestSessionLocal = app_client._test_session  # type: ignore
    async with TestSessionLocal() as db:
        u = User(
            email="noperms@poc.local",
            password_hash=hash_password("Valid!Passw0rd123"),
            is_active=True,
        )
        db.add(u)
        await db.commit()
        uid = str(u.id)

    token, _, _ = mint_access_token(
        user_id=uid, email="noperms@poc.local", roles=[], permissions=[]
    )
    resp = await app_client.get(
        "/clients", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"
