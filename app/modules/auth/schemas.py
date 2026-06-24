from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field
from app.core.email_types import EmailStrLoose as EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expiry


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    # Optional: revoke a specific refresh token family on logout.
    refresh_token: str | None = None


class MessageResponse(BaseModel):
    message: str


class UserInfo(BaseModel):
    id: str
    email: EmailStr
    roles: List[str]
    permissions: List[str]
