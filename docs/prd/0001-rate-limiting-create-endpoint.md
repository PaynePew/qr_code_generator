# PRD 0001: Per-IP rate limiting on the create endpoint

**Status:** Ready for agent
**Tracking issue:** [#22](https://github.com/PaynePew/qr_code_generator/issues/22)
**Related:** ADR 0007 (`docs/adr/0007-rate-limiting-per-ip-in-memory.md`); supersedes Item 4 of `docs/feature-0510.md`.

**Implementation slices:**
- [#23 — Slice 1](https://github.com/PaynePew/qr_code_generator/issues/23) — Minimal end-to-end rate limiter (tracer bullet)
- [#24 — Slice 2](https://github.com/PaynePew/qr_code_generator/issues/24) — Daily bucket + dual-window fairness (blocked by #23)
- [#25 — Slice 3](https://github.com/PaynePew/qr_code_generator/issues/25) — IP extraction module + retire broken `_client_ip` (blocked by #23)
- [#26 — Slice 4](https://github.com/PaynePew/qr_code_generator/issues/26) — Resilience + observability (blocked by #23)

---

## Problem Statement

`POST /api/qr/create` has no ceiling. Any caller can script unlimited Token creation, and the resulting Short URLs become a vehicle for phishing/malware redirects — making this project the abuse vector and the takedown burden. The operator has no control surface over create-volume; legitimate users have no protection against a noisy neighbor; and a future cost-bearing feature (S3-backed image persistence) would inherit an unmetered abuse channel on day one.

The product spec also requires anonymous use to remain available (`未登入用戶可直接使用`). Any rate-limit identity that requires authentication silently deletes that property and is therefore disqualified.

## Solution

Apply a per-IP, in-memory token-bucket rate limit to `POST /api/qr/create`, with two windows enforced together (hourly + daily). All non-error responses on that endpoint advertise the current policy and remaining quota via IETF `RateLimit-*` headers, so well-behaved clients can self-throttle before being denied. When the ceiling is reached, the endpoint returns `429 Too Many Requests` with `Retry-After`. The limit is operator-tunable via environment variables and disabled-by-default in tests so the existing test suite is unaffected.

The decision posture and trade-offs (single-process-only storage, restart-loses-state, shared-IP collateral acceptance, deferred PATCH/DELETE/scan-path coverage) are captured in ADR 0007 and are not re-litigated in this PRD.

## User Stories

### Operator / abuse defense

1. As the operator, I want a per-IP ceiling on `POST /api/qr/create`, so that a single abuser cannot script unlimited Token creation against my service.
2. As the operator, I want the rate limit to apply without requiring authentication, so that anonymous create remains a product feature while abuse is still bounded.
3. As the operator, I want to tune the rate-limit thresholds via environment variables, so that I can react to observed traffic patterns in week 1 of launch without redeploying code.
4. As the operator, I want a master kill-switch env var, so that I can disable the rate limiter immediately during an incident or for local development without code changes.
5. As the operator, I want a structured `WARNING` log line every time a request is denied, so that I have signal for tuning the limits and detecting abuse spikes.
6. As the operator, I want the deny-log emission to be capped per IP per second, so that an abuser cannot weaponize my own log volume against me.
7. As the operator, I want the rate limiter to fail-open with an `ERROR` log if it raises an internal exception, so that a bug in the defense layer does not take down create for legitimate users.
8. As the operator, I want an explicit startup warning when more than one worker process is detected, so that I cannot silently run the limiter in a configuration where its in-memory state is per-worker (and the effective ceiling is `N×` what I configured).
9. As the operator, I want a configurable trusted-proxy depth for client IP extraction, so that the rate limiter sees real client IPs whether the app is direct, behind one proxy, or behind a chain.
10. As the operator, I want all environment-variable values validated at process startup, so that misconfiguration fails fast rather than producing wrong behavior at request time.

### End user (the QR creator)

11. As a casual user creating one or two Tokens at a time, I want to never notice that rate limiting exists, so that the feature is invisible to me in normal use.
12. As a power user creating a small batch of Tokens (e.g., 5–15 in a few minutes), I want my burst to succeed without artificial smoothing, so that the tool keeps up with my workflow.
13. As a user behind a shared IP (corporate NAT, mobile CGNAT, public Wi-Fi), I want generous default limits, so that other users on my network do not consume my quota in normal use.
14. As a user who hits the ceiling, I want a 429 response with a clear `Retry-After` header, so that my client (or I) can wait the correct amount of time and resume.
15. As a user whose browser caches a denial, I want every successful response to also include current `RateLimit-*` headers, so that I can know my remaining quota before I hit the wall — not after.
16. As a user who hit the ceiling once, I want the bucket to refill gradually rather than reset at a fixed window boundary, so that I am not hard-blocked for up to an hour just because I hit the wall at the wrong second.
17. As a user, I want the 429 response body to follow the same `{"detail": "..."}` shape as other client errors on this API, so that any error-handling code I have already written continues to work.

### Developer / contributor

18. As a contributor, I want existing tests in the repo to continue passing without modification when this feature lands, so that my work is not blocked by an infrastructure change.
19. As a contributor writing tests for the limiter, I want to control time deterministically via injected clock, so that my tests are not flaky and do not require `time.sleep`.
20. As a contributor writing tests for non-limiter features, I want the limiter to be off by default in tests, so that I can fire many requests in a loop without artificial denials.
21. As a contributor reading the rate-limit code, I want the algorithm logic separated from the FastAPI wiring, so that I can understand and modify each in isolation.
22. As a contributor introducing a future Redis-backed store, I want the in-memory implementation isolated behind a small module surface, so that the swap is a localized change rather than an architectural rewrite.

## Implementation Decisions

### Decision 1 — Scope and identity

- The limiter applies to `POST /api/qr/create` only. PATCH, DELETE, the redirect path, and read endpoints are **not** rate-limited in this PRD; the rationale and triggers for revisiting are pinned in ADR 0007's `Consequences`.
- Identity key is the source IP. There are no API keys, no session UUIDs, no auth dependency. Per-user rate limits are out of scope and will layer on top of per-IP if and when authentication is introduced — they will not replace it.

### Decision 2 — Algorithm

- Token bucket, not fixed window or sliding-window log.
- Two buckets per IP, both must allow: hourly and daily.
- For each bucket, `capacity = limit` and `refill = limit / period` (so `30/hour` means capacity 30, refill rate one token per 120 seconds).
- A request consumes one token from each bucket on success. On denial, no tokens are consumed.
- Bucket math uses **monotonic time only**, never wall-clock time. Wall-clock jumps (NTP sync, leap seconds, DST) must not corrupt bucket state.

### Decision 3 — Storage

- In-memory `dict` keyed by client IP, holding a small per-IP record (one bucket state per window).
- TTL pruning: every entry expires after `2 × max_window` of inactivity and is pruned on next access. This is the only mechanism that bounds memory; without it the dict grows unboundedly.
- Single-process-only. Multi-worker deploys will see effective limit `= N × configured limit`. The lifespan startup must surface this as a warning.

### Decision 4 — Module shape

Four new modules under a single `rate_limiter` package, plus three modification points in existing files. Modules are layered so that each can be tested in isolation:

| Module | Responsibility | Surface |
|---|---|---|
| `TokenBucket` | Pure algorithm. Refill, capacity cap, allow/deny decision. | Dataclass + `step(bucket, now, cost=1) → (allowed, new_bucket)`. |
| `ip_extraction` | Resolve the client IP given a request and a trusted-proxy depth. | One function: `extract_client_ip(request, trusted_proxies) → str \| None`. |
| `RateLimiter` | Orchestrate dual-bucket evaluation; in-memory registry; TTL pruning; env-driven configuration. | `check(ip) → CheckResult` where `CheckResult` carries `allowed`, `remaining` (min across buckets), `retry_after_seconds`, `limit`, `reset_seconds`, `policy`. |
| `RateLimitMiddleware` | FastAPI ASGI middleware scoped to the create endpoint. Extract IP, call `RateLimiter.check`, write `RateLimit-*` and `Retry-After` headers onto the outgoing response (success or 429), short-circuit with 429 when denied, and fail-open + `ERROR` log on internal exception. | Standard Starlette middleware shape. |

Modification points:

| File | Change |
|---|---|
| Application entry | Validate the four new env vars in `lifespan()`, instantiate the singleton `RateLimiter`, register `RateLimitMiddleware`, warn on `WORKERS > 1`. |
| Router for `POST /api/qr/create` | No handler change. The middleware does all the work. |
| Test conftest | Set `RATE_LIMIT_ENABLED=false` at module load. Add opt-in `rate_limiter_enabled` and `fake_clock` fixtures for limiter-specific tests. |

The `TokenBucket` module is the deepest: ~one dataclass plus one ~10-line function, but it encapsulates the entire algorithm and is rarely going to change. `ip_extraction` is similarly deep — one function hides every XFF/trusted-proxy concern. `RateLimiter` is the orchestrator, intentionally narrower in depth because it composes the deep modules with stateful registry + config concerns.

### Decision 5 — Configuration

Four environment variables, validated at `lifespan()` startup using the same fail-fast pattern as the existing `SECRET` and `BASE_URL`:

| Var | Default | Validation |
|---|---|---|
| `RATE_LIMIT_ENABLED` | `true` | Parsed as boolean (`true`/`false` case-insensitive); test suite default is `false`. |
| `RATE_LIMIT_HOURLY` | `30` | Positive integer. |
| `RATE_LIMIT_DAILY` | `200` | Positive integer; `RATE_LIMIT_DAILY ≥ RATE_LIMIT_HOURLY` enforced. |
| `TRUSTED_PROXIES` | `0` | Non-negative integer. `0` means use `request.client.host` directly, ignore XFF entirely. |

When `RATE_LIMIT_ENABLED=false`, the middleware is registered as a passthrough — IP extraction and bucket evaluation are skipped, no headers are written, and no log lines are emitted. This makes the kill-switch O(1) per request.

### Decision 6 — Response contract

On every response from `POST /api/qr/create` (200 or 429), when the limiter is enabled, include:

```
RateLimit-Limit: <most-restrictive-bucket-capacity>
RateLimit-Remaining: <min(remaining across all buckets)>
RateLimit-Reset: <seconds until at least 1 token is available again>
RateLimit-Policy: "<hourly_limit>;w=3600", "<daily_limit>;w=86400"
```

On 429 only, additionally:

```
Retry-After: <seconds keyed to the triggering bucket>
```

The 429 body is `{"detail": "Rate limit exceeded"}` — matching the existing `HTTPException` body shape used by other client-error responses on this API. Numeric quotas are header-only; they are not part of the body contract, so tuning the limit is not a body-shape change.

### Decision 7 — Logging

- One structured `WARNING` log per denial: `rate_limiter.denied ip=<ip> bucket=<hourly|daily> limit=<n> retry_after=<s> path=/api/qr/create`.
- Anti-spam cap on the `WARNING` emission: at most 10 denial logs per IP per second; further denials in the same second drop to `DEBUG`. The cap state lives in a small in-memory counter alongside the buckets.
- One `ERROR` log on internal limiter exception (carries the traceback). Request still completes (fail-open).
- No Prometheus / metrics surface. None exists in this codebase; introducing one for a single counter is the wrong moment.

### Decision 8 — Failure mode

Fail-open. If `RateLimiter.check` raises any exception, the middleware swallows it, logs at `ERROR`, and forwards the request to the route handler unconditionally. The rate limiter is a defense layer, not a security gate; its failure must not take down create for legitimate users.

## Testing Decisions

### What makes a good test, in this codebase

- Test external behavior, not internal state. For `TokenBucket`, that means: given (state, now, cost), assert `(allowed, new_state)`. Do not assert on private fields or intermediate computations.
- Avoid time-mocking via `freezegun` or monkey-patching the `time` module. Inject the clock as a callable so tests advance time explicitly. The `fake_clock` fixture is monotonic-shaped (one-way `advance()`), which prevents accidentally writing tests that depend on wall-clock semantics the limiter does not have.
- Avoid `time.sleep` in tests. Always.
- Match the existing flat layout in `tests/`: one file per module under test, no nested folders.

### Modules to be tested

| Module | Test file | Style |
|---|---|---|
| `TokenBucket` (algorithm) | `tests/test_rate_limiter_token_bucket.py` | Pure-function unit tests. Cover: empty bucket allows up to capacity; denial when empty and no time elapsed; refill after elapsed time; refill capped at capacity (no over-refill); zero-cost edge; first call from unseen state; a few clock-sequence scenarios. |
| `ip_extraction` | `tests/test_rate_limiter_ip_extraction.py` | Unit tests over mocked `Request`-like objects covering: `trusted_proxies=0` ignores XFF entirely; `trusted_proxies=1` with single-entry XFF returns the entry; `trusted_proxies=1` with multi-hop XFF returns the rightmost-trusted boundary; missing XFF falls back to `request.client.host`; missing both returns `None`. |
| `RateLimiter` (orchestrator) | `tests/test_rate_limiter.py` | Unit tests with `fake_clock` injection. Cover: separate IPs are independent; both buckets enforced (denial when hourly is exhausted but daily isn't, and vice versa); TTL pruning removes a long-idle entry; `CheckResult` reports `min(remaining)`; `Retry-After` is from the triggering bucket. |
| Full middleware on the FastAPI app | `tests/test_rate_limiter_integration.py` | `TestClient` with the opt-in `rate_limiter_enabled` fixture (sets small numbers like 3/hour, 5/day). Cover: success responses include `RateLimit-*` headers; the Nth+1 request returns 429 with correct headers and body shape; clock advance unlocks one more request; two TestClient instances simulating different IPs are independent; passthrough when `RATE_LIMIT_ENABLED=false` (no headers, no denials); fail-open when the limiter raises. |

### Prior art in this codebase

- The `tests/conftest.py` `client` fixture is the model for fixture-based dependency overrides. The new `rate_limiter_enabled` and `fake_clock` fixtures follow the same pattern (FastAPI `app.dependency_overrides`), so a contributor learning the test layout encounters one pattern, not two.
- `tests/test_token_generator.py` is the closest analogue for pure-function unit tests against an algorithmic module — same shape we use for `TokenBucket`.
- `tests/test_router.py` is the closest analogue for `TestClient`-based integration tests on the API surface.

### Out of scope for the test plan

- Load testing / k6 / locust. Verifying the limiter holds at thousands of RPS for sustained windows is a deploy-time activity, not a per-PR test. ADR 0007 explicitly defers this.

## Out of Scope

- **Authentication, accounts, OAuth.** Tracked under Item 1 of `feature-0510.md`. When it lands, per-user rate-limit buckets layer on top of per-IP — see ADR 0007.
- **PATCH and DELETE rate limiting.** PATCH's true Phase-1 gap is *authorization* (anyone with a Token can PATCH `original_url`); the right fix arrives via Item 1's ownership check. PATCH rate limiting becomes earned only after Item 2 (S3 image persistence) makes each PATCH expensive.
- **Scan-path (`/r/{token}`) rate limiting.** Different threat (scan-flood DDoS, write-amplification on `scans`); different remediation path (async scan logging). Tracked separately.
- **Redis or any external state store.** The single-process in-memory choice is deliberate. Redis becomes earned the moment a multi-worker or multi-instance deploy is introduced; that change is architectural, not a swap, and requires its own design pass.
- **Captcha-on-threshold.** A real mitigation for shared-IP collateral, but not needed at launch. Revisit only if observed false-positive rates from the structured deny-logs justify it.
- **Prometheus / OpenTelemetry metrics.** No metrics infra exists; adding it for one counter is premature.
- **Admin / runtime config endpoint.** Tuning happens via env-var redeploy, not via API.
- **Per-endpoint policy customization.** All four env vars are global. There is exactly one protected endpoint, so per-endpoint policy is over-engineered.

## Further Notes

- **ADR 0007 is the canonical reference for the load-bearing trade-offs.** This PRD describes *what to build*; the ADR explains *why these specific shapes were chosen and what alternatives were rejected*. Future contributors who disagree with a decision in this PRD should read the ADR before proposing a reversal.
- **The `_client_ip` helper currently in `router.py` takes the *last* entry of `X-Forwarded-For`, which is wrong for any single-trusted-proxy deployment.** This is a latent bug in the existing scan-logging path. The new `ip_extraction` module replaces the broken helper; the existing scan-log call sites should be migrated to the new function as part of this PR. This is a small, safe migration but it is intentionally inside scope — landing the new helper without retiring the old one would leave two IP-extraction code paths with different semantics.
- **The PATCH-authorization gap is being deliberately deferred.** ADR 0007 pins this on Item 1's PR as a non-deferrable requirement. This PRD does not attempt to mitigate it via rate limiting (which would be the wrong defense anyway).
- **The default numbers (30/hour, 200/day) are starting points, not final values.** Expect tuning in week 1 of real traffic. The structured `WARNING` deny-logs are the signal source for that tuning; capturing them in a queryable form (even just `grep`) is part of the post-launch operational story.
