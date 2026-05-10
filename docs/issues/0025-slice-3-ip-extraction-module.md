## Parent

PRD 0001: Per-IP rate limiting on the create endpoint — #22

## What to build

The current `_client_ip` helper in `router.py` takes the **last** entry of `X-Forwarded-For`, which is the trusted proxy itself in any single-trusted-proxy deployment. Behind such a proxy, every request appears to come from the same IP — making the rate limiter useless and silently corrupting the existing `scans.ip_address` data the analytics pipeline reads.

This slice replaces that helper with a configurable `ip_extraction` module and migrates every call site.

The slice introduces:

- `ip_extraction` module exposing one function: `extract_client_ip(request, trusted_proxies: int) → str | None`.
  - `trusted_proxies=0` → ignore `X-Forwarded-For` entirely, use `request.client.host`. This is the safe default for any deployment that is not behind a known reverse proxy.
  - `trusted_proxies=N` → take the entry at position `-(N+1)` from the end of `X-Forwarded-For` (i.e., one hop closer to the client than the trusted boundary). Falls back to `request.client.host` if XFF is missing or shorter than expected.
  - Returns `None` only if neither XFF nor `request.client` provide an address.
- `TRUSTED_PROXIES` env var (default `0`), validated as a non-negative integer at `lifespan()` startup.
- The `RateLimiter` middleware is updated to call the new function.
- The existing `_client_ip` helper in `router.py` is removed; the call site that records `scans.ip_address` is migrated to the new function. This means the existing scan-logging path now records the *scanner's* IP correctly behind a proxy — fixing the latent bug noted in PRD 0001's Further Notes.

The slice does not change the response contract or the bucket algorithm. It changes the IP source used by both the rate limiter and the scan logger.

## Acceptance criteria

- [ ] `backend/rate_limiter/ip_extraction.py` exists with one public function `extract_client_ip(request, trusted_proxies)`
- [ ] `TRUSTED_PROXIES` env var validated at startup as non-negative integer (negative or non-integer aborts startup)
- [ ] `_client_ip` helper in `router.py` is removed
- [ ] Scan-logging call site (`_log_scan` → `scan_repository.record_scan`) uses the new function with the configured `TRUSTED_PROXIES` value
- [ ] Rate-limiter middleware uses the new function with the same configured value
- [ ] Unit tests in `tests/test_rate_limiter_ip_extraction.py` covering:
  - [ ] `trusted_proxies=0` ignores XFF entirely, returns `request.client.host`
  - [ ] `trusted_proxies=1` with single-entry XFF returns that entry
  - [ ] `trusted_proxies=1` with multi-hop XFF returns the rightmost-trusted boundary
  - [ ] `trusted_proxies=N` greater than XFF length falls back to `request.client.host`
  - [ ] Missing XFF returns `request.client.host`
  - [ ] Missing both returns `None`
  - [ ] Whitespace and casing variations in XFF values are handled
- [ ] Existing scan-logging integration tests pass without modification

## Blocked by

- #23 — Slice 1: Minimal end-to-end rate limiter
