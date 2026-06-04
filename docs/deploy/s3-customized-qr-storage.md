# Deploy note: S3 storage for customized QR (ADR 0011 / bd qr_code_generator-6c0)

Provisioned object storage for customized-QR composites + uploaded logos. This is the
HITL output of `qr_code_generator-6c0`; the backend `S3Gateway` (`backend/storage.py`)
reads it at runtime. **No secrets in this file** — credentials live only in the deploy
environment / local `.env` (gitignored).

## Resource facts

| Item | Value |
|---|---|
| Bucket name | `qrgen-customized-prod` |
| Region | `ap-northeast-1` (Tokyo) |
| AWS account | `489990873558` |
| Versioning | Enabled |
| Object Ownership | ACLs disabled (bucket-owner-enforced) |
| IAM user | `qrgen-app` (inline policy `qrgen-s3-rw`) |

## Object key layout (set by `backend/router.py:_build_versioned_key`)

```
qr/{token}/composite_{uuid}.{ext}   # rendered composite — PUBLIC read
qr/{token}/logo_{uuid}.{ext}        # uploaded logo — PRIVATE, served via app
```

A new UUID per write makes keys immutable; re-styling writes a new version and the old
one is reaped by the lifecycle rule.

## Configuration applied

- **Block Public Access**: ACL blocks ON; policy blocks OFF (public reach only via the
  bucket policy below).
- **Bucket policy** `PublicReadComposites`: `s3:GetObject` for `*` on
  `arn:aws:s3:::qrgen-customized-prod/qr/*/composite_*`. Logos are not covered → private.
- **CORS**: `GET`/`HEAD` from `*` (tighten `AllowedOrigins` to the frontend origin before
  production).
- **Lifecycle** `expire-noncurrent-qr-versions` (prefix `qr/`): delete noncurrent versions
  after 30 days; abort incomplete multipart uploads after 7 days.
- **IAM inline policy** `qrgen-s3-rw`: `s3:PutObject` / `s3:GetObject` / `s3:DeleteObject`
  on `arn:aws:s3:::qrgen-customized-prod/qr/*` (no `ListBucket`, no bucket-level admin).

## Required environment variables

Set in the deploy secret store / local `.env` (see `.env.example`). Loaded via
`load_dotenv()` in `backend/main.py`.

```
AWS_S3_BUCKET=qrgen-customized-prod
AWS_REGION=ap-northeast-1
AWS_ACCESS_KEY_ID=<qrgen-app access key>
AWS_SECRET_ACCESS_KEY=<qrgen-app secret>
# AWS_ENDPOINT_URL — leave empty for real AWS; set only for local MinIO/LocalStack
```

## Verification (smoke test, passed 2026-06-04)

Upload a composite + a logo, then check public reachability:

- `composite_*` over the public S3 URL → **200**
- `logo_*` over the public S3 URL → **403**

Both PUT and DELETE under `qr/*` succeed with the `qrgen-app` credentials, confirming the
least-privilege policy is sufficient.

## Storage gateway wiring (resolved)

`backend/main.py`'s lifespan calls `build_storage_gateway(os.environ)`, which returns an
`S3Gateway` when `AWS_S3_BUCKET` + `AWS_REGION` are set and an `InMemoryGateway` otherwise.
The running app uses this bucket once those vars are present; on S3 misconfiguration the app
refuses to start rather than silently falling back to in-process storage.
