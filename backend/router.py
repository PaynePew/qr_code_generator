import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from . import analytics
from . import link_repository
from . import scan_repository
from .auth import get_current_user
from .authorization import authorize_owner
from .database import get_db
from .link_state import LinkState, derive_state
from .models import Link, User
from .token_generator import TokenCollisionError
from .url_validator import validate_and_normalize, InvalidURLError
from .qr_generator import generate_qr_png
from .rate_limiter.ip_extraction import extract_client_ip

router = APIRouter(prefix="/api")
redirect_router = APIRouter()

# get_db now lives in backend.database (shared with the auth layer to avoid a
# router<->auth import cycle); it is imported above so existing
# `from backend.router import get_db` call sites keep working.


def _config():
    return {
        "secret": os.environ["SECRET"],
        "base_url": os.environ["BASE_URL"].rstrip("/"),
    }


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _link_response(link: Link, base_url: str, state: LinkState) -> dict:
    return {
        "token": link.token,
        "original_url": link.original_url,
        "short_url": f"{base_url}/r/{link.token}",
        "qr_code_url": f"{base_url}/api/qr/{link.token}/image",
        "status": state,
        "created_at": link.created_at.isoformat(),
        "updated_at": link.updated_at.isoformat(),
        "expires_at": link.expires_at.isoformat() if link.expires_at else None,
    }


def _log_scan(db: Session, token: str, status_code: int, request: Request):
    trusted_proxies = int(os.environ.get("TRUSTED_PROXIES", "0"))
    scan_repository.record_scan(
        db,
        token=token,
        scanned_at=_now_utc(),
        status_code=status_code,
        ip_address=extract_client_ip(request, trusted_proxies),
        user_agent=request.headers.get("user-agent"),
    )


class CreateRequest(BaseModel):
    url: str
    expires_at: Optional[datetime] = None


@router.post("/qr/create")
def create_qr(
    body: CreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Login-to-create (ADR 0009): get_current_user raises 401 when there is no
    # valid session, so an unauthenticated create never reaches here. The created
    # Link is stamped with the caller as owner.
    try:
        normalized_url = validate_and_normalize(body.url)
    except InvalidURLError as e:
        raise HTTPException(status_code=422, detail=str(e))

    cfg = _config()
    now = _now_utc()
    expires_at = body.expires_at.replace(tzinfo=None) if body.expires_at else None

    try:
        link = link_repository.create_link(
            db,
            normalized_url=normalized_url,
            secret=cfg["secret"],
            owner_id=current_user.id,
            expires_at=expires_at,
            now=now,
        )
    except TokenCollisionError:
        raise HTTPException(status_code=500, detail="Token generation failed")

    base_url = cfg["base_url"]
    return {
        "token": link.token,
        "short_url": f"{base_url}/r/{link.token}",
        "qr_code_url": f"{base_url}/api/qr/{link.token}/image",
        "original_url": link.original_url,
    }


@router.get("/qr/{token}/image")
def qr_image(token: str, db: Session = Depends(get_db)):
    link_repository.get_link(db, token)
    cfg = _config()
    short_url = f"{cfg['base_url']}/r/{token}"
    png_bytes = generate_qr_png(short_url)
    return Response(content=png_bytes, media_type="image/png")


@redirect_router.get("/r/{token}")
def redirect(token: str, request: Request, db: Session = Depends(get_db)):
    link = link_repository.get_link(db, token)

    state = derive_state(link, _now_utc())
    if not state.is_redirectable:
        _log_scan(db, token, 410, request)
        raise HTTPException(status_code=410, detail="Link is gone")

    _log_scan(db, token, 302, request)
    return RedirectResponse(url=link.original_url, status_code=302)


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
    state = derive_state(link, _now_utc())
    return _link_response(link, cfg["base_url"], state)


class PatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    original_url: Optional[str] = Field(default=None, min_length=1)
    expires_at: Optional[datetime] = None


@router.patch("/qr/{token}")
def patch_link(
    token: str,
    body: PatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Owner-only (ADR 0009): closes the redirect-hijack hole — a stranger who
    # photographed the QR (the Token is not secret) cannot repoint it. Non-owner
    # -> 404, authorized before any field is read.
    link = link_repository.get_link(db, token)
    authorize_owner(link, current_user)
    now = _now_utc()

    fields_to_update = body.model_fields_set & {"original_url", "expires_at"}
    if not fields_to_update:
        raise HTTPException(status_code=422, detail="No updatable fields provided")

    normalized_url: Optional[str] = None
    if "original_url" in fields_to_update:
        if body.original_url is None:
            raise HTTPException(status_code=422, detail="original_url cannot be null")
        try:
            normalized_url = validate_and_normalize(body.original_url)
        except InvalidURLError as e:
            raise HTTPException(status_code=422, detail=str(e))

    normalized_expires: Optional[datetime] = None
    if "expires_at" in fields_to_update:
        normalized_expires = body.expires_at.replace(tzinfo=None) if body.expires_at else None

    link = link_repository.apply_patch(
        db,
        link,
        fields=fields_to_update,
        original_url=normalized_url,
        expires_at=normalized_expires,
        now=now,
    )

    cfg = _config()
    new_state = derive_state(link, _now_utc())
    return _link_response(link, cfg["base_url"], new_state)


@router.delete("/qr/{token}")
def delete_link(
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Owner-only (ADR 0009): only the owner can take down their campaign;
    # non-owner -> 404.
    link = link_repository.get_link(db, token)
    authorize_owner(link, current_user)
    link_repository.mark_deleted(db, link, _now_utc())
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
