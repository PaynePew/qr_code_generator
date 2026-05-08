import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Link
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


class CreateRequest(BaseModel):
    url: str


@router.post("/api/qr/create")
def create_qr(body: CreateRequest, db: Session = Depends(get_db)):
    try:
        normalized_url = validate_and_normalize(body.url)
    except InvalidURLError as e:
        raise HTTPException(status_code=422, detail=str(e))

    cfg = _config()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    def try_insert(token: str):
        with db.begin_nested():  # savepoint — collision rolls back only to here
            link = Link(token=token, original_url=normalized_url, created_at=now, updated_at=now)
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
    png_bytes = generate_qr_png(link.original_url)
    return Response(content=png_bytes, media_type="image/png")


@router.get("/r/{token}")
def redirect(token: str, db: Session = Depends(get_db)):
    link = db.query(Link).filter(Link.token == token).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Token not found")
    return RedirectResponse(url=link.original_url, status_code=302)
