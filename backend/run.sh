#!/usr/bin/env bash
# Local dev runner — no Docker networking involved beyond starting the
# already-created dataforge-postgres container (docker start never creates
# a new network, it just resumes a container that already uses --network host).
set -euo pipefail
cd "$(dirname "$0")"

export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://dataforge:dataforge@localhost:5544/dataforge}"
export JWT_SECRET="${JWT_SECRET:-dev-secret}"

if ! docker ps --format '{{.Names}}' | grep -q '^dataforge-postgres$'; then
  echo "Starting dataforge-postgres container..."
  docker start dataforge-postgres
  sleep 2
fi

.venv/bin/alembic upgrade head
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
