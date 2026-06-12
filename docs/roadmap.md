# QR Code Generator — Multi-Tenant Roadmap

> Tracked planning doc (`docs/roadmap.md`, promoted from gitignored `.docs-local/` on 2026-06-04 so
> it travels across worktrees/clones). Living document — updated as each
> Phase is grilled and decisions crystallise. Domain terms that survive grilling get promoted
> to `CONTEXT.md`; hard, surprising trade-offs get an ADR under `docs/adr/`.

**Created:** 2026-06-02
**Driving goal:** Take the single-tenant prototype to a multi-tenant product deployed at
`https://qrcode.paynepew.dev`, co-located with the existing `scheduler.paynepew.dev` on Lightsail.

---

## ⏯️ Session state — RESUME HERE (last updated 2026-06-12 — P8+P9 backend build LANDED on main (15l/xdm/6bk/uq9) · prod geo wired & verified (4nw) · Phase 6 backups bug fixed → epic p6 CLOSED 14/14; NEXT = Phase 7 frontend redesign, the last phase)

> **✅ 2026-06-12 — P8+P9 backend build LANDED + prod geo wired + Phase 6 backups bug fixed → epic CLOSED.**
> - **Phase 6 backups were SILENTLY BROKEN, not "awaiting the first tick"** (corrects every note below):
>   the systemd `qrcode-backup.service` ran `ExecStart=/opt/qrcode/backup.sh` *directly*, but CD ships
>   `backup.sh` via plain `scp` as `0644` (non-executable) → `status=203/EXEC` on every 18:00 UTC tick since
>   06-05 → **zero backups ever produced** (the `qrcode-backup` IAM user showed zero activity — the symptom
>   that opened bd `zen`). **Fixed** (unit → `ExecStart=/usr/bin/env bash …`, `+x` in git, CD `chmod +x`
>   post-scp) and **verified**: dump in S3 (`AES256`), `restore-drill` PASSED, IAM key now active, **14-day
>   lifecycle confirmed**. → **bd `zen` CLOSED; `p6s5` + epic `p6` CLOSED (14/14).** Phase 6 is now *actually*
>   complete, not just "shipped, backups pending".
> - **P8+P9 backend build landed on `main`** (the "ONE backend build" the prior note pointed to):
>   `15l` (privacy-by-construction `Scan` + in-process async redirect ingest), `xdm` (coarse scan-analytics
>   UI, drops `user_agent`), `6bk` (bucket-correctness tests), `uq9` (independent DB Session for the async 302
>   scan write); `link_cache.py` (redirect `TTLCache`) + image `immutable` + `ebf` (CloudFront + OAC,
>   `CDN_BASE_URL`) confirm ADR 0016/0017 now have code on `main`.
> - **Prod geo wired & VERIFIED (bd `4nw`).** GeoLite2-City `.mmdb` on the box, **bind-mounted ro** into
>   `qrcode-app`, weekly `geoipupdate` cron; `derive_geo('8.8.8.8') → ('US', None)`; `scans` carries
>   `country`/`subdivision`/`device_class`. ⚠️ Gotcha (now in the runbook + bd memory): geoipupdate's
>   compiled-default `DatabaseDirectory` on this box is `/var/lib/GeoIP`, **not** `/usr/share/GeoIP` — pin it.
> - **NEXT = Phase 7 (frontend redesign) — the last phase.** Carries the analytics dashboard panel
>   (ADR 0016), labels `nk4`, re-edit-in-LinkDetail `yfx`, Tailwind v3→v4 `5mz`; React 19 `n13` decoupled.
>
> **✅ 2026-06-11 — Phase 9 GRILLED → ADR 0016** (done out of order, *before* finishing Phase 8,
> because Phase 9 unblocks it). Decided: **privacy-by-construction scan model** (store coarse derived
> `country`+`device_class`, raw IP/UA never stored; total not unique-visitor counts) · **in-process
> async ingestion** (FastAPI `BackgroundTasks`, at-most-once) — *this is the prerequisite that unblocks
> the Phase 8 redirect read-cache* · **analytics = live SQL** (`scans_by_country`/`_by_device_class` +
> coarse `recent_scans`, no IP/UA) · **`SQS→S3→batch` designed but deferred** (~5–8 days if built; needs
> idempotency + DLQ). Fixes a live **ADR 0006 violation** (`analytics._recent_scans` leaks raw IP/UA).
> → CONTEXT.md `## Scan` updated. **Phase 8 partial decisions this session: Redis dropped** (read-cache
> in front of a sync write = theater; Redis's only real homes = post-Phase-9 redirect cache + moving the
> rate-limiter store off-process to unlock >1 worker) · **image caching = `immutable` on the versioned
> S3 object, NOT the token endpoint** (which stays a `no-cache` 302 pointer; re-customization, not
> never-expiry, is the staleness trap) · **CloudFront-on-S3** is feasible & VPS-independent (whole-site
> CDN is platform-owned). **Phase 8 then fully GRILLED same session → ADR 0017** — build the in-process
> redirect cache (`cachetools.TTLCache`, derive-state-on-read, evict on PATCH/DELETE, 300s safety net, no
> negative cache) + image immutable-caching via **CloudFront + OAC** (private bucket, default
> `*.cloudfront.net`; token endpoint → 302 to CDN URL). **NEXT FRONTIER = ONE backend build covering P8+P9
> together** (same redirect/scan code), **then Phase 7.** P8 also needs a **HITL CloudFront provisioning** task.

