from datetime import datetime, timedelta

from backend.models import Scan


class TestScanLogging:
    def test_scan_logged_on_302_redirect(self, auth_client, db_session):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/scan302"}
        ).json()["token"]
        auth_client.get(f"/r/{token}", follow_redirects=False)
        scans = db_session.query(Scan).filter(Scan.token == token).all()
        assert len(scans) == 1
        assert scans[0].status_code == 302

    def test_scan_logged_on_410_for_deleted_link(self, auth_client, db_session):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/scan410del"}
        ).json()["token"]
        auth_client.delete(f"/api/qr/{token}")
        auth_client.get(f"/r/{token}", follow_redirects=False)
        scans = db_session.query(Scan).filter(Scan.token == token).all()
        assert len(scans) == 1
        assert scans[0].status_code == 410

    def test_scan_logged_on_410_for_expired_link(self, auth_client, db_session):
        token = auth_client.post(
            "/api/qr/create",
            json={
                "url": "https://example.com/scan410exp",
                "expires_at": "2000-01-01T00:00:00",
            },
        ).json()["token"]
        auth_client.get(f"/r/{token}", follow_redirects=False)
        scans = db_session.query(Scan).filter(Scan.token == token).all()
        assert len(scans) == 1
        assert scans[0].status_code == 410

    def test_scan_not_logged_for_404(self, client, db_session):
        client.get("/r/UNKNOWN1", follow_redirects=False)
        scans = db_session.query(Scan).filter(Scan.token == "UNKNOWN1").all()
        assert len(scans) == 0

    def test_scan_never_stores_raw_ip(self, auth_client, db_session, monkeypatch):
        """Raw IP must be derived-and-discarded, never persisted (ADR 0016)."""
        monkeypatch.setenv("TRUSTED_PROXIES", "1")
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/scanip"}
        ).json()["token"]
        auth_client.get(
            f"/r/{token}",
            follow_redirects=False,
            headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8, 9.10.11.12"},
        )
        scan = db_session.query(Scan).filter(Scan.token == token).first()
        assert not hasattr(scan, "ip_address"), "ip_address must not exist on Scan"

    def test_scan_never_stores_raw_user_agent(self, auth_client, db_session):
        """Raw user agent must be derived-and-discarded, never persisted (ADR 0016)."""
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/scanuа"}
        ).json()["token"]
        auth_client.get(
            f"/r/{token}",
            follow_redirects=False,
            headers={"User-Agent": "TestBot/1.0"},
        )
        scan = db_session.query(Scan).filter(Scan.token == token).first()
        assert not hasattr(scan, "user_agent"), "user_agent must not exist on Scan"

    def test_scan_records_device_class_from_user_agent(self, auth_client, db_session):
        """device_class is derived from User-Agent and stored coarsely (ADR 0016)."""
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/devclass"}
        ).json()["token"]
        auth_client.get(
            f"/r/{token}",
            follow_redirects=False,
            headers={"User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)"},
        )
        scan = db_session.query(Scan).filter(Scan.token == token).first()
        assert scan.device_class == "bot"

    def test_scan_write_uses_its_own_session_not_the_request_session(self, db_session):
        """bead uq9: the 302 scan write runs as a BackgroundTask AFTER FastAPI
        (>=0.106) closes the request's get_db session, so _record_scan_background
        takes only the request's *bind* and opens its OWN session — it never
        borrows (a possibly-closed) request session.
        """
        from backend.router import _record_scan_background

        # Hand the background task only the bind (as the redirect handler does) —
        # no live session. It must still persist the scan via its own session.
        _record_scan_background(
            db_session.get_bind(), "BGSESS1", 302, None, "Googlebot/2.1"
        )

        rows = db_session.query(Scan).filter(Scan.token == "BGSESS1").all()
        assert len(rows) == 1
        assert rows[0].status_code == 302
        assert rows[0].device_class == "bot"


