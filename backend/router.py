from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from . import (
    analytics,
    customization_repository,
    link_repository,
    scan_derivation,
    scan_repository,
)
from .auth import get_current_user
from .authorization import authorize_owner, forbid_if_demo
from .database import get_db
from .errors import (
    AppError,
    ErrorCode,
    file_too_large,
    invalid_image,
    invalid_url,
    link_gone,
    not_found,
    token_allocation_failed,
)
from .link_cache import LinkSnapshot, _link_cache
from .link_state import LinkState, derive_state
from .models import Link, User
from .qr_generator import generate_qr_png
from .rate_limiter.ip_extraction import extract_client_ip
from .storage import (
    IMMUTABLE_CACHE_CONTROL,
    MAX_IMAGE_BYTES,
    InMemoryGateway,
    LocalDiskGateway,
    S3Gateway,
    StorageGateway,
    sniff_image_content_type,
    strip_png_exif,
)
from .timeutil import iso_utc, now_utc, to_naive_utc
from .token_generator import TokenCollisionError
from .url_validator import InvalidURLError, validate_and_normalize

router = APIRouter(prefix="/api")
redirect_router = APIRouter()

# get_db now lives in backend.database (shared with the auth layer to avoid a
# router<->auth import cycle); it is imported above so existing
# `from backend.router import get_db` call sites keep working.

# ---------------------------------------------------------------------------
# Storage gateway — injected via FastAPI dependency so tests can swap it out.
# ---------------------------------------------------------------------------

# Module-level singleton for the real app.
# Initialised to InMemoryGateway (inert import-time default; no filesystem side
# effects). main.py lifespan calls build_storage_gateway() at startup and replaces
# this with the env-selected gateway (LocalDiskGateway for dev, S3Gateway for prod).
_storage_gateway: StorageGateway = InMemoryGateway()

# Default on-disk location for the dev gateway. Resolved relative to the backend
# package (not the CWD) so a fresh clone works regardless of where uvicorn runs.
# Gitignored; auto-created on first write. Override with LOCAL_STORAGE_DIR.
_DEFAULT_LOCAL_STORAGE_DIR = Path(__file__).resolve().parent / "data" / "storage"


def build_storage_gateway(env: dict[str, str | None]) -> StorageGateway:
    """Select and return the appropriate StorageGateway from the environment.

    Rules (ADR 0011 / ADR 0017):
    - AWS_S3_BUCKET absent → LocalDiskGateway (dev default: on-disk, survives
      restarts, zero setup). Override the path with LOCAL_STORAGE_DIR.
    - AWS_S3_BUCKET present → S3Gateway; AWS_REGION is then required.
    - AWS_ENDPOINT_URL (optional) is forwarded to S3Gateway for MinIO/LocalStack.
    - CDN_BASE_URL (optional) enables CloudFront URL generation in url_for (ADR 0017).

    Raises RuntimeError when configuration is incomplete (e.g. bucket without region).
    """
    bucket = env.get("AWS_S3_BUCKET", "").strip()
    if not bucket:
        storage_dir = env.get("LOCAL_STORAGE_DIR", "").strip() or str(
            _DEFAULT_LOCAL_STORAGE_DIR
        )
        return LocalDiskGateway(storage_dir)

    region = env.get("AWS_REGION", "").strip()
    if not region:
        raise RuntimeError(
            "AWS_REGION must be set when AWS_S3_BUCKET is configured (ADR 0011)"
        )

    endpoint_url: str | None = env.get("AWS_ENDPOINT_URL", "").strip() or None
    cdn_base_url: str | None = env.get("CDN_BASE_URL", "").strip() or None
    return S3Gateway(
        bucket=bucket,
        region=region,
        endpoint_url=endpoint_url,
        cdn_base_url=cdn_base_url,
    )


def _get_storage() -> StorageGateway:
    """FastAPI dependency: return the active StorageGateway instance."""
    return _storage_gateway


