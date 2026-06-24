from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from jose import jwt
from jose.exceptions import JWTError

from app.core.config import get_settings

settings = get_settings()


# --- Transient login-flow state (PKCE verifier, state, nonce) ---
# Stored server-side keyed by `state`. Redis-backed in real deployments; here we
# keep a TTL dict to avoid extra moving parts in the POC. Swap for Redis easily.

@dataclass
class FlowState:
    code_verifier: str
    nonce: str
    created_at: float


class FlowStore:
    def __init__(self, ttl_seconds: int = 600):
        self._data: dict[str, FlowState] = {}
        self._ttl = ttl_seconds

    def put(self, state: str, fs: FlowState) -> None:
        self._gc()
        self._data[state] = fs

    def pop(self, state: str) -> Optional[FlowState]:
        self._gc()
        return self._data.pop(state, None)

    def _gc(self) -> None:
        now = time.time()
        expired = [k for k, v in self._data.items() if now - v.created_at > self._ttl]
        for k in expired:
            self._data.pop(k, None)


flow_store = FlowStore()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_pkce_pair() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(64))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def make_state() -> str:
    return secrets.token_urlsafe(32)


def make_nonce() -> str:
    return secrets.token_urlsafe(32)


# --- OIDC discovery + JWKS caching ---

class _Cache:
    metadata: Optional[dict[str, Any]] = None
    metadata_at: float = 0.0
    jwks: Optional[dict[str, Any]] = None
    jwks_at: float = 0.0


_cache = _Cache()


async def get_discovery() -> dict[str, Any]:
    now = time.time()
    if _cache.metadata and now - _cache.metadata_at < settings.oidc_jwks_cache_ttl_seconds:
        return _cache.metadata
    url = settings.oidc_authority.rstrip("/") + "/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        _cache.metadata = resp.json()
        _cache.metadata_at = now
    return _cache.metadata


async def get_jwks(force: bool = False) -> dict[str, Any]:
    now = time.time()
    if (
        not force
        and _cache.jwks
        and now - _cache.jwks_at < settings.oidc_jwks_cache_ttl_seconds
    ):
        return _cache.jwks
    meta = await get_discovery()
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(meta["jwks_uri"])
        resp.raise_for_status()
        _cache.jwks = resp.json()
        _cache.jwks_at = now
    return _cache.jwks


async def build_authorize_url() -> tuple[str, str]:
    """Returns (authorize_url, state). Stores PKCE verifier + nonce server-side."""
    meta = await get_discovery()
    state = make_state()
    nonce = make_nonce()
    verifier, challenge = make_pkce_pair()
    flow_store.put(
        state, FlowState(code_verifier=verifier, nonce=nonce, created_at=time.time())
    )
    params = {
        "client_id": settings.oidc_client_id,
        "response_type": "code",
        "redirect_uri": settings.oidc_redirect_uri,
        "scope": settings.oidc_scopes,
        "state": state,
        "nonce": nonce,
    }
    if settings.oidc_use_pkce:
        params["code_challenge"] = challenge
        params["code_challenge_method"] = "S256"
    from urllib.parse import urlencode

    return f"{meta['authorization_endpoint']}?{urlencode(params)}", state


class SSOError(Exception):
    pass


async def exchange_and_validate(
    *, code: str, state: str
) -> dict[str, Any]:
    """Exchange the auth code, validate the ID token (sig, iss, aud, exp/nbf,
    nonce). Returns ID-token claims."""
    fs = flow_store.pop(state)
    if fs is None:
        raise SSOError("Invalid or expired state (possible CSRF).")

    meta = await get_discovery()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.oidc_redirect_uri,
        "client_id": settings.oidc_client_id,
        "client_secret": settings.oidc_client_secret,
    }
    if settings.oidc_use_pkce:
        data["code_verifier"] = fs.code_verifier

    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.post(meta["token_endpoint"], data=data)
        if resp.status_code != 200:
            raise SSOError(f"Token exchange failed: {resp.status_code}")
        tokens = resp.json()

    id_token = tokens.get("id_token")
    if not id_token:
        raise SSOError("No id_token in token response.")

    claims = await _validate_id_token(id_token, expected_nonce=fs.nonce)
    return claims


async def _validate_id_token(id_token: str, *, expected_nonce: str) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(id_token)
    except JWTError as e:
        raise SSOError(f"Malformed id_token: {e}") from e

    kid = header.get("kid")
    jwks = await get_jwks()
    key = _find_jwk(jwks, kid)
    if key is None:
        # Possible key rotation: refresh once.
        jwks = await get_jwks(force=True)
        key = _find_jwk(jwks, kid)
    if key is None:
        raise SSOError("No matching JWKS key for id_token.")

    try:
        claims = jwt.decode(
            id_token,
            key,
            algorithms=[header.get("alg", "RS256")],
            audience=settings.oidc_client_id,
            options={
                "require_iss": True,
                "require_aud": True,
                "require_exp": True,
                "verify_aud": True,
                "verify_exp": True,
                "verify_nbf": True,
                "leeway": settings.jwt_clock_skew_seconds,
            },
        )
    except JWTError as e:
        raise SSOError(f"id_token validation failed: {e}") from e

    if claims.get("nonce") != expected_nonce:
        raise SSOError("Nonce mismatch (possible replay).")

    return claims


def _find_jwk(jwks: dict[str, Any], kid: Optional[str]) -> Optional[dict]:
    for k in jwks.get("keys", []):
        if k.get("kid") == kid:
            return k
    return None