class TestAnalyticsEndpoint:
    def test_analytics_returns_404_for_unknown_token(self, auth_client):
        # Owner-only now (ADR 0009): authenticated + unknown token -> 404.
        resp = auth_client.get("/api/qr/NOTEXIST/analytics")
        assert resp.status_code == 404

    def test_analytics_returns_200_for_active_link(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/ana1"}
        ).json()["token"]
        resp = auth_client.get(f"/api/qr/{token}/analytics")
        assert resp.status_code == 200

    def test_analytics_returns_200_for_deleted_link(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/anadel"}
        ).json()["token"]
        auth_client.delete(f"/api/qr/{token}")
        resp = auth_client.get(f"/api/qr/{token}/analytics")
        assert resp.status_code == 200

    def test_analytics_returns_200_for_expired_link(self, auth_client):
        token = auth_client.post(
            "/api/qr/create",
            json={
                "url": "https://example.com/anaexp",
                "expires_at": "2000-01-01T00:00:00",
            },
        ).json()["token"]
        resp = auth_client.get(f"/api/qr/{token}/analytics")
        assert resp.status_code == 200

    def test_analytics_response_shape(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/shape"}
        ).json()["token"]
        data = auth_client.get(f"/api/qr/{token}/analytics").json()
        assert data["token"] == token
        assert data["timezone"] == "UTC"
        assert "total_scans" in data
        assert "scans_by_day" in data
        assert "scans_by_country" in data
        assert "scans_by_subdivision" in data
        assert "scans_by_device_class" in data
        assert "recent_scans" in data

    def test_analytics_total_scans_zero_with_no_redirects(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/zero"}
        ).json()["token"]
        data = auth_client.get(f"/api/qr/{token}/analytics").json()
        assert data["total_scans"] == 0
        assert data["scans_by_day"] == []
        assert data["recent_scans"] == []

    def test_analytics_total_scans_counts_all_redirects(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/count"}
        ).json()["token"]
        auth_client.get(f"/r/{token}", follow_redirects=False)
        auth_client.get(f"/r/{token}", follow_redirects=False)
        data = auth_client.get(f"/api/qr/{token}/analytics").json()
        assert data["total_scans"] == 2

    def test_analytics_scans_by_day_has_correct_fields(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/dayfields"}
        ).json()["token"]
        auth_client.get(f"/r/{token}", follow_redirects=False)
        data = auth_client.get(f"/api/qr/{token}/analytics").json()
        assert len(data["scans_by_day"]) == 1
        day = data["scans_by_day"][0]
        assert "date" in day
        assert "count" in day
        assert "status_codes" in day

    def test_analytics_scans_by_day_status_code_breakdown(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/breakdown"}
        ).json()["token"]
        auth_client.get(f"/r/{token}", follow_redirects=False)  # 302
        auth_client.delete(f"/api/qr/{token}")
        auth_client.get(f"/r/{token}", follow_redirects=False)  # 410
        data = auth_client.get(f"/api/qr/{token}/analytics").json()
        day = data["scans_by_day"][0]
        assert day["count"] == 2
        assert day["status_codes"]["302"] == 1
        assert day["status_codes"]["410"] == 1

    def test_analytics_recent_scans_fields(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/recent"}
        ).json()["token"]
        auth_client.get(f"/r/{token}", follow_redirects=False)
        data = auth_client.get(f"/api/qr/{token}/analytics").json()
        scan = data["recent_scans"][0]
        assert "scanned_at" in scan
        assert "status_code" in scan
        assert "country" in scan
        assert "subdivision" in scan
        assert "device_class" in scan
        assert "ip_address" not in scan
        assert "user_agent" not in scan

    def test_analytics_recent_scans_ordered_desc(self, auth_client, db_session):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/orderdesc"}
        ).json()["token"]
        now = datetime(2026, 5, 8, 12, 0, 0)
        for i in range(3):
            db_session.add(
                Scan(
                    token=token,
                    scanned_at=now + timedelta(seconds=i),
                    status_code=302,
                    country=None,
                    subdivision=None,
                    device_class=None,
                )
            )
        db_session.commit()
        data = auth_client.get(f"/api/qr/{token}/analytics").json()
        timestamps = [s["scanned_at"] for s in data["recent_scans"]]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_analytics_recent_scans_capped_at_50(self, auth_client, db_session):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/cap50"}
        ).json()["token"]
        base = datetime(2026, 5, 8, 0, 0, 0)
        for i in range(60):
            db_session.add(
                Scan(
                    token=token,
                    scanned_at=base + timedelta(seconds=i),
                    status_code=302,
                    country=None,
                    subdivision=None,
                    device_class=None,
                )
            )
        db_session.commit()
        data = auth_client.get(f"/api/qr/{token}/analytics").json()
        assert len(data["recent_scans"]) == 50

    def test_analytics_scans_by_day_ascending_order(self, auth_client, db_session):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/dayasc"}
        ).json()["token"]
        db_session.add(
            Scan(
                token=token,
                scanned_at=datetime(2026, 5, 7, 10, 0, 0),
                status_code=302,
                country=None,
                subdivision=None,
                device_class=None,
            )
        )
        db_session.add(
            Scan(
                token=token,
                scanned_at=datetime(2026, 5, 9, 10, 0, 0),
                status_code=302,
                country=None,
                subdivision=None,
                device_class=None,
            )
        )
        db_session.add(
            Scan(
                token=token,
                scanned_at=datetime(2026, 5, 8, 10, 0, 0),
                status_code=302,
                country=None,
                subdivision=None,
                device_class=None,
            )
        )
        db_session.commit()
        data = auth_client.get(f"/api/qr/{token}/analytics").json()
        dates = [d["date"] for d in data["scans_by_day"]]
        assert dates == sorted(dates)
        assert dates == ["2026-05-07", "2026-05-08", "2026-05-09"]
