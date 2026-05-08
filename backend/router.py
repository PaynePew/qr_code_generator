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
from .database import SessionLocal
from .link_state import LinkState, derive_state
from .models import Link
from .token_generator import TokenCollisionError
from .url_validator import validate_and_normalize, InvalidURLError
from .qr_generator import generate_qr_png

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _config():
    return {
        "secret": os.environ["SECRET"],
        "base_url": os.environ["BASE_URL"].rstrip("/"),
    }


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _client_ip(request: Request) -> Optional[str]:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else None


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
    scan_repository.record_scan(
        db,
        token=token,
        scanned_at=_now_utc(),
        status_code=status_code,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


class CreateRequest(BaseModel):
    url: str
    expires_at: Optional[datetime] = None


@router.post("/api/qr/create")
def create_qr(body: CreateRequest, db: Session = Depends(get_db)):
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


@router.get("/api/qr/{token}/image")
def qr_image(token: str, db: Session = Depends(get_db)):
    link_repository.get_or_404(db, token)
    cfg = _config()
    short_url = f"{cfg['base_url']}/r/{token}"
    png_bytes = generate_qr_png(short_url)
    return Response(content=png_bytes, media_type="image/png")


@router.get("/r/{token}")
def redirect(token: str, request: Request, db: Session = Depends(get_db)):
    link = link_repository.get_or_404(db, token)

    state = derive_state(link, _now_utc())
    if not state.is_redirectable:
        _log_scan(db, token, 410, request)
        raise HTTPException(status_code=410, detail="Link is gone")

    _log_scan(db, token, 302, request)
    return RedirectResponse(url=link.original_url, status_code=302)


@router.get("/api/qr/{token}")
def get_link_info(token: str, db: Session = Depends(get_db)):
    link = link_repository.get_or_404(db, token)
    cfg = _config()
    state = derive_state(link, _now_utc())
    return _link_response(link, cfg["base_url"], state)


class PatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    original_url: Optional[str] = Field(default=None, min_length=1)
    expires_at: Optional[datetime] = None


@router.patch("/api/qr/{token}")
def patch_link(token: str, body: PatchRequest, db: Session = Depends(get_db)):
    link = link_repository.get_or_404(db, token)

    now = _now_utc()
    if not derive_state(link, now).is_patchable:
        raise HTTPException(status_code=410, detail="Link is deleted")

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


@router.delete("/api/qr/{token}")
def delete_link(token: str, db: Session = Depends(get_db)):
    link = link_repository.get_or_404(db, token)
    link_repository.mark_deleted(db, link, _now_utc())
    return {"token": token, "status": "deleted"}


@router.get("/api/qr/{token}/analytics")
def get_analytics(token: str, db: Session = Depends(get_db)):
    link_repository.get_or_404(db, token)
    scans = scan_repository.scans_for_token(db, token)
    return {
        "token": token,
        "timezone": "UTC",
        **analytics.aggregate_scans(scans),
    }
