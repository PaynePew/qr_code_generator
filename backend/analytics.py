from collections import defaultdict

from .models import Scan

DEFAULT_RECENT_LIMIT = 50


def aggregate_scans(
    scans: list[Scan], *, recent_limit: int = DEFAULT_RECENT_LIMIT
) -> dict:
    return {
        "total_scans": len(scans),
        "scans_by_day": _scans_by_day(scans),
        "recent_scans": _recent_scans(scans, recent_limit),
    }


def _scans_by_day(scans: list[Scan]) -> list[dict]:
    day_data: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "status_codes": defaultdict(int)}
    )
    for scan in scans:
        day = scan.scanned_at.date().isoformat()
        day_data[day]["count"] += 1
        day_data[day]["status_codes"][str(scan.status_code)] += 1
    return [
        {
            "date": day,
            "count": data["count"],
            "status_codes": dict(data["status_codes"]),
        }
        for day, data in sorted(day_data.items())
    ]


def _recent_scans(scans: list[Scan], limit: int) -> list[dict]:
    return [
        {
            "scanned_at": scan.scanned_at.isoformat(),
            "status_code": scan.status_code,
            "ip_address": scan.ip_address,
            "user_agent": scan.user_agent,
        }
        for scan in sorted(scans, key=lambda s: s.scanned_at, reverse=True)[:limit]
    ]
