# ADR 0017: Caching & CDN — in-process redirect cache, immutable image assets via CloudFront + OAC; Redis deferred

**Status:** Accepted

## Context

Phase 8 ("Caching & CDN") set out to add a caching layer so the hot redirect path and
QR-image fetches don't hit DB / origin on every request, and to give the architecture a
credible cache + CDN story. Grilling the proposal against the actual code, traffic
pattern, and scale reshaped it — and it depends on Phase 9 (ADR 0016).

Two facts frame everything:

1. **The redirect is the hot path; the image is not.** A scanner points a camera at the
   printed / displayed QR, which decodes the Short URL and hits `GET /r/{token}` — that
   path never serves the QR *image*. The image endpoint (`GET /api/qr/{token}/image`) is
   fetched only by the owner viewing their dashboard / link detail, or by someone a link is
   shared with. So image caching / CDN is a **low-traffic** concern, while the redirect is
   the only real hot path.

2. **The redirect's cost is now a single read.** After ADR 0016 moved scan-writes off the
   redirect path (in-process async), the only synchronous work left in `GET /r/{token}` is
   one read of the Link — and that read is a sub-millisecond primary-key lookup against a
   Postgres on the *same VPS* (docker network). There is no remote round-trip to cache away.

This is a personal / interview-portfolio deployment on a 2 GB shared Lightsail box, single
uvicorn worker (ADR 0007). At this scale none of the caching here is load-driven; the
honest value is architecture demonstration plus a couple of genuine correctness /
security-posture wins.

## Decision

### 1. Redis — not introduced now

A read-cache in front of the redirect read would be in-process anyway (no Redis), and the
read it shields is a sub-ms localhost PK lookup. Redis has exactly two real homes, both
recorded for the future and the deep-dive story:

- **The multi-worker upgrade of the redirect cache** (below) — an in-process cache is
  correct only at one worker; a shared Redis cache is what makes it correct across workers.
- **Moving the rate-limiter store off-process** — ADR 0007's in-memory counter is what pins
  us to one uvicorn worker; Redis is the path to `--workers=N`.

Neither is needed at current scale, so Redis stays out.

### 2. Redirect read-cache — built, in-process

`GET /r/{token}` caches the Link lookup in an in-process TTL cache (`cachetools.TTLCache`;
no Redis). The design is chosen so correctness is structural:

- **Cache unit:** `token → { original_url, expires_at, deleted_at }` — the fields needed to
  *derive* state, not just the URL.
- **Derive-state-on-read:** every hit recomputes `derive_state(fields, now())`. Expiry is
  therefore handled automatically — once `now()` passes `expires_at` the cached entry
  resolves to `expired` (410) with no eviction. Only data *changes* need eviction.
- **Active eviction at exactly two points:** PATCH (which can change `original_url` or
  `expires_at`) and DELETE evict the token. A create mints a fresh, un-cached token; the
  now-async scan write never mutates the Link — so neither needs eviction.
- **TTL = 300 s, as a pure safety net.** Active eviction does the real work; the TTL only
  bounds the blast radius of a hypothetical missed-eviction bug to five minutes. It is a
  one-line tunable constant.
- **No negative caching of unknown (404) tokens.** A flood of *random* garbage tokens
  defeats it (every entry is unique, zero repeat hits) while bloating memory; only a
  repeated same-bad-token would benefit, which is rare. The correct defense against redirect
  flooding is a rate limit on `/r/{token}` at the edge — which is platform-owned (cf. topic
  #5) — not negative caching.
- **The 302 redirect is never CDN-cached.** A printed QR outlives any cache; a stale
  `Location` after an edit sends scanners to the wrong place — a correctness bug, not
  staleness. Redirect caching stays in-process with active invalidation, never at a CDN.

Correctness caveat (recorded): the in-process cache is correct **only at one worker**. Going
multi-worker without Redis would let an edit on worker A leave worker B serving stale for up
to the TTL. That is the trigger to adopt the Redis version.

### 3. QR image — immutable assets served via CloudFront + OAC

The composite QR is content-addressed and immutable by construction (re-styling writes a new
`qr/{token}/composite_{uuid}` key; ADR 0011), so it is a textbook CDN / immutable-cache
asset — but the *token endpoint* is a stable pointer whose content changes on
re-customization, so the two must be cached differently:

- **The versioned S3 object** gets `Cache-Control: public, max-age=31536000, immutable` set
  at upload (PutObject metadata). Correct because the key is content-addressed.
- **The token endpoint `GET /api/qr/{token}/image` becomes a pointer, not a byte-proxy** (it
  currently fetches from S3 and streams the bytes through the app, with no cache header). For
  a customized Link it returns a **302 to the CloudFront URL** of the current composite (the
  302 itself `no-cache`); for a vanilla Link it regenerates the PNG inline with `no-cache` (a
  vanilla Link can later become customized). `storage.public_url(key)` returns the CloudFront URL.
- **CloudFront with Origin Access Control (OAC).** A distribution fronts the
  `qrgen-customized-prod` bucket; the bucket is made **private** and readable **only** via the
  distribution (OAC), replacing the current public-read bucket policy. Single access path, no
  direct-to-S3 bypass, AWS Shield Standard included.
- **Default `*.cloudfront.net` domain.** A custom domain (`cdn.qrcode.paynepew.dev`) needs an
  ACM cert in us-east-1 plus DNS records under `paynepew.dev`, which is **platform-owned** —
  and under the option-A design the CDN domain is hidden behind the app's 302 anyway (users
  only ever see `qrcode.paynepew.dev`; the CloudFront domain shows only as a 302 target in
  DevTools). So a custom domain is near-zero value here and is deferred.

