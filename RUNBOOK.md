# DataForge Runbook — instances, and how to start/stop everything

Host: `mssplser13`, project at `/home/merit/Dinesh/dataforge`. This document is
about the *actual* running dev setup on this machine, not the (stale)
`docker-compose.yml` in this repo — see the note at the bottom.

## Instance inventory

| # | Instance | What it is | Port | Started as | Used by the app? |
|---|----------|-----------|------|-----------|-------------------|
| 1 | Postgres | Docker container `dataforge-postgres` (host networking) | 5544 | `docker` | **Yes — the real dev database** |
| 2 | Redis | Docker container `dataforge-redis` (host networking) | 6390 | `docker` | **Yes — the real cache/queue/broker** |
| 3 | MySQL | Docker container `dataforge-mysql` (host networking) | 3316 | `docker` | Yes — sample MySQL data source (for the two-way sync demo) |
| 4 | Elasticsearch | Docker container `dataforge-elasticsearch` (host networking, security disabled) | 9250 | `docker` | Yes — sample Elasticsearch data source (for the two-way sync demo) |
| 5 | Backend API | `uvicorn` inside `screen -S dataforge-backend` (has `--reload`, picks up most code changes automatically) | 8000 | `screen` | Yes |
| 6 | arq worker | inside `screen -S dataforge-arq` — runs background jobs: sync push/pull, automations, audit log, daily snapshots. **No hot-reload** — must be restarted by hand after backend code changes | — | `screen` | Yes |
| 7 | Frontend | Vite dev server inside `screen -S dataforge-frontend` (`npm run dev`) | 5173 | `screen` | Yes |
| — | `dataforge-postgres-1` | leftover container, state `Created`, never started | — | — | No — safe to ignore/remove |

