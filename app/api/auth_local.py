from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import CurrentUserDep
from app.core.errors import AppError
from app.core.jwt import mint_access_token
from app.core.passwords import PasswordPolicyError
from app.db.session import get_session
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserInfo,
)
from app.services import auth as auth_service
from app.services import token as token_service

router = APIRouter(prefix="/auth", tags=["auth-local"])
settings = get_settings()

# Generic, identical message for register/login to prevent account enumeration.
_GENERIC_AUTH_ERROR = "Invalid credentials."


def _token_response(user_id: str, email: str, roles, perms, refresh_raw: str) -> TokenResponse:
    access, _jti, exp = mint_access_token(
        user_id=user_id, email=email, roles=roles, permissions=perms
    )
    import time

    return TokenResponse(
        access_token=access,
        refresh_token=refresh_raw,
        expires_in=int(exp.timestamp() - time.time()),
    )


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> MessageResponse:
    try:
        await auth_service.register_local_user(
            db, email=body.email, password=body.password,
            default_role=settings.oidc_default_role,
        )
        await db.commit()
    except PasswordPolicyError as e:
        # Policy feedback is safe to return (not account-existence related).
        raise AppError("weak_password", str(e), status.HTTP_400_BAD_REQUEST) from e
    except auth_service.RegistrationError:
        # Account already exists: respond identically to the success path shape
        # would leak nothing, but we must not confirm existence. Return 201-like
        # generic message without creating anything.
        await db.rollback()
        return MessageResponse(message="Registration received.")
    return MessageResponse(message="Registration received.")


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> TokenResponse:
    user = await auth_service.authenticate_local(
        db, email=body.email, password=body.password
    )
    if user is None:
        raise AppError(
            "invalid_credentials", _GENERIC_AUTH_ERROR, status.HTTP_401_UNAUTHORIZED
        )
    refresh_raw = await token_service.issue_refresh_token(db, user_id=user.id)
    resp = _token_response(
        str(user.id), user.email, user.role_names, user.permission_names, refresh_raw
    )
    await db.commit()
    return resp


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> TokenResponse:
    try:
        user_id, new_raw = await token_service.rotate_refresh_token(
            db, body.refresh_token
        )
    except token_service.RefreshReuseError:
        await db.commit()  # persist family revocation
        raise AppError(
            "token_reuse",
            "Refresh token reuse detected. Please log in again.",
            status.HTTP_401_UNAUTHORIZED,
        )
    except token_service.RefreshInvalidError as e:
        await db.rollback()
        raise AppError(
            "invalid_refresh", "Invalid refresh token.", status.HTTP_401_UNAUTHORIZED
        ) from e

    user = await auth_service.get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        await db.rollback()
        raise AppError(
            "invalid_refresh", "Invalid refresh token.", status.HTTP_401_UNAUTHORIZED
        )
    resp = _token_response(
        str(user.id), user.email, user.role_names, user.permission_names, new_raw
    )
    await db.commit()
    return resp


@router.post("/logout", response_model=MessageResponse)
async def logout(
    body: LogoutRequest,
    current: CurrentUserDep,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> MessageResponse:
    # Revoke current access token by jti.
    jti = current.claims.get("jti")
    exp = current.claims.get("exp")
    if jti and exp:
        from datetime import datetime, timezone

        await token_service.revoke_access_jti(
            db, jti, datetime.fromtimestamp(exp, tz=timezone.utc)
        )
    # Optionally revoke the presented refresh family.
    if body.refresh_token:
        await token_service.revoke_refresh_family(db, body.refresh_token)
    await db.commit()
    return MessageResponse(message="Logged out.")


@router.get("/me", response_model=UserInfo)
async def me(current: CurrentUserDep) -> UserInfo:
    return UserInfo(
        id=str(current.id),
        email=current.email,
        roles=current.roles,
        permissions=current.permissions,
    )