> **✅ 2026-06-05 — Phase 6 is SHIPPED (supersedes the 2026-06-04 "grill PAUSED" note below).**
> Verified first-hand this session against git + bd (not just roadmap text):
> - bd epic `qr_code_generator-p6` = **13/14 done (92%)**; go-live (`p6s6`), prod-login fix
>   (`p6.3`), demo-seed (`p6.4`), CD pipeline (`p6s4`), SHA-pin (`p6.1`) all closed. Git log confirms
>   (`60a91d6` CD+backups, `49e1400` pin SHA, `9e5ae1c` bake VITE_GOOGLE_CLIENT_ID).
> - Only open child `p6s5` (daily `pg_dump`→S3) is code-complete: `backup.sh`/`restore-drill.sh`
>   scp'd by CD; box-side IAM/`.env.backup`/systemd timer owner-installed; **first real dump runs at
>   the next 18:00 UTC tick** — operational, not a design gap.
> - Footguns handled: `.env.prod.example` pins `TRUSTED_PROXIES=1` + `ip_extraction.py` implements XFF;
>   CORS inert in prod (same-origin). **💬 topic #5 (infra-layer rate limiting) = raised to the platform
>   layer** (the edge is platform-owned, ADR 0014 lives in the platform repo) — **closed from qrcode's
>   roadmap.** Architecture lock (own Postgres · 1 uvicorn worker until Redis · single `qrcode-app:8000`
>   · co-equal tenant on platform `edge`) stands.
>
> **🔀 2026-06-05 — Phase order re-ranked. Phase 7 (frontend redesign) moved to LAST.**
> Rationale (user decision): a redesign should *skin a stable feature surface* — doing it before the
> analytics surface (Phase 9) is settled = redrawing dashboard/LinkDetail twice. So **next-frontier
> order = Phase 10 → 8 → 9 → 7**. Consequences: the **Tailwind v3→v4 migration (`5mz`) rides with
> Phase 7** (v4's CSS-first `@theme` is where the redesign's tokens belong — token work done once);
> **React 18→19 is decoupled** (independent P3, `n13`).
>
> **✅ 2026-06-10 — Phase 10 GRILLED → ADR 0015.** Framing corrected: the service **never fetches the
> destination server-side** (store + 302 `Location` only) ⇒ **no SSRF surface today**; the live threat is
> open redirect. **Shipped scope = string-only mint-time hygiene** (length cap 2048 · IDNA/UTS-46 host
> normalization via `idna` · IP-literal blocklist hardening · scheme allowlist already done); reuse
> `INVALID_URL` 422, redirect path unchanged. **SSRF + malware-reputation DEFERRED** to access-time (ADR
> 0015 records the fetch-time resolve-and-pin / serve-time-interstitial future home; Safe Browsing v4 is
> deprecated → Web Risk). ✅ **Implemented & merged** — bd `qr_code_generator-ltr` CLOSED (PR #113, `c730311`→`57f96d2`; 460 tests green; independent opus review APPROVE-WITH-NITS). **NEXT FRONTIER = Phase 8 (🔵 grilling now, 2026-06-10).**
>
> **🐞 2026-06-05 — 4 issues found in real use, triaged + filed to bd:**
> - `40o` (#1, P2, bug): user-facing **size/resolution knob still present** — violates ADR 0011
>   ("resolution is system-managed"; the "pixel" knob). → **fix now**.
> - `65g` (#2, P1, bug): **customized QR shows vanilla** — `LinkDetail.tsx:545-564` re-renders from the
>   recipe and **drops the logo**, never showing the authoritative stored composite; Dashboard has no QR
>   image at all. **Fix = A** (view shows `GET /api/qr/{token}/image`; canvas only for create/edit). → **fix now**.
> - `nk4` (#3, P3, feat): **labels never wired into the frontend** (backend ready, ADR 0010). → **Phase 7**.
> - `yfx` (#4, P3, feat): **re-edit customization in LinkDetail** (extract `<QRCustomizer>` from
>   Generator; depends on `65g`). → **Phase 7**.
> **Immediate plan:** fix `40o` + `65g` (Phase-4 finish), then grill Phase 10.
>
> **⏸️ 2026-06-04 (later, SUPERSEDED by the 2026-06-05 note above) — Phase 6 grill PAUSED + decision layer raised to a platform layer.**
> The shared-VPS architecture is now owned by a **platform layer** at `live_sessions/platform`
> (its own repo). Outcomes of the Phase-6 grill before pausing:
> - **Co-location grilled** against scheduler's box (2 vCPU / 2 GB Lightsail, Tokyo, static IP
>   `52.197.62.39`; Caddy 2 owns :80/:443 via GitOps). Platform context:
>   `live_sessions/VPS-DEPLOY-CONTEXT.md`.
> - **Locked:** Postgres = own container (A) · 1 uvicorn worker until Redis (ADR 0007) · single
>   upstream `qrcode-app:8000` (SPA + `/api` + `/r` from one container) · shared layer = passive
>   routing, each tenant deploys **independently** (Q2).
> - **Q1 (ingress ownership) RESOLVED:** ingress extracted into a neutral platform-owned `edge`
>   (**ADR 0014, in the platform repo — NOT qrcode's**). qrcode onboards as a **co-equal tenant**,
>   not a scheduler guest.
> - **Timing gate (Plan A):** qrcode go-live / first TLS cert waits for the platform edge
>   extraction; all deploy artifacts build + test locally **now**, unblocked.
> - **Seeds received** (untracked in this worktree, qrcode to review/commit via bd): `Dockerfile`,
>   `docker-compose.prod.yml`, `.dockerignore`, `.env.prod.example`. Brief:
>   `live_sessions/platform/docs/requests/qrcode-onboarding-handoff.md`.
> - **Remaining qrcode work (→ bd):** SPA-wiring slice (`main.py` StaticFiles + SPA fallback +
>   `/healthz`), local docker build validation, CD pipeline (ghcr → SSH → compose), `pg_dump`→S3 backups.

**Foundation (Phases 0–2) AND Phases 3–5 are now implemented and landed on `main`.** Phases 3–5
shipped via PR #67 (slices `ql8` error-envelope, `ai0` labels, `jn4` login tests, `hkb` server-side
QR storage, `oor` structured logging, `mcc` frontend save/restore) plus follow-ups `rxi` (wire
`S3Gateway` at startup), `6bs` (require `SECRET` env), `8s9` (wire logging helpers into the request
path), and `tl8` (`boto3` + `python-multipart` deps). Grilling continues just-in-time from **Phase 6**.
*(The Phase 0–2 grilling log below is historical — see the Phase overview table for authoritative status.)*

> **🆕 2026-06-04 — Phase 4 infra provisioned + CI/CD added.**
> - **S3 (bead `6c0`, HITL, DONE):** bucket `qrgen-customized-prod` (ap-northeast-1) — versioning +
>   noncurrent-version lifecycle, public-read composites / private logos, CORS, least-privilege IAM
>   (`qrgen-app`). Smoke-tested (composite 200 / logo 403). Creds in deploy `.env` (uncommitted).
>   Facts in `docs/deploy/s3-customized-qr-storage.md`. → unblocks Phase 6 deploy.
> - **Engineering CI/CD (3 tiers):** `.github/workflows/ci.yml` runs **Lint (ruff)** + **Backend
>   (pytest, 425)** + **Frontend (typecheck/vitest/build)** on every PR + push to `main`; `main` now
>   has **branch protection** requiring all three. Fixed a flaky `useGoogleOneTap` test + 33 ruff
>   violations along the way. Remaining CI follow-ups tracked in bead `qr_code_generator-38x`.

> **📥 2026-06-03 — 7 demo-architecture topics filed for later discussion** (user request):
> landed in Phases 2/4/6 (💬 markers) + new Phases 8 (caching/CDN) / 9 (analytics & daily report) /
> 10 (URL safety & SSRF). They do **not** change the active question — finish Phase 1 Q7 first.
> See the Phase overview table + Key findings log (2026-06-03).

**Progress so far:**
- Framing locked: multi-tenant = **per-user**; discussion order **0 → 7**.
- ✅ **Phase 0 — DECIDED** (full spec in the Phase 0 section below).
- 🔵 **Phase 1 — IN PROGRESS.**
  - ✅ Q1: **login required to create + manage** (option 1; reconfirmed after weighing the funnel).
    New Links are owned; reverses ADR 0005 (→ ADR pending). Redirect `GET /r/{token}` stays
    **public**. Funnel friction solved by **One Tap login + a seeded demo/guest account**, not a hybrid.
  - 🔴 PATCH/DELETE authz hole → closed by an owner check (same PR as auth).
  - ✅ Q2: authorization matrix — info / analytics / PATCH / DELETE = owner-only; redirect + image = public.
  - ✅ Q3: auth = **server-side session + httpOnly/Secure/SameSite=Lax cookie** (signed-cookie lean,
    Starlette `SessionMiddleware`). One Tap ID token → verify (google-auth) → upsert User → own cookie.
    New deps: `google-auth`, `itsdangerous`. axios needs `withCredentials`; add Vite dev `/api` proxy.
  - ✅ Q4: `GET /api/qr` owner-scoped list (`{items,next_cursor}` + per-row `scan_count`, deleted→trash,
    `created_at desc`). Retires localStorage `dismissed`/`missing` (CONTEXT.md cleanup happens in Phase 1).
  - ✅ Q5: rejected "userId-in-token" — token stays `sha256(url+secret+random nonce)`; owner in `owner_id`.
  - ✅ Q6: demo = shared, seeded, **read-only** account (`is_demo` → 403 `DEMO_READ_ONLY`). Must be
    visibly badged as demo (Phase 7) so read-only ≠ "unimplemented".
  - ✅ Q7: create → **per-user** quota; per-IP limiter moves to the auth endpoint (partial ADR 0007
    reversal). User fields = id/google_sub/email/name/picture_url/created_at/last_login_at/is_demo.
    OAuth UX = One Tap + "Sign in with Google" fallback + "Try as guest".
  - ✅ **Phase 1 fully grilled (Q1–Q7).** ADR 0009 written (supersedes ADR 0005). CONTEXT.md cleanup deferred to impl.
- 🔵 **Phase 2 — IN PROGRESS.**
  - ✅ Q1: engine = **self-hosted PostgreSQL** (docker, same VPS). `DATABASE_URL` already env-driven; drop SQLite-only args.
  - ✅ Q2: **Postgres for DB tests** (testcontainers; schema via Alembic; per-test rollback). Pure-logic
    tests stay no-DB. `conftest.py` in-memory-SQLite fixture gets rewritten (a foundation issue).
  - ✅ Q3: adopt **Alembic** (baseline = current schema, autogen+review); remove `create_all` from lifespan;
    migrations run as an explicit deploy step (not on startup) + per-session in tests; no data migration.
  - ✅ Q4: backups = daily `pg_dump -Fc` → S3, retain 7–14, restore drill. (Impl lands ~Phase 6.)
  - ✅ **Phase 2 fully grilled (Q1–Q4).** Cleanup/retention 💬 → Phase 9.

**⏳ NEXT — grill just-in-time (foundation already shipped):**
> **Phases 3–5 are decided & documented but unimplemented** — see
> `.docs-local/prd-link-customization-and-labels.md` (PRD), ADR 0010 (labels/no-dedup),
> ADR 0011 (customized-QR persistence, partially supersedes 0004), ADR 0012/0013 (error envelope
> + no-IP logs). CONTEXT.md gained `## Label` and `## Customization`.
> **Remaining to grill:** Phase 6 (deploy) · Phase 7 (frontend) · 💬 Phase 8 (Redis/CDN) ·
> 💬 Phase 9 (analytics; incl. the ADR-0006-triggered "surface IP to owner?" decision) ·
> 💬 Phase 10 (SSRF — note `url_validator` already does partial SSRF).
> **Impl note:** when Phase 4 lands, flip ADR 0004 `Status:` → "Partially superseded by ADR 0011".
> bd issues remain LOCAL only (conservative profile).

**How to resume after a restart:**
1. Re-run `/grill-with-docs` (optionally say: *"繼續 `.docs-local/roadmap.md` 的 Phase 1"*).
2. It reads this file during exploration — this section says exactly where we stopped.
3. Answer the pending question; grilling continues through Phase 1 (OAuth flow, session vs JWT,
   DB engine choice, localStorage migration), then Phases 2 → 7.

> Remaining Phase 1 sub-questions queued: **Q2 authorization matrix (current)** · OAuth flow
> (One Tap/FedCM vs redirect) · session vs JWT · cookie strategy · DB engine (SQLite vs Postgres,
> forced here) · per-user quota · demo/guest account seeding · the "userId-in-token" interrogation.
> (Legacy localStorage migration = resolved: start empty.)

---

## Confirmed framing decisions

| Decision | Value | Date |
|---|---|---|
| "Multi-tenant" means | **per-user account** (each Google account = one isolated `owner`; row-level `owner_id` isolation; B2C). NOT per-organization / team sharing. | 2026-06-02 |
| Discussion + build order | Phase 0 → 7 (as below) | 2026-06-02 |
| "card" (UI term) | = the dashboard's visual representation of a **Link** (a Link History entry). Domain docs use **Link**; "card" is UI-only. | 2026-06-02 |
| Multiple tokens per URL | **Keep, as a feature** (option A). Each POST → fresh random token, unbounded. Serves per-placement/campaign scan tracking. Per-token **label** to be added so they're distinguishable (→ Phase 3). | 2026-06-02 |
| Auth posture | **Login required to create + manage** (option 1). Reverses ADR 0005 / feature-0510 anonymous-use posture (→ ADR 0009). Scope = mint/manage only; **redirect `GET /r/{token}` stays public**. `owner_id NOT NULL`. | 2026-06-02 |
| DB engine | **Self-hosted PostgreSQL** (docker-compose, same Lightsail VPS). Over SQLite (sufficient but off-narrative) and managed/Neon (zero-ops but external dep). | 2026-06-03 |

---

## Phase overview

| Phase | Theme | Source | Depends on | Status |
|---|---|---|---|---|
| 0 | Fix token allocation bug (random nonce) | #4 | — | 🟢 decided |
| 1 | Multi-tenant identity (Google OAuth + User + owner_id) | #1 | 0 | 🟢 decided (ADR 0009) |
| 2 | Database: engine / hosting / migrations / backups | 🆕 | 1 | 🟢 decided · 💬 cleanup→P9 |
| 3 | Ownership & duplicate-URL / token-collision rules | #5 | 0+1 | ✅ implemented (ADR 0010) |
| 4 | QR image object storage (**S3**) | #2 | 1 | ✅ implemented (ADR 0011) · S3 provisioned (6c0) |
| 5 | Unified error handling & logging interface | 🆕 | 1–4 | ✅ implemented (ADR 0012, 0013) |
| 6 | Lightsail deployment (qrcode.paynepew.dev) | #3 | 2+5 | ✅ **shipped** (epic p6 **CLOSED 14/14**; backups were silently failing → fixed & verified 06-12, bd `zen`) · 💬 topic #5 → platform |
| 7 | Frontend redesign (frontend-design) | #6 | 1+4 | ⚪ pending — **next & LAST** (06-05); analytics panel (ADR 0016) + Tailwind v4 `5mz` + labels `nk4` + re-edit `yfx` ride here |
| 8 | Caching & CDN (Redis + CDN purge + SWR) | 🆕 06-03 | 1+4 | ✅ backend on `main` 06-12 (`link_cache` redirect cache + image `immutable` + `ebf` CloudFront/OAC) · ADR 0017 |
| 9 | Analytics & daily reporting (SQS → S3 → batch) | 🆕 06-03 | 1+2 | ✅ backend on `main` 06-12 (`15l`/`xdm`; geo `4nw` live in prod) · ADR 0016 |
| 10 | Production hardening: URL safety & SSRF | 🆕 06-03 | 1 | ✅ implemented (ADR 0015, bd `ltr` / PR #113) |

Legend: 🔵 grilling · 🟢 decided · ✅ implemented (on `main`) · ⚪ pending · 💬 discussion topic queued

---

## Phase 0 — Fix token allocation bug

**Root cause (confirmed).** `generate_token(url, secret, nonce)` is a *deterministic* hash
([token_generator.py:13](../backend/token_generator.py)); `allocate_token` uses the retry
counter `range(MAX_RETRIES=3)` **as** the nonce ([token_generator.py:25](../backend/token_generator.py)).
So any one URL has exactly **3 possible tokens**. 1st–3rd POST of the same URL succeed
(A/B/C); the 4th exhausts all retries → `TokenCollisionError` → **HTTP 500**
([router.py:93](../backend/router.py)). This matches the reported "3 cards then server error."

**This was never a feature.** `3` is a collision-retry constant, not an "activities per URL"
limit. ADR 0002's stated intent is *unbounded* new tokens per URL.

**Test gap.** `test_two_calls_same_url_return_different_tokens` only goes to N=2, so the suite
stayed green. Needs a regression test at N≥4.

**Fix direction.** Make the nonce *random* (e.g. `secrets.randbits`), so each POST of the same
URL gets a fresh token; the retry loop then only handles genuinely-rare cross-URL collisions.

**🟢 Decided spec (2026-06-02):**
- Behaviour contract: **unbounded random tokens** (option A). No dedup in Phase 0 (revisited in Phase 3).
- `allocate_token` passes a **random** nonce (`secrets.randbits`) per attempt instead of the retry counter.
- Keep **7-char** Base62 tokens (62⁷ ≈ 3.5T; birthday-collision ~50% only near ~2.2M tokens — fine at personal scale). Bump `MAX_RETRIES` 3→5 for cheap headroom.
- Add **regression test at N≥4** (same URL, 4 POSTs → 4 distinct tokens, no 500).
- Abuse is already capped by the per-IP rate limiter on `/api/qr/create` (ADR 0007, 30/h + 200/day) — confirmed sufficient for Phase 0. Multi-tenant hardening deferred (see Phase 1/6 caveats).

---

## Phase 1 — Multi-tenant identity (Google OAuth + User + owner_id)

**Goal.** Real per-user auth. Introduces `User`, `owner_id` on `links`, a session/token
mechanism. Supersedes ADR 0005 (localStorage-as-identity). Maps to feature-0510 **Item 1**.

**🟢 Decided (2026-06-02):**
- **Q1 — Login required to create + manage** (option 1). Every Link is owned; `owner_id NOT NULL`.
  Scope is mint/manage only — the redirect `GET /r/{token}` stays **public** (scanners have no
  account). Reverses ADR 0005 / feature-0510 "anonymous flow continues" → **ADR pending** (write
  once the identity model is fully settled).
- Legacy migration = simplest path: pre-auth ownerless Links don't appear in any dashboard; their
  tokens still redirect (ADR 0005 path 1, "start empty"). *(Exact `owner_id` column nullability /
  legacy backfill is a Phase 2 migration detail.)*
- **Funnel preserved without going hybrid** (reconfirmed after weighing interviewer friction):
  kill login friction with **Google One Tap / FedCM** (one tap, no redirect) **+ a seeded
  demo/guest account** (sample Links + scan data → interviewers see the full multi-tenant
  dashboard with zero real login). Chosen over an anonymous-create hybrid, which would have cost a
  claim/ownership-transfer mechanism (token-possession = proof → ownership race, per ADR 0005) plus
  maintaining two identity systems (localStorage + accounts) at once. Audience = interview/portfolio-first.
- **Q2 — Authorization matrix:** `POST create` = auth-required · `GET /r/{token}` (redirect) =
  **public** · `GET /api/qr/{token}` (info, has `original_url`) = **owner-only** · `GET …/image`
  (QR PNG) = **public** (encodes only the short URL → leaks nothing) · `GET …/analytics` =
  **owner-only** (tightened from today's public) · `PATCH`/`DELETE` = **owner-only**. ADR 0006
  still binds (owner sees aggregates, never raw scanner IPs).
- **Consequence → Q4:** info going owner-only means the dashboard can no longer fan out per-token
  reads → needs a new **owner-scoped `GET /api/qr` list endpoint** (ADR 0005 forbade it while
  anonymous; safe now that links are owned).
- **Q3 — Auth mechanism: server-side session + httpOnly cookie** (option A; JWT-in-JS rejected).
  Prod serves SPA + API **same-origin** behind the proxy. Session flavor leaning **signed-cookie**
  (Starlette `SessionMiddleware`, no `sessions` table) over a DB-session table — finalize at build.
  Flow: Google One Tap → Google-signed ID token → backend verifies (`google-auth`) → upsert `User`
  by `google_sub` → backend sets its **own** session cookie. New deps: `google-auth`, `itsdangerous`.
  Wiring: axios `withCredentials: true`; add a Vite dev `server.proxy` for `/api` (else CORS must set
  `allow_credentials=True` + an explicit origin — today [main.py:104](../backend/main.py) has neither,
  and the current `allow_methods/headers="*"` is incompatible with credentialed CORS).
- **Q4 — Owner-scoped list endpoint `GET /api/qr`** (auth required). Returns the current user's Links
  as `{ items: [...], next_cursor }` (envelope now, pagination logic deferred). Each row carries a
  `scan_count` aggregated from `scans` by token (avoids dashboard N+1). Default **excludes**
  soft-deleted; deleted reachable via a trash filter (`?status=deleted`). Order `created_at desc`.
- **Domain simplification (the auth dividend):** the localStorage two-level reconciliation retires —
  **`dismissed`** (localStorage-only) and **`missing`** (localStorage token → 404) lose their reason
  to exist once the server list IS the truth. Deletion collapses to one level (soft-delete + trash
  view). → CONTEXT.md "missing / dismissed / Display priority" sections get removed **in Phase 1**
  (not now — current code still uses them). Folds into **ADR 0009** (supersedes ADR 0005); the Phase 1
  impl slice also flips **ADR 0005 `Status:` to `Superseded by ADR 0009`** (it still reads `Accepted`).
- **Q5 — Rejected: "userId-in-token".** Token stays `sha256(url + secret + random nonce)` (Phase 0);
  ownership lives in the `owner_id` column, never hashed into the token. Folding userId in solves
  nothing — uniqueness is already handled by the nonce; SHA-256 is irreversible so you can't recover
  userId anyway; per-owner dedup (if ever wanted in Phase 3) uses a DB constraint, not a hash.
  Recorded as rejected so it is not re-proposed.
- **Q6 — Demo account = (a) one shared, richly-seeded, READ-ONLY account** (`is_demo` flag on User;
  all mutations → 403, enforced server-side). **UX requirement (load-bearing):** the demo state must
  be *unmistakably* shown so an interviewer never reads read-only as "not implemented" — a persistent
  "Demo mode · read-only" badge/banner + login CTA, and mutation attempts convert into a friendly
  "log in to create" nudge, not a raw error. Backend returns 403 with a **distinct code**
  (e.g. `DEMO_READ_ONLY`) so the frontend can tell it apart from 401/owner-404 and render the nudge.
  → error-code taxonomy is Phase 5; badge + disabled/nudge controls are Phase 7. Seed quality matters:
  several Links across statuses + multi-day scan spread so analytics looks alive.
- **Q7 — Final cleanup:** (1) **Rate-limit re-architecture** — `/api/qr/create` keyed by **user**
  (login required); the per-IP limiter **moves to** the auth endpoint to stop account-farming
  (partially reverses ADR 0007's anonymous-survives consequence). (2) **User model:** `id`,
  `google_sub` (unique identity key — email can change/recycle), `email`, `name`, `picture_url`,
  `created_at`, `last_login_at`, `is_demo`. (3) **OAuth UX:** One Tap primary + "Sign in with Google"
  fallback + "Try as guest" (demo). → all captured in **ADR 0009**.

**🔴 MUST (non-negotiable, same PR as auth):** close the PATCH/DELETE authorization hole.
Today [router.py:141](../backend/router.py)/[:177](../backend/router.py) mutate by token alone —
anyone holding a token can rewrite `original_url` (redirect hijack) or delete the link.
Add an owner check to PATCH + DELETE in the same change that introduces accounts.

**✅ Resolved (Q5):** the feature-0510 "use userId to hash and generate token" idea is **rejected**
(see Decided list). Token derivation is unchanged from Phase 0.

**✅ Phase 1 grilled — all open decisions resolved** (Q1–Q7 above; canonical record in **ADR 0009**).
Deferred to implementation, not open design questions: exact `owner_id` column nullability / legacy
backfill (a Phase 2 migration detail); removal of the CONTEXT.md `missing` / `dismissed` /
Display-priority sections (happens with the code). The one thing that "gets forced" next is the
**DB engine** choice → **Phase 2**.

---

## Phase 2 — Database: engine / hosting / migrations / backups

**Goal.** Decide where prod data lives and how it's managed. Currently SQLite
(`sqlite:///./qr_codes.db` + WAL, [database.py:5](../backend/database.py)); schema created via
`Base.metadata.create_all` ([main.py:97](../backend/main.py)) with **no Alembic** and **no backups**.

**🟢 Decided (2026-06-03):**
- **Q1 — Engine: self-hosted PostgreSQL** (docker-compose on the same Lightsail VPS), option (b).
  Chosen for multi-tenant credibility + consistency with the SQS/S3/Redis system-design narrative,
  over SQLite (technically sufficient at this scale but off-narrative) and managed Postgres/Neon
  (zero-ops but an external dep). Connection is already env-driven (`DATABASE_URL`,
  [database.py:5](../backend/database.py)); the swap drops the SQLite-only `connect_args`
  (`check_same_thread`) + the WAL `PRAGMA` event listener.
- **Q2 — DB tests run on PostgreSQL** (option A): testcontainers (or CI `services: postgres`), schema
  built via Alembic so migrations get tested too, per-test transaction-rollback isolation. Pure-logic
  tests (token_generator, analytics, link_state, qr_image, rate_limiter) touch no DB and stay instant —
  so this is *not* a two-engine setup. Rewriting the in-memory-SQLite fixture
  ([tests/conftest.py](../tests/conftest.py)) is a foundation issue. Rationale: incoming Postgres-specific
  paths (`ON CONFLICT` upsert, real `BOOLEAN`, `begin_nested` savepoint semantics) are untestable on SQLite.
- **Q3 — Migrations: adopt Alembic.** Baseline migration = current schema (`links`, `scans`) via
  autogenerate + manual review; a later migration adds `User`/`owner_id`/`is_demo`. Remove
  `Base.metadata.create_all` from lifespan ([main.py:97](../backend/main.py)) — migrations own schema.
  `alembic upgrade head` runs as an **explicit deploy step**, NOT on app startup (avoids multi-process
  races + decouples two different-risk operations). Tests run migrations once per session against the
  testcontainer (tests the migrations + auto-catches model↔migration drift) + per-test rollback. No data
  migration (throwaway prototype data). Autogenerate is a starting point only — review every migration.
- **Q4 — Backups:** daily `pg_dump -Fc` → **S3** (off-box; reuses the Phase 4 bucket, though the backup
  bucket/IAM can be stood up independently), retain 7–14 + rotate (or S3 lifecycle), via cron/systemd
  timer; **document + test one restore** ("Schrödinger's backup"). Decision is Phase 2; implementation
  lands around Phase 6 (needs prod) — not part of the local foundation build.

**✅ Phase 2 grilled (Q1–Q4).** Self-hosted Postgres · Postgres for DB tests (testcontainers) · Alembic ·
daily pg_dump→S3. The 💬 data cleanup/retention topic stays deferred to Phase 9 (depends on the scan model).

**Open decisions:** engine (SQLite-on-volume vs self-hosted Postgres vs managed Postgres —
Lightsail managed / Neon / Supabase); migration tool (adopt Alembic?); backup cadence &
restore drill; connection config across the multi-app VPS.

**💬 Data cleanup / retention (topic #6, 2026-06-03):** a mechanism to purge **expired data** —
soft-deleted Links in trash (Phase 1 Q4), aged scan/analytics rows (Phase 9), expired/abandoned
tokens. To grill: retention window per data type; hard-delete vs anonymize (ADR 0006); who runs the
job (cron / the Phase 9 batch); cross-refs Phase 5 log retention.

---

## Phase 3 — Ownership & duplicate-URL / token-collision rules

**Goal.** With `owner_id` in place, redefine what "duplicate" and "collision" mean.

**🟢 Decided (2026-06-03) — canonical record in ADR 0010:**
- **Q1 — No deduplication, incl. per-owner.** owner_id newly made per-owner dedup *possible*;
  re-evaluated and rejected. Each POST mints a fresh token even for same owner + same URL —
  multiple-tokens-per-URL is the headline feature (per-placement/channel tracking), dedup is
  incompatible. ADR 0002 stands, reinforced. Accidental double-submit = UI concern (Phase 7), not a constraint.
- **Token uniqueness stays global** (forced by the public, owner-less `GET /r/{token}`);
  owner_id never enters the token. Settled by architecture.
- **Q2 — `label` = free-text string on Link; NO Campaign entity.** "Campaign/placement" = the
  owner's by-eye grouping via labels; per-campaign rollups (if ever) = later label-based GROUP BY (Phase 9).
- **Q3 — Label shape:** optional (nullable/empty) · **not unique** · create + PATCH-editable ·
  trim + ~100-char cap · NULL when absent (UI fallback Phase 7) · in `GET /api/qr` list + info
  (owner-only) · per-Link. → CONTEXT.md gained `## Label`.

---

## Phase 4 — QR image object storage (S3)

**Goal.** Store generated QR images in object storage; DB tracks the URL.

**🟢 Decided (2026-06-03) — ADR 0011 (partially reverses ADR 0004):**
- Requirement: a user's **customized** QR must return identically next time + across devices.
  Incompatible with ADR 0004 (logos die on refresh; localStorage per-browser, wrong under Phase 1
  accounts) → ADR 0004's persistence stance reversed; client-side rendering (`qr-code-styling`) kept.
- **Approach A — store result + recipe:** rendered composite PNG → **S3** (public, versioned/
  immutable, CDN-cacheable); style recipe → **DB** (re-editable); uploaded logo → **S3** (owner-only,
  referenced by recipe). 1:1 `link_customization` table. No server-side styling engine.
- Vendor = **S3** (real binary need; coheres with SQS/Batch; R2/e2 set aside, low lock-in, no ADR).
  `…/image`: serve stored composite if present, else regenerate vanilla.
- **Decided impl details:** upload = validating **backend proxy** (presigned rejected at this scale —
  tiny assets, low-frequency, non-serverless); render resolution **fixed** + ECL **auto-derived**
  (logo→H), neither a user knob; recipe = colours + dot style + format + logo. → CONTEXT.md `## Customization`.
- **Impl note:** flip ADR 0004 `Status:` → "Partially superseded by 0011" in the impl slice.

---

## Phase 5 — Unified error handling & logging interface

**Goal.** Consistent error responses + structured logging for post-launch ops.

**Current state.** Scattered: two exception handlers in `main.py` (404/410), hand-written
`HTTPException`s across router, `TokenCollisionError`→500, `_logger` barely used.

**🟢 Decided (2026-06-03) — ADR 0012 (envelope+taxonomy) + ADR 0013 (no-IP-logs):**
- **One envelope for every error** (incl. framework 422 / HTTPException / 500):
  `{ "error": { "code": <STABLE_ENUM>, "message": <human, mutable>, "details": {…} } }`.
  `code` = stable enum the frontend branches on; `message` mutable/i18n; `details` holds
  `fields` / `retry_after` / `correlation_id`.
- **`AppError` hierarchy + 4 handlers**: AppError · RequestValidationError (→VALIDATION_ERROR) ·
  StarletteHTTPException (framework 404/405, status→code) · catch-all Exception (→INTERNAL_ERROR).
- **Taxonomy:** UNAUTHENTICATED 401 · DEMO_READ_ONLY 403 · FORBIDDEN 403 · NOT_FOUND 404 (incl.
  **owner-404**) · LINK_GONE 410 · LINK_DELETED **409** · VALIDATION_ERROR 422 · INVALID_URL 422 ·
  INVALID_IMAGE 422 · FILE_TOO_LARGE 413 · RATE_LIMITED 429 · TOKEN_ALLOCATION_FAILED 500 · INTERNAL_ERROR 500.
- **Logging:** JSON · per-request **correlation id** (`X-Request-ID` in/out, contextvars; echoed in
  `details.correlation_id`) · post-auth `user_id` bound · log via the handler seam.
- **No raw IP in logs** (ADR 0013): redirect path none; abuse paths salted-hash/truncated; never
  secrets/cookies/tokens/email; `original_url` not logged by default. **Sentry deferred**; retention **30d**.
- *(ADR-0006-triggered "surface IP to owner in analytics UI?" = Phase 9, not here.)*

---

## Phase 6 — Lightsail deployment (qrcode.paynepew.dev)

**Goal.** Ship to the existing VPS alongside `scheduler.paynepew.dev`.

**Open decisions:** reverse proxy (nginx/caddy) & TLS; OAuth callback URLs; `BASE_URL`; CORS
(currently localhost-only regex, [main.py:104](../backend/main.py)); process manager; secrets management.
- **Rate-limiter behind the proxy (footgun):** must set `TRUSTED_PROXIES` correctly + ensure the
  proxy sends `X-Forwarded-For`, else every request looks like the proxy IP → one shared bucket →
  whole site 429s ([ip_extraction.py:20](../backend/rate_limiter/ip_extraction.py)).
- **Rate-limiter storage:** in-memory is single-process; `--workers=N` multiplies the limit
  N× (ADR 0007, [main.py:61](../backend/main.py) warns). Replace store before scaling workers.
- **💬 Infrastructure-layer rate limiting (topic #5, 2026-06-03):** whether to add rate limiting at
  the infra tier (nginx/caddy `limit_req`, or Cloudflare / WAF) **in front of** the app-level
  per-IP/per-user limiter (ADR 0007). To grill: which layer owns which limit (edge = coarse DoS
  shield, app = business quota); moving the coarse limit off-process sidesteps the in-memory
  single-process footgun above; interaction with `TRUSTED_PROXIES`.

---

## Phase 7 — Frontend redesign (frontend-design)

**Goal.** Re-skin with the `frontend-design` skill: login, dashboard, generator, link detail.

**Depends on:** auth UI (Phase 1), image presentation (Phase 4).

**Carried-in requirement (Q6):** unmistakable **demo-mode UX** — persistent "Demo · read-only" badge/
banner + login CTA; mutation controls disabled or converted to a "log in to create" nudge (driven by
the backend `DEMO_READ_ONLY` 403 code), so an interviewer never mistakes read-only for unimplemented.

---

## Phase 8 — Caching & CDN (Redis + CDN purge + SWR)

**Source:** user topic #2 (2026-06-03). **Status:** 🟢 GRILLED → **ADR 0017** (2026-06-11) · ✅ **backend on
`main`** 06-12 (`link_cache.py` redirect `TTLCache` + image `immutable` + `ebf` CloudFront/OAC). **Framing:**
是否為了 demo 架構完整加入 Redis Cache（為展示完整性，而非當前負載必要）。

**🟢 Decided (2026-06-11) — canonical record in ADR 0017:**
- **Redis: dropped (do not introduce now).** A read-cache in front of the redirect's **synchronous Scan
  write** is theater, and the read it would shield is a sub-ms PK lookup. Redis has exactly two real homes
  here, both recorded for the "說詞" / future: (1) **after Phase 9** makes scan-ingestion async, a
  token→`original_url` cache **with active invalidation on PATCH/DELETE** becomes meaningful; (2) moving
  the **rate-limiter store** off-process (ADR 0007's in-memory counter pins us to 1 uvicorn worker).
- **Image caching (the genuinely valuable, honest half) — `immutable` must target the versioned object.**
  Finding: `GET /api/qr/{token}/image` currently **proxies bytes through the app** (S3 fetch → stream;
  [router.py:210](../backend/router.py)) with **no `Cache-Control`**. Fix: serve the versioned S3 object
  `qr/{token}/composite_{uuid}` with `Cache-Control: public, max-age=31536000, immutable`, and turn the
  **token endpoint into a `no-cache` 302 pointer** to the current version. The staleness trap is
  **re-customization** (a new `composite_{uuid}` is minted), **not** the never-expiry option — the image
  encodes the stable Short URL, so a never-expiring link is the *best* case for image caching.
- **CDN = CloudFront-on-S3, not whole-site.** The image origin is **S3, not the VPS**, so CloudFront drops
  in front of the bucket independently of the VPS/platform; it only requires serving the S3 URL directly
  (stop proxying). A **whole-site** CDN (Cloudflare in front of `qrcode.paynepew.dev`) is **platform-owned**
  (the `edge`, like topic #5) — not qrcode's call, and not where our CDN story lives. **Never CDN-cache the
  302 redirect** (printed QR outlives any cache; stale destination = sends scanners to the wrong place).
- **Redirect read-cache: BUILD it, in-process** (not deferred — cheap + a demonstrable cache pattern; the
  read it shields is sub-ms localhost so this is demonstration > load). `cachetools.TTLCache`, unit
  `token→{original_url, expires_at, deleted_at}`, **derive-state-on-read** (expiry auto-correct, no
  eviction), **active eviction only on PATCH/DELETE** (2 points), **TTL = 300s safety net**, **no negative
  caching** (random-token floods defeat it; redirect flood = edge rate-limit, platform-owned). Correct only
  at 1 worker → Redis is the multi-worker upgrade. **302 never CDN-cached.**
- **Image: option A + CloudFront NOW (甲).** Token endpoint → **302 to the CloudFront URL** (customized) /
  regen inline `no-cache` (vanilla); versioned S3 object gets `immutable` at upload. **CloudFront + OAC**
  (bucket made **private**, read only via the distribution), **default `*.cloudfront.net`** (custom domain
  deferred — needs platform DNS, and option A hides the CDN domain behind the 302 anyway). `storage.public_url`
  → CloudFront URL. **HITL** AWS provisioning (distribution + OAC + bucket-policy change) like S3 `6c0`.
- **SWR: N/A** — immutable images don't need stale-while-revalidate, and the 302 isn't CDN-cached; dropped
  from scope (the roadmap title's "SWR" was speculative).

**Goal (proposed).** Add a caching layer so the hot redirect path (`GET /r/{token}` → `original_url`)
and QR-image fetches don't hit DB/origin on every scan, and so the architecture shows a credible
cache + CDN story.

**Proposed design (to grill):**
- **Redis** cache for token → `original_url` (+ maybe link metadata), with a sane **TTL** **and
  active invalidation** — never TTL-only: a redirect serving a stale URL after an edit is a
  *correctness* bug, not mere staleness.
- **Active purge on write:** on PATCH of `original_url`, call the **CDN purge API** (Cloudflare
  ≈ second-level, CloudFront ≈ minute-level) + evict the Redis key so edits take effect promptly.
- **SWR (stale-while-revalidate)** on cacheable responses:
  `Cache-Control: max-age=300, stale-while-revalidate=60`
  - `0–300s` → serve straight from cache.
  - `300–360s` → serve **stale** instantly + background refresh (user waits 0).
  - `360s+` → synchronous revalidate against origin.

**Open questions:** what's actually cacheable — a 3xx redirect at the CDN needs aggressive purge,
so maybe Redis-only for the redirect and CDN only for the immutable **image** (Phase 4)? · is Redis
justified at this scale or architecture-for-show (be honest in the ADR) · where Redis runs on the
shared VPS (Phase 6, memory budget vs scheduler) · caching must NOT swallow the scan/analytics event
(Phase 9, ADR 0006).

---

## Phase 9 — Analytics & daily reporting (SQS → S3 → batch)

**Source:** user topics #3 + #4 (2026-06-03). **Status:** 🟢 GRILLED 2026-06-11 → **ADR 0016** · ✅ **backend
on `main`** 06-12 (`15l` scan model + async ingest, `xdm` analytics UI; geo `4nw` live in prod — `scans`
derives `country`/`subdivision`/`device_class`).
Framing **corrected during the grill** (mirrors Phase 10): the `SQS→S3→batch` pipeline is
**for-show at this scale** (a single SQL `GROUP BY` over `scans` is the identical report), and a
load-bearing code finding reshaped the phase (see below).

**🔑 Load-bearing findings (verified in code):**
- The redirect hot path writes a Scan **synchronously** (`scan_repository.record_scan` →
  `db.add; db.commit`) *before* returning the 302 ([scan_repository.py:26](../backend/scan_repository.py)).
  The **write**, not the sub-ms PK read, dominates — so a Phase 8 token→`original_url` *read* cache
  cannot take Postgres off the redirect path until this write is decoupled. **Phase 9 unblocks Phase 8.**
- `analytics._recent_scans` ([analytics.py:42](../backend/analytics.py)) **leaks raw `ip_address` +
  `user_agent`** to the owner — a live **ADR 0006 violation** despite the endpoint comment asserting
  the opposite. Phase 9 fixes it *by construction* (drop the columns).

**🟢 Decided (2026-06-11) — canonical record in ADR 0016:**
- **Privacy-by-construction scan model.** A Scan stores only coarse *derived* attributes —
  `scanned_at`, `status_code`, `token`, **`country`** (from IP at ingest) and **`device_class`**
  (from UA at ingest); **raw IP + UA derived-then-discarded, never stored**. Owner sees **total**
  counts, **not** unique-visitors → **no per-scanner identifier** (not even a salted hash). → CONTEXT.md `## Scan`.
- **In-process async ingestion (option 2), not a queue.** Redirect hands the Scan write to FastAPI
  `BackgroundTasks` and returns the 302 without blocking on `commit`. Zero new infra; **at-most-once**
  (a lost scan on crash is acceptable for counting, not billing). This is the foundation the deferred
  pipeline swaps onto — never throwaway.
- **Analytics surface = live SQL, not batch.** Owner-only `GET …/analytics` aggregates on demand:
  `total_scans` · `scans_by_day` · **`scans_by_country`** · **`scans_by_device_class`** · a **coarse
  `recent_scans`** (`scanned_at`/`status_code`/`country`/`device_class`, **no IP/UA**). Phase 7 renders
  a dashboard panel. **No** daily email/report job this phase.
- **Deferred (designed, not built): `SQS→S3→batch` + daily report.** ADR 0016 records the full design —
  producer enqueues (still async) → durable SQS → consumer batches NDJSON to S3 → daily batch rollup →
  report (email digest). **Non-negotiable when built:** at-least-once ⇒ **idempotent** consumer/rollup
  (dedupe by msg id) + **DLQ** for poison messages. Build when volume justifies durable decoupling.
  Estimate if built robustly ≈ **5–8 working days** (consumer process is the bulk + risk).

**Impl notes (→ bd when Phase 9 lands):** Alembic migration drops raw `ip_address`/`user_agent`,
adds `country`/`device_class` (no backfill, per Phase 2 "no data migration"); derive country (IP→geo)
+ device_class (UA parse) at ingest; rewrite `aggregate_scans` (`scans_by_country`/`_by_device_class`,
coarse `recent_scans`). **`scans`-table retention** (topic #6) stays open — keep-forever is fine at
this scale; revisit if the table grows.

---

## Phase 10 — Production hardening: URL safety & SSRF

**Source:** user topic #7 (2026-06-03). **Status:** ✅ IMPLEMENTED 2026-06-10 → **ADR 0015**. Framing
**corrected during the grill** (see below). Implementation = bd `qr_code_generator-ltr` (**CLOSED**, PR #113 → main `57f96d2`).

**🔑 Framing correction (the load-bearing finding).** The service **never fetches `original_url`
server-side** — it only *stores* it (create/PATCH) and returns it as a 302 `Location` to the
scanner's browser (`GET /r/{token}`); the QR encodes the Short URL, not the destination. So **SSRF
has no surface today** — the live threat is **open redirect**, and SSRF/malware-reputation only
become real (and must be gated at *access time*, not mint) once a server-side fetch is added. The
phase title keeps "SSRF" for continuity, but the SSRF work is deferred. → CONTEXT.md `## Destination URL`.

**Decided — ships now (deterministic, string-only mint-time hygiene in `url_validator`, create+PATCH):**
- **Scheme allowlist** — `http`/`https` only. ✅ already in place.
- **Length cap** — reject input > **2048** chars → `INVALID_URL` 422.
- **IDNA / UTS-46** — normalize host with the `idna` package (IDNA 2008 + UTS-46), store canonical
  ASCII/punycode, reject IDNA-invalid hosts. **Homograph *detection* out of scope** (normalize only).
  `idna` promoted from transitive → explicit dependency.
- **IP-literal blocklist** — existing loopback/private/link-local **+** `is_reserved`/`is_multicast`/
  `is_unspecified` + IPv4-mapped-IPv6 unwrap.
- **Rejection shape** — reuse existing `INVALID_URL` 422 envelope (ADR 0012); **no new error code**.
- **Redirect path unchanged** — SSRF + malware deferred ⇒ no serve-time work this phase.

**Deferred (with correct future home recorded in ADR 0015):**
- **SSRF** — only when a server-side fetch of the destination exists; guard goes **at the fetch point**
  doing DNS **resolve-and-pin** + per-redirect-hop re-validation (mint-time DNS = false confidence,
  rebinding bypasses it). Adopt `Drawbridge` / `ssrf-protect`; OWASP SSRF Cheat Sheet.
- **Malware-reputation screening** — authoritative gate is **serve-time interstitial + background
  re-scan**, not mint (mint-only = theater for printed QRs). ⚠️ **Safe Browsing v4 is DEPRECATED** —
  server-side successor is **Google Cloud Web Risk API** (`google-cloud-webrisk`), not the wording
  used earlier in this section.

---

## Key findings log

- **2026-06-02** — #4 is a bug, not a feature. Nonce == retry counter ⇒ 3 tokens/URL ⇒ 4th = 500.
  No evidence of any "3 activities per URL" design intent. Scans are per-token regardless.
- **2026-06-02** — Existing same-URL test stops at N=2, masking the bug. Need N≥4 regression test.
- **2026-06-02** — Phase 0 decision: keep multiple-tokens-per-URL as a feature (A); abuse already
  capped by per-IP rate limiter on `/api/qr/create` (ADR 0007). Caveats pushed to Phase 1
  (per-user quota, anonymous-create question) and Phase 6 (`TRUSTED_PROXIES` proxy config).
- **2026-06-02** — `feature-0510.md` is the pre-existing wishlist; user's #1/#2/#6 = its Items 1/2/3;
  rate limiting (Item 4) already shipped. Aligning roadmap to it.
- **2026-06-02** — 🔴 PATCH/DELETE have zero authorization ([router.py:141](../backend/router.py)/
  [:177](../backend/router.py)). Token-holder can hijack redirect or delete. Phase 1 must fix in
  the auth PR (per feature-0510 Item 1: "not optional, not deferrable").
- **2026-06-03** — Filed 7 "demo-architecture completeness" topics for later discussion (user
  request, not yet grilled): #1 S3 (not e2) for images → Phase 4; #2 Redis cache + CDN purge + SWR
  → new Phase 8; #3 analytics four-Ws + #4 SQS→S3→daily-batch report → new Phase 9; #5 infra-layer
  rate limiting → Phase 6; #6 expired-data cleanup → Phase 2; #7 URL safety / SSRF / IDNA / scheme
  allowlist → new Phase 10. All marked 💬; Phase 1 Q7 still the active grill.
- **2026-06-03** — Foundation (Phase 0+1+2) published to bd as **10 slices** under epic
  `qr_code_generator-ttb` via `bd create --graph`: s1-token `9av` · s2-postgres `4hu` ·
  s3-oauth-provision `0ni` (HITL) · s3a-auth-backend `9m8` · s3b-login-frontend `d3w` ·
  s4a-ownership `ef8` · s4b-authz `3o7` · s5-dashboard `ni7` · s6-ratelimit `dt5` · s7-demo `a0b`.
  DAG: (9av)(4hu+0ni→9m8); 9m8→{d3w, ef8}; ef8→{3o7, dt5}; 3o7→ni7→a0b. Roots: 9av, 4hu, 0ni.
  ⚠️ bd-graph gotcha: a `blocks` edge imports as **"from_key depends on to_key"** (from = blocked),
  so authoring `{from: blocker}` wires it backwards — caught via `bd ready`, fixed with
  `bd dep remove` + `bd dep <blocker> --blocks <blocked>`; `bd dep cycles` clean.
- **2026-06-03** — Foundation (Phases 0–2 + full Phase 1) implemented & landed on `main` (commits
  58b9f40 token / 496535e db / 87dfb90 auth / 0c66188 ownership / 84fbb61 dashboard+demo / 349d51c
  rate-limit / 2e1071c frontend-auth). Phases 3–5 then grilled this session & reconciled to main.
- **2026-06-03** — Phase 3 grilled (ADR 0010). No dedup incl. per-owner (rejected the option owner_id
  newly enabled; multiple-tokens-per-URL + labels is the feature dedup would kill). Token stays
  global-unique. `label` = free-text on Link, optional/non-unique/owner-private; deliberately NO
  Campaign entity. → CONTEXT.md `## Label`.
- **2026-06-03** — Phase 4 grilled (ADR 0011). "Same customized QR next time + cross-device" is
  incompatible with ADR 0004 (logos die on refresh; localStorage per-browser wrong under accounts) →
  0004's persistence stance reversed (client rendering kept). Store result+recipe: composite PNG→S3
  (public/versioned) + style params→DB + logo→S3 (owner-only). Backend-proxy upload (presigned
  rejected). size/ECL system-managed, not user knobs. → CONTEXT.md `## Customization`.
- **2026-06-03** — Phase 5 grilled (ADR 0012+0013). One error envelope `{error:{code,message,details}}`
  for ALL errors (incl. framework 422/HTTPException/500) + AppError + 4 handlers. owner-404;
  mutation-on-deleted→409; distinct upload codes. JSON logs + correlation id (X-Request-ID,
  contextvars) + post-auth user_id. NO raw IP in logs (redirect none; abuse hashed/truncated) —
  extends ADR 0006. Sentry deferred; 30-day retention.
- **2026-06-04** — Phases 3–5 **implemented** and merged to `main` (PR #67 squash → later rewritten to
  the real per-commit history). Slices: `ql8` error envelope · `ai0` labels · `jn4` login tests ·
  `hkb` server-side QR storage (`StorageGateway`, alembic 0005) · `oor` structured logging · `mcc`
  frontend save/restore. Then `rxi`/`6bs`/`8s9` (run via the slice-orchestrator workflow) + `tl8`.
- **2026-06-04** — Phase 4 **S3 provisioned** (bead `6c0`, HITL, DONE): bucket `qrgen-customized-prod`
  (ap-northeast-1) — versioning + noncurrent-version lifecycle, public-read composites / private logos,
  CORS, least-privilege IAM `qrgen-app`. Smoke-tested (composite 200 / logo 403). Creds in deploy `.env`
  (uncommitted). Documented in `docs/deploy/s3-customized-qr-storage.md`. → Phase 6 deploy unblocked.
- **2026-06-04** — **CI/CD added (3 tiers):** `ci.yml` = Lint (ruff) + Backend (pytest 425) + Frontend
  (typecheck/vitest/build) on every PR + push to `main`; `main` branch protection requires all three
  (no required reviews — solo; admins can bypass). Surfaced + fixed a flaky `useGoogleOneTap` test
  (mock-miss race → real `loadGoogleScript` hung in jsdom) and 33 ruff violations. Follow-ups
  (ruff format, Dependabot, alembic drift check) tracked in bead `qr_code_generator-38x`.
- **2026-06-05** — Resumed grill. Verified Phase 6 **shipped** (git + bd epic `p6` 13/14; only `p6s5`
  backups awaits the 1st 18:00 UTC tick); 💬 topic #5 infra-rate-limit **raised to the platform layer**
  (closed from qrcode). **Phase 7 (frontend redesign) re-ranked to LAST** — skin a stable surface;
  redrawing dashboard before Phase 9 analytics = twice. New order **10→8→9→7**; Tailwind v4 (`5mz`)
  rides with P7, React 19 (`n13`) decoupled. **NEXT = Phase 10.** 4 real-use issues filed: `40o`
  size/"pixel" knob (ADR 0011) + `65g` customized-QR-shows-vanilla (`LinkDetail` re-renders from recipe,
  drops logo; **Fix = A** serve stored composite) → both **fix-now**; `nk4` labels-not-wired + `yfx`
  re-edit-in-LinkDetail → **Phase 7**.
- **2026-06-10** — Phase 10 grilled (**ADR 0015**). 🔑 Framing corrected: the service **never fetches
  `original_url` server-side** (store + 302 `Location` only; QR encodes Short URL) ⇒ **no SSRF surface
  today**; live threat = open redirect. Both SSRF and malware-reputation are time-of-check-vs-use
  problems QR maximizes (minted once, scanned for months) ⇒ their real gate is **access-time, deferred**.
  **Ships now:** string-only mint-time hygiene — length cap 2048 · IDNA/UTS-46 host normalize via `idna`
  (homograph *detection* out) · IP-literal blocklist + `is_reserved`/`is_multicast`/`is_unspecified` +
  IPv4-mapped-IPv6 · scheme allowlist (done). Reuse `INVALID_URL` 422 (no new code); redirect unchanged.
  ⚠️ Safe Browsing v4 deprecated → **Web Risk**. Tools: `idna` (promote to explicit dep), `Drawbridge`/
  `ssrf-protect` (future fetch-time). → CONTEXT.md `## Destination URL`; impl bd `qr_code_generator-ltr`.
- **2026-06-10 (later)** — Phase 10 **implemented & merged** (bd `ltr` CLOSED, PR #113, `c730311`→`57f96d2`):
  `validate_and_normalize` hardened per ADR 0015 — length cap 2048 · IDNA/UTS-46 punycode · IP-literal
  blocklist (reserved/multicast/unspecified + IPv4-mapped-IPv6) + IPv6 netloc fix; **460 tests green**; opus
  review APPROVE-WITH-NITS. Phase 10 → ✅ implemented. **Earlier 06-05 "fix-now" bugs both shipped:** `65g`
  (customized-QR-shows-vanilla, 4 stacked root causes, Fix = A serve stored composite) + `40o` (size knob)
  merged in PR #100 (`40b5cfa`), verified in real browser. Quality follow-ups since: timestamp-UTC fixes
  (`8s8`/`r5n`/`0sq`, PRs #101–103), Playwright e2e auth-bypass (`8vd`, PR #110); new open bead `n1q` =
  Playwright CI integration (P3). Backups `p6s5` still IN_PROGRESS (awaits first 18:00 UTC timer tick — not
  yet confirmed). **Phase 8 grill OPENED** — leading finding: the redirect path writes a Scan **synchronously**
  per hit (`scan_repository.record_scan` does `db.add; db.commit`), so a token→`original_url` *read* cache
  **cannot** take Postgres off the redirect hot path until Phase 9 makes scan-ingestion async; it only shields
  an already sub-ms indexed PK lookup. Recasts Phase 8's "redirect doesn't hit DB" story as coupled to Phase 9.
- **2026-06-11** — Phase 9 grilled (**ADR 0016**), out of order before finishing Phase 8 because it unblocks
  it. **Privacy-by-construction scan model:** store coarse derived `country`+`device_class`, raw IP/UA
  **never stored** (makes ADR 0006 structural, not display-time) — surfaced a *live* ADR 0006 violation
  (`analytics._recent_scans` leaks raw IP/UA). No unique-visitor counts ⇒ no per-scanner id, not even a
  salted hash. **In-process async ingestion** (FastAPI `BackgroundTasks`, at-most-once) chosen over SQS —
  removes the sync write from the redirect hot path (unblocking the Phase 8 read-cache) with zero infra;
  **`SQS→S3→batch` designed but deferred** in the ADR (~5–8 days if built robustly; idempotency + DLQ are
  the hard parts, exactly what a deep-dive interviewer probes). **Analytics = live SQL** (`GROUP BY`):
  total/by-day/by-country/by-device + coarse `recent_scans`; daily email/report rides with the deferred
  pipeline. → CONTEXT.md `## Scan` updated. **Phase 8 partial decisions same session** (see Phase 8
  section): Redis dropped; image `immutable` on the versioned S3 object + token endpoint as `no-cache` 302
  pointer (re-customization, not never-expiry, is the staleness trap); CloudFront-on-S3 (VPS-independent),
  whole-site CDN is platform-owned; never CDN-cache the 302.
- **2026-06-11 (later)** — Phase 8 grilled to done (**ADR 0017**), same session, right after Phase 9 (which
  unblocked it). **Honesty lens (again):** the image endpoint is **not** the scan hot path (scanners hit
  `/r/{token}`, which doesn't serve the image), and post-Phase-9 the redirect's only sync work is a sub-ms
  localhost PK read — so none of Phase 8 is load-driven; value = correctness-clean cache pattern + OAC
  security posture + portfolio. **Redis dropped** (two real homes recorded: multi-worker redirect cache +
  off-process rate-limiter). **Redirect read-cache BUILT in-process** (`cachetools.TTLCache`,
  derive-state-on-read so expiry is automatic, evict only on PATCH/DELETE, 300s safety-net TTL, no negative
  cache; 1-worker-only → Redis is the upgrade). **Image: option A + CloudFront NOW** — versioned object
  `immutable` at upload, token endpoint → 302 to **CloudFront** URL, **CloudFront + OAC** (private bucket,
  default `*.cloudfront.net`; custom domain deferred, hidden behind the 302 anyway). HITL AWS provisioning
  like S3 `6c0`. SWR dropped (immutable assets don't need it). **Next = ONE backend build for P8+P9** (same
  redirect/scan code), then Phase 7.
- **2026-06-12** — **P8+P9 backend build landed + prod geo + Phase 6 backups bug.** The "ONE backend build"
  shipped to `main`: `15l` (privacy-by-construction `Scan` + in-process async redirect ingest), `xdm` (coarse
  scan-analytics UI, drops `user_agent`), `6bk` (bucket-correctness tests), `uq9` (independent DB Session for
  the async 302 scan write); `link_cache.py` (redirect `TTLCache`) + image `immutable` + `ebf` CloudFront/OAC
  (`CDN_BASE_URL`) confirm ADR 0017's cache/CDN on `main`. **Prod geo (`4nw`):** GeoLite2-City bind-mounted ro
  into `qrcode-app` + weekly `geoipupdate` cron; verified `derive_geo('8.8.8.8')→('US',None)`, `scans` has
  `country`/`subdivision`/`device_class`. ⚠️ geoipupdate's compiled-default `DatabaseDirectory` on this box is
  `/var/lib/GeoIP`, **not** `/usr/share/GeoIP` — pinned (runbook + bd memory `geoipupdate-databasedirectory-…`).
  **Phase 6 backups were silently FAILING, not "awaiting the first tick":** `qrcode-backup.service` exec'd a
  `0644` (scp'd, non-executable) `backup.sh` directly → `203/EXEC` every tick since 06-05, **zero backups**.
  Fixed (unit → `bash <script>`, `+x` in git, CD `chmod`), verified (S3 dump `AES256` + `restore-drill` PASS +
  IAM active + 14d lifecycle). **bd `zen` + `p6s5` + epic `p6` CLOSED (14/14).** Next frontier = Phase 7 (last phase).
