from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.jwt import TokenError, verify_access_token
from app.db.session import get_session
from app.models.auth import User
from app.services import auth as auth_service
from app.services import token as token_service

bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser:
    def __init__(self, user: User, claims: dict):
        self.user = user
        self.claims = claims

    @property
    def id(self):
        return self.user.id

    @property
    def email(self) -> str:
        return self.user.email

    @property
    def permissions(self) -> list[str]:
        return self.user.permission_names

    @property
    def roles(self) -> list[str]:
        return self.user.role_names

    def has_permission(self, permission: str) -> bool:
        # Admin implicitly has all permissions.
        if "Admin" in self.roles:
            return True
        return permission in self.permissions


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> CurrentUser:
    if credentials is None or not credentials.credentials:
        raise AppError(
            "unauthorized", "Missing bearer token.", status.HTTP_401_UNAUTHORIZED
        )
    token = credentials.credentials
    try:
        claims = verify_access_token(token)
    except TokenError as e:
        raise AppError(
            "unauthorized", f"Invalid token: {e}", status.HTTP_401_UNAUTHORIZED
        ) from e

    jti = claims.get("jti")
    if jti and await token_service.is_access_jti_revoked(db, jti):
        raise AppError(
            "unauthorized", "Token has been revoked.", status.HTTP_401_UNAUTHORIZED
        )

    user = await auth_service.get_user_by_id(db, claims["sub"])
    if user is None or not user.is_active:
        raise AppError(
            "unauthorized", "User not found or inactive.", status.HTTP_401_UNAUTHORIZED
        )
    return CurrentUser(user=user, claims=claims)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_permission(permission: str):
    async def _dep(current: CurrentUserDep) -> CurrentUser:
        if not current.has_permission(permission):
            raise AppError(
                "forbidden",
                f"Missing required permission: {permission}",
                status.HTTP_403_FORBIDDEN,
            )
        return current

    return _dep
