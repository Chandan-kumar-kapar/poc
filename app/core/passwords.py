from __future__ import annotations

import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

_settings = get_settings()

_ph = PasswordHasher(
    memory_cost=_settings.argon2_memory_kib,
    time_cost=_settings.argon2_time_cost,
    parallelism=_settings.argon2_parallelism,
)

# A pre-computed dummy hash used to keep verification time constant when the
# account does not exist (anti-enumeration).
_DUMMY_HASH = _ph.hash("dummy-password-for-constant-time-x9Q!")

_PASSWORD_RE_UPPER = re.compile(r"[A-Z]")
_PASSWORD_RE_LOWER = re.compile(r"[a-z]")
_PASSWORD_RE_DIGIT = re.compile(r"[0-9]")
_PASSWORD_RE_SPECIAL = re.compile(r"[^A-Za-z0-9]")


class PasswordPolicyError(ValueError):
    pass


def validate_password_policy(password: str) -> None:
    """Min length 12 with upper/lower/number/special. Raises on violation."""
    if len(password) < 12:
        raise PasswordPolicyError("Password must be at least 12 characters long.")
    if not _PASSWORD_RE_UPPER.search(password):
        raise PasswordPolicyError("Password must contain an uppercase letter.")
    if not _PASSWORD_RE_LOWER.search(password):
        raise PasswordPolicyError("Password must contain a lowercase letter.")
    if not _PASSWORD_RE_DIGIT.search(password):
        raise PasswordPolicyError("Password must contain a number.")
    if not _PASSWORD_RE_SPECIAL.search(password):
        raise PasswordPolicyError("Password must contain a special character.")


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-time-ish verify. When hash is None, still does work against a
    dummy hash so timing does not reveal account existence."""
    target = password_hash if password_hash is not None else _DUMMY_HASH
    try:
        _ph.verify(target, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    # Never authenticate against the dummy hash.
    return password_hash is not None


def needs_rehash(password_hash: str) -> bool:
    try:
        return _ph.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True
