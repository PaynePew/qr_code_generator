#!/usr/bin/env bash
#
# Nightly Postgres backup for qrcode -> S3.
#
# Runs on the Linux box as user `deploy`. CD scp-s this to /opt/qrcode/backup.sh
# every deploy (non-secret, no-sudo runtime file). Invoked by the systemd unit
# qrcode-backup.service, which supplies the AWS credentials via
# EnvironmentFile=/opt/qrcode/.env.backup.
#
# What it does: pg_dump (custom format) the qrcode database out of the running
# qrcode-db container and stream it straight to S3, server-side encrypted.
#
# Retention is NOT handled here: the bucket owner applies a 14-day S3 lifecycle
# rule on the backups/qrcode prefix. This script only PutObject-uploads. A
# same-day re-run simply overwrites that day's object, which is acceptable.
set -euo pipefail

# --- Constants (the backup destination is fixed) ---
readonly S3_BUCKET="qrgen-customized-prod"
readonly S3_PREFIX="backups/qrcode"
readonly DEPLOY_DIR="/opt/qrcode"
readonly COMPOSE_FILE="docker-compose.prod.yml"
readonly PROD_ENV="${DEPLOY_DIR}/.env.prod"

# AWS_DEFAULT_REGION defaults if the EnvironmentFile didn't set it.
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"

# UTC datestamp -> one object per day (overwritten on same-day re-run).
DATESTAMP="$(date -u +%Y-%m-%d)"
readonly DATESTAMP
readonly S3_URI="s3://${S3_BUCKET}/${S3_PREFIX}/${DATESTAMP}.dump"

echo "[backup] starting qrcode backup for ${DATESTAMP} (UTC)"

# --- Postgres user/db come from the owner-placed .env.prod (read-only) ---
# Extract ONLY the two PG vars we need. We deliberately do NOT `source` the whole
# file: .env.prod also defines AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (the app's
# customized-QR storage keys), and sourcing would clobber the least-privilege,
# backup-only AWS creds that systemd's EnvironmentFile=/opt/qrcode/.env.backup put
# in our environment — making this job upload with the wrong (over-privileged) keys.
if [[ ! -r "${PROD_ENV}" ]]; then
  echo "[backup] ERROR: cannot read ${PROD_ENV}" >&2
  exit 1
fi
read_prod_env() {
  # Print the value of the requested key from .env.prod, last assignment wins,
  # stripping an optional `export ` prefix and surrounding quotes. No eval/source.
  local key="$1" line value
  line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}=" "${PROD_ENV}" | tail -n1)" || return 0
  value="${line#*=}"
  value="${value%\"}"; value="${value#\"}"
  value="${value%\'}"; value="${value#\'}"
  printf '%s' "${value}"
}
POSTGRES_USER="$(read_prod_env POSTGRES_USER)"
POSTGRES_DB="$(read_prod_env POSTGRES_DB)"

if [[ -z "${POSTGRES_USER}" || -z "${POSTGRES_DB}" ]]; then
  echo "[backup] ERROR: POSTGRES_USER / POSTGRES_DB not set in ${PROD_ENV}" >&2
  exit 1
fi

cd "${DEPLOY_DIR}"

echo "[backup] dumping db '${POSTGRES_DB}' as user '${POSTGRES_USER}' -> ${S3_URI}"

# Dump (custom format) straight from the running db container into aws s3 cp,
# reading the stream from stdin. set -o pipefail makes a pg_dump failure fail
# the whole pipe, so the unit is marked failed.
docker compose -f "${COMPOSE_FILE}" exec -T qrcode-db \
  pg_dump -Fc -U "${POSTGRES_USER}" "${POSTGRES_DB}" \
  | aws s3 cp - "${S3_URI}" --sse AES256

echo "[backup] done: uploaded ${S3_URI}"
