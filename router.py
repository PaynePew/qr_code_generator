import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Link, Scan
from token_generator import allocate_token, TokenCollisionError
from url_validator import validate_and_normalize, InvalidURLError
from qr_generator import generate_qr_png

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


def _get_status(link: Link) -> str:
    if link.deleted_at is not None:
        return "deleted"
    if link.expires_at is not None and link.expires_at <= _now_utc():
        return "expired"
    return "active"


def _link_response(link: Link, base_url: str) -> dict:
    return {
        "token": link.token,
        "original_url": link.original_url,
        "short_url": f"{base_url}/r/{link.token}",
        "qr_code_url": f"{base_url}/api/qr/{link.token}/image",
        "status": _get_status(link),
        "created_at": link.created_at.isoformat(),
        "updated_at": link.updated_at.isoformat(),
        "expires_at": link.expires_at.isoformat() if link.expires_at else None,
    }


def _log_scan(db: Session, token: str, status_code: int, request: Request):
    xff = request.headers.get("x-forwarded-for")
    if xff:
        ip = xff.split(",")[-1].strip()
    else:
        ip = request.client.host if request.client else None
    scan = Scan(
        token=token,
        scanned_at=_now_utc(),
        status_code=status_code,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(scan)
    db.commit()


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

    def try_insert(token: str):
        with db.begin_nested():  # savepoint — collision rolls back only to here
            link = Link(
                token=token,
                original_url=normalized_url,
                created_at=now,
                updated_at=now,
                expires_at=expires_at,
            )
            db.add(link)
            db.flush()

    try:
        token = allocate_token(normalized_url, cfg["secret"], try_insert)
        db.commit()
    except TokenCollisionError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Token generation failed")

    base_url = cfg["base_url"]
    return {
        "token": token,
        "short_url": f"{base_url}/r/{token}",
        "qr_code_url": f"{base_url}/api/qr/{token}/image",
        "original_url": normalized_url,
    }


@router.get("/api/qr/{token}/image")
def qr_image(token: str, db: Session = Depends(get_db)):
    link = db.query(Link).filter(Link.token == token).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Token not found")
    cfg = _config()
    short_url = f"{cfg['base_url']}/r/{token}"
    png_bytes = generate_qr_png(short_url)
    return Response(content=png_bytes, media_type="image/png")


@router.get("/r/{token}")
def redirect(token: str, request: Request, db: Session = Depends(get_db)):
    link = db.query(Link).filter(Link.token == token).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Token not found")

    status = _get_status(link)
    if status in ("deleted", "expired"):
        _log_scan(db, token, 410, request)
        raise HTTPException(status_code=410, detail="Link is gone")

    _log_scan(db, token, 302, request)
    return RedirectResponse(url=link.original_url, status_code=302)


@router.get("/api/qr/{token}")
def get_link_info(token: str, db: Session = Depends(get_db)):
    link = db.query(Link).filter(Link.token == token).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Token not found")

    cfg = _config()
    return _link_response(link, cfg["base_url"])


class PatchRequest(BaseModel):
    original_url: Optional[str] = None
    expires_at: Optional[datetime] = None


@router.patch("/api/qr/{token}")
def patch_link(token: str, body: PatchRequest, db: Session = Depends(get_db)):
    link = db.query(Link).filter(Link.token == token).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Token not found")

    if link.deleted_at is not None:
        raise HTTPException(status_code=410, detail="Link is deleted")

    fields_to_update = body.model_fields_set & {"original_url", "expires_at"}
    if not fields_to_update:
        raise HTTPException(status_code=422, detail="No updatable fields provided")

    if "original_url" in fields_to_update:
        try:
            link.original_url = validate_and_normalize(body.original_url)
        except InvalidURLError as e:
            raise HTTPException(status_code=422, detail=str(e))

    if "expires_at" in fields_to_update:
        link.expires_at = body.expires_at.replace(tzinfo=None) if body.expires_at else None

    link.updated_at = _now_utc()
    db.commit()
    db.refresh(link)

    cfg = _config()
    return _link_response(link, cfg["base_url"])


@router.delete("/api/qr/{token}")
def delete_link(token: str, db: Session = Depends(get_db)):
    link = db.query(Link).filter(Link.token == token).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Token not found")

    if link.deleted_at is None:
        link.deleted_at = _now_utc()
        db.commit()

    return {"token": token, "status": "deleted"}


@router.get("/api/qr/{token}/analytics")
def get_analytics(token: str, db: Session = Depends(get_db)):
    link = db.query(Link).filter(Link.token == token).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Token not found")

    all_scans = db.query(Scan).filter(Scan.token == token).all()

    day_data = defaultdict(lambda: {"count": 0, "status_codes": defaultdict(int)})
    for scan in all_scans:
        day = scan.scanned_at.date().isoformat()
        day_data[day]["count"] += 1
        day_data[day]["status_codes"][str(scan.status_code)] += 1

    scans_by_day = [
        {"date": day, "count": data["count"], "status_codes": dict(data["status_codes"])}
        for day, data in sorted(day_data.items())
    ]

    recent_scans = [
        {
            "scanned_at": scan.scanned_at.isoformat(),
            "status_code": scan.status_code,
            "ip_address": scan.ip_address,
            "user_agent": scan.user_agent,
        }
        for scan in sorted(all_scans, key=lambda s: s.scanned_at, reverse=True)[:50]
    ]

    return {
        "token": token,
        "total_scans": len(all_scans),
        "timezone": "UTC",
        "scans_by_day": scans_by_day,
        "recent_scans": recent_scans,
    }
