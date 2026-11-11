# Installing DataForge on a new machine

This is a from-zero setup guide — for restarting an *already-installed*
copy on this machine, see [RUNBOOK.md](RUNBOOK.md) instead. This guide
sets up the same stack in a cleaner, more portable way (standard Docker
port publishing instead of this machine's host-networking setup, which
only works on Linux and was more confusing than it was worth — see
RUNBOOK.md's troubleshooting section for the story).

## Prerequisites

- **Docker** (with `docker compose` or plain `docker run` — either works with the commands below)
- **Python 3.13**
- **Node.js 20+** and npm
- A way to get the code onto the new machine (git, if you push this repo to a remote first, or a plain `rsync`/`tar` copy — this repo currently has no git remote configured)

## 1. Get the code onto the new machine

```bash
# Option A: if you set up a git remote first
git clone <your-remote-url> dataforge

# Option B: just copy the directory (this repo has no remote yet)
rsync -av --exclude .venv --exclude node_modules --exclude backups \
  /home/merit/Dinesh/dataforge/ newmachine:/path/to/dataforge/
```

## 2. Data stores

Standard port-published containers — simpler than this machine's
host-networking setup and works the same on Linux/Mac/Windows Docker Desktop:

```bash
# Postgres -- the real database
docker run -d --name dataforge-postgres \
  -e POSTGRES_USER=dataforge -e POSTGRES_PASSWORD=dataforge -e POSTGRES_DB=dataforge \
  -p 5544:5432 -v dataforge-postgres-data:/var/lib/postgresql/data \
  postgres:16

# Redis -- job queue, circuit-breaker state, sync-poll locks
docker run -d --name dataforge-redis -p 6390:6379 -v dataforge-redis-data:/data redis:7

# MySQL -- only needed if you want the MySQL two-way-sync demo
docker run -d --name dataforge-mysql \
  -e MYSQL_ROOT_PASSWORD=rootpass -e MYSQL_DATABASE=external_test_db \
  -e MYSQL_USER=dataforge -e MYSQL_PASSWORD=dataforge \
  -p 3316:3306 -v dataforge-mysql-data:/var/lib/mysql \
  mysql:8.0

# Elasticsearch -- only needed for the Elasticsearch two-way-sync demo
docker run -d --name dataforge-elasticsearch \
  -e discovery.type=single-node -e xpack.security.enabled=false \
  -e "ES_JAVA_OPTS=-Xms512m -Xmx512m" \
  -p 9250:9200 -v dataforge-es-data:/usr/share/elasticsearch/data \
  docker.elastic.co/elasticsearch/elasticsearch:8.15.0
```

Wait ~10-20s for Postgres/Elasticsearch to finish starting, then confirm:
```bash
docker ps   # all four should show "Up"
```

Also create the dedicated test database (used only by the backend's own test suite, never the running app):
```bash
docker exec dataforge-postgres createdb -U dataforge dataforge_test
```

## 3. Backend

```bash
cd dataforge/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env` — **do not reuse this machine's `.env` file or the
defaults baked into `app/config.py`**. `ENCRYPTION_KEY` in particular
defaults to a value committed in the source (it decrypts every stored
connector credential) and `JWT_SECRET` defaults to the literal string
`"change-me-in-production"` — both must be real, unique secrets on any
machine that isn't purely disposable/local:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # -> ENCRYPTION_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(48))"                                 # -> JWT_SECRET
```

```
# backend/.env
DATABASE_URL=postgresql+asyncpg://dataforge:dataforge@localhost:5544/dataforge
REDIS_URL=redis://localhost:6390/0
JWT_SECRET=<paste the generated value>
ENCRYPTION_KEY=<paste the generated value>
CORS_ORIGINS=["http://localhost:5173", "http://127.0.0.1:5173"]
```

Run migrations:
```bash
alembic upgrade head
```

## 4. Frontend

```bash
cd dataforge/frontend
npm install
```

No `.env` needed — the Vite dev server proxies `/api` and `/ws` to
`localhost:8000` on its own (see `vite.config.ts`), so the browser never
needs separate backend configuration.

## 5. Start everything

```bash
# Backend API
cd dataforge/backend && source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &

# arq worker (background jobs: sync push/pull, automations, snapshots, audit log)
cd dataforge/backend && source .venv/bin/activate
arq app.worker.arq_app.WorkerSettings &

# Frontend
cd dataforge/frontend
npm run dev -- --host 0.0.0.0 --port 5173 &
```

Open `http://<new-machine>:5173` and register the first account.

## 6. Backups (optional but recommended)

`scripts/backup.sh` / `scripts/restore.sh` work unchanged on any machine —
they just need `pg_dump`/`pg_restore`/`psql` client tools installed
(`apt install postgresql-client` on Debian/Ubuntu, or reuse the ones
bundled with `psycopg2-binary`'s dependencies if that's simpler on your
platform). See RUNBOOK.md's "Backups" section for the cron line to add and
what it actually does; the daily automatic Base snapshots (separate from
this) need no extra setup — they run from the arq worker's own cron
(`app/worker/arq_app.py`) once it's up.

## 7. Verify

```bash
curl -s http://localhost:8000/api/auth/me   # 401/403 JSON = backend is up
curl -s http://localhost:5173               # 200 = frontend is up
docker ps                                   # all data-store containers "Up"
```

Then walk through: register a user → create a workspace/base/table → add a
row. If you want the sync demos too, connect a Postgres/MySQL/Elasticsearch
data source (Data sources page) pointing at the containers from step 2 and
import a table with "keep in sync" checked.