def _build_versioned_key(token: str, prefix: str, ext: str) -> str:
    """Return an immutable versioned storage key.

    Format: ``qr/{token}/{prefix}_{uuid4}.{ext}``
    A new UUID4 on every call guarantees the key is unique across re-stylings
    (ADR 0011: old composite untouched; reaped by S3 lifecycle rule).
    """
    return f"qr/{token}/{prefix}_{uuid.uuid4().hex}.{ext}"


def _config():
    return {
        "secret": os.environ["SECRET"],
        "base_url": os.environ["BASE_URL"].rstrip("/"),
    }


_LABEL_MAX_LEN = 100


def _normalise_label(raw: Optional[str]) -> Optional[str]:
    """Trim whitespace and cap at _LABEL_MAX_LEN. None passes through as None."""
    if raw is None:
        return None
    trimmed = raw.strip()
    return trimmed[:_LABEL_MAX_LEN] if trimmed else None


def _link_response(link: Link, base_url: str, state: LinkState) -> dict:
    return {
        "token": link.token,
        "original_url": link.original_url,
        "short_url": f"{base_url}/r/{link.token}",
        "qr_code_url": f"{base_url}/api/qr/{link.token}/image",
        "label": link.label,
        "status": state,
        "created_at": iso_utc(link.created_at),
        "updated_at": iso_utc(link.updated_at),
        "expires_at": iso_utc(link.expires_at),
    }


def _persist_scan(
    db: Session,
    token: str,
    status_code: int,
    ip: str | None,
    ua: str | None,
) -> None:
    """Derive coarse geo + device attributes and persist the Scan into ``db``.

    Raw IP and UA are derived-and-discarded here (ADR 0016: privacy-by-construction)
    and never reach a persisted column.
    """
    country, subdivision = scan_derivation.derive_geo(ip)
    device_class = scan_derivation.derive_device_class(ua)
    scan_repository.record_scan(
        db,
        token=token,
        scanned_at=now_utc(),
        status_code=status_code,
        country=country,
        subdivision=subdivision,
        device_class=device_class,
    )


def _record_scan_background(
    bind: Engine | Connection,
    token: str,
    status_code: int,
    ip: str | None,
    ua: str | None,
) -> None:
    """BackgroundTasks callback for the 302 scan write — opens its OWN Session.

    By the time this runs, FastAPI (>=0.106) has finalised the get_db
    yield-dependency and closed the request session, so the write must not borrow
    it (bead uq9). The session is built from the request session's ``bind`` (the
    prod engine, or a test's live connection) and always closed.
    ``join_transaction_mode="create_savepoint"`` is a no-op against a plain engine
    bind, and keeps the write inside the outer transaction when a test binds to a
    live connection — so the background write stays visible and is rolled back.
    """
    db = Session(bind=bind, join_transaction_mode="create_savepoint")
    try:
        _persist_scan(db, token, status_code, ip, ua)
    finally:
        db.close()


class CreateRequest(BaseModel):
    url: str
    expires_at: Optional[datetime] = None
    label: Optional[str] = None


