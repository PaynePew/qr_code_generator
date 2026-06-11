# HITL runbook — country-derivation source (bd `bii`) + CloudFront/OAC (bd `ebf`)

> The two **human-in-the-loop** slices of the P8+P9 backend build (PRD bd `qr_code_generator-ba6`).
> These are steps **you** execute by hand (MaxMind sign-up, AWS console / CLI); the AFK code
> slices (`15l` scan model, `mrv` image app-side) consume the outputs documented here.
> Verified against current AWS / MaxMind docs on 2026-06-11 (sources at the bottom).

---

## Part A — Country-derivation data source · bd `qr_code_generator-bii`

Turns a scanner IP into a coarse `country` **at ingest, then the raw IP is discarded** (ADR 0016).
Only the `scan_derivation` module touches the IP. `device_class` is **not** part of this slice — it
comes from a pure pip UA-parser dependency with no external data, handled in the AFK slice `15l`.

### Decision (recommended: GeoLite2-Country, offline `.mmdb`)

| Option | Verdict | Why |
|---|---|---|
| **MaxMind GeoLite2-Country `.mmdb`** | ✅ recommended | Free, **offline** lookup (no per-scan network call), microsecond lookups, no rate limit on lookups |
| Ingest-time geo API (ipinfo / ip-api) | ⚪ | Adds an external call per scan (even if async), rate limits, another runtime dependency |
| Device-class only (drop country) | ⚪ fallback | Zero setup, but loses the country dimension stories 3 |

### Steps (GeoLite2)

1. **Create a free MaxMind account** — https://www.maxmind.com/en/geolite2/signup
2. **Generate a license key** — account portal → *Manage License Keys* →
   https://www.maxmind.com/en/accounts/current/license-key → **Generate New License Key**.
   When asked *"Will this key be used for GeoIP Update?"* answer **Yes** (so the key works with the
   `geoipupdate` tool). Record your **Account ID** and the **License Key**.
3. **Get `GeoLite2-Country.mmdb`** — two ways:
   - **Manual:** account → *Download Files* → **GeoLite2 Country** → download the `.tar.gz`, extract
     `GeoLite2-Country.mmdb`.
   - **`geoipupdate` (recommended — keeps it fresh):** install `geoipupdate`, write `/etc/GeoIP.conf`:
     ```
     AccountID <your account id>
     LicenseKey <your license key>
     EditionIDs GeoLite2-Country
     ```
     Run `geoipupdate` → writes `GeoLite2-Country.mmdb` into the configured `DatabaseDirectory`
     (default `/usr/share/GeoIP/`).
4. **EULA / freshness constraints (load-bearing):**
   - The GeoLite EULA requires you to **keep data current — delete a database within 30 days of a new
     release**. → run `geoipupdate` on a **weekly cron** (the compliant path); do **not** bake a stale
     `.mmdb` once and forget it.
   - **30 database downloads per day** limit (irrelevant for a weekly cron).
   - **Attribution required:** show *"This product includes GeoLite2 data created by MaxMind,
     available from https://www.maxmind.com"* somewhere (e.g. an About/footer line) — fold into Phase 7.
5. **Deploy placement** — either bundle the `.mmdb` into the prod image, or fetch it at deploy via
   `geoipupdate`. Expose the path to the app via a new env var (the config output of this slice):
   ```
   GEOIP_DB_PATH=/usr/share/GeoIP/GeoLite2-Country.mmdb
   ```
6. **Python read (for the AFK `scan_derivation` slice)** — `pip install geoip2`; the module opens the
   reader once and looks up:
   ```python
   import geoip2.database, geoip2.errors
   reader = geoip2.database.Reader(GEOIP_DB_PATH)          # open once at startup
   try:
       country = reader.country(ip).country.iso_code        # e.g. "TW", "US"
   except (geoip2.errors.AddressNotFoundError, ValueError):
       country = None                                       # private/unknown IP → None
   ```

### Hand-off to AFK slice `15l`
- `GeoLite2-Country.mmdb` reachable at `GEOIP_DB_PATH` in **dev and prod**.
- `geoip2` added to `requirements.txt` (the UA parser too, for `device_class`).
- Attribution line placement decided (Phase 7).

---

## Part B — CloudFront + OAC in front of the composite bucket · bd `qr_code_generator-ebf`

Front `qrgen-customized-prod` (ap-northeast-1, account `489990873558`) with a CloudFront
distribution using **Origin Access Control (OAC)**, make the bucket **private** (CloudFront-only),
and point the app at it via `CDN_BASE_URL`. Composites are currently public-read
(`PublicReadComposites` policy) — that public statement is **removed** by this slice.

> Prereq already satisfied: the bucket's **Object Ownership = Bucket owner enforced** (ACLs disabled,
> per `docs/deploy/s3-customized-qr-storage.md`) — this is an OAC requirement.

### Steps (AWS console)

