from __future__ import annotations

import enum
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthMode(str, enum.Enum):
    NORMAL = "NORMAL"
    SSO = "SSO"
    BOTH = "BOTH"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    auth_mode: AuthMode = AuthMode.BOTH

    # JWT
    jwt_algorithm: str = "RS256"
    jwt_private_key_path: str = "/run/secrets/jwt_private.pem"
    jwt_public_keys_path: str = "/run/secrets/jwks/"
    jwt_active_kid: str = "poc-key-a"
    jwt_issuer: str = "https://api.poc.local"
    jwt_audience: str = "poc-api"
    jwt_clock_skew_seconds: int = 60
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Argon2id (floors enforced)
    argon2_memory_kib: int = 19456
    argon2_time_cost: int = 2
    argon2_parallelism: int = 1

    # SSO / OIDC
    enable_sso: bool = True
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_authority: str = ""
    oidc_redirect_uri: str = ""
    oidc_scopes: str = "openid profile email"
    oidc_use_pkce: bool = True
    oidc_require_email_verified: bool = True
    oidc_jwks_cache_ttl_seconds: int = 3600
    auto_provision_sso_users: bool = True
    oidc_default_role: str = "User"

    # Infra
    database_url: str = "postgresql+asyncpg://poc:poc@db:5432/poc"
    redis_url: str = "redis://redis:6379/0"

    # Seed
    seed_admin_email: str = "admin@poc.local"
    seed_admin_password: str = "Admin!Passw0rd123"
    seed_user_email: str = "user@poc.local"
    seed_user_password: str = "User!Passw0rd123"

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Testing hook: when True, JWT keys are generated in-memory and OIDC config
    # is not required. Never set in production.
    testing: bool = False

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def normal_enabled(self) -> bool:
        return self.auth_mode in (AuthMode.NORMAL, AuthMode.BOTH)

    @property
    def sso_enabled(self) -> bool:
        return self.auth_mode in (AuthMode.SSO, AuthMode.BOTH)

    @field_validator("argon2_memory_kib")
    @classmethod
    def _argon2_memory_floor(cls, v: int) -> int:
        if v < 19456:
            raise ValueError("ARGON2_MEMORY_KIB must be >= 19456 (19 MiB floor)")
        return v

    @field_validator("argon2_time_cost")
    @classmethod
    def _argon2_time_floor(cls, v: int) -> int:
        if v < 2:
            raise ValueError("ARGON2_TIME_COST must be >= 2")
        return v

    @field_validator("argon2_parallelism")
    @classmethod
    def _argon2_parallelism_floor(cls, v: int) -> int:
        if v < 1:
            raise ValueError("ARGON2_PARALLELISM must be >= 1")
        return v

    @model_validator(mode="after")
    def _validate_active_mode(self) -> "Settings":
        if self.testing:
            return self
        # NORMAL requirements: signing keys must be present.
        if self.normal_enabled:
            missing = []
            if not self.jwt_private_key_path:
                missing.append("JWT_PRIVATE_KEY_PATH")
            if not self.jwt_public_keys_path:
                missing.append("JWT_PUBLIC_KEYS_PATH")
            if not self.jwt_active_kid:
                missing.append("JWT_ACTIVE_KID")
            if missing:
                raise ValueError(
                    f"AUTH_MODE={self.auth_mode.value} requires: {', '.join(missing)}"
                )
        # SSO requirements.
        if self.sso_enabled:
            missing = []
            for name, val in (
                ("OIDC_CLIENT_ID", self.oidc_client_id),
                ("OIDC_CLIENT_SECRET", self.oidc_client_secret),
                ("OIDC_AUTHORITY", self.oidc_authority),
                ("OIDC_REDIRECT_URI", self.oidc_redirect_uri),
            ):
                if not val:
                    missing.append(name)
            if missing:
                raise ValueError(
                    f"AUTH_MODE={self.auth_mode.value} requires SSO config: "
                    f"{', '.join(missing)}"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
