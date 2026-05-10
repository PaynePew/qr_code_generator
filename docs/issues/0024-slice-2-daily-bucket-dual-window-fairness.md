## Parent

PRD 0001: Per-IP rate limiting on the create endpoint — #22

## What to build

Extend the limiter from Slice 1 with a second window so sustained abuse is bounded across days, not just hours.

The slice adds:

- A new env var `RATE_LIMIT_DAILY` (default `200`), validated at `lifespan()` startup. Validation must enforce `RATE_LIMIT_DAILY >= RATE_LIMIT_HOURLY` so daily can never be tighter than hourly (a misconfiguration that would never bind on the daily window).
- A second `TokenBucket` per IP. The `RateLimiter` now holds a list of `(window_label, TokenBucket)` per IP, evaluates them in declaration order, and denies on the first bucket that would deny.
- The fairness rules:
  - `RateLimit-Remaining` = `min(remaining)` across all buckets — telling the client the truthful headroom.
  - `Retry-After` is keyed to the **bucket that triggered the deny**, not to the most-restrictive overall, so the client waits the right amount of time.
  - `RateLimit-Policy` advertises every bucket: `"30;w=3600", "200;w=86400"`.
- One token is consumed from each bucket on a successful (allowed) request. On a denial, no tokens are consumed from any bucket.

The slice does not add new modules. It thickens the existing `RateLimiter` and updates the integration tests.

## Acceptance criteria

- [ ] `RATE_LIMIT_DAILY` env var validated at startup; `RATE_LIMIT_DAILY >= RATE_LIMIT_HOURLY` enforced (fail fast otherwise)
- [ ] Each IP holds two buckets (hourly + daily); both must allow for the request to pass
- [ ] On allow, one token consumed from each bucket
- [ ] On deny, no token consumed from any bucket
- [ ] `RateLimit-Remaining` reports the minimum across all buckets
- [ ] `Retry-After` (on 429) reports the wait time of the bucket that triggered the deny
- [ ] `RateLimit-Policy` lists all buckets in `"<limit>;w=<seconds>"` form, comma-separated
- [ ] New tests:
  - [ ] Hourly exhausted while daily has slack → 429 with hourly-keyed `Retry-After`
  - [ ] Daily exhausted while hourly has slack → 429 with daily-keyed `Retry-After`
  - [ ] After clock advances past hourly refill but daily still exhausted → still denied with daily `Retry-After`
  - [ ] `RateLimit-Remaining` correctly reports `min(remaining)` in mixed-state scenarios
  - [ ] Validation: `RATE_LIMIT_DAILY < RATE_LIMIT_HOURLY` aborts startup
- [ ] Existing tests still pass without modification

## Blocked by

- #23 — Slice 1: Minimal end-to-end rate limiter