1. **Create the distribution** (CloudFront → *Create distribution*):
   - **Origin domain** = `qrgen-customized-prod.s3.ap-northeast-1.amazonaws.com`
     (the **REST** endpoint — **not** an S3 *website* endpoint; OAC does not work with website endpoints).
   - **Origin access** → **Origin access control settings (recommended)** → **Create control setting**:
     Name e.g. `qrgen-composites-oac`, **Origin type = S3**, **Signing behavior = Sign requests
     (recommended)** (= `always`; required, else a private bucket returns errors). Save.
   - **Viewer protocol policy** = **Redirect HTTP to HTTPS**; **Allowed methods** = `GET, HEAD`.
   - **Cache policy** = **CachingOptimized** — it respects the origin's `Cache-Control`, so the
     `public, max-age=31536000, immutable` we set on composite upload (slice `mrv`) is honored and the
     versioned objects are cached at the edge essentially forever. No invalidation needed (versioned keys).
   - Leave **Default root object** blank (we serve specific `qr/{token}/composite_{uuid}` keys).
   - **Create.** Record the **distribution domain** `dxxxxxxxxxxxxx.cloudfront.net` and the
     **distribution ID** / ARN.
2. **Replace the bucket policy with a CloudFront-only one** (S3 → bucket → *Permissions* → *Bucket
   policy* → *Edit*). The CloudFront console also offers a **copy policy** button when you attach the
   OAC — paste it into S3. Scope the `Resource` to the **composite prefix** so logos stay private:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "AllowCloudFrontServicePrincipalReadOnly",
         "Effect": "Allow",
         "Principal": { "Service": "cloudfront.amazonaws.com" },
         "Action": "s3:GetObject",
         "Resource": "arn:aws:s3:::qrgen-customized-prod/qr/*/composite_*",
         "Condition": {
           "StringEquals": {
             "AWS:SourceArn": "arn:aws:cloudfront::489990873558:distribution/<DIST_ID>"
           }
         }
       }
     ]
   }
   ```
   The `AWS:SourceArn` condition locks access to **this** distribution only.
3. **Make the bucket private** — *Permissions* → **Block Public Access** → turn **ON** (and **remove**
   the old `PublicReadComposites` public statement). The app's IAM user (`qrgen-app`) keeps full
   access — Block Public Access only blocks **anonymous** access, not IAM-authenticated calls, so
   uploads and the app's private-logo reads are unaffected.
4. **Wire the app** — set the deploy env var consumed by `storage.url_for` (slice `mrv`):
   ```
   CDN_BASE_URL=https://dxxxxxxxxxxxxx.cloudfront.net
   ```
   Redeploy. (With `CDN_BASE_URL` unset the app falls back to direct S3 URLs, so `mrv` can ship and be
   tested before this slice lands.)
5. **Verify:**
   - `https://dxxxxxxxxxxxxx.cloudfront.net/qr/<token>/composite_<uuid>.png` → **200**.
   - Direct S3 `https://qrgen-customized-prod.s3.ap-northeast-1.amazonaws.com/qr/<token>/composite_<uuid>.png`
     → **403** (now private).
   - The app's `GET /api/qr/{token}/image` for a customized Link **302s to the CloudFront URL**.

### Gotchas / notes
- **OAC, not OAI** — OAI is legacy; OAC is the current recommendation and supports all Regions + SSE-KMS.
- **Default `*.cloudfront.net` domain is fine** — it's hidden behind the app's 302 (users only ever see
  `qrcode.paynepew.dev`; the CloudFront domain shows only as a 302 target in DevTools). A custom domain
  (`cdn.qrcode.paynepew.dev`) is **deferred** — it needs an ACM cert in **us-east-1** + DNS records under
  `paynepew.dev`, which is **platform-owned** (ADR 0017).
- **This distribution fronts the image bucket ONLY** — never put the app/redirect behind it; the 302
  redirect must not be CDN-cached (ADR 0017).
- **Shield Standard** (free L3/L4 DDoS protection) comes with CloudFront automatically.
- Existing bucket **CORS** (`GET`/`HEAD` from `*`) continues to apply; `<img>` loads via the 302 are fine.

### Hand-off to AFK slice `mrv`
- `CDN_BASE_URL` set in the deploy env → `storage.url_for` returns CloudFront URLs.
- Bucket private; only public path to composites is via CloudFront.

---

## Sources (verified 2026-06-11)

- AWS — *Restrict access to an Amazon S3 origin* (OAC, bucket policy, Object Ownership requirement):
  https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html
- AWS re:Post — *Configure OAC for CloudFront distributions with Amazon S3 origins*:
  https://repost.aws/knowledge-center/cloudfront-oac-origins
- MaxMind — *GeoLite2 free geolocation data* (sign-up, license key, EULA, 30-day freshness, 30/day limit):
  https://dev.maxmind.com/geoip/geolite2-free-geolocation-data/
- MaxMind — *Download and update databases* (`geoipupdate`, `GeoIP.conf`):
  https://support.maxmind.com/knowledge-base/articles/download-and-update-maxmind-databases
