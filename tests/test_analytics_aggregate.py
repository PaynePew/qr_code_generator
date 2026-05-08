from datetime import datetime, timedelta

from backend.analytics import aggregate_scans, DEFAULT_RECENT_LIMIT
from backend.models import Scan


def _scan(scanned_at: datetime, status_code: int = 302, ip="1.2.3.4", ua="UA/1.0") -> Scan:
    return Scan(
        token="ABCDEFG",
        scanned_at=scanned_at,
        status_code=status_code,
        ip_address=ip,
        user_agent=ua,
    )


class TestEmptyInput:
    def test_empty_list_yields_zero_totals(self):
        result = aggregate_scans([])
        assert result == {
            "total_scans": 0,
            "scans_by_day": [],
            "recent_scans": [],
        }


class TestTotalScans:
    def test_total_matches_input_length(self):
        scans = [_scan(datetime(2026, 5, 8, 10, 0, 0)) for _ in range(7)]
        assert aggregate_scans(scans)["total_scans"] == 7


class TestScansByDay:
    def test_single_day_single_scan(self):
        scans = [_scan(datetime(2026, 5, 8, 10, 0, 0))]
        result = aggregate_scans(scans)
        assert result["scans_by_day"] == [
            {"date": "2026-05-08", "count": 1, "status_codes": {"302": 1}}
        ]

    def test_status_code_subtotals(self):
        day = datetime(2026, 5, 8, 10, 0, 0)
        scans = [
            _scan(day, status_code=302),
            _scan(day + timedelta(seconds=1), status_code=302),
            _scan(day + timedelta(seconds=2), status_code=410),
        ]
        result = aggregate_scans(scans)
        bucket = result["scans_by_day"][0]
        assert bucket["count"] == 3
        assert bucket["status_codes"] == {"302": 2, "410": 1}

    def test_multiple_days_sorted_ascending(self):
        scans = [
            _scan(datetime(2026, 5, 9, 10, 0, 0)),
            _scan(datetime(2026, 5, 7, 10, 0, 0)),
            _scan(datetime(2026, 5, 8, 10, 0, 0)),
        ]
        dates = [d["date"] for d in aggregate_scans(scans)["scans_by_day"]]
        assert dates == ["2026-05-07", "2026-05-08", "2026-05-09"]

    def test_status_codes_is_plain_dict_not_defaultdict(self):
        # Defensive: we serialize to JSON, so leaking a defaultdict would change behavior.
        result = aggregate_scans([_scan(datetime(2026, 5, 8))])
        assert type(result["scans_by_day"][0]["status_codes"]) is dict


class TestRecentScans:
    def test_field_shape(self):
        scans = [_scan(datetime(2026, 5, 8, 10, 0, 0))]
        recent = aggregate_scans(scans)["recent_scans"]
        assert recent[0] == {
            "scanned_at": "2026-05-08T10:00:00",
            "status_code": 302,
            "ip_address": "1.2.3.4",
            "user_agent": "UA/1.0",
        }

    def test_sorted_descending_by_scanned_at(self):
        base = datetime(2026, 5, 8, 10, 0, 0)
        scans = [_scan(base + timedelta(seconds=i)) for i in range(5)]
        timestamps = [s["scanned_at"] for s in aggregate_scans(scans)["recent_scans"]]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_capped_at_default_limit(self):
        base = datetime(2026, 5, 8, 0, 0, 0)
        scans = [_scan(base + timedelta(seconds=i)) for i in range(DEFAULT_RECENT_LIMIT + 10)]
        result = aggregate_scans(scans)
        assert len(result["recent_scans"]) == DEFAULT_RECENT_LIMIT

    def test_custom_limit(self):
        base = datetime(2026, 5, 8, 0, 0, 0)
        scans = [_scan(base + timedelta(seconds=i)) for i in range(20)]
        result = aggregate_scans(scans, recent_limit=3)
        assert len(result["recent_scans"]) == 3

    def test_limit_zero_returns_empty(self):
        scans = [_scan(datetime(2026, 5, 8))]
        assert aggregate_scans(scans, recent_limit=0)["recent_scans"] == []

    def test_total_scans_unaffected_by_recent_limit(self):
        # total_scans counts ALL scans, not just the recent window.
        base = datetime(2026, 5, 8, 0, 0, 0)
        scans = [_scan(base + timedelta(seconds=i)) for i in range(75)]
        result = aggregate_scans(scans, recent_limit=10)
        assert result["total_scans"] == 75
        assert len(result["recent_scans"]) == 10
