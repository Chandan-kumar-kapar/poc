from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from jose import jwt
from jose.exceptions import JWTError

from app.core.config import get_settings
from app.core.keys import get_keyset


class TokenError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def mint_access_token(
    *,
    user_id: str,
    email: str,
    roles: List[str],
    permissions: List[str],
) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at)."""
    settings = get_settings()
    keyset = get_keyset()
    jti = str(uuid.uuid4())
    iat = _now()
    exp = iat + timedelta(minutes=settings.access_token_expire_minutes)
    claims: Dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "roles": roles,
        "permissions": permissions,
        "jti": jti,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(iat.timestamp()),
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(
        claims,
        keyset.private_pem,
        algorithm=settings.jwt_algorithm,
        headers={"kid": keyset.active_kid},
    )
    return token, jti, exp


def verify_access_token(token: str) -> Dict[str, Any]:
    """Validate signature, iss, aud, exp/nbf (with skew), and kid resolution.
    Rejects tokens missing iss/aud. Raises TokenError on any failure."""
    settings = get_settings()
    keyset = get_keyset()

    try:
        header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise TokenError(f"Malformed token header: {e}") from e

    kid = header.get("kid")
    if not kid:
        raise TokenError("Token header missing 'kid'.")
    public_pem = keyset.public_pems.get(kid)
    if public_pem is None:
        raise TokenError(f"Unknown signing key id (kid={kid}).")

    try:
        claims = jwt.decode(
            token,
            public_pem,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={
                "require_iss": True,
                "require_aud": True,
                "require_exp": True,
                "verify_iss": True,
                "verify_aud": True,
                "verify_exp": True,
                "verify_nbf": True,
                "leeway": settings.jwt_clock_skew_seconds,
            },
        )
    except JWTError as e:
        raise TokenError(f"Token validation failed: {e}") from e

    if "iss" not in claims or "aud" not in claims:
        raise TokenError("Token missing required iss/aud claims.")
    return claims
