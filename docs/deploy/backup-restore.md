# Deploy: qrcode-db backup & restore

Operator runbook for the daily Postgres backup and for proving / performing a
restore. The backup protects the `qr_codes` database (tables `users`, `links`,
`scans`, `link_customizations`). Customized-QR images live in S3 and are covered
separately by [`s3-customized-qr-storage.md`](./s3-customized-qr-storage.md) —
this doc is **database only**.

Related files:

- [`backup.sh`](../../backup.sh) — the daily dump + upload script (runs on the box).
- [`deploy/restore-drill.sh`](../../deploy/restore-drill.sh) — non-destructive restore proof.
- `docker-compose.prod.yml` — defines `qrcode-db` and the `qrcode_pgdata` volume.

## What the backup is

A daily logical dump of the live `qrcode-db` Postgres, taken with `pg_dump` in
**custom format** (`-Fc`) so it can be selectively restored with `pg_restore`.

| Item | Value |
|---|---|
| Schedule | Daily **18:00 UTC** (systemd timer on the box) |
| Source | `qrcode-db` via `docker compose exec -T qrcode-db pg_dump` |
| Format | PostgreSQL custom format (`pg_dump -Fc`) |
| Destination bucket | `s3://qrgen-customized-prod` |
| Key prefix | `backups/qrcode/` |
| Key format | `backups/qrcode/YYYY-MM-DD.dump` |
| Encryption | S3 server-side, **AES256** SSE |
| Credentials | `/opt/qrcode/.env.backup` (least-priv backup IAM user) |

The dump is **not** the image store; uploaded composites/logos are versioned in
S3 under `qr/` and have their own lifecycle.

## Retention

A **14-day** S3 lifecycle rule on the `backups/qrcode/` prefix expires old
dumps. This is **owner-managed in the bucket configuration** and is intentionally
NOT done by `backup.sh` — the script only writes; it never deletes. Do not add
deletion logic to the script.

## Owner one-time setup

These are placed once by the box owner and are **never** touched by CD (they are
secret or need sudo):

1. **Install the AWS CLI** on the box (e.g. the official `awscli-exe` bundle).
   Verify with `aws --version`.

2. **Place the backup credentials.** Copy `.env.backup.example` to
   `/opt/qrcode/.env.backup` and fill in the least-privilege **backup IAM user**
   keys (read/write on `backups/qrcode/*` only — distinct from the runtime
   `qrgen-app` user). `chmod 600 /opt/qrcode/.env.backup`. Both `backup.sh` and
   `restore-drill.sh` source this file.

3. **Install the systemd units and enable the timer** (units are owner-placed,
   not shipped by CD):

   ```bash
   # qrcode-backup.service  → runs /opt/qrcode/backup.sh once (Type=oneshot)
   # qrcode-backup.timer    → OnCalendar=*-*-* 18:00:00 UTC, Persistent=true
   sudo systemctl daemon-reload
   sudo systemctl enable --now qrcode-backup.timer
   systemctl list-timers qrcode-backup.timer      # confirm next run is 18:00 UTC
   ```

`docker-compose.prod.yml`, `backup.sh`, and `restore-drill.sh` are scp-ed to
`/opt/qrcode` by CD every deploy; `.env.prod`, `.env.backup`, the systemd units,
and the AWS CLI are owner-only and CD never overwrites them.

## Verify a backup restores (the drill)

[`restore-drill.sh`](../../deploy/restore-drill.sh) proves a dump is good
**without touching anything live**. It pulls a dump from S3, restores it into a
throwaway `postgres:16` container on a temp volume, prints row counts for the
application tables, and tears the throwaway container + volume down on exit
(even on failure). It never touches `qrcode-db` or `qrcode_pgdata`.

```bash
# latest dump:
/opt/qrcode/restore-drill.sh

# a specific day:
/opt/qrcode/restore-drill.sh 2026-06-04
```

A pass ends with `RESTORE DRILL PASSED.` and shows non-error row counts. Run it
periodically (e.g. monthly) and after any change to `backup.sh` or the schema.

## Performing a REAL restore (destructive — last resort)

> **⚠️ DESTRUCTIVE.** A real restore **overwrites the live `qr_codes` database**.
> Any data written since the chosen dump is lost. Only do this on confirmed data
> loss/corruption, after taking a fresh dump of the current (broken) state if at
> all possible. When in doubt, run the **drill** first to confirm the dump is
> sound. Most incidents are better handled by restoring into a side database and
> copying out only what's needed.

On the box, in `/opt/qrcode`:

```bash
# 0. Load backup creds and pick the dump.
set -a; . /opt/qrcode/.env.backup; set +a
DUMP_DATE=2026-06-04                                  # the dump you want
aws s3 cp "s3://qrgen-customized-prod/backups/qrcode/${DUMP_DATE}.dump" /tmp/restore.dump

# 1. Stop the app so nothing writes during the restore (DB stays up).
docker compose -f docker-compose.prod.yml stop qrcode-app qrcode-migrate

# 2. Restore into the live DB. --clean --if-exists drops existing objects first;
#    --no-owner because the dump's role names are recreated by compose env, not
#    guaranteed present. Adjust -U / -d if you changed POSTGRES_USER / POSTGRES_DB.
docker compose -f docker-compose.prod.yml exec -T qrcode-db \
  pg_restore --clean --if-exists --no-owner --no-privileges \
  -U qrcode -d qr_codes < /tmp/restore.dump

# 3. Bring the app back. qrcode-migrate re-runs `alembic upgrade head` (a no-op
#    if the dump is already at head) before qrcode-app starts.
docker compose -f docker-compose.prod.yml up -d

# 4. Confirm health and sanity-check.
docker inspect --format '{{.State.Health.Status}}' qrcode-app
docker compose -f docker-compose.prod.yml exec -T qrcode-db \
  psql -U qrcode -d qr_codes -c "SELECT count(*) FROM links;"

rm -f /tmp/restore.dump
```

If the restored dump predates the current migration head, `qrcode-migrate` will
fast-forward the schema on the next `up`; never run a real restore against a
dump from a *newer* schema than the deployed image.
