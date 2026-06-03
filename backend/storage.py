"""Object-storage gateway: put/url_for/delete over S3 (ADR 0011).

This is the **only** module that knows about S3.  All other code calls
``StorageGateway`` and never imports boto3 directly.

Two implementations:
- ``S3Gateway``        — real AWS S3 (or S3-compatible), reads env at call time.
- ``InMemoryGateway``  — pure in-memory fake, used in all tests; no network,
                         no side-effects, resets on instantiation.

Both implement ``StorageGateway``.  Application code should depend only on the
protocol; the DI wiring lives in ``router.py`` / ``main.py``.
"""
from __future__ import annotations

import struct
from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageGateway(Protocol):
    """Minimal interface over object storage (ADR 0011)."""

    def put(self, key: str, data: bytes, content_type: str) -> None:
        """Write ``data`` under ``key``.  Overwrites silently if key already exists."""
        ...

    def url_for(self, key: str) -> str:
        """Return a URL at which the object at ``key`` can be fetched publicly."""
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

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._store[key] = (data, content_type)

    def url_for(self, key: str) -> str:
        return f"{self._base_url}/{key}"

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
    """

    def __init__(self, bucket: str, region: str, endpoint_url: str | None = None) -> None:
        self._bucket = bucket
        self._region = region
        self._endpoint_url = endpoint_url

    def _client(self):  # type: ignore[return]
        import boto3  # deferred so tests never need boto3 installed

        kwargs: dict = {"region_name": self._region}
        if self._endpoint_url:
            kwargs["endpoint_url"] = self._endpoint_url
        return boto3.client("s3", **kwargs)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._client().put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    def url_for(self, key: str) -> str:
        if self._endpoint_url:
            return f"{self._endpoint_url.rstrip('/')}/{self._bucket}/{key}"
        return f"https://{self._bucket}.s3.{self._region}.amazonaws.com/{key}"

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
        total_chunk = data[pos : pos + 12 + length]  # length(4) + type(4) + data(N) + crc(4)
        pos += 12 + length
        if chunk_type in _EXIF_CHUNK_TYPES:
            continue  # drop chunk
        result += total_chunk
    return bytes(result)
