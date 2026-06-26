"""Object-storage gateway: put/url_for/delete over S3 (ADR 0011).

This is the **only** module that knows about S3.  All other code calls
``StorageGateway`` and never imports boto3 directly.

Two implementations:
- ``S3Gateway``        — real AWS S3 (or S3-compatible), reads env at call time.
- ``InMemoryGateway``  — pure in-memory fake, used in all tests; no network,
                         no side-effects, resets on instantiation.

Both implement ``StorageGateway``.  Application code should depend only on the
protocol; the DI wiring lives in ``router.py`` / ``main.py``.

CDN integration (ADR 0017):
- ``S3Gateway`` accepts an optional ``cdn_base_url``; ``url_for`` returns the
  CloudFront URL when set, else the existing S3 URL.
- Composite uploads should call ``put`` with
  ``cache_control=IMMUTABLE_CACHE_CONTROL`` so CloudFront caches them forever.
  Logo uploads omit the header (private/owner-only assets).
"""

from __future__ import annotations

import struct
from typing import Protocol, runtime_checkable

# Immutable cache header for composite QR objects (ADR 0017).
# The versioned key is content-addressed, so 1-year immutable is safe.
IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"


@runtime_checkable
class StorageGateway(Protocol):
    """Minimal interface over object storage (ADR 0011)."""

    def put(
        self,
        key: str,
        data: bytes,
        content_type: str,
        cache_control: str | None = None,
    ) -> None:
        """Write ``data`` under ``key``.  Overwrites silently if key already exists.

        ``cache_control`` is forwarded to S3 as the ``CacheControl`` metadata so
        CloudFront (and any HTTP client) respects it.  Pass
        ``IMMUTABLE_CACHE_CONTROL`` for composite uploads (ADR 0017).
        """
        ...

    def url_for(self, key: str) -> str:
        """Return a URL at which the object at ``key`` can be fetched publicly.

        Returns the CloudFront URL when the gateway is configured with a
        ``cdn_base_url`` (ADR 0017), else the S3 URL.
        """
        ...

    def public_url_for(self, key: str) -> str | None:
        """Return a browser-fetchable PUBLIC URL for ``key``, or None if none exists.

        Distinct from ``url_for``: this returns a URL only when an
        unauthenticated browser can genuinely fetch it — i.e. a CDN
        (CloudFront) fronts the object. When it returns None the object lives in
        a private bucket or an in-process store the browser cannot reach, so the
        caller must proxy the bytes itself (the backend holds the credentials;
        the browser does not). This is the hook that lets the image endpoint
        redirect to the CDN when one is configured and stream bytes otherwise
        (ADR 0017, Route A).
        """
        ...

    def delete(self, key: str) -> None:
        """Delete the object at ``key``.  No-ops if the key does not exist."""
        ...

    def exists(self, key: str) -> bool:
        """Return True when the key is present in storage."""
        ...

    def get(self, key: str) -> bytes | None:
        """Return the raw bytes at ``key``, or None if the key does not exist."""
        ...


class InMemoryGateway:
    """In-memory fake storage gateway for tests.

    Thread-safe is not a requirement — tests are single-threaded.
    The ``base_url`` is the prefix used by ``url_for`` so tests can assert on
    the returned URL without knowing a real bucket name.
    """

    def __init__(self, base_url: str = "http://fake-storage") -> None:
        self._store: dict[str, tuple[bytes, str]] = {}  # key -> (data, content_type)
        self._base_url = base_url.rstrip("/")

    def put(
        self,
        key: str,
        data: bytes,
        content_type: str,
        cache_control: str | None = None,  # accepted but unused in the in-memory fake
    ) -> None:
        self._store[key] = (data, content_type)

    def url_for(self, key: str) -> str:
        return f"{self._base_url}/{key}"

    def public_url_for(self, key: str) -> str | None:
        # In-process store — never reachable by a browser, so the image endpoint
        # must proxy the bytes (returned by ``get``) rather than redirect here.
        return None

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self._store

    def get(self, key: str) -> bytes | None:
        entry = self._store.get(key)
        return entry[0] if entry is not None else None

    def list_keys(self) -> list[str]:
        """Test-helper: return all stored keys."""
        return list(self._store.keys())