CloudFront + OAC + the bucket-policy change is a HITL AWS-provisioning task (like the S3
bucket, bead `6c0`); the app side is the `public_url` / 302 integration.

### 3a. Route A refinement (2026-06-26) — proxy bytes when no CDN is configured

Decision 3 as originally written had the image endpoint **always** 302 to
`storage.url_for(image_key)`. In practice that URL is browser-fetchable **only when a CDN
fronts the (private) bucket**: with `CDN_BASE_URL` unset, `url_for` returns the raw S3 URL,
and because the bucket is private (OAC-only, per this ADR) a browser GET 403s → broken
image. The same endpoint also 302'd to an unreachable `http://fake-storage/...` in local
dev (InMemoryGateway), so customized QR images never displayed locally. (This was a live
prod incident on 2026-06-26: `CDN_BASE_URL` was unset, every customized QR 403'd.)

The endpoint now decides via `storage.public_url_for(key)`, which returns a URL **only when
one is genuinely public** (a CDN is configured), else `None`:

- **CDN configured** → 302 to the CloudFront URL (unchanged — the Decision-3 edge-cache path).
- **No CDN** (local dev, or prod before/without CloudFront) → the backend reads the composite
  (`storage.get`, with its own S3 creds — which the browser lacks) and **streams the bytes
  inline** (`Cache-Control: no-cache`). Symmetric to ADR 0011's already-accepted "uploads
  proxy through the validating backend"; per-image bandwidth is negligible (tiny,
  low-frequency assets — the same rationale that rejected presigned uploads).
- **Composite key recorded but object missing** → graceful fallback to vanilla regeneration
  so the Link keeps a scannable QR.

The 302 path keeps the CDN edge-cache benefit where it exists; the proxy path removes the
load-bearing (and, when the bucket is private, false) assumption that the storage URL is
publicly fetchable. The endpoint now also answers **HEAD** (not only GET) so og:image /
link-preview crawlers get the real 200/302 instead of the SPA mount's reserved-prefix 404.
Decision 3's `storage.public_url(key)` is implemented as `public_url_for`.

## Consequences

- **What this actually buys at current scale:** for the redirect, a correctness-clean
  in-process cache demonstrating TTL + active invalidation (the latency saved on a sub-ms
  localhost read is noise); for the image, a cleaner security posture (private bucket via OAC)
  and a correct, demonstrable CDN + immutable-asset architecture. None of it is load-driven —
  stated plainly so it is not mistaken for one. The honest deep-dive story is "here is a
  correct cache / CDN design, here is why it's the right pattern, and here is the scale at
  which each piece starts to matter."
- The redirect handler's lookup is wrapped by the cache; the two eviction calls live in the
  PATCH and DELETE handlers. A future contributor adding any other Link-mutating path MUST add
  an eviction there — the 300 s TTL is only a backstop, not a license to skip it.
- The image endpoint stops streaming bytes through the VPS for customized Links; the bytes are
  served by CloudFront. The app still serves the lightweight 302 (with its DB lookup), because
  option A keeps "where is the current image" server-side rather than exposing the versioned
  CDN URL in the API.
- Going multi-worker (ADR 0007) now has two prerequisites recorded here: a shared
  rate-limiter store and a shared redirect cache — both Redis.
- This ADR concerns infrastructure, so no CONTEXT.md (domain glossary) term changes; caching
  and CDN are deliberately kept out of the glossary.

> Numbering note: ADR 0014 is the platform repo's edge-ingress decision; qrcode's sequence
> skips it (see ADR 0015). This is qrcode ADR 0017.
