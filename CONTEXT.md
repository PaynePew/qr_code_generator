# QR Code Generator — Domain Glossary

## Link States

A **Link** (one row in the `links` table) can be in exactly one of three states at any point in time, derived at read time:

| State | Condition | Mutable via PATCH? |
|-------|-----------|-------------------|
| `active` | `deleted_at IS NULL` AND (`expires_at IS NULL` OR `expires_at > now()`) | Yes |
| `expired` | `deleted_at IS NULL` AND `expires_at <= now()` | Yes — can be re-activated |
| `deleted` | `deleted_at IS NOT NULL` | No — terminal state |

**deleted** takes precedence over **expired** in status derivation.

### Key distinctions

- **Deleted** is intentional and terminal. A deleted link cannot be reactivated via PATCH.
- **Expired** is time-based and reversible. A user may update `expires_at` to a future value (or null) to reactivate an expired link.

### Reactivation (重新啟用)

**Reactivation** is the canonical name for the operation that returns an `expired` Link to `active` by PATCH-ing `expires_at` to a future value or `null`. It is the inverse of natural expiry, exposed in the dashboard as a one-click action.

Reactivation applies only to `expired`. It is **not** valid on `deleted` links — terminal state remains terminal.

## Dashboard

The **Dashboard** is the signed-in user's server-driven home: it lists exactly the Links they own (ADR 0009), newest-first, each with its current state and total **scan count**, fetched from the owner-scoped list endpoint (`GET /api/qr`). Soft-deleted Links are excluded by default and reachable via a trash filter (`?deleted=true`). The list is wrapped in an `items` + `next_cursor` envelope; `next_cursor` is a forward-compatibility placeholder (no pagination logic yet).

The Dashboard is authoritative because the server is the single source of truth for "my Links" — the same Links appear on any device the user signs in from. (This supersedes the Phase-1 `localStorage` Link History and its `missing` / `dismissed` / Display-priority reconciliation, which existed only to paper over per-browser drift before accounts; see ADR 0005, superseded by ADR 0009.)

## User

A **User** (one row in the `users` table) is an authenticated account, introduced in Phase 1 (ADR 0009). Identity is keyed by **`google_sub`** — Google's stable, unique subject id — not by email (which can change). A User carries `email`, `name`, `picture`, `created_at`, `last_login_at`, and an **`is_demo`** flag marking the single shared read-only demo account.

A User is created or refreshed by a Google sign-in: the backend verifies Google's ID token once, then issues its own session (it does not reuse Google's token). A User **owns** the Links they create (see Ownership) and sees them on the server-driven Dashboard from any device.

## Ownership

Every Link minted after Phase 1 is **owned**: the `links.owner_id` column references the creating `User` (ADR 0009). Creating a Link **requires a logged-in User** — an unauthenticated create is rejected (401) — and the creator is stamped as `owner_id` at mint time.

`owner_id` is **nullable**: legacy pre-auth Links predate accounts, so they stay ownerless (`owner_id IS NULL`). Ownerless Links still redirect when scanned, but never surface in any dashboard ("start empty" — there is no backfill). Per ADR 0009, owner-scoped listing (the Dashboard's `GET /api/qr`) returns only the caller's own Links, and owner-only authorization makes info/analytics/PATCH/DELETE return 404 to a non-owner so Token existence is not leaked.

## Session

A **Session** is the app's own proof of a signed-in User, carried in a signed, `httpOnly` + `SameSite=Lax` cookie (`Secure` in production). It encodes only the User id and is verified on each request; a tampered, expired, or dangling cookie is treated as no session at all (401 on owner-only endpoints). Per ADR 0009 the app issues this session after verifying Google's ID token — Google's token is never the session.

## Scan

A **Scan** is a record of a single redirect attempt on a known token. Scans are logged for all known tokens (302 and 410 outcomes). Unknown tokens (404) do not produce a Scan.

## Token

A **Token** is the 7-character Base62 identifier that appears in the short URL. It is derived deterministically from the normalized `original_url`, a server-side secret, and a nonce.

Each POST always produces a new token — duplicate URLs are not deduplicated. Normalization exists for security and storage consistency, not as a deduplication key.

## Short URL

The **Short URL** is the full redirect endpoint URL (`{BASE_URL}/r/{token}`). It is encoded into the QR code image.

## Link Lifecycle

```
[created] → active → expired  ←→  (re-activated by PATCH expires_at)
                 ↓
              deleted  (terminal)
```
