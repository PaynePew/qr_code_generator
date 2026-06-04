#!/usr/bin/env bash
#
# restore-drill.sh — PROVE that a qrcode-db backup actually restores.
#
# This is a DRILL. It NEVER touches the live qrcode-db container, its volume,
# or any production data. It downloads a backup dump from S3, restores it into a
# brand-new THROWAWAY postgres:16 container on a temp volume, prints row counts
# for the real application tables, and then destroys the throwaway container and
# volume — even if something fails.
#
# Backup layout this drill consumes (authored by deploy/backup.sh):
#   s3://qrgen-customized-prod/backups/qrcode/YYYY-MM-DD.dump   (pg_dump -Fc, AES256 SSE)
#
# Run on the box (deploy dir is flat — same level as backup.sh):
#   /opt/qrcode/restore-drill.sh              # latest dump
#   /opt/qrcode/restore-drill.sh 2026-06-04   # a specific date
#
# Credentials: reads /opt/qrcode/.env.backup (the least-priv backup IAM user),
# the same file deploy/backup.sh uses. AWS CLI must be installed (owner setup).
#
set -euo pipefail

# --- Configuration -----------------------------------------------------------
S3_BUCKET="${S3_BUCKET:-qrgen-customized-prod}"
S3_PREFIX="${S3_PREFIX:-backups/qrcode}"
ENV_BACKUP_FILE="${ENV_BACKUP_FILE:-/opt/qrcode/.env.backup}"

# Throwaway Postgres target (deliberately NOT qrcode-db / qrcode_pgdata).
PG_IMAGE="postgres:16"
DRILL_CONTAINER="qrcode-restore-drill-$$"
DRILL_VOLUME="qrcode-restore-drill-vol-$$"
DRILL_DB="qrcode_restore_drill"
DRILL_USER="drill"
DRILL_PASSWORD="drill"

# Real application tables to sanity-check (backend/models.py).
APP_TABLES=(users links scans link_customizations)

# --- Banner ------------------------------------------------------------------
cat <<'BANNER'
================================================================================
  qrcode RESTORE DRILL
  This is a DRILL. It restores a backup into a THROWAWAY postgres container on a
  temp volume to prove the backup is good. It does NOT touch the live qrcode-db
  container, the qrcode_pgdata volume, or any production data. The throwaway
  container and volume are destroyed when this script exits.
================================================================================
BANNER

# --- Temp working area + teardown trap --------------------------------------
WORKDIR="$(mktemp -d)"
DUMP_FILE="${WORKDIR}/restore-drill.dump"

cleanup() {
  status=$?
  echo
  echo "--- Teardown (drill cleanup) ---"
  docker rm -f "${DRILL_CONTAINER}" >/dev/null 2>&1 || true
  docker volume rm -f "${DRILL_VOLUME}" >/dev/null 2>&1 || true
  rm -rf "${WORKDIR}" >/dev/null 2>&1 || true
  if [ "${status}" -eq 0 ]; then
    echo "Throwaway container + volume removed. Live database untouched."
    echo "RESTORE DRILL PASSED."
  else
    echo "Throwaway container + volume removed. Live database untouched."
    echo "RESTORE DRILL FAILED (exit ${status})." >&2
  fi
  exit "${status}"
}
trap cleanup EXIT

# --- Preflight ---------------------------------------------------------------
command -v aws >/dev/null 2>&1 || { echo "ERROR: aws CLI not found (owner one-time setup)." >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "ERROR: docker not found." >&2; exit 1; }

if [ ! -f "${ENV_BACKUP_FILE}" ]; then
  echo "ERROR: backup creds file not found: ${ENV_BACKUP_FILE}" >&2
  echo "       The box owner must place it from .env.backup.example (least-priv IAM user)." >&2
  exit 1
fi

# Load backup IAM credentials (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY /
# AWS_DEFAULT_REGION live in .env.backup). set -a so they export to aws CLI.
set -a
# shellcheck disable=SC1090
. "${ENV_BACKUP_FILE}"
set +a

# --- Resolve which dump to restore ------------------------------------------
if [ "$#" -ge 1 ] && [ -n "${1:-}" ]; then
  DUMP_DATE="$1"
  S3_KEY="${S3_PREFIX}/${DUMP_DATE}.dump"
  echo "Requested dump date: ${DUMP_DATE}"
else
  echo "No date given; resolving the latest dump under s3://${S3_BUCKET}/${S3_PREFIX}/ ..."
  # List the prefix, keep only *.dump, sort by the leading ISO date column, take last.
  LATEST_KEY="$(aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" \
    | awk '{print $4}' \
    | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}\.dump$' \
    | sort \
    | tail -n 1 || true)"
  if [ -z "${LATEST_KEY}" ]; then
    echo "ERROR: no YYYY-MM-DD.dump objects found under s3://${S3_BUCKET}/${S3_PREFIX}/" >&2
    exit 1
  fi
  S3_KEY="${S3_PREFIX}/${LATEST_KEY}"