@router.post("/qr/create")
def create_qr(
    body: CreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Login-to-create (ADR 0009): get_current_user raises 401 when there is no
    # valid session, so an unauthenticated create never reaches here. The created
    # Link is stamped with the caller as owner.
    # The demo account is read-only — reject before any work so a guest sees the
    # DEMO_READ_ONLY login nudge rather than a 422 on a URL it can't even submit.
    forbid_if_demo(current_user)
    try:
        normalized_url = validate_and_normalize(body.url)
    except InvalidURLError as e:
        raise invalid_url(str(e))

    cfg = _config()
    now = now_utc()
    expires_at = to_naive_utc(body.expires_at)

    try:
        link = link_repository.create_link(
            db,
            normalized_url=normalized_url,
            secret=cfg["secret"],
            owner_id=current_user.id,
            expires_at=expires_at,
            label=_normalise_label(body.label),
            now=now,
        )
    except TokenCollisionError:
        raise token_allocation_failed()

    base_url = cfg["base_url"]
    return {
        "token": link.token,
        "short_url": f"{base_url}/r/{link.token}",
        "qr_code_url": f"{base_url}/api/qr/{link.token}/image",
        "original_url": link.original_url,
        "label": link.label,
    }


@router.api_route("/qr/{token}/image", methods=["GET", "HEAD"])
def qr_image(
    token: str,
    db: Session = Depends(get_db),
    storage: StorageGateway = Depends(_get_storage),
):
    """Return the QR image for a Link (ADR 0011 / ADR 0017, Route A).

    Customized Link:
    - CDN configured (``public_url_for`` returns a URL) → 302 redirect to the
      CloudFront URL so the edge serves the immutable composite. The 302 carries
      ``Cache-Control: no-cache`` because this endpoint is a mutable pointer —
      re-customizing the Link changes its target.
    - No CDN (dev InMemory, or prod S3 without a CDN) → the backend reads the
      composite from storage and streams the bytes itself. The browser cannot
      reach a private bucket / the in-process store, but the backend can (it
      holds the S3 creds), so proxying is the only path that works without a
      public object URL. This is the fix for the broken-image bug where the old
      code redirected the browser straight to a 403/unreachable storage URL.
    - Composite key recorded but the object is gone (reaped by lifecycle, or
      lost on a dev restart) → fall through to vanilla regeneration so the Link
      still has a scannable QR.

    Vanilla Link → regenerate the plain PNG inline with ``Cache-Control: no-cache``
    (a vanilla Link can later become customized, so we must not let clients cache
    the vanilla response indefinitely).

    HEAD is accepted (not only GET) so og:image / link-preview crawlers that
    probe with HEAD get the real 200/302 instead of falling through to the SPA
    mount's reserved-prefix 404 (main.py SPAStaticFiles).
    """
    link = link_repository.get_link(db, token)
    customization = customization_repository.get_customization(db, link.id)

    if customization is not None:
        public_url = storage.public_url_for(customization.image_key)
        if public_url is not None:
            return RedirectResponse(
                url=public_url,
                status_code=302,
                headers={"Cache-Control": "no-cache"},
            )
        composite = storage.get(customization.image_key)
        if composite is not None:
            return Response(
                content=composite,
                media_type="image/png",
                headers={"Cache-Control": "no-cache"},
            )
        # Composite key recorded but object absent → graceful vanilla fallback.

    # Fallback: regenerate vanilla PNG inline (uncustomized Links).
    cfg = _config()
    short_url = f"{cfg['base_url']}/r/{token}"
    png_bytes = generate_qr_png(short_url)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "no-cache"},
    )


def _validate_and_strip_image(
    data: bytes, field_name: str = "image"
) -> tuple[bytes, str]:
    """Validate image bytes: size cap, magic-byte sniff, EXIF strip.

    Returns ``(stripped_bytes, content_type)``.
    Raises ``AppError`` on invalid or oversized uploads (ADR 0011).
    """
    if len(data) > MAX_IMAGE_BYTES:
        raise file_too_large(MAX_IMAGE_BYTES)
    content_type = sniff_image_content_type(data)
    if content_type is None:
        raise invalid_image(
            f"{field_name} is not a recognised image format (PNG, JPEG, GIF, WebP)"
        )
    stripped = strip_png_exif(data)
    return stripped, content_type


