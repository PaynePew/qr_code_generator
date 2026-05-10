## Parent

PRD 0001: Per-IP rate limiting on the create endpoint — #22

## What to build

The tracer-bullet first slice for ADR 0007 / PRD 0001. After this lands, `POST /api/qr/create` is rate-limited end-to-end and demoable: 30 successful creates from one source IP, the 31st returns 429 with the correct headers.

The slice introduces a new `rate_limiter` package with three components and wires it as middleware:

- **`TokenBucket`** — pure dataclass + step function. Given current state, monotonic time, and a cost, returns `(allowed, new_state)`. No I/O, no globals. Implements refill-on-access with capacity cap. Algorithm-only; no FastAPI knowledge.
- **`RateLimiter`** — orchestrator holding an in-memory dict of per-IP `TokenBucket` state plus the configured limit. Single bucket in this slice (hourly only). Returns a `CheckResult` with `allowed`, `remaining`, `retry_after_seconds`, `limit`, `reset_seconds`, `policy`.
- **`RateLimitMiddleware`** — Starlette/ASGI middleware scoped to `POST /api/qr/create`. Extracts source IP using the existing `_client_ip` helper (the broken-XFF behavior is intentionally retained in this slice; Slice 3 replaces it). Calls `RateLimiter.check`, writes IETF `RateLimit-*` headers onto the outgoing response (success or 429), and short-circuits with 429 + `Retry-After` + `{"detail": "Rate limit exceeded"}` when denied.

Two env vars are introduced:

- `RATE_LIMIT_ENABLED` (default `true`) — master kill switch. When `false`, the middleware is a passthrough: no IP extraction, no header writing, no log emission. Test conftest sets this to `false` at module load so existing tests are unaffected.
- `RATE_LIMIT_HOURLY` (default `30`) — per-IP hourly capacity.

Both validated at `lifespan()` startup using the same fail-fast pattern as `SECRET` and `BASE_URL`.

If `RateLimiter.check` raises any exception, the middleware logs an `ERROR` line with traceback and forwards the request to the route handler unconditionally. Defense layers must not take down the service they're defending.

Algorithm uses `time.monotonic()`. Wall-clock time is not consulted anywhere in the bucket math.

The `RateLimit-*` header set on every response when the limiter is enabled:

```
RateLimit-Limit: 30
RateLimit-Remaining: <integer>
RateLimit-Reset: <seconds>
RateLimit-Policy: "30;w=3600"
```

On 429, additionally `Retry-After: <seconds>`.

Test conftest grows two opt-in fixtures: `rate_limiter_enabled` (sets the env vars to small values for limiter tests) and `fake_clock` (monotonic-shaped, one-way `advance()`).

**Deferred to later slices:** daily bucket, `TRUSTED_PROXIES`, the `ip_extraction` module, TTL pruning, structured deny-log + anti-spam cap, multi-worker startup warning.

## Acceptance criteria

- [ ] `backend/rate_limiter/` package created with `token_bucket`, `limiter`, and `middleware` modules
- [ ] `TokenBucket.step(now, cost=1) → (allowed, new_state)` is a pure function: no I/O, no globals, clock injected
- [ ] `RateLimiter.check(ip)` returns a `CheckResult` carrying `allowed` / `remaining` / `retry_after_seconds` / `limit` / `reset_seconds` / `policy`
- [ ] `RateLimitMiddleware` runs only on `POST /api/qr/create`; other endpoints are unaffected
- [ ] `RATE_LIMIT_ENABLED` and `RATE_LIMIT_HOURLY` env vars validated at `lifespan()` startup; non-positive integer or unparseable boolean fails fast
- [ ] When `RATE_LIMIT_ENABLED=false`, no IP extraction, no header writing, no log emission, no bucket evaluation occurs
- [ ] When enabled, every successful response from `POST /api/qr/create` carries `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`, `RateLimit-Policy`
- [ ] When the bucket is exhausted, the response is 429 with `Retry-After`, the same `RateLimit-*` headers, and body `{"detail": "Rate limit exceeded"}`
- [ ] If `RateLimiter.check` raises, the middleware logs at ERROR with traceback and forwards the request; the response is the route handler's response
- [ ] Bucket math uses `time.monotonic()` only; wall-clock time is not consulted
- [ ] Existing tests in `tests/` pass without modification (conftest sets `RATE_LIMIT_ENABLED=false` at module load)
- [ ] New tests:
  - [ ] `tests/test_rate_limiter_token_bucket.py` — pure-function unit tests covering empty bucket, exhaustion, refill, capacity-cap-on-refill, zero-cost edge
  - [ ] `tests/test_rate_limiter_integration.py` — TestClient with `rate_limiter_enabled` fixture covering: success carries headers, Nth+1 returns 429 with correct shape, clock advance unlocks one more, two IPs are independent, kill-switch passthrough leaves no headers, fail-open path returns the route response when the limiter raises

## Blocked by

None — can start immediately.
