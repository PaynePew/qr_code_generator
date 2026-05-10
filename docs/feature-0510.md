# Feature roadmap — 2026-05-10

## Roadmap (longer-term wishlist)

1. 登入登出功能 (OAuth)，多租戶概念實現
2. QR Code Image 持久化儲存在 S3，DB 儲存 blob url
3. 用戶可以對已生成的 QR Code Image 重新修改設計
4. Application Layer Rate Limiting

These four items were originally bundled. Each one extends or reverses an Accepted ADR (Items 1 reverses ADR 0005's Phase-1 posture; Items 2 and 3 reverse ADR 0004's "no server-side styling"; Item 4 is the only pure addition). They are now scoped as separate plans rather than one PR.

---

## Next slice: Item 4 — Application-layer rate limiting

**Status:** designed, ready for implementation. See `docs/adr/0007-rate-limiting-per-ip-in-memory.md` for the load-bearing decisions and `consequences`.

### Scope

Add per-IP rate limiting to **`POST /api/qr/create` only**. Threat model is abuse-bot mass token creation (throwaway redirects to phishing/malware). Accidental DoS protection comes free.

### Locked design

| Aspect | Decision |
|---|---|
| Identity key | Per source IP (no API keys, no auth dependency) |
| `_client_ip` | Made configurable via `TRUSTED_PROXIES` env var, default `0` |
| Algorithm | Token bucket; `capacity = limit`, `refill = limit / period` |
| Windows | Hourly + daily, both must allow; first-to-deny triggers 429 |
| Storage | In-memory dict + TTL pruning, single-process-only |
| Implementation | Hand-rolled, ~80 LOC under `backend/rate_limiter/`, no new deps |
| Response | `{"detail": "..."}` body + IETF `RateLimit-*` + `Retry-After` headers on **every** response |
| Failure mode | Fail-open + ERROR log on bug |
| Observability | Structured WARNING per 429, anti-spam cap 10/sec/IP then DEBUG |
| Testing | Unit (clock-injected pure function) + integration (opt-in fixture); existing tests untouched |

### Env vars

| Var | Default | Purpose |
|---|---|---|
| `RATE_LIMIT_ENABLED` | `true` | Master kill-switch (tests default to `false`) |
| `RATE_LIMIT_HOURLY` | `30` | Per-IP hourly cap |
| `RATE_LIMIT_DAILY` | `200` | Per-IP daily cap |
| `TRUSTED_PROXIES` | `0` | Number of trusted reverse proxies in front of the app |

All validated at `lifespan()` startup, fail fast on non-positive integers (matching the existing `SECRET` / `BASE_URL` pattern).

### UI change (independent, small)

- GitHub icon moved to sidebar.

This is unrelated to rate limiting; can ship as a trivial separate PR or bundle with another frontend change.

---

## Deferred — Items 1, 2, 3

Each one needs its own design pass before implementation. The following notes capture decisions surfaced during Item 4 grilling that affect these plans, so they are not lost.

### Item 1 — OAuth + multi-tenancy

- Migration path out of ADR 0005 (`localStorage` as identity proxy) is **not yet decided**. ADR 0005 lists three options (ignore / one-shot import / auto-attach); each has different ownership ambiguity costs. Pick this in the Item 1 plan.
- **Critical: PATCH and DELETE currently have zero authorization.** Anyone holding a token can change its `original_url` — including someone who scraped a token from a printed QR or screenshot. The Item 1 PR **must** add ownership checks to PATCH/DELETE in the same change as accounts. This is not optional and not deferrable to a follow-up.
- Once Item 1 ships, per-user rate-limit buckets layer **on top of** per-IP (anonymous flow continues), not replace it. ADR 0007's `Consequences` section pins this.
- The Design Requirement line "use userId to hash and generate token" needs interrogation — it changes token derivation but doesn't change uniqueness (already handled via nonce per ADR 0002). What problem is it solving? Defer until Item 1 plan.

### Item 2 — S3 image persistence

- Direct conflict with ADR 0004 ("backend stores no styling; printed QR survives forever because token never changes"). Item 2 plan must either (a) explicitly reverse ADR 0004 with a new ADR, or (b) re-scope to "S3 caches client-rendered output without persisting style state server-side" — those are very different features.
- Once any PATCH triggers an S3 re-upload, **PATCH rate-limiting becomes load-bearing** (each call costs real money). Bundle the rate-limit rule with the Item 2 PR, not as a separate change.

### Item 3 — Re-edit existing QR Code Image design

- Depends on Item 2's resolution. If Item 2 = "server persists styling," then Item 3 is the natural follow-on. If Item 2 = "S3 caches output only," then Item 3 conflicts with ADR 0004 and needs its own ADR.

### Async analytics on redirect path (originally bullet 3 of Design Requirements)

- Separate concern from rate limiting; not part of Item 4.
- Note: the original bullet listed "where: GeoIP / Referer" as new analytics fields. ADR 0006 ("scanner IPs not rendered in UI") still binds — adding GeoIP-derived data needs to consider the same threat model (token-holder reads scanner location). Re-open ADR 0006 if pursuing.
- The Phase-1 scan-path rate limit is also deferred; the design tree explicitly chose not to bundle it with Item 4.