@router.put("/qr/{token}/customization")
async def put_customization(
    token: str,
    style: str = Form(..., description="JSON-serialised style recipe"),
    image: UploadFile = File(..., description="Rendered composite QR PNG"),
    logo: UploadFile | None = File(
        default=None, description="Optional logo (re-upload or omit)"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageGateway = Depends(_get_storage),
):
    """Persist a customization recipe + rendered composite (owner-only).

    Accepts a multipart/form-data body:
    - ``style``: JSON-serialised style recipe (colours, dot style, …).
    - ``image``: The rendered composite QR PNG exported by the frontend.
    - ``logo`` (optional): Raw logo image; if omitted the previous logo is cleared.

    Writes a NEW versioned key on every call so re-styling never touches the old
    composite (ADR 0011: immutable versioned keys, reaped by S3 lifecycle rule).
    Owner-only: non-owners receive 404 (owner-404 rule, ADR 0009/0012).
    Demo account is read-only.
    """
    link = link_repository.get_link(db, token)
    authorize_owner(link, current_user)
    forbid_if_demo(current_user)

    # Validate style JSON at the router edge (must be a JSON object).
    try:
        style_parsed = json.loads(style)
        if not isinstance(style_parsed, dict):
            raise ValueError("style must be a JSON object")
    except (ValueError, json.JSONDecodeError) as exc:
        raise AppError(
            ErrorCode.VALIDATION_ERROR, 422, f"Invalid style: {exc}"
        ) from exc

    # Validate and strip EXIF from composite image.
    image_bytes = await image.read()
    stripped_image, image_content_type = _validate_and_strip_image(image_bytes, "image")

    # Validate logo if supplied.
    logo_bytes: bytes | None = None
    logo_content_type: str | None = None
    if logo is not None and logo.filename:
        raw_logo = await logo.read()
        if raw_logo:
            logo_bytes, logo_content_type = _validate_and_strip_image(raw_logo, "logo")

    now = now_utc()

    # Write composite under a NEW versioned key (old one left untouched).
    # Composite objects are immutable (content-addressed key; ADR 0017).
    image_ext = "png" if image_content_type == "image/png" else "bin"
    image_key = _build_versioned_key(token, "composite", image_ext)
    storage.put(image_key, stripped_image, image_content_type, IMMUTABLE_CACHE_CONTROL)

    # Write logo if provided.  Logos are private/owner-only — no immutable header.
    logo_key: str | None = None
    if logo_bytes is not None and logo_content_type is not None:
        logo_ext = logo_content_type.split("/")[-1]
        logo_key = _build_versioned_key(token, "logo", logo_ext)
        storage.put(logo_key, logo_bytes, logo_content_type)

    customization_repository.upsert_customization(
        db,
        link_id=link.id,
        style_json=json.dumps(style_parsed, separators=(",", ":")),
        image_key=image_key,
        logo_key=logo_key,
        now=now,
    )

    return {
        "token": token,
        "image_key": image_key,
        "logo_key": logo_key,
        "updated_at": iso_utc(now),
    }


@router.get("/qr/{token}/customization")
def get_customization(
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageGateway = Depends(_get_storage),
):
    """Return the style recipe + logo ref for re-editing (owner-only).

    Returns 404 when the Link has no customization yet (same shape as not-found
    so the owner cannot probe whether a token exists).
    Owner-only: non-owners receive 404 (owner-404 rule, ADR 0009/0012).
    """
    link = link_repository.get_link(db, token)
    authorize_owner(link, current_user)

    customization = customization_repository.get_customization(db, link.id)
    if customization is None:
        raise not_found("No customization found for this token")

    # The logo is owner-private (ADR 0011) and must NEVER be handed out as a
    # storage URL: InMemory's ``http://fake-storage`` is unreachable, and a
    # cross-origin CloudFront URL is CORS-blocked when the editor re-hydrates
    # the kept logo with ``fetch(logo_url)``. Point at the same-origin owner
    # proxy below instead, so the session cookie authorizes the read and the
    # logo stays behind the owner check (Route A for the logo).
    logo_url: str | None = None
    if customization.logo_key:
        logo_url = f"/api/qr/{token}/logo"

    return {
        "token": token,
        "style": json.loads(customization.style_json),
        "image_url": storage.url_for(customization.image_key),
        "logo_url": logo_url,
        "updated_at": iso_utc(customization.updated_at),
    }


# Logo content-type is inferred from the stored key's extension, which PUT sets
# to the sniffed image subtype (``logo_content_type.split("/")[-1]``): png /
# jpeg / gif / webp. ``storage.get`` returns bytes only (no content-type), so
# this map is how the proxy labels the response.
_LOGO_EXT_CONTENT_TYPE = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}


