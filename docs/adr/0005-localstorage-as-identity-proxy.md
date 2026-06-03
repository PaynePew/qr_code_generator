# ADR 0005: `localStorage` is the Phase-1 identity proxy; no public list endpoint

**Status:** Superseded by [ADR 0009](0009-authentication-required-per-user-ownership.md)

> Superseded: authentication is now required and Links are owned per-user (ADR 0009). The `localStorage` Link History — with its `missing` / `dismissed` states and Display-priority reconciliation — is retired in favor of the server-driven owner Dashboard backed by the owner-scoped `GET /api/qr` list endpoint. The "no public list endpoint" caution still holds in spirit: the list endpoint added by ADR 0009 is **owner-scoped and authenticated** (a non-owner gets 404), never a public enumeration. The original decision below is kept for historical context.

## Context

The dashboard view in PRD #6 shows "the user's links," but the system has no authentication. The backend exposes per-token routes (`GET /api/qr/{token}`, `PATCH`, `DELETE`, `analytics`) but deliberately has **no list-all endpoint**, and `links` rows have no `owner_id`. So the question is: how does the dashboard decide which links to display?

Three options were considered:

1. **`localStorage` browser history.** The frontend writes `{token, originalUrl, createdAt, dismissed}` to `localStorage` on every successful create. The dashboard reads that list and fans out `GET /api/qr/{token}` per token via TanStack Query. Privacy boundary is "this browser." Zero backend change.
2. **Backend `GET /api/qr` list endpoint, fully public.** Anyone can fetch every link in the database. Privacy red flag: short URLs are often used for private content (drafts, pre-launch pages); one user's typo could expose another's secret link.
3. **Session UUID + new `links.session_id` column.** Frontend mints a UUID on first visit, stores it in `localStorage`, sends it as a header on create. Backend filters by it. "Almost auth" — a clear precursor to real auth, but if we are touching the schema we should just build real auth.

## Decision

Take Option 1. The Phase-1 identity surface is `localStorage`. Each browser sees only the tokens it has minted. The backend ships unchanged; no list endpoint is added; `links` rows remain ownerless.

The frontend treats a `localStorage`-known token returning 404 as a **first-class state** (`missing`, see `CONTEXT.md`) rather than a silent failure. Auto-purging history on 404 is forbidden — the user must see that data drift happened.

## Consequences

- **Zero backend change.** Phase 1 ships against the existing API surface. This is the dominant practical reason.
- **Privacy by construction.** A browser cannot see other browsers' links because the dashboard cannot enumerate them. Adding a public list endpoint later — even gated by a flag — would silently expose every link ever created in the database. Future contributors must NOT add `GET /api/qr` without first auditing every existing link for shareability assumptions; the safe path is to add it only after authentication exists and only behind it.
- **History does not sync across devices or browsers.** Clearing browser data, switching browsers, or going incognito loses the dashboard view of created links. The "Recover by token" empty-state input is the explicit Phase-1 mitigation: the user can paste a known token to manually re-add it to history.
- **Dashboard data lives in two places.** The token list is in `localStorage`; per-token state is on the server. The frontend reconciles them at read time. The `dismissed` flag in `localStorage` lives only on the client.
- **Migration story when auth lands.** Possible paths, in roughly increasing complexity:
  1. Ignore `localStorage`. Authenticated dashboard starts empty. Users re-create links they care about. Simplest.
  2. One-shot import. On first sign-in, the frontend offers "Import the {N} links from this browser into your account." Each token is associated with the new `owner_id` server-side. Requires a new backend endpoint and an ownership claim model (what if two browsers' histories overlap?).
  3. Auto-attach. On sign-in, every `localStorage` token is silently claimed by the user. Easy if no overlap exists; explosive if it does.
  This ADR does not pick the migration path — it just notes that the cost exists and that any contributor introducing auth should design the migration explicitly rather than discovering it under deadline.
- **No multi-device usage in Phase 1.** Acceptable for the prototype audience.
- **Public-by-default inspection still works.** Anyone with a token in hand can `GET /api/qr/{token}` to see its info and analytics — the system was never designed for token confidentiality. The privacy property protected here is *enumeration*, not *per-token secrecy*.
