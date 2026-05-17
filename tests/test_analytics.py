from datetime import datetime, timedelta

import pytest

from backend.models import Scan


class TestScanLogging:
    def test_scan_logged_on_302_redirect(self, client, db_session):
        token = client.post("/api/qr/create", json={"url": "https://example.com/scan302"}).json()["token"]
        client.get(f"/r/{token}", follow_redirects=False)
        scans = db_session.query(Scan).filter(Scan.token == token).all()
        assert len(scans) == 1
        assert scans[0].status_code == 302

    def test_scan_logged_on_410_for_deleted_link(self, client, db_session):
        token = client.post("/api/qr/create", json={"url": "https://example.com/scan410del"}).json()["token"]
        client.delete(f"/api/qr/{token}")
        client.get(f"/r/{token}", follow_redirects=False)
        scans = db_session.query(Scan).filter(Scan.token == token).all()
        assert len(scans) == 1
        assert scans[0].status_code == 410

    def test_scan_logged_on_410_for_expired_link(self, client, db_session):
        token = client.post(
            "/api/qr/create",
            json={"url": "https://example.com/scan410exp", "expires_at": "2000-01-01T00:00:00"},
        ).json()["token"]
        client.get(f"/r/{token}", follow_redirects=False)
        scans = db_session.query(Scan).filter(Scan.token == token).all()
        assert len(scans) == 1
        assert scans[0].status_code == 410

    def test_scan_not_logged_for_404(self, client, db_session):
        client.get("/r/UNKNOWN1", follow_redirects=False)
        scans = db_session.query(Scan).filter(Scan.token == "UNKNOWN1").all()
        assert len(scans) == 0

    def test_scan_ip_uses_extract_client_ip(self, client, db_session, monkeypatch):
        # With TRUSTED_PROXIES=1 the scan should record the entry one before the
        # last (trusted) XFF entry, not the rightmost entry (which is the proxy).
        monkeypatch.setenv("TRUSTED_PROXIES", "1")
        token = client.post("/api/qr/create", json={"url": "https://example.com/scanip"}).json()["token"]
        client.get(
            f"/r/{token}",
            follow_redirects=False,
            headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8, 9.10.11.12"},
        )
        scan = db_session.query(Scan).filter(Scan.token == token).first()
        assert scan.ip_address == "5.6.7.8"

    def test_scan_user_agent_captured(self, client, db_session):
        token = client.post("/api/qr/create", json={"url": "https://example.com/scanuа"}).json()["token"]
        client.get(
            f"/r/{token}",
            follow_redirects=False,
            headers={"User-Agent": "TestBot/1.0"},
        )
        scan = db_session.query(Scan).filter(Scan.token == token).first()
        assert scan.user_agent == "TestBot/1.0"


