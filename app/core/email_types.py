from __future__ import annotations

from typing import Annotated

import email_validator
from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator

# email-validator 2.x rejects reserved/special-use domains (e.g. ".local",
# ".internal") as a SYNTAX error, even when deliverability checks are disabled.
# For a POC that uses internal addresses we relax this by removing the entries
# we want to permit from the module-level special-use list. This affects only
# syntax classification, not deliverability.
_ALLOWED_RESERVED = {"local", "internal", "lan", "home", "corp"}
try:  # be defensive across library versions
    email_validator.SPECIAL_USE_DOMAIN_NAMES = [
        d for d in email_validator.SPECIAL_USE_DOMAIN_NAMES
        if d not in _ALLOWED_RESERVED
    ]
except Exception:  # pragma: no cover - attribute name changed upstream
    pass


def _validate_email_allow_reserved(value: str) -> str:
    """Validate email syntax with deliverability checks off so internal
    addresses (e.g. admin@poc.local) are accepted. Returns normalized form."""
    try:
        result = validate_email(value, check_deliverability=False)
    except EmailNotValidError as e:
        raise ValueError(str(e)) from e
    return result.normalized


# Drop-in replacement for pydantic EmailStr that tolerates internal domains.
EmailStrLoose = Annotated[str, AfterValidator(_validate_email_allow_reserved)]