class S3Gateway:
    """Real AWS S3 gateway.

    Reads ``AWS_S3_BUCKET``, ``AWS_REGION``, and (optionally) ``AWS_ENDPOINT_URL``
    from the environment at call time so the gateway can be instantiated before
    env is fully loaded (e.g. during FastAPI startup).

    ``AWS_ENDPOINT_URL`` supports S3-compatible stores (MinIO, LocalStack) for
    local development without touching real AWS.

    ``cdn_base_url`` (optional, ADR 0017): when set, ``url_for`` returns a
    CloudFront URL (``{cdn_base_url}/{key}``) instead of the S3 URL.  Omit for
    local development or when CloudFront is not yet provisioned.
    """

    def __init__(
        self,
        bucket: str,
        region: str,
        endpoint_url: str | None = None,
        cdn_base_url: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._region = region
        self._endpoint_url = endpoint_url
        self._cdn_base_url = cdn_base_url.rstrip("/") if cdn_base_url else None

    def _client(self):  # type: ignore[return]
        import boto3  # deferred so tests never need boto3 installed

        kwargs: dict = {"region_name": self._region}
        if self._endpoint_url:
            kwargs["endpoint_url"] = self._endpoint_url
        return boto3.client("s3", **kwargs)

    def put(
        self,
        key: str,
        data: bytes,
        content_type: str,
        cache_control: str | None = None,
    ) -> None:
        """Write ``data`` under ``key``.

        ``cache_control`` is forwarded as the ``CacheControl`` S3 metadata so
        CloudFront (and HTTP clients) respect it.  Pass
        ``IMMUTABLE_CACHE_CONTROL`` for composite uploads (ADR 0017).
        """
        kwargs: dict = {
            "Bucket": self._bucket,
            "Key": key,
            "Body": data,
            "ContentType": content_type,
        }
        if cache_control:
            kwargs["CacheControl"] = cache_control
        self._client().put_object(**kwargs)

    def url_for(self, key: str) -> str:
        """Return the public URL for ``key``.

        Returns the CloudFront URL when ``cdn_base_url`` is configured
        (ADR 0017), the LocalStack/MinIO URL when ``endpoint_url`` is set,
        else the standard S3 HTTPS URL.
        """
        if self._cdn_base_url:
            return f"{self._cdn_base_url}/{key}"
        if self._endpoint_url:
            return f"{self._endpoint_url.rstrip('/')}/{self._bucket}/{key}"
        return f"https://{self._bucket}.s3.{self._region}.amazonaws.com/{key}"

    def public_url_for(self, key: str) -> str | None:
        """Public URL only when a CDN fronts the (private) bucket; else None.

        The bucket is private (CloudFront OAC-only in prod), so the raw S3 URL
        is NOT publicly fetchable — handing it to a browser 403s. Only the
        CloudFront URL is public. With no CDN we return None so the image
        endpoint proxies the bytes: the backend reads the private object with
        its IAM creds (``get``), which the browser cannot do. A bare
        ``endpoint_url`` (MinIO/LocalStack) is likewise treated as non-public —
        proxying works there too without assuming a public-read bucket policy.
        """
        if self._cdn_base_url:
            return f"{self._cdn_base_url}/{key}"
        return None

    def delete(self, key: str) -> None:
        self._client().delete_object(Bucket=self._bucket, Key=key)

    def exists(self, key: str) -> bool:
        import botocore.exceptions

        try:
            self._client().head_object(Bucket=self._bucket, Key=key)
            return True
        except botocore.exceptions.ClientError:
            return False

    def get(self, key: str) -> bytes | None:
        import botocore.exceptions

        try:
            resp = self._client().get_object(Bucket=self._bucket, Key=key)
            return resp["Body"].read()
        except botocore.exceptions.ClientError:
            return None


# ---------------------------------------------------------------------------
# Image validation helpers (used by the customization router)
# ---------------------------------------------------------------------------

# Maximum upload size: 5 MiB (composite QR + logo are tiny; this is generous)
MAX_IMAGE_BYTES = 5 * 1024 * 1024

# Recognized image magic bytes (header sniff, not MIME trust)
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = (b"\xff\xd8\xff",)
_GIF_MAGIC = (b"GIF87a", b"GIF89a")
_WEBP_PREFIX = b"RIFF"
_WEBP_MARKER = b"WEBP"


def sniff_image_content_type(data: bytes) -> str | None:
    """Return a MIME type if ``data`` looks like a supported image, else None.

    Checks magic bytes only — never trusts the client-supplied Content-Type.
    Supported: PNG, JPEG, GIF, WebP.
    """
    if data[:8] == _PNG_MAGIC:
        return "image/png"
    if len(data) >= 3 and data[:3] in _JPEG_MAGIC:
        return "image/jpeg"
    for magic in _GIF_MAGIC:
        if data[: len(magic)] == magic:
            return "image/gif"
    if data[:4] == _WEBP_PREFIX and len(data) >= 12 and data[8:12] == _WEBP_MARKER:
        return "image/webp"
    return None


def strip_png_exif(data: bytes) -> bytes:
    """Remove all tEXt/zTXt/iTXt/eXIf chunks from a PNG.

    This is a best-effort EXIF strip for composite QR PNGs.  Non-PNG data is
    returned unchanged (JPEG EXIF stripping is out of scope for Phase 4).
    """
    if data[:8] != _PNG_MAGIC:
        return data

    _EXIF_CHUNK_TYPES = {b"tEXt", b"zTXt", b"iTXt", b"eXIf"}
    result = bytearray(_PNG_MAGIC)
    pos = 8
    while pos + 12 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        chunk_type = data[pos + 4 : pos + 8]
        total_chunk = data[
            pos : pos + 12 + length
        ]  # length(4) + type(4) + data(N) + crc(4)
        pos += 12 + length
        if chunk_type in _EXIF_CHUNK_TYPES:
            continue  # drop chunk
        result += total_chunk
    return bytes(result)