fi

echo "Restoring from: s3://${S3_BUCKET}/${S3_KEY}"
aws s3 cp "s3://${S3_BUCKET}/${S3_KEY}" "${DUMP_FILE}"
echo "Downloaded $(du -h "${DUMP_FILE}" | awk '{print $1}') to ${DUMP_FILE}"

# --- Start the throwaway Postgres -------------------------------------------
echo
echo "--- Starting throwaway ${PG_IMAGE} (container ${DRILL_CONTAINER}, volume ${DRILL_VOLUME}) ---"
docker volume create "${DRILL_VOLUME}" >/dev/null
docker run -d \
  --name "${DRILL_CONTAINER}" \
  -e POSTGRES_USER="${DRILL_USER}" \
  -e POSTGRES_PASSWORD="${DRILL_PASSWORD}" \
  -e POSTGRES_DB="${DRILL_DB}" \
  -v "${DRILL_VOLUME}:/var/lib/postgresql/data" \
  "${PG_IMAGE}" >/dev/null

echo "Waiting for the throwaway Postgres to become ready ..."
ready=""
for _ in $(seq 1 30); do
  if docker exec "${DRILL_CONTAINER}" pg_isready -U "${DRILL_USER}" -d "${DRILL_DB}" >/dev/null 2>&1; then
    ready="yes"
    break
  fi
  sleep 2
done
if [ -z "${ready}" ]; then
  echo "ERROR: throwaway Postgres did not become ready in time." >&2
  docker logs "${DRILL_CONTAINER}" || true
  exit 1
fi
echo "Throwaway Postgres is ready."

# --- Restore the custom-format dump -----------------------------------------
# Restore into a fresh database so we never depend on the dump's own DB name.
# --no-owner: the dump's roles (e.g. qrcode) don't exist in the throwaway PG.
RESTORE_DB="restored"
echo
echo "--- Restoring dump into a fresh database '${RESTORE_DB}' (pg_restore --no-owner) ---"
docker exec -e PGPASSWORD="${DRILL_PASSWORD}" "${DRILL_CONTAINER}" \
  createdb -U "${DRILL_USER}" "${RESTORE_DB}"

# Stream the dump into pg_restore inside the container. Capture the exit code
# WITHOUT letting `set -e` abort first (|| short-circuits the errexit), so the
# explicit check below is actually reachable on a non-zero pg_restore.
RESTORE_RC=0
docker exec -i -e PGPASSWORD="${DRILL_PASSWORD}" "${DRILL_CONTAINER}" \
  pg_restore --no-owner --no-privileges \
  -U "${DRILL_USER}" -d "${RESTORE_DB}" < "${DUMP_FILE}" || RESTORE_RC=$?
echo "pg_restore exited ${RESTORE_RC}."
if [ "${RESTORE_RC}" -ne 0 ]; then
  echo "ERROR: pg_restore reported a non-zero exit; restore is NOT verified." >&2
  exit "${RESTORE_RC}"
fi

# --- Verify ------------------------------------------------------------------
echo
echo "--- Verification: row counts for real application tables ---"
verified_any=""
for tbl in "${APP_TABLES[@]}"; do
  # to_regclass returns NULL if the table is absent → treat as "missing".
  exists="$(docker exec -e PGPASSWORD="${DRILL_PASSWORD}" "${DRILL_CONTAINER}" \
    psql -U "${DRILL_USER}" -d "${RESTORE_DB}" -tAc \
    "SELECT to_regclass('public.${tbl}') IS NOT NULL;")"
  if [ "${exists}" = "t" ]; then
    count="$(docker exec -e PGPASSWORD="${DRILL_PASSWORD}" "${DRILL_CONTAINER}" \
      psql -U "${DRILL_USER}" -d "${RESTORE_DB}" -tAc \
      "SELECT count(*) FROM public.${tbl};")"
    printf '  %-22s %s rows\n' "${tbl}" "${count}"
    verified_any="yes"
  else
    printf '  %-22s (table not present in dump)\n' "${tbl}"
  fi
done

if [ -z "${verified_any}" ]; then
  echo
  echo "None of the expected application tables were found; falling back to a"
  echo "generic sanity check (count of base tables in information_schema)."
  generic="$(docker exec -e PGPASSWORD="${DRILL_PASSWORD}" "${DRILL_CONTAINER}" \
    psql -U "${DRILL_USER}" -d "${RESTORE_DB}" -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';")"
  echo "  public base tables restored: ${generic}"
  if [ "${generic}" -eq 0 ]; then
    echo "ERROR: the restored database has no public tables — restore looks empty." >&2
    exit 1
  fi
fi

echo
echo "Verification complete: pg_restore exited 0 and the restored schema is queryable."
# trap 'cleanup' prints the PASS banner and tears everything down.
