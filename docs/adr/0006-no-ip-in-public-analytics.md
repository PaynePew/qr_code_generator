# ADR 0006: Scanner IP addresses are not rendered in the analytics UI in Phase 1

**Status:** Accepted

## Context

`GET /api/qr/{token}/analytics` returns a `recent_scans` array whose entries include `ip_address` (captured from `X-Forwarded-For` or the request peer in `_log_scan`). The data exists in the database and travels over the API. The dashboard's analytics view, however, deliberately omits an IP column.

The reason is the combination of two facts:

1. **No authentication exists in Phase 1** (see ADR 0005). Anyone in possession of a token can `GET /api/qr/{token}/analytics`.
2. **Per-link analytics URLs (`/dashboard/:token`) are designed to be shareable bookmarks.** The PRD treats sharing the analytics URL across tabs/devices as a feature.

Combined: rendering scanner IPs in the analytics view would mean any token-holder — including someone who guesses a token, scrapes one from a screenshot, or receives a link from a third party — can read the IP addresses of everyone who scanned that QR. The QR generator becomes a low-effort IP-leak channel for the people scanning, who never opted into being tracked beyond the redirect itself.

Four presentations were considered:

1. **Hide IP column entirely** (chosen).
2. **Show full IP.** Maximum information density. Worst privacy posture.
3. **Show partial IP (e.g., `1.2.3.x`).** Useful for "are these the same person?" pattern detection, with reduced precision. Still leaks /24 subnet, which is enough to identify many home networks or organizations.
4. **Drop the recent-scans table entirely.** Avoids the question, but loses the time-stamp + UA inspection signal that is genuinely useful.

## Decision

Phase 1 ships the recent-scans table without an IP column. The columns are: timestamp, status code badge, parsed user agent. The backend continues to log IPs in `scans.ip_address` and continues to return them in the API payload — only the UI omits them.

When authentication is introduced, the default for the IP column remains **hidden**. The decision to surface IPs (full, masked, or self-only) is reserved for that future moment and SHOULD be made under its own ADR rather than slipped in as part of an auth feature.

## Consequences

- **Reversibility is asymmetric.** Adding an IP column later is one frontend change. Removing it after it has been visible — invalidating cached pages, screenshots, and user expectations — is much harder. Choosing the more conservative default now keeps the easy direction open.
- **Backend payload is unchanged.** `recent_scans[*].ip_address` continues to flow over the API. Tools that consume the API directly (curl, scripts, future internal dashboards) still see IPs. Only the unauthenticated public UI hides them.
- **The decision is about *rendering*, not *retention*.** IPs remain in the database for compliance with whatever scan-log policy emerges later. This ADR does not address retention.
- **Future contributors must NOT add an IP column casually.** A PR titled "surface available analytics fields" or "show IPs in recent scans" should be rejected without an explicit auth-aware design and ideally a follow-up ADR. The CODEOWNERS or review checklist for the analytics view should reference this ADR.
- **"Same IP, repeated scans" pattern detection is unavailable.** This is a real lost feature for users who legitimately want to deduplicate. Acceptable in Phase 1; revisit when auth lands.
- **No mitigation via partial masking.** Option 3 (`1.2.3.x`) was rejected because /24 still identifies many home networks and organizations. If a future ADR re-opens this, partial masking should be evaluated against actual threat models rather than treated as a free privacy improvement.
