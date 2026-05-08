from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from models import Scan


def record_scan(
    db: Session,
    *,
    token: str,
    scanned_at: datetime,
    status_code: int,
    ip_address: Optional[str],
    user_agent: Optional[str],
) -> None:
    scan = Scan(
        token=token,
        scanned_at=scanned_at,
        status_code=status_code,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(scan)
    db.commit()


def scans_for_token(db: Session, token: str) -> list[Scan]:
    return db.query(Scan).filter(Scan.token == token).all()
