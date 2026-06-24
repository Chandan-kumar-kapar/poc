from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.passwords import (
    hash_password,
    needs_rehash,
    validate_password_policy,
    verify_password,
)
from app.models.auth import OAuthAccount, Role, User


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(
        select(User).where(func.lower(User.email) == email.lower())
    )
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str | uuid.UUID) -> Optional[User]:
    if isinstance(user_id, str):
        try:
            user_id = uuid.UUID(user_id)
        except ValueError:
            return None
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_role(db: AsyncSession, name: str) -> Optional[Role]:
    result = await db.execute(select(Role).where(Role.name == name))
    return result.scalar_one_or_none()


class RegistrationError(Exception):
    pass


async def register_local_user(
    db: AsyncSession, *, email: str, password: str, default_role: str = "User"
) -> User:
    validate_password_policy(password)
    existing = await get_user_by_email(db, email)
    if existing is not None:
        # Caller must NOT reveal this to the client (anti-enumeration).
        raise RegistrationError("exists")

    user = User(
        email=email,
        password_hash=hash_password(password),
        email_verified=False,
        is_active=True,
    )
    role = await get_role(db, default_role)
    if role is not None:
        user.roles.append(role)
    db.add(user)
    await db.flush()
    return user


async def authenticate_local(
    db: AsyncSession, *, email: str, password: str
) -> Optional[User]:
    """Returns the user on success, else None. Always does hash work to avoid
    timing-based account enumeration."""
    user = await get_user_by_email(db, email)
    stored_hash = user.password_hash if user else None
    ok = verify_password(password, stored_hash)
    if not ok or user is None or not user.is_active:
        return None
    # Opportunistic rehash if params changed.
    if user.password_hash and needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        await db.flush()
    return user


async def find_or_provision_sso_user(
    db: AsyncSession,
    *,
    provider: str,
    subject: str,
    email: Optional[str],
    email_verified: bool,
    auto_provision: bool,
    default_role: str,
    require_email_verified: bool,
) -> tuple[Optional[User], str]:
    """Returns (user, status). status in:
    'linked_existing', 'provisioned', 'needs_explicit_link', 'denied'."""
    # 1) Already-linked provider identity?
    result = await db.execute(
        select(OAuthAccount).where(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_subject == subject,
        )
    )
    oauth = result.scalar_one_or_none()
    if oauth is not None:
        user = await get_user_by_id(db, oauth.user_id)
        return user, "linked_existing"

    # 2) Try to link by verified email to an existing local account.
    if email:
        existing = await get_user_by_email(db, email)
        if existing is not None:
            if email_verified:
                db.add(
                    OAuthAccount(
                        user_id=existing.id,
                        provider=provider,
                        provider_subject=subject,
                        email=email,
                    )
                )
                await db.flush()
                return existing, "linked_existing"
            # Email not verified by IdP -> require explicit linking.
            return None, "needs_explicit_link"

    # 3) No existing user. Provision if allowed and email is acceptable.
    if not auto_provision:
        return None, "denied"
    if require_email_verified and not email_verified:
        return None, "needs_explicit_link"

    user = User(
        email=email or f"{subject}@{provider}.sso.local",
        password_hash=None,
        email_verified=bool(email_verified),
        is_active=True,
    )
    role = await get_role(db, default_role)
    if role is not None:
        user.roles.append(role)
    db.add(user)
    await db.flush()

    db.add(
        OAuthAccount(
            user_id=user.id,
            provider=provider,
            provider_subject=subject,
            email=email,
        )
    )
    await db.flush()
    return user, "provisioned"
