#!/usr/bin/env bash
# Daily backup for the real dataforge database + local-disk assets it
# references (attachment files, uploaded sqlite sources) -- restoring the DB
# alone without these would leave records pointing at files that don't
# exist. Deliberately NOT backing up Redis: everything in it (arq's job
# queue, circuit-breaker state, the sync-poll advisory locks) is either
# already durable in Postgres or safely disposable -- losing it just means
# a queued job runs late, never data loss.
#
# Run manually with ./scripts/backup.sh, or see the cron entry this repo's
# RUNBOOK.md documents for the scheduled daily run.
set -euo pipefail
cd "$(dirname "$0")/.."

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5544}"
PGUSER="${PGUSER:-dataforge}"
PGDATABASE="${PGDATABASE:-dataforge}"
export PGPASSWORD="${PGPASSWORD:-dataforge}"

BACKUP_ROOT="$(pwd)/backups"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
DEST="$BACKUP_ROOT/$STAMP"

ATTACHMENTS_DIR="backend/data/attachments"
SQLITE_SOURCES_DIR="backend/data/sqlite_sources"

mkdir -p "$DEST"
echo "[$(date -u +%FT%TZ)] Starting backup -> $DEST"

# Custom format (-Fc), not plain SQL: supports selective restore
# (pg_restore -t <table>) and is already compressed, so no separate gzip step.
pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -Fc -f "$DEST/dataforge.dump"

# Sanity check the dump is actually readable before calling the backup good
# -- a truncated or corrupt dump file failing silently until the day it's
# actually needed is the worst possible time to find out.
pg_restore --list "$DEST/dataforge.dump" > /dev/null

if [ -d "$ATTACHMENTS_DIR" ] && [ -n "$(ls -A "$ATTACHMENTS_DIR" 2>/dev/null)" ]; then
  tar -czf "$DEST/attachments.tar.gz" -C "$(dirname "$ATTACHMENTS_DIR")" "$(basename "$ATTACHMENTS_DIR")"
fi
if [ -d "$SQLITE_SOURCES_DIR" ] && [ -n "$(ls -A "$SQLITE_SOURCES_DIR" 2>/dev/null)" ]; then
  tar -czf "$DEST/sqlite_sources.tar.gz" -C "$(dirname "$SQLITE_SOURCES_DIR")" "$(basename "$SQLITE_SOURCES_DIR")"
fi

{
  echo "timestamp_utc: $STAMP"
  echo "database: $PGDATABASE"
  echo "pg_dump_version: $(pg_dump --version)"
  echo "server_version: $(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -tc 'show server_version;' | xargs)"
  echo "database_size: $(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -tc "select pg_size_pretty(pg_database_size('$PGDATABASE'));" | xargs)"
  echo "files:"
  du -h "$DEST"/* | sed 's/^/  /'
} > "$DEST/manifest.txt"

echo "[$(date -u +%FT%TZ)] Backup complete:"
cat "$DEST/manifest.txt"

# Retention: delete backup directories older than RETENTION_DAYS. Each run
# is its own timestamped directory (not a flat file), so this is a plain
# directory-age prune, not bespoke per-file bookkeeping.
echo "[$(date -u +%FT%TZ)] Pruning backups older than $RETENTION_DAYS days..."
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime "+$RETENTION_DAYS" -print -exec rm -rf {} \;

echo "[$(date -u +%FT%TZ)] Done."
