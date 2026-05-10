# ADR 0007: Phase-1 rate limiting is per-IP, in-memory, on the create endpoint only

**Status:** Accepted

## Context

`POST /api/qr/create` is the abuse surface of this codebase. A determined caller can script mass token creation with no current ceiling — the resulting links could be used as throwaway redirects to phishing or malware, which makes the short URL the abuse vector and turns the project into a takedown burden. Adding a ceiling to the create path is therefore standard for any link shortener. The question is *what shape* the ceiling takes given Phase-1 constraints.

The constraints shape the option space:

- **No authentication exists** (see ADR 0005). There are no API keys, no user accounts, no session UUIDs. The only durable identity surface for an unauthenticated POST is the source IP.
- **No Redis or external state store.** The deploy story is a single FastAPI process against a SQLite file.
- **The threat is abuse, not billing or compliance.** Imprecision (e.g., a brief boundary burst) is acceptable; a hard 429 ceiling that abusers hit within seconds is sufficient.
- **The product spec includes anonymous use** (`feature-0510.md`: "未登入用戶可直接使用"). A rate-limit identity that requires auth would silently delete that property.

Four shapes were considered:

1. **Per-IP, in-memory, hand-rolled token bucket** (chosen). One small module, no new dependencies, scoped to the create endpoint.
2. **Per-API-key.** No API keys exist. Adding them is a separate feature with its own product surface (issuance, rotation, UI). Out of scope.
3. **Per-Google-OAuth-account** (rate-limit gated by auth). Solves the shared-IP collateral problem precisely, but reverses the "anonymous create" product property and folds Item 1 (auth) into a ticket that was deliberately scoped to ship before it. Account-creation friction also raises the abuse cost only ~1.5–5×, not enough to justify the scope expansion.
4. **`slowapi` + `limits` + Redis backend.** Library-backed, multi-process-safe, future-proof. Adds dependencies and infra (Redis) for a single endpoint, before any multi-process deploy exists. Premature.

## Decision

Phase-1 rate limiting is implemented on `POST /api/qr/create` only, keyed by source IP, backed by an in-memory token bucket with **two windows enforced together: 30 requests/hour and 200 requests/day** (defaults; tunable via `RATE_LIMIT_HOURLY` and `RATE_LIMIT_DAILY`). Both buckets must allow a request for it to pass; whichever denies first triggers a 429 with `Retry-After` keyed to that bucket's refill time.

The implementation lives under `backend/rate_limiter/` as ~80 LOC of dependency-free Python: a pure `step()` function on a `TokenBucket` dataclass, a TTL-pruned in-memory registry, and FastAPI dependency wiring. Source IP comes from a configurable trusted-proxy depth (`TRUSTED_PROXIES`, default `0` = use `request.client.host`). A master kill-switch (`RATE_LIMIT_ENABLED`, default `true`) disables the layer entirely; tests default it to `false`.

Responses always carry IETF `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`, and `RateLimit-Policy` headers (success or 429), so well-behaved clients can self-throttle before being denied. The 429 body matches the existing `{"detail": "..."}` shape used by other non-2xx responses; numeric limits live in headers, not body, so tuning the limit is not a body-shape change.

A bug in the limiter fails **open**, with an `ERROR`-level log: this is a defense layer, not a security gate.

## Consequences

- **Restart loses state.** A backend restart resets every IP's bucket to full. An abuser who detects a restart can re-burst. Acceptable: restarts are rare and the ceiling re-engages within seconds.
- **Single-process-only.** Each worker holds its own dict. Running with `--workers=N` makes the effective limit `N × 30/hour`. **Multi-process deploys must replace the storage layer before being enabled** — this is not a cosmetic swap. The `lifespan()` startup should warn or fail fast if a worker count > 1 is detected.
- **Memory is bounded by TTL pruning, not by request count.** Every bucket entry expires after `2 × max_window` of inactivity and is pruned on next access. Without this the dict grows unboundedly with new IPs over the process lifetime.
- **Shared-IP collateral is accepted.** Corporate NAT, university networks, mobile CGNAT, VPNs, and Tor exit nodes share one public IP among many users. The defaults (30/hour, 200/day) are deliberately wide enough that legitimate shared-IP traffic does not realistically reach the ceiling. If observed false-positive rates are high after launch, the right remediation is captcha-on-threshold, not lowering the limit or switching to per-account identity.
- **PATCH and DELETE are not rate-limited in this ADR.** Their abuse vector is much narrower (requires a known token; the current namespace is 62⁷ ≈ 3.5T) and their per-call cost is one row update. The real Phase-1 gap on PATCH is *authorization*, not rate limiting — anyone holding a token can change its `original_url` today. That gap is owned by the auth feature (Item 1) and must be closed in the same change that introduces accounts.
- **Scan-path (`/r/{token}`) is not rate-limited.** A different threat (scan-flood DDoS, write-amplification on `scans`) and a different remediation (async scan logging, listed separately in `feature-0510.md`).
- **When auth lands, per-user buckets layer on top of per-IP, not replace it.** Authenticated callers get a generous per-user quota; unauthenticated callers continue under the per-IP ceiling. Anonymous use survives.
- **Tuning is operational, not a code change.** Limits are env-driven, validated on `lifespan()` startup. Expect tuning in the first week of real traffic; structured WARNING logs (`rate_limiter.denied ip=… bucket=… retry_after=…`) provide the signal. Anti-spam-cap log emission at 10/sec/IP (then DEBUG) prevents an abuser from amplifying their attack into log-volume cost.
- **No Prometheus metrics in this ADR.** None exist anywhere else in the project. Adding a metrics surface for one counter is the wrong moment; logs are sufficient signal.