class TestAnalyticsEndpoint:
    def test_analytics_returns_404_for_unknown_token(self, client):
        resp = client.get("/api/qr/NOTEXIST/analytics")
        assert resp.status_code == 404

    def test_analytics_returns_200_for_active_link(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/ana1"}).json()["token"]
        resp = client.get(f"/api/qr/{token}/analytics")
        assert resp.status_code == 200

    def test_analytics_returns_200_for_deleted_link(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/anadel"}).json()["token"]
        client.delete(f"/api/qr/{token}")
        resp = client.get(f"/api/qr/{token}/analytics")
        assert resp.status_code == 200

    def test_analytics_returns_200_for_expired_link(self, client):
        token = client.post(
            "/api/qr/create",
            json={"url": "https://example.com/anaexp", "expires_at": "2000-01-01T00:00:00"},
        ).json()["token"]
        resp = client.get(f"/api/qr/{token}/analytics")
        assert resp.status_code == 200

    def test_analytics_response_shape(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/shape"}).json()["token"]
        data = client.get(f"/api/qr/{token}/analytics").json()
        assert data["token"] == token
        assert data["timezone"] == "UTC"
        assert "total_scans" in data
        assert "scans_by_day" in data
        assert "recent_scans" in data

    def test_analytics_total_scans_zero_with_no_redirects(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/zero"}).json()["token"]
        data = client.get(f"/api/qr/{token}/analytics").json()
        assert data["total_scans"] == 0
        assert data["scans_by_day"] == []
        assert data["recent_scans"] == []

    def test_analytics_total_scans_counts_all_redirects(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/count"}).json()["token"]
        client.get(f"/r/{token}", follow_redirects=False)
        client.get(f"/r/{token}", follow_redirects=False)
        data = client.get(f"/api/qr/{token}/analytics").json()
        assert data["total_scans"] == 2

    def test_analytics_scans_by_day_has_correct_fields(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/dayfields"}).json()["token"]
        client.get(f"/r/{token}", follow_redirects=False)
        data = client.get(f"/api/qr/{token}/analytics").json()
        assert len(data["scans_by_day"]) == 1
        day = data["scans_by_day"][0]
        assert "date" in day
        assert "count" in day
        assert "status_codes" in day

    def test_analytics_scans_by_day_status_code_breakdown(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/breakdown"}).json()["token"]
        client.get(f"/r/{token}", follow_redirects=False)  # 302
        client.delete(f"/api/qr/{token}")
        client.get(f"/r/{token}", follow_redirects=False)  # 410
        data = client.get(f"/api/qr/{token}/analytics").json()
        day = data["scans_by_day"][0]
        assert day["count"] == 2
        assert day["status_codes"]["302"] == 1
        assert day["status_codes"]["410"] == 1

    def test_analytics_recent_scans_fields(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/recent"}).json()["token"]
        client.get(f"/r/{token}", follow_redirects=False)
        data = client.get(f"/api/qr/{token}/analytics").json()
        scan = data["recent_scans"][0]
        assert "scanned_at" in scan
        assert "status_code" in scan
        assert "ip_address" in scan
        assert "user_agent" in scan

    def test_analytics_recent_scans_ordered_desc(self, client, db_session):
        token = client.post("/api/qr/create", json={"url": "https://example.com/orderdesc"}).json()["token"]
        now = datetime(2026, 5, 8, 12, 0, 0)
        for i in range(3):
            db_session.add(Scan(
                token=token,
                scanned_at=now + timedelta(seconds=i),
                status_code=302,
                ip_address=None,
                user_agent=None,
            ))
        db_session.commit()
        data = client.get(f"/api/qr/{token}/analytics").json()
        timestamps = [s["scanned_at"] for s in data["recent_scans"]]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_analytics_recent_scans_capped_at_50(self, client, db_session):
        token = client.post("/api/qr/create", json={"url": "https://example.com/cap50"}).json()["token"]
        base = datetime(2026, 5, 8, 0, 0, 0)
        for i in range(60):
            db_session.add(Scan(
                token=token,
                scanned_at=base + timedelta(seconds=i),
                status_code=302,
                ip_address=None,
                user_agent=None,
            ))
        db_session.commit()
        data = client.get(f"/api/qr/{token}/analytics").json()
        assert len(data["recent_scans"]) == 50

    def test_analytics_scans_by_day_ascending_order(self, client, db_session):
        token = client.post("/api/qr/create", json={"url": "https://example.com/dayasc"}).json()["token"]
        db_session.add(Scan(
            token=token,
            scanned_at=datetime(2026, 5, 7, 10, 0, 0),
            status_code=302,
            ip_address=None,
            user_agent=None,
        ))
        db_session.add(Scan(
            token=token,
            scanned_at=datetime(2026, 5, 9, 10, 0, 0),
            status_code=302,
            ip_address=None,
            user_agent=None,
        ))
        db_session.add(Scan(
            token=token,
            scanned_at=datetime(2026, 5, 8, 10, 0, 0),
            status_code=302,
            ip_address=None,
            user_agent=None,
        ))
        db_session.commit()
        data = client.get(f"/api/qr/{token}/analytics").json()
        dates = [d["date"] for d in data["scans_by_day"]]
        assert dates == sorted(dates)
        assert dates == ["2026-05-07", "2026-05-08", "2026-05-09"]
