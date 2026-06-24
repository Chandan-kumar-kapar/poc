from __future__ import annotations

import os

os.environ.setdefault("TESTING", "true")
os.environ.setdefault("AUTH_MODE", "NORMAL")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("POC_INMEMORY_KEYS", "1")

import pytest

from app.core.passwords import (
    PasswordPolicyError,
    hash_password,
    validate_password_policy,
    verify_password,
)


@pytest.mark.parametrize(
    "pw",
    ["short1!A", "alllower123!", "ALLUPPER123!", "NoDigitHere!!!!", "NoSpecial1234ABc"],
)
def test_password_policy_rejects_weak(pw):
    with pytest.raises(PasswordPolicyError):
        validate_password_policy(pw)


def test_password_policy_accepts_strong():
    validate_password_policy("Valid!Passw0rd123")


def test_hash_and_verify_roundtrip():
    h = hash_password("Valid!Passw0rd123")
    assert h != "Valid!Passw0rd123"
    assert verify_password("Valid!Passw0rd123", h) is True
    assert verify_password("wrong-password", h) is False


def test_verify_against_none_is_false_but_does_work():
    # Anti-enumeration: verifying against a missing hash must return False,
    # never raise, never authenticate.
    assert verify_password("anything", None) is False


def test_jwt_mint_and_verify():
    from app.core.jwt import TokenError, mint_access_token, verify_access_token

    token, jti, exp = mint_access_token(
        user_id="u1", email="a@b.com", roles=["User"], permissions=["client:view"]
    )
    claims = verify_access_token(token)
    assert claims["sub"] == "u1"
    assert claims["jti"] == jti
    assert "client:view" in claims["permissions"]
    assert claims["iss"] == "https://api.poc.local"
    assert claims["aud"] == "poc-api"


def test_jwt_rejects_tampered_token():
    from app.core.jwt import TokenError, mint_access_token, verify_access_token

    token, _, _ = mint_access_token(
        user_id="u1", email="a@b.com", roles=[], permissions=[]
    )
    tampered = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")
    with pytest.raises(TokenError):
        verify_access_token(tampered)


def test_jwt_rejects_wrong_audience(monkeypatch):
    from app.core import jwt as jwtmod
    from app.core.jwt import TokenError, mint_access_token, verify_access_token

    token, _, _ = mint_access_token(
        user_id="u1", email="a@b.com", roles=[], permissions=[]
    )
    # Change expected audience after minting -> must reject.
    settings = jwtmod.get_settings()
    monkeypatch.setattr(settings, "jwt_audience", "different-aud")
    with pytest.raises(TokenError):
        verify_access_token(token)


def test_pkce_pair_is_valid():
    import base64
    import hashlib

    from app.services.sso import make_pkce_pair

    verifier, challenge = make_pkce_pair()
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert challenge == expected
