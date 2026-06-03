from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Scan


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


def scan_counts_for_tokens(db: Session, tokens: list[str]) -> dict[str, int]:
    """Total Scan count per token, for many tokens in a single aggregate query.

    Backs the owner dashboard (ADR 0009): one GROUP BY over the requested
    tokens, never one query per Link (no N+1). Tokens with no scans are absent
    from the map; callers default missing entries to 0.
    """
    if not tokens:
        return {}
    rows = (
        db.query(Scan.token, func.count(Scan.id))
        .filter(Scan.token.in_(tokens))
        .group_by(Scan.token)
        .all()
    )
    return {token: count for token, count in rows}
