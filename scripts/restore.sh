#!/usr/bin/env bash
# Restores a backup made by backup.sh into a target database.
#
# Usage:
#   ./scripts/restore.sh <backup_timestamp> <target_database>
#
# Example (the safe, default use -- restore into a throwaway database to
# verify a backup or inspect old data, never touching the real one):
#   ./scripts/restore.sh 20260921_082605 dataforge_restore_check
#
# Restoring into the real "dataforge" database is refused unless
# CONFIRM_OVERWRITE_REAL_DB=yes is set explicitly -- this exists because a
# stray env var overriding the wrong database already truncated real dev
# data once this project. Don't remove this check to save a step.
set -euo pipefail
cd "$(dirname "$0")/.."

STAMP="${1:-}"
TARGET_DB="${2:-}"
if [ -z "$STAMP" ] || [ -z "$TARGET_DB" ]; then
  echo "Usage: $0 <backup_timestamp> <target_database>" >&2
  echo "Available backups:" >&2
  ls -1 backups/ >&2
  exit 1
fi

SRC="$(pwd)/backups/$STAMP"
DUMP="$SRC/dataforge.dump"
if [ ! -f "$DUMP" ]; then
  echo "No dump found at $DUMP" >&2
  exit 1
fi

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5544}"
PGUSER="${PGUSER:-dataforge}"
export PGPASSWORD="${PGPASSWORD:-dataforge}"

if [ "$TARGET_DB" = "dataforge" ] && [ "${CONFIRM_OVERWRITE_REAL_DB:-}" != "yes" ]; then
  echo "Refusing to restore over the real 'dataforge' database without CONFIRM_OVERWRITE_REAL_DB=yes." >&2
  echo "Restore into a throwaway database first (e.g. dataforge_restore_check) to verify the backup," >&2
  echo "or re-run with: CONFIRM_OVERWRITE_REAL_DB=yes $0 $STAMP dataforge" >&2
  exit 1
fi

echo "[$(date -u +%FT%TZ)] Creating database '$TARGET_DB' (dropping it first if it already exists)..."
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -c "DROP DATABASE IF EXISTS $TARGET_DB;"
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -c "CREATE DATABASE $TARGET_DB OWNER $PGUSER;"

echo "[$(date -u +%FT%TZ)] Restoring $DUMP into '$TARGET_DB'..."
pg_restore -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$TARGET_DB" --no-owner "$DUMP"

echo "[$(date -u +%FT%TZ)] Restore complete. Row counts by schema:"
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$TARGET_DB" -c "
  select schemaname, count(*) as tables
  from pg_tables
  where schemaname in ('df_meta', 'df_data', 'sample_data')
  group by schemaname;
"

if [ -f "$SRC/attachments.tar.gz" ]; then
  echo "Attachments are also backed up at: $SRC/attachments.tar.gz"
  echo "Extract with: tar -xzf $SRC/attachments.tar.gz -C backend/data/"
fi
if [ -f "$SRC/sqlite_sources.tar.gz" ]; then
  echo "SQLite sources are also backed up at: $SRC/sqlite_sources.tar.gz"
  echo "Extract with: tar -xzf $SRC/sqlite_sources.tar.gz -C backend/data/"
fi
