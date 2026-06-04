# ADR 0009: Authentication required; per-user ownership (supersedes ADR 0005)

**Status:** Accepted — design locked during grilling; implemented in Phase 1 of the multi-tenant roadmap (`docs/roadmap.md`).

## Context

The prototype had no authentication. Identity was a per-browser `localStorage` history (ADR 0005): anyone could create a Link anonymously, and the dashboard could only ever show "what this browser minted." Links were ownerless — ADR 0002 deliberately removed URL dedup so that adding `owner_id` later would be a clean `ALTER TABLE`. Rate limiting was per-IP and explicitly anonymous-first (ADR 0007).

This posture carried three load-bearing problems as the project pivots to a multi-tenant (per-user) product at `https://qrcode.paynepew.dev`, with interviewers / portfolio reviewers as the primary audience:

1. **A redirect-hijack security hole.** `PATCH` and `DELETE` authorize on *possession of the token alone* (`router.py`). A token is not secret — it is printed on the QR and visible in any screenshot. So anyone could rewrite a printed Link's `original_url` to point at malware, or delete it. With no owner, there is nothing to authorize against.
2. **No durable identity.** "The user's links" lived in `localStorage`, which drifts from the server — the `missing` / `dismissed` / Display-priority reconciliation in `CONTEXT.md` exists only to paper over that drift. It does not survive a browser change.
3. **Shared-IP collateral** in the per-IP rate limiter (ADR 0007).

The alternative considered was a **hybrid**: keep anonymous create, require login only to view analytics / edit. It was rejected because it cannot close hole #1 cleanly (anonymous Links have no owner) and forces a claim / ownership-transfer mechanism (token-possession = proof → ownership race) plus maintaining two identity systems at once.

## Decision

**Authentication (Google OAuth) is required to create and manage Links.** Every new Link is owned (`owner_id`). *Using* a Link — the redirect `GET /r/{token}` — stays public.

- **Authorization matrix.** Public: `GET /r/{token}` (redirect), `GET /api/qr/{token}/image` (the QR PNG encodes only the short URL, leaking nothing about the destination). Owner-only: `GET /api/qr/{token}` (info — carries `original_url`), `GET …/analytics`, `PATCH`, `DELETE`. Non-owner access returns **404, not 403**, so token existence is not leaked. ADR 0006 still binds (owners see aggregates, never raw scanner IPs).
- **Session mechanism.** Server-side session in an `httpOnly` + `Secure` + `SameSite=Lax` cookie (signed-cookie via Starlette `SessionMiddleware`); SPA + API served same-origin behind the reverse proxy. Stateless JWT-in-JS was rejected — XSS token theft, hard revocation, and no horizontal-scale benefit on a single VPS. Google One Tap returns a Google-signed ID token; the backend verifies it (`google-auth`), upserts a `User` by `google_sub`, and issues its **own** session cookie — Google's token is not reused as the session.
- **Funnel preserved without the hybrid.** Google One Tap (one tap, no redirect) plus one shared, richly-seeded, **read-only demo account** (`is_demo`; mutations → `403 DEMO_READ_ONLY`, enforced server-side, and unmistakably badged in the UI). Interviewers see the full multi-tenant dashboard with zero real login.
- **`localStorage` identity retires.** With the server list as the source of truth, the `dismissed` and `missing` states and the Display-priority reconciliation collapse; deletion becomes one level (soft-delete + a trash view).
- **Rate-limit re-architecture.** `POST /api/qr/create` is keyed by **user** (login is required to reach it); the per-IP limiter moves to guard the auth endpoint against account-farming. This partially reverses ADR 0007's "anonymous use survives" consequence.
- **Token derivation is unchanged** (random nonce — Phase 0). `userId` is **not** hashed into tokens; ownership lives in `owner_id`.

## Consequences

- **Supersedes ADR 0005** entirely. **Partially reverses ADR 0007** (anonymous create no longer exists). Resolves ADR 0002's open "ownerless resource" note — Links are now owned.
- **Closes the redirect-hijack hole** in the same change that introduces accounts (owner check on PATCH/DELETE). Non-negotiable; ships with auth, not as a follow-up.
- **Loses the no-login instant-create funnel.** Mitigated by One Tap (~2s for already-signed-in Google users) and the demo account.
- **New deps:** `google-auth`, `itsdangerous`. CORS simplifies to nothing under same-origin prod; dev uses a Vite `/api` proxy (the current `allow_methods/headers="*"` is incompatible with credentialed CORS).
- **`CONTEXT.md`** loses its `missing` / `dismissed` / Display-priority sections when this is implemented (the current code still uses them, so the doc edit lands with the code).
- **Legacy pre-auth Links** (ownerless) do not appear in any dashboard but still redirect — "start empty" migration (ADR 0005 path 1). Exact `owner_id` column nullability / backfill is a Phase 2 migration detail.
- **The demo account is read-only by construction** — the seeded data *is* the demo; guests who want to create use the real 2-second login.
