#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint] AUTH_MODE=${AUTH_MODE:-unset}"

# 1) Ensure JWT signing keys exist (NORMAL/BOTH issue our own RS256 tokens).
KEY_DIR="${JWT_KEY_DIR:-/run/secrets}"
PRIV="${JWT_PRIVATE_KEY_PATH:-/run/secrets/jwt_private.pem}"
KID="${JWT_ACTIVE_KID:-poc-key-a}"
if [ ! -f "$PRIV" ]; then
  echo "[entrypoint] No signing key at $PRIV — generating a dev keypair."
  mkdir -p "$KEY_DIR"
  python scripts/generate_keys.py --kid "$KID" --out "$KEY_DIR"
fi

# 2) Wait for PostgreSQL.
if [ -n "${DATABASE_URL:-}" ]; then
  echo "[entrypoint] Waiting for database..."
  python - <<'PY'
import asyncio, os, sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def wait():
    url = os.environ["DATABASE_URL"]
    eng = create_async_engine(url)
    for attempt in range(30):
        try:
            async with eng.connect() as c:
                await c.execute(text("SELECT 1"))
            print("[entrypoint] Database is ready.")
            await eng.dispose()
            return
        except Exception as e:
            print(f"[entrypoint] DB not ready ({attempt+1}/30): {e}")
            await asyncio.sleep(2)
    print("[entrypoint] Database never became ready.", file=sys.stderr)
    sys.exit(1)

asyncio.run(wait())
PY
fi

# 3) Migrate + seed.
echo "[entrypoint] Running migrations..."
alembic upgrade head

echo "[entrypoint] Seeding demo data..."
python -m app.db.seed

# 4) Launch.
echo "[entrypoint] Starting API: $*"
exec "$@"
