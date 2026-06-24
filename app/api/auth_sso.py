from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.jwt import mint_access_token
from app.db.session import get_session
from app.schemas.auth import TokenResponse
from app.services import auth as auth_service
from app.services import sso as sso_service
from app.services import token as token_service

router = APIRouter(prefix="/auth/sso", tags=["auth-sso"])
settings = get_settings()


@router.get("/login")
async def sso_login() -> RedirectResponse:
    try:
        url, _state = await sso_service.build_authorize_url()
    except Exception as e:
        # IdP discovery unreachable. In BOTH mode local login still works.
        raise AppError(
            "sso_unavailable",
            "SSO provider is currently unavailable.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from e
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


@router.get("/callback", response_model=TokenResponse)
async def sso_callback(
    db: Annotated[AsyncSession, Depends(get_session)],
    code: str = Query(...),
    state: str = Query(...),
) -> TokenResponse:
    try:
        claims = await sso_service.exchange_and_validate(code=code, state=state)
    except sso_service.SSOError as e:
        raise AppError("sso_error", str(e), status.HTTP_400_BAD_REQUEST) from e

    provider = "oidc"
    subject = claims.get("sub")
    email = claims.get("email")
    email_verified = bool(claims.get("email_verified", False))
    if not subject:
        raise AppError("sso_error", "ID token missing subject.", status.HTTP_400_BAD_REQUEST)

    user, outcome = await auth_service.find_or_provision_sso_user(
        db,
        provider=provider,
        subject=subject,
        email=email,
        email_verified=email_verified,
        auto_provision=settings.auto_provision_sso_users,
        default_role=settings.oidc_default_role,
        require_email_verified=settings.oidc_require_email_verified,
    )

    if user is None:
        if outcome == "needs_explicit_link":
            raise AppError(
                "link_required",
                "An account with this email exists but requires explicit linking "
                "(email not verified by provider).",
                status.HTTP_409_CONFLICT,
            )
        raise AppError(
            "sso_denied", "SSO login not permitted.", status.HTTP_403_FORBIDDEN
        )

    refresh_raw = await token_service.issue_refresh_token(db, user_id=user.id)
    access, _jti, exp = mint_access_token(user_id=str(user.id))
    import time

    resp = TokenResponse(
        access_token=access,
        refresh_token=refresh_raw,
        expires_in=int(exp.timestamp() - time.time()),
    )
    await db.commit()
    return resp
