# E2E (Playwright) — session-cookie auth bypass (bead 8vd)

Google login can't be automated, so these tests don't log in. The session cookie
is just an `itsdangerous`-signed `{uid}` (`backend/session.py`), so `global-setup`
mints one for the seeded demo user and injects it via Playwright `storageState` —
no Google round-trip.

## First cut: assume-running

This slice assumes the dev stack is already up. **CI orchestration (Postgres
service + browser provisioning + server startup in Actions) is a separate
follow-up bead.** Bring the stack up with a **test `SECRET`** (it MUST match what
the mint helper signs with) and the SPA pointed at the **same-origin proxy**:

1. Postgres: `docker compose up -d` (root compose, db on `:5432`).
2. Backend on `:8000` with a test env — **not** the prod `.env` creds:
   ```pwsh
   $env:SECRET='e2e-test-secret'; $env:BASE_URL='http://localhost:8000'
   $env:DATABASE_URL='postgresql://postgres:postgres@localhost:5432/qr_codes'
   $env:SESSION_COOKIE_SECURE='false'; $env:AWS_S3_BUCKET=''; $env:RATE_LIMIT_ENABLED='false'
   .venv\Scripts\python -m alembic upgrade head
   .venv\Scripts\python -m uvicorn backend.main:app --port 8000
   ```
3. Frontend on `:5173` in **test mode** — so `.env.local`'s cross-origin
   `VITE_API_BASE_URL` is skipped and the SPA rides the same-origin proxy
   (see `.env.test`):
   ```pwsh
   npm run dev -- --mode test
   ```
4. Run the tests (the mint helper shares `SECRET` + `DATABASE_URL`):
   ```pwsh
   $env:SECRET='e2e-test-secret'
   $env:DATABASE_URL='postgresql://postgres:postgres@localhost:5432/qr_codes'
   npm run e2e
   ```

`global-setup.ts` runs `scripts/mint_session_cookie.py`, which idempotently seeds
the demo account and writes a signed cookie to `e2e/.auth/state.json`
(gitignored).

## Why same-origin

The httpOnly session cookie is `SameSite=Lax`. Riding the Vite proxy keeps the
SPA and API same-origin (prod-like), so the cookie is sent without CORS. The dev
default (`VITE_API_BASE_URL=http://localhost:8000`, cross-origin) would send the
cookie to a different backend; `.env.test` empties it so axios uses the proxy.
