"""Scan-count aggregation for the owner dashboard (ADR 0009, Phase 1).

The dashboard shows a total scan count per Link. Counting must happen in a
single aggregate query for many tokens at once — never one query per Link
(N+1) — so this exercises ``scan_repository.scan_counts_for_tokens``.

Behavioral contract:
- counts are keyed by token and equal the number of Scan rows for that token;
- a token with no scans is absent from the map (callers default to 0);
- an empty token list yields an empty map without touching the database;
- counts are scoped to the requested tokens only (no cross-token bleed).
"""

from datetime import datetime, timedelta

from backend import scan_repository

NOW = datetime(2026, 6, 3, 12, 0, 0)


def _scan(db_session, token: str, *, offset_seconds: int = 0, status_code: int = 302):
    scan_repository.record_scan(
        db_session,
        token=token,
        scanned_at=NOW + timedelta(seconds=offset_seconds),
        status_code=status_code,
        ip_address=None,
        user_agent=None,
    )


class TestScanCountsForTokens:
    def test_counts_scans_per_token(self, db_session):
        _scan(db_session, "TOKAAA", offset_seconds=0)
        _scan(db_session, "TOKAAA", offset_seconds=1)
        _scan(db_session, "TOKAAA", offset_seconds=2)
        _scan(db_session, "TOKBBB", offset_seconds=0)

        counts = scan_repository.scan_counts_for_tokens(
            db_session, ["TOKAAA", "TOKBBB"]
        )

        assert counts["TOKAAA"] == 3
        assert counts["TOKBBB"] == 1

    def test_counts_both_redirect_and_gone_scans(self, db_session):
        # ADR/CONTEXT: a Scan is logged for both 302 and 410 outcomes; the
        # dashboard total counts every Scan, not only successful redirects.
        _scan(db_session, "MIXED00", status_code=302)
        _scan(db_session, "MIXED00", offset_seconds=1, status_code=410)

        counts = scan_repository.scan_counts_for_tokens(db_session, ["MIXED00"])

        assert counts["MIXED00"] == 2

    def test_token_with_no_scans_is_absent(self, db_session):
        _scan(db_session, "HASONE0")

        counts = scan_repository.scan_counts_for_tokens(
            db_session, ["HASONE0", "NOSCANS"]
        )

        assert counts["HASONE0"] == 1
        assert "NOSCANS" not in counts

    def test_empty_token_list_returns_empty_map(self, db_session):
        assert scan_repository.scan_counts_for_tokens(db_session, []) == {}

    def test_only_requested_tokens_are_counted(self, db_session):
        _scan(db_session, "WANTED0")
        _scan(db_session, "IGNORED")

        counts = scan_repository.scan_counts_for_tokens(db_session, ["WANTED0"])

        assert counts == {"WANTED0": 1}
