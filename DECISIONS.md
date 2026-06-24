# DECISIONS.md

Design decisions, assumptions, and deliberate POC deferrals.

## Assumptions

- **Single IdP / OIDC provider.** SSO is modeled around one OIDC authority
  (Azure AD by default in the example config). Provider identity is keyed by
  `(provider, sub)` and stored in `oauth_accounts`, never on the user row.
- **Demo seed volume.** 20 clients and 50 policies, generated deterministically
  (fixed RNG seed) so search/view return stable, realistic data immediately.
- **Roles for the POC** are `Admin` and `User`. `Admin` implicitly holds all
  permissions; `User` holds `client:view` and `policy:view`. Authorization
  checks are **permission-based**, not role-name based (Admin is the single
  documented exception, resolved inside the permission check).
- **Readiness semantics.** `/ready` requires the database. Redis being down is
  *tolerated* (returns `redis: false` but still ready), because the access-token
  denylist falls back to PostgreSQL, which is the source of truth.
- **Refresh tokens are opaque** random strings, stored only as SHA-256 hashes.
  They are not JWTs. Access tokens are RS256 JWTs.
- **Self-issued tokens in all modes.** Even after SSO, the API issues its *own*
  access/refresh tokens; the IdP's `id_token` is used only to authenticate and
  link/provision, then discarded.

## Security decisions (implemented, not deferred)

- **Argon2id** with enforced floors (memory ≥ 19 MiB, time ≥ 2, parallelism ≥ 1);
  config values below the floor fail validation at startup.
- **Password policy**: min length 12 with upper/lower/number/special.
- **Anti-enumeration**: register never confirms whether an email already exists;
  login returns an identical generic error and performs hash work against a
  dummy hash when the account is missing, to avoid timing leaks.
- **JWT validation** enforces signature, `iss`, `aud`, `exp`/`nbf` (with
  configurable clock skew), and `kid` resolution; tokens missing `iss`/`aud`
  are rejected.
- **Refresh rotation + family reuse detection**: every refresh rotates the
  token; replay of a consumed token revokes the entire family.
- **Access-token revocation** via a `jti` denylist on logout, mirrored to Redis
  with a PostgreSQL fallback/record.
- **OIDC**: authorization-code flow with PKCE (S256), `state` (CSRF on
  callback), and `nonce` (validated against the id_token). The id_token is
  verified against the IdP JWKS (cached, with forced refresh on key rotation),
  checking `iss`/`aud`/`exp`/`nbf` with skew.
- **Account linking** auto-links to a local account only when the IdP asserts
  `email_verified`; otherwise explicit linking is required (`409`).
- **Security headers** on every response: `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, plus HSTS; CORS is configurable.

## Deferred (from the larger spec — out of POC scope)

These were explicitly allowed to be deferred. Clean extension points are left in
place; none weaken the implemented auth core.

- **MFA / TOTP / WebAuthn** — no second factor. Extension point: a `User` flag
  plus a post-password step before issuing tokens.
- **Email verification & password reset flows** — `User.email_verified` exists
  and is set by SSO, but no email-sending or reset endpoints are implemented.
- **Account lockout / CAPTCHA escalation** — no brute-force throttling beyond
  the generic-error + constant-time behavior. Extension point: per-identity
  counters in Redis feeding a lockout decision in `authenticate_local`.
- **Multi-tenancy** — single tenant; no org/tenant scoping on entities.
- **Audit log hash-chaining** — structured logs with correlation IDs are
  present, but no tamper-evident audit chain.
- **Outbox / async queue** — all writes are synchronous within the request.
- **Explicit account-linking UI/endpoint** — when verified-email linking is not
  possible, the callback returns `409 link_required`; the interactive linking
  endpoint itself is not built.
- **JWKS endpoint for our own tokens** — we expose tokens signed by a local
  keypair but do not publish a `/.well-known/jwks.json` for downstream
  verifiers. The key-by-`kid` file layout makes adding one trivial.
- **Refresh-token flow state in Redis for SSO** — the OIDC PKCE/state/nonce
  store is an in-process TTL map in this POC. For multi-instance deployments,
  swap `FlowStore` for a Redis-backed implementation (interface is already
  isolated).

## Notable implementation choices

- **Email validation allows internal domains.** Pydantic's default `EmailStr`
  (via `email-validator` 2.x) rejects reserved/special-use domains such as
  `.local` and `.internal` as a *syntax* error — even with deliverability
  checks off — so demo accounts like `admin@poc.local` would fail validation
  with a 422. `app/core/email_types.py` provides `EmailStrLoose`, which removes
  a small allow-list (`local`, `internal`, `lan`, `home`, `corp`) from
  `email_validator.SPECIAL_USE_DOMAIN_NAMES` and validates with
  `check_deliverability=False`. Genuinely-invalid reserved names (`localhost`,
  `invalid`) remain rejected. All schema `email` fields use this type.

- **Portable `GUID` type** (`app/db/types.py`): native PostgreSQL `UUID` in
  production, `CHAR(36)` under SQLite so the test suite runs with no external
  services. Always surfaces `uuid.UUID` in Python.
- **`testing` settings flag** relaxes mode config validation and switches to
  in-memory signing keys, so unit/integration tests need neither real OIDC
  config nor mounted PEM files.
- **App factory + conditional routers**: `create_app()` mounts auth routers
  based on `AUTH_MODE`; in SSO-only mode `/auth/logout` is still exposed by
  reusing the local logout handler.
