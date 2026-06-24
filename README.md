# Auth + Client & Policy POC (FastAPI)

A small but production-shaped proof-of-concept backend API with three
selectable auth modes (`NORMAL` / `SSO` / `BOTH`), plus read-only **Client**
and **Policy** search & view. Async end-to-end: FastAPI + SQLAlchemy 2.x async +
asyncpg, PostgreSQL primary store, Redis for the access-token denylist and
refresh-reuse fast path.

> This is a POC. The auth core (passwords, JWT, refresh rotation/reuse
> detection, OIDC validation) is implemented at production depth. Client/Policy
> are intentionally read-only and simple. See `DECISIONS.md` for what was
> deliberately deferred.

---

## Quick start (one command)

```bash
docker compose up --build       # or: make up
```

This builds the API image, starts **PostgreSQL** and **Redis**, generates a dev
RS256 keypair if none is mounted, runs Alembic migrations, seeds demo data, and
starts the API.

- API:     http://localhost:8000
- Swagger: http://localhost:8000/docs
- ReDoc:   http://localhost:8000/redoc
- Health:  http://localhost:8000/health  /  Readiness: `/ready`

Default mode is `NORMAL` (local login only). To run with SSO see
[Switching AUTH_MODE](#switching-auth_mode).

### Demo credentials

| Role  | Email             | Password (default)   | Permissions                 |
|-------|-------------------|----------------------|-----------------------------|
| Admin | `admin@poc.local` | `Admin!Passw0rd123`  | all (implicit)              |
| User  | `user@poc.local`  | `User!Passw0rd123`   | `client:view`, `policy:view`|

Override via `SEED_ADMIN_PASSWORD` / `SEED_USER_PASSWORD` env vars. Passwords are
never hardcoded in source — the seed reads them from config.

---

## Try it

```bash
# 1) Log in -> get access + refresh tokens
curl -s http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@poc.local","password":"User!Passw0rd123"}'

# 2) Call a protected endpoint
TOKEN=...   # access_token from above
curl -s http://localhost:8000/clients?q=smith \
  -H "Authorization: Bearer $TOKEN"

# 3) Policy detail (includes a nested client summary)
curl -s http://localhost:8000/policies/<policy_id> \
  -H "Authorization: Bearer $TOKEN"
```

---

## Switching `AUTH_MODE`

The mode is **env-only** — no code changes. Startup **fails fast** if the active
mode is missing required config.

```bash
# Local only (default)
AUTH_MODE=NORMAL docker compose up --build

# SSO only — requires OIDC_* values
AUTH_MODE=SSO ENABLE_SSO=true \
  OIDC_CLIENT_ID=... OIDC_CLIENT_SECRET=... \
  OIDC_AUTHORITY=https://login.microsoftonline.com/<tenant>/v2.0 \
  OIDC_REDIRECT_URI=http://localhost:8000/auth/sso/callback \
  docker compose up --build

# Both — local + SSO; accounts linked by verified email
AUTH_MODE=BOTH ENABLE_SSO=true OIDC_CLIENT_ID=... ... docker compose up --build
```

| Mode     | Endpoints mounted                                                   |
|----------|---------------------------------------------------------------------|
| `NORMAL` | `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout` |
| `SSO`    | `GET /auth/sso/login`, `GET /auth/sso/callback`, `POST /auth/logout`  |
| `BOTH`   | all of the above                                                    |

In `BOTH`, IdP downtime does not break local login (graceful degradation): the
SSO login route returns `503`, while `/auth/login` keeps working.

---

## Key generation

The API signs its own access tokens with RS256. In Docker, a dev keypair is
auto-generated on first boot. To generate one yourself (e.g. for local runs):

```bash
python scripts/generate_keys.py --kid poc-key-a --out secrets
# -> secrets/jwt_private.pem and secrets/jwks/poc-key-a.pem
```

Public keys live in a directory named `<kid>.pem`, so key **rotation** is just
dropping in a new public key and pointing `JWT_ACTIVE_KID` at the new private
key. Old tokens still validate against the retained public key.

---

## Running locally without Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
make keys                            # generate signing keys into ./secrets
export JWT_PRIVATE_KEY_PATH=secrets/jwt_private.pem
export JWT_PUBLIC_KEYS_PATH=secrets/jwks/
export DATABASE_URL=postgresql+asyncpg://poc:poc@localhost:5432/poc
export REDIS_URL=redis://localhost:6379/0
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --reload
```

---

## Tests

```bash
make test        # or: pytest -q
```

The suite runs against in-memory SQLite with in-memory signing keys (no Postgres
or Redis required) and covers:

- **Security units** — password policy, Argon2 hash/verify, anti-enumeration,
  JWT mint/verify, tamper & wrong-audience rejection, PKCE correctness.
- **Auth integration** — login, generic errors for wrong-password vs unknown
  user, register non-disclosure, refresh **rotation**, refresh **reuse
  detection** (family revocation), logout **jti** denylist.
- **Clients/Policies** — search, pagination, detail, `404`s, and the authz
  paths: `401` (no token) and `403` (missing permission).

---

## Endpoints

```
GET  /health                 liveness
GET  /ready                  readiness (db required; redis degradation tolerated)
GET  /metrics                Prometheus (nice-to-have)

POST /auth/register          NORMAL/BOTH
POST /auth/login             NORMAL/BOTH
POST /auth/refresh           NORMAL/BOTH  (rotation + reuse detection)
POST /auth/logout            all modes    (revokes access jti; optional refresh family)
GET  /auth/me                any authenticated user
GET  /auth/sso/login         SSO/BOTH     (PKCE + state + nonce -> IdP redirect)
GET  /auth/sso/callback      SSO/BOTH     (validates id_token; links/provisions)

GET  /clients                require client:view  (q, status, page, page_size)
GET  /clients/{id}           require client:view  (404 if missing)
GET  /policies               require policy:view  (q, status, product_type, client_id, page, page_size)
GET  /policies/{id}          require policy:view  (404; includes client summary)
```

All errors use a consistent envelope:

```json
{ "error": { "code": "not_found", "message": "Client not found.", "correlation_id": "..." } }
```

---

## Project layout

```
app/
  core/        config, keys, passwords, jwt, deps (RBAC), errors, middleware
  models/      auth (user/role/permission/oauth), token, domain (client/policy)
  schemas/     pydantic request/response models
  api/         auth_local, auth_sso, clients, policies, health
  services/    auth, token, sso, client, policy
  db/          session, redis_client, types (portable GUID), seed, migrations
tests/         unit/ + integration/
deploy/        Dockerfile, entrypoint.sh
scripts/       generate_keys.py
```