def _logo_content_type(key: str) -> str:
    ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
    return _LOGO_EXT_CONTENT_TYPE.get(ext, "application/octet-stream")


@router.get("/qr/{token}/logo")
def qr_logo(
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageGateway = Depends(_get_storage),
):
    """Stream the owner's uploaded logo (owner-only proxy; ADR 0011, Route A).

    The logo is owner-private: unlike the immutable composite (ADR 0017, which
    302s to CloudFront when a CDN is configured) the logo is ALWAYS proxied by
    the backend so it never escapes the owner check via a public CDN URL. The
    backend reads the private object with its own creds (``storage.get``) — the
    browser cannot. The editor re-hydrates the kept logo with a same-origin
    ``fetch(/api/qr/{token}/logo)`` whose session cookie authorizes this read
    (works in dev via the Vite proxy and in prod same-origin); a cross-origin
    storage URL would be unreachable (InMemory) or CORS-blocked (CloudFront).

    Owner-only: a non-owner, a token with no customization, and a token whose
    customization has no logo all return 404 (owner-404 rule, ADR 0009/0012) so
    a stranger cannot probe whether a logo exists. ``Cache-Control: no-cache``
    because re-customizing the Link can replace the logo.
    """
    link = link_repository.get_link(db, token)
    authorize_owner(link, current_user)

    customization = customization_repository.get_customization(db, link.id)
    if customization is None or not customization.logo_key:
        raise not_found("No logo found for this token")

    logo_bytes = storage.get(customization.logo_key)
    if logo_bytes is None:
        # Key recorded but the object is gone (dev restart / S3 lifecycle reap).
        raise not_found("No logo found for this token")

    return Response(
        content=logo_bytes,
        media_type=_logo_content_type(customization.logo_key),
        # nosniff: this proxies user-uploaded bytes from the app's own origin, so
        # stop the browser MIME-sniffing the response into anything executable
        # if an owner is ever lured to open the URL as a top-level navigation.
        headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"},
    )