**Important — instances #1 and #2 look like Docker containers with no port
bindings if you run `docker inspect`, but they ARE the real thing.** They use
Docker's *host networking* mode, which means `.NetworkSettings.Ports` always
shows empty (there's no Docker-managed port forwarding to display — the
container's process binds the host port directly). Don't take an empty
`docker inspect` ports field as "this container is unused" — check what's
actually listening on the port instead (see Troubleshooting below). This
tripped me up earlier in this project too.

`backend/.env` is the source of truth for what the backend actually connects to:
```
DATABASE_URL=postgresql+asyncpg://dataforge:dataforge@localhost:5544/dataforge
REDIS_URL=redis://localhost:6390/0
JWT_SECRET=<real generated secret -- see below>
ENCRYPTION_KEY=<real generated key -- see below>
```

**`JWT_SECRET` and `ENCRYPTION_KEY` are real, unique values here, not the
defaults baked into `app/config.py`** — rotated on 2026-09-22, once other
people started actually using this instance (a shared box running on the
committed default key/secret means anyone who can read the source code can
forge a login token for any user, or decrypt every stored connector
credential — fine for a solo throwaway box, not once it's shared). If you
ever need to rotate `ENCRYPTION_KEY` again: run
`backend/scripts/rotate_encryption_key.py <old_key> <new_key>` **before**
changing `.env` — it re-encrypts every stored DataSource config from the old
key to the new one, so nothing goes stale mid-rotation. Rotating
`JWT_SECRET` needs no migration; it just signs everyone out (every existing
token stops validating), which is harmless, just log back in.

## Starting everything from scratch

Order matters — data stores first, then the app processes that depend on them.

The three app processes run inside named `screen` sessions, not bare
`nohup`/`disown` background jobs — either survives a terminal closing, but
`screen` also means you (or anyone else with shell access) can reattach
later and watch live output, which `nohup`'s log-file-only approach doesn't
give you. Either way they survive your own logout/login; `screen` is just
strictly more useful once more than one person might need to check on them.

```bash
# 1. Data stores (skip any that are already running -- `docker ps` to check)
docker start dataforge-postgres
docker start dataforge-redis
docker start dataforge-mysql          # only needed for the MySQL sync demo
docker start dataforge-elasticsearch  # only needed for the ES sync demo

# 2. Backend API
screen -dmS dataforge-backend bash -c 'cd /home/merit/Dinesh/dataforge/backend && source .venv/bin/activate && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload'

# 3. arq worker (background jobs)
screen -dmS dataforge-arq bash -c 'cd /home/merit/Dinesh/dataforge/backend && source .venv/bin/activate && exec arq app.worker.arq_app.WorkerSettings'

# 4. Frontend
screen -dmS dataforge-frontend bash -c 'cd /home/merit/Dinesh/dataforge/frontend && export PATH="$PWD/.conda-node/bin:$PATH" && exec npm run dev -- --host 0.0.0.0 --port 5173'
```

Open `http://<this-host>:5173` in a browser — the frontend's own dev-server
proxy forwards `/api` and `/ws` to `localhost:8000` (see
`frontend/vite.config.ts`), so you never need to point it at the backend
manually, even over SSH/VSCode port-forwarding.

**Checking on / reattaching to a running session:**
```bash
screen -ls                        # list all three -- confirms they're alive
screen -r dataforge-backend       # attach and watch live logs
# Ctrl-A then D to detach again WITHOUT stopping it -- Ctrl-C would kill it.
```
If a session isn't listed at all, it exited (crashed or was killed) — check
`screen -r <name>` won't work for a dead session; just re-run its start
command from step 2-4 above.

## Stopping everything

Reverse order — app processes first, so nothing tries to write to a store
that's already gone.

```bash
# 1-3. App processes -- kills the screen session and the process inside it together
screen -S dataforge-frontend -X quit
screen -S dataforge-arq -X quit       # let in-flight jobs finish first if you can -- see note below
screen -S dataforge-backend -X quit

# 4. Data stores -- only stop these if you actually want the whole stack down.
#    Stopping postgres/redis takes down real data connections, not just a cache.
docker stop dataforge-mysql dataforge-elasticsearch   # sample sources -- safe to stop anytime
docker stop dataforge-postgres dataforge-redis        # the real DB + queue -- stop last, start first
```

`screen -X quit` sends the equivalent of closing the terminal, which arq
treats the same as SIGTERM (graceful) rather than SIGKILL -- in-flight jobs
still get a chance to finish, same as the old `pkill` approach did.

In everyday dev work you'll almost never want to stop `dataforge-postgres` /
`dataforge-redis` at all — just restart the backend/arq/frontend processes
when you need to. Stop the two data-store containers only when you're
shutting the whole environment down (e.g. before a host reboot).

## Per-instance start/stop (when you only need one)

| Instance | Start | Stop |
|---|---|---|
| Postgres | `docker start dataforge-postgres` | `docker stop dataforge-postgres` |
| Redis | `docker start dataforge-redis` | `docker stop dataforge-redis` |
| MySQL | `docker start dataforge-mysql` | `docker stop dataforge-mysql` |
| Elasticsearch | `docker start dataforge-elasticsearch` | `docker stop dataforge-elasticsearch` |
| Backend | see step 2 above | `screen -S dataforge-backend -X quit` |
| arq worker | see step 3 above | `screen -S dataforge-arq -X quit` |
| Frontend | see step 4 above | `screen -S dataforge-frontend -X quit` |

**Restarting just the arq worker** (needed after editing any file under
`app/worker/`, since it has no hot-reload):
```bash
screen -S dataforge-arq -X quit
screen -dmS dataforge-arq bash -c 'cd /home/merit/Dinesh/dataforge/backend && source .venv/bin/activate && exec arq app.worker.arq_app.WorkerSettings'
```

## Health checks

```bash
curl -s http://localhost:8000/api/auth/me        # 401 JSON = backend is up
curl -s http://127.0.0.1:9250                    # Elasticsearch cluster info
docker ps --filter name=dataforge                # all 4 containers should show "Up"
screen -ls                                       # all three dataforge-* sessions should be listed
screen -S dataforge-arq -X hardcopy /tmp/arq-check.log && tail -f /tmp/arq-check.log   # confirm the per-minute cron is ticking
```

## Troubleshooting: "is this container actually listening?"

Don't trust `docker inspect ... .NetworkSettings.Ports` alone for a
host-networking container (it's always empty). Instead:
```bash
ss -ltn | grep -E "5544|6390|3316|9250"          # what's actually bound, host-wide
docker inspect <container> --format '{{.State.Pid}}'   # host-side PID of the container's PID 1
ps -o pid,user,cmd -p <that PID>                 # confirm it's the process you expect
```

## Backups

`scripts/backup.sh` takes a full backup of the real database plus the two
local-disk asset directories it references (attachment files, uploaded
sqlite sources) — restoring the DB alone without these would leave records
pointing at files that no longer exist. It runs automatically **daily at
2:30 AM** via cron (`crontab -l` to see it), writing into
`backups/<UTC timestamp>/`, and self-prunes anything older than 14 days.
Each run also sanity-checks its own dump with `pg_restore --list` before
declaring success — a corrupt backup fails loudly at backup time, not
months later when it's actually needed.

Deliberately **not** backed up: Redis. Everything in it (arq's job queue,
circuit-breaker state, sync-poll advisory locks) is either already durable
in Postgres or safely disposable — losing it just delays a queued job, never
loses data.

```bash
# Run one manually (e.g. before a risky migration or schema change)
./scripts/backup.sh

# List what's available
ls backups/

# Restore into a THROWAWAY database to inspect old data or verify a backup
# -- always do this first, never restore straight into the real one.
./scripts/restore.sh <timestamp> dataforge_restore_check

# Restore over the real database -- refused unless you explicitly confirm.
# This check exists because a stray env var already truncated real dev data
# once this project (see the standing pytest DATABASE_URL rule elsewhere in
# this doc's history) -- don't remove it to save a step.
CONFIRM_OVERWRITE_REAL_DB=yes ./scripts/restore.sh <timestamp> dataforge
```

Attachment/sqlite-source files live alongside the dump as `attachments.tar.gz`
/ `sqlite_sources.tar.gz` in the same timestamped directory — `restore.sh`
prints the exact extract command for each after a successful restore.

This is logical, point-in-time-at-backup-time backup (a snapshot once a day),
not continuous point-in-time recovery (WAL archiving, which would let you
restore to *any* second, not just 2:30 AM) — a deliberate v1 scope choice.
If losing up to a day of edits in a true disaster ever becomes unacceptable,
that's the next thing to add here, not a sign this setup is wrong.

## About `docker-compose.yml` in this repo

It exists but **does not describe the current dev setup** — it defines a
self-contained stack (Postgres on 5432, no Redis, no MySQL/Elasticsearch, no
arq worker) that nothing here actually runs from. Running `docker compose up`
would start a second, empty Postgres on a different port and is unrelated to
everything above — don't use it to start/stop this environment.
