## Parent

PRD 0001: Per-IP rate limiting on the create endpoint — #22

## What to build

Production-readiness for the limiter. After this, an in-memory limiter can run unattended without leaking memory, can be debugged from logs, and refuses to silently degrade when deployed multi-worker.

The slice adds three behaviors:

**TTL pruning.** Every per-IP entry has an effective expiry of `2 × max_window` (currently `2 × 86400 = 172800` seconds with the default daily window). On every access to the registry, expired entries are pruned. The pruning is amortized: there is no separate background thread or scheduler; pruning happens lazily when an IP's bucket is checked, and additionally a small bounded-size sweep (e.g., examine ten arbitrary entries per check) keeps total memory bounded even for IPs that never come back.

**Structured deny-log with anti-spam cap.** Every 429 emits one structured WARN log line:

```
rate_limiter.denied ip=<ip> bucket=<hourly|daily> limit=<n> retry_after=<s> path=/api/qr/create
```

To prevent an abuser from amplifying the attack into log volume cost, the WARN emission is capped at 10/sec/IP. Beyond that cap within the same second, the same line drops to DEBUG. The cap state is a tiny in-memory counter (one int + last-emit timestamp) per IP, kept alongside the bucket state.

**Multi-worker startup warning.** At `lifespan()`, detect the worker count (best-effort: check `WEB_CONCURRENCY` env var, `UVICORN_WORKERS`, gunicorn's `--workers`, or any equivalent the deploy environment exposes). If any indicator suggests more than one worker, emit a WARNING log loudly explaining that the in-memory state is per-worker and the effective limit is `N × configured`. The startup does not abort — the warning is the explicit forcing function described in ADR 0007's `Consequences`.

No new modules. The slice modifies `RateLimiter` (TTL pruning, deny-log with cap), `RateLimitMiddleware` (calls the new log emitter), and `lifespan()` (worker detection).

## Acceptance criteria

- [ ] Per-IP entries expire after `2 × max_window` of inactivity and are pruned lazily on registry access
- [ ] A bounded sweep examines a small number of arbitrary entries per access so unreferenced IPs are eventually pruned
- [ ] Every 429 emits a structured WARN log line with fields: `ip`, `bucket`, `limit`, `retry_after`, `path`
- [ ] WARN-level deny logs are capped at 10/sec/IP; the 11th+ within the same second drop to DEBUG with the same fields
- [ ] At `lifespan()` startup, a WARNING is emitted if any worker-count indicator suggests > 1 worker; the process does not abort
- [ ] New tests:
  - [ ] An idle-then-pruned scenario: IP makes a request, clock advances past the TTL, registry shows the entry pruned on next access
  - [ ] An attack scenario: 100 denies in one second produce ≤ 10 WARN lines + 90 DEBUG lines for the same IP
  - [ ] A two-IP scenario: anti-spam cap is per-IP, not global
  - [ ] A multi-worker startup test that asserts the WARNING log is emitted when the environment hints multi-worker
- [ ] Existing tests still pass without modification

## Blocked by

- #23 — Slice 1: Minimal end-to-end rate limiter