@redirect_router.get("/r/{token}")
def redirect(
    token: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    # In-process read-cache (ADR 0017): miss hits Postgres once; hits skip the DB.
    # LinkNotFoundError from the loader propagates unchanged → 404.
    # State is derived on every request; expiry resolves automatically without eviction.
    snapshot: LinkSnapshot = _link_cache.get_or_load(
        token, lambda: link_repository.get_link(db, token)
    )
    state = derive_state(snapshot, now_utc())

    trusted_proxies = int(os.environ.get("TRUSTED_PROXIES", "0"))
    ip = extract_client_ip(request, trusted_proxies)
    ua = request.headers.get("user-agent")

    if not state.is_redirectable:
        # Write the 410 scan synchronously before raising — BackgroundTasks are not
        # executed when an exception escapes the handler. This runs in-handler while
        # the request session is still open, so it writes through `db` directly.
        _persist_scan(db, token, 410, ip, ua)
        raise link_gone(token)

    # Hand the 302 scan write to BackgroundTasks so the redirect returns before
    # db.commit (ADR 0016 §2: off the hot path; at-most-once is acceptable for analytics).
    # The task opens its OWN session from the request session's bind — by the time it
    # runs, FastAPI (>=0.106) has already closed this request's get_db session (bead uq9).
    background_tasks.add_task(
        _record_scan_background, db.get_bind(), token, 302, ip, ua
    )
    return RedirectResponse(url=snapshot.original_url, status_code=302)


@router.get("/qr")
def list_links(
    deleted: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Owner dashboard (ADR 0009): the caller's own Links only, newest-first,
    # soft-deleted excluded unless ?deleted=true (the trash filter). Auth is
    # required — get_current_user 401s an anonymous caller. Returns an
    # items + next_cursor envelope; next_cursor is a forward-compat placeholder
    # (no pagination yet). Total scan count per Link comes from one aggregate
    # query (no N+1).
    links = link_repository.list_links_for_owner(
        db, current_user.id, include_deleted=deleted
    )
    scan_counts = scan_repository.scan_counts_for_tokens(
        db, [link.token for link in links]
    )
    cfg = _config()
    now = now_utc()
    items = [
        {
            "token": link.token,
            "original_url": link.original_url,
            "short_url": f"{cfg['base_url']}/r/{link.token}",
            "label": link.label,
            "status": derive_state(link, now),
            "scan_count": scan_counts.get(link.token, 0),
            "created_at": iso_utc(link.created_at),
            "expires_at": iso_utc(link.expires_at),
        }
        for link in links
    ]
    return {"items": items, "next_cursor": None}


@router.get("/qr/{token}")
def get_link_info(
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Owner-only (ADR 0009): info carries original_url. A non-owner is treated as
    # not-found (404, not 403) so Token existence is not leaked.
    link = link_repository.get_link(db, token)
    authorize_owner(link, current_user)
    cfg = _config()
    state = derive_state(link, now_utc())
    return _link_response(link, cfg["base_url"], state)


class PatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    original_url: Optional[str] = Field(default=None, min_length=1)
    expires_at: Optional[datetime] = None
    label: Optional[str] = None


@router.patch("/qr/{token}")
def patch_link(
    token: str,
    body: PatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Owner-only (ADR 0009): closes the redirect-hijack hole — a stranger who
    # photographed the QR (the Token is not secret) cannot repoint it. Non-owner
    # -> 404, authorized before any field is read. Ownership is checked first so a
    # demo user targeting a Link it doesn't own still gets 404 (no leak); only a
    # demo user's own Link reaches the read-only 403 DEMO_READ_ONLY.
    link = link_repository.get_link(db, token)
    authorize_owner(link, current_user)
    forbid_if_demo(current_user)
    now = now_utc()

    fields_to_update = body.model_fields_set & {"original_url", "expires_at", "label"}
    if not fields_to_update:
        raise AppError(ErrorCode.VALIDATION_ERROR, 422, "No updatable fields provided")

    normalized_url: Optional[str] = None
    if "original_url" in fields_to_update:
        if body.original_url is None:
            raise AppError(
                ErrorCode.VALIDATION_ERROR, 422, "original_url cannot be null"
            )
        try:
            normalized_url = validate_and_normalize(body.original_url)
        except InvalidURLError as e:
            raise invalid_url(str(e))

    normalized_expires: Optional[datetime] = None
    if "expires_at" in fields_to_update:
        normalized_expires = to_naive_utc(body.expires_at)

    normalised_label: Optional[str] = None
    if "label" in fields_to_update:
        normalised_label = _normalise_label(body.label)

    link = link_repository.apply_patch(
        db,
        link,
        fields=fields_to_update,
        original_url=normalized_url,
        expires_at=normalized_expires,
        label=normalised_label,
        now=now,
    )

    # Evict after DB commit so the very next redirect reads the new state (ADR 0017).
    _link_cache.evict(token)

    cfg = _config()
    new_state = derive_state(link, now_utc())
    return _link_response(link, cfg["base_url"], new_state)


@router.delete("/qr/{token}")
def delete_link(
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Owner-only (ADR 0009): only the owner can take down their campaign;
    # non-owner -> 404. A demo user owns its seeded Links but is read-only, so
    # its own delete is rejected 403 DEMO_READ_ONLY (ownership checked first).
    link = link_repository.get_link(db, token)
    authorize_owner(link, current_user)
    forbid_if_demo(current_user)
    link_repository.mark_deleted(db, link, now_utc())
    # Evict after DB commit so the very next redirect returns 410 (ADR 0017).
    _link_cache.evict(token)
    return {"token": token, "status": "deleted"}


@router.get("/qr/{token}/analytics")
def get_analytics(
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Owner-only (ADR 0009): campaign performance stays private; non-owner -> 404.
    # ADR 0006 still binds — aggregates only, never raw scanner IPs.
    link = link_repository.get_link(db, token)
    authorize_owner(link, current_user)
    scans = scan_repository.scans_for_token(db, token)
    return {
        "token": token,
        "timezone": "UTC",
        **analytics.aggregate_scans(scans),
    }
