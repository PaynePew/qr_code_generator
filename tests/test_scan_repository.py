from datetime import datetime, timedelta

from backend import scan_repository
from backend.models import Scan


NOW = datetime(2026, 5, 8, 12, 0, 0)


class TestRecordScan:
    def test_inserts_row(self, db_session):
        scan_repository.record_scan(
            db_session,
            token="ABCDEFG",
            scanned_at=NOW,
            status_code=302,
            ip_address="1.2.3.4",
            user_agent="TestBot/1.0",
        )
        rows = db_session.query(Scan).filter(Scan.token == "ABCDEFG").all()
        assert len(rows) == 1
        row = rows[0]
        assert row.scanned_at == NOW
        assert row.status_code == 302
        assert row.ip_address == "1.2.3.4"
        assert row.user_agent == "TestBot/1.0"

    def test_persists_null_ip_and_user_agent(self, db_session):
        scan_repository.record_scan(
            db_session,
            token="HIJKLMN",
            scanned_at=NOW,
            status_code=410,
            ip_address=None,
            user_agent=None,
        )
        row = db_session.query(Scan).filter(Scan.token == "HIJKLMN").first()
        assert row.ip_address is None
        assert row.user_agent is None


class TestScansForToken:
    def test_returns_only_scans_with_matching_token(self, db_session):
        scan_repository.record_scan(
            db_session,
            token="MATCH00",
            scanned_at=NOW,
            status_code=302,
            ip_address=None,
            user_agent=None,
        )
        scan_repository.record_scan(
            db_session,
            token="MATCH00",
            scanned_at=NOW + timedelta(seconds=1),
            status_code=410,
            ip_address=None,
            user_agent=None,
        )
        scan_repository.record_scan(
            db_session,
            token="OTHER00",
            scanned_at=NOW,
            status_code=302,
            ip_address=None,
            user_agent=None,
        )
        scans = scan_repository.scans_for_token(db_session, "MATCH00")
        assert len(scans) == 2
        assert all(s.token == "MATCH00" for s in scans)

    def test_returns_empty_list_when_no_scans(self, db_session):
        assert scan_repository.scans_for_token(db_session, "NONESUCH") == []
