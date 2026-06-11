# ADR 0016: Scan analytics — privacy-by-construction model, in-process async ingestion; SQS/batch pipeline deferred

**Status:** Accepted

## Context

Phase 9 ("Analytics & daily reporting") set out to pin down the scan-event data model
and a batch reporting pipeline (the roadmap proposed `scan → SQS → consumer → S3 →
daily Batch Job → report`). Grilling that proposal against the actual code and the
project's scale changed the framing on three fronts.

**The redirect hot path writes synchronously.** `GET /r/{token}` does one indexed
primary-key read (`link_repository.get_link`) and then a **synchronous** Scan write
(`scan_repository.record_scan` → `db.add; db.commit`) *before* returning the 302. The
write — a network round-trip plus commit — dominates the path; the PK read is sub-millisecond.
(This is also why a Phase 8 token→`original_url` *read* cache cannot take Postgres off the
redirect path while the write stays synchronous — recorded here because Phase 8 depends on it.)

**The pipeline is for-show at this scale.** This is a personal / interview-portfolio
deployment on a 2 GB shared Lightsail box. A durable SQS → consumer → S3 → daily-batch
pipeline buys durability and independent scaling that the current volume does not need;
a single `GROUP BY` over the `scans` table produces the identical daily report. Building
the full pipeline now would add a second always-on process and real operational surface
(idempotency, dead-letter handling, consumer recovery) for no present benefit.

**The current analytics endpoint violates ADR 0006.** `analytics._recent_scans` returns
raw `ip_address` and `user_agent` to the owner, directly contradicting ADR 0006 ("owner
sees aggregates, never raw scanner IPs") — even though the endpoint's own comment asserts
the constraint holds.

## Decision

**1. Privacy-by-construction scan model.** A Scan retains only coarse, *derived*
attributes: `scanned_at`, `status_code`, `token`, a coarse **`country`** (derived from
the scanner IP at ingest) and a coarse **`device_class`** (derived from the user agent at
ingest). The raw IP and user agent are derived-then-discarded and **never stored**. This
makes ADR 0006 structurally true — you cannot leak what you never persisted — rather than
enforced only at display time, and it fixes the current `_recent_scans` leak by removing
the columns it reads from. The owner sees **total** scan counts, not unique-visitor
counts, so **no per-scanner identifier is retained** — not even a salted IP hash, which
would only be needed to count uniques.

**2. In-process async ingestion (not a queue).** The redirect handler hands the Scan
write to an in-process background task (FastAPI `BackgroundTasks`) and returns the 302
without blocking on `db.commit`. This takes the write off the redirect's critical path
with **zero new infrastructure**. The tradeoff is **at-most-once** recording — a scan can
be lost if the process dies between responding and writing — which is acceptable for
analytics (we are counting, not billing). This async seam is also the foundation the
deferred pipeline builds on (decision 4), so it is never throwaway work.

**3. Analytics surface = live SQL, not batch.** The owner-only
`GET /api/qr/{token}/analytics` endpoint aggregates on demand (`GROUP BY` over `scans`)
and returns: `total_scans`, `scans_by_day` (time series), **`scans_by_country`**,
**`scans_by_device_class`**, and a **coarse `recent_scans`** feed (`scanned_at`,
`status_code`, `country`, `device_class` — no IP / UA). Phase 7 renders this as a
dashboard panel. There is **no** daily email / report job in this phase.

**4. Deferred — designed, not built: the SQS → S3 → batch pipeline (and the daily report
it would feed).** When scan volume justifies durable decoupling and independent scaling,
the upgrade swaps the background write's *target* from "Postgres directly" to "SQS":
`redirect → (background) → SQS`; a separate consumer batches events to S3 (partitioned
NDJSON, **not** one object per scan) and/or Postgres; a scheduled daily batch aggregates
the day's events into per-owner / per-Link / per-token rollups and delivers a report (e.g.
an email digest). Two correctness requirements are non-negotiable when this is built:
because SQS is **at-least-once**, the consumer (or the aggregation) must be **idempotent** —
dedupe by message id, or make the rollup tolerant of duplicates, so scan counts do not
inflate; and a **dead-letter queue** must catch poison messages so one malformed event
cannot wedge the consumer. Because decision 2 already moved the write to a background
seam, this is an **incremental swap, not a rewrite**.

## Consequences

- A migration drops the raw `ip_address` / `user_agent` columns and adds `country` /
  `device_class`; existing rows are not backfilled (throwaway prototype data, consistent
  with the Phase 2 "no data migration" stance). The current ADR-0006 violation disappears
  with the columns.
- The redirect hot path stops blocking on the Scan write. This is the **prerequisite that
  unblocks the Phase 8 redirect read-cache** (token→`original_url` with active invalidation
  on PATCH / DELETE): with the write off the path, the read is the only thing left to cache.
  Phase 8's redirect-cache work is therefore sequenced *after* this phase.
- Ingestion is at-most-once by choice. If that tradeoff ever becomes unacceptable, the
  deferred SQS path provides at-least-once durability — at the cost of the idempotency /
  DLQ machinery above.
- A future contributor who proposes "add the SQS pipeline" has the design and the
  idempotency / DLQ requirements here. One who proposes "cache the redirect in Redis"
  should first confirm scan ingestion is async — otherwise the read cache shields a sub-ms
  PK read while the synchronous write still dominates (the same false-confidence trap ADR
  0015 flags for mint-time SSRF checks).
- The pipeline being for-show is stated plainly so it is not mistaken for a load-driven
  decision. The honest story — "live SQL now, event pipeline when volume justifies it,
  here is the at-least-once / idempotency / DLQ design for that day" — is a stronger
  artifact than a fragile half-built pipeline missing exactly those parts.
