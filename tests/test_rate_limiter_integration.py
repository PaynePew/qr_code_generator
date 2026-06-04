import itertools
import logging

import pytest
from fastapi.testclient import TestClient

from backend import session as session_module
from backend.main import _maybe_warn_multi_worker, app
from backend.router import get_db
from tests.conftest import make_user

_counter = itertools.count(1)


def _login_as(client, user):
    """Authenticate the client via a real signed session cookie (ADR 0009).

    The create cap is now keyed by user, and the middleware reads the *cookie's*
    uid — so a real cookie, not a get_current_user override, is what drives
    per-user keying. The dual-window create tests here send a fixed IP but rely
    on this single logged-in user to hit the per-user cap.
    """
    config = session_module.SessionConfig()
    client.cookies.set(
        session_module.COOKIE_NAME, session_module.issue_session(user.id, config)
    )


def _create(client, *, ip="1.2.3.4"):
    # Send "ip, testproxy" so that with TRUSTED_PROXIES=1 the IP resolves to
    # `ip` (entries[-2]); the create cap keys by user, so the IP is incidental
    # here and only matters for the per-IP auth-endpoint tests.
    return client.post(
        "/api/qr/create",
        json={"url": f"https://example.com/p{next(_counter)}"},
        headers={"x-forwarded-for": f"{ip}, testproxy"},
    )


@pytest.fixture
def rate_limiter_enabled(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_HOURLY", "3")
    monkeypatch.setenv("TRUSTED_PROXIES", "1")
    # Cookie must be storable over the HTTP TestClient for per-user keying.
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")


@pytest.fixture
def rl_client(db_session, rate_limiter_enabled):
    from backend.rate_limiter.middleware import RateLimitMiddleware

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    RateLimitMiddleware.reset_for_tests()
    user = make_user(db_session)
    with TestClient(app, raise_server_exceptions=True) as c:
        _login_as(c, user)
        yield c
    app.dependency_overrides.clear()


def test_successful_response_includes_ratelimit_headers(rl_client):
    resp = _create(rl_client)
    assert resp.status_code == 200
    assert "ratelimit-limit" in resp.headers
    assert "ratelimit-remaining" in resp.headers
    assert "ratelimit-reset" in resp.headers
    assert "ratelimit-policy" in resp.headers


def test_nth_plus_one_request_returns_429(rl_client):
    for _ in range(3):
        assert _create(rl_client).status_code == 200
    r = _create(rl_client)
    assert r.status_code == 429
    body = r.json()
    # ADR 0012: unified error envelope; code is stable RATE_LIMITED.
    assert body["error"]["code"] == "RATE_LIMITED"
    assert body["error"]["message"] == "Rate limit exceeded"
    assert "retry-after" in r.headers
    assert "ratelimit-limit" in r.headers
    assert "ratelimit-remaining" in r.headers


def test_capped_user_stays_capped_across_ips(rl_client):
    """The create cap follows the user, not the IP: changing IP does not reset it.

    (Per-IP independence now lives on the auth endpoint — see
    test_rate_limiter_per_user.test_auth_cap_two_ips_are_independent.)
    """
    for _ in range(3):
        _create(rl_client, ip="10.0.0.1")
    assert _create(rl_client, ip="10.0.0.1").status_code == 429
    # Same logged-in user, different IP — still capped.
    assert _create(rl_client, ip="10.0.0.2").status_code == 429


def test_clock_advance_unlocks_one_more_request(db_session, monkeypatch):
    import backend.rate_limiter.middleware as mw_module
    from backend.rate_limiter.limiter import RateLimiter
    from backend.rate_limiter.middleware import RateLimitMiddleware

    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_HOURLY", "3")
    monkeypatch.setenv("TRUSTED_PROXIES", "1")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    RateLimitMiddleware.reset_for_tests()

    clock_time = [0.0]
    monkeypatch.setattr(
        mw_module,
        "_create_limiter",
        RateLimiter(hourly_limit=3, clock=lambda: clock_time[0]),
    )
    user = make_user(db_session)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        _login_as(c, user)
        for _ in range(3):
            assert _create(c).status_code == 200
        assert _create(c).status_code == 429
        clock_time[0] = 1201.0  # one full token refills at 3600/3 = 1200s
        assert _create(c).status_code == 200
    app.dependency_overrides.clear()


def test_kill_switch_passthrough_leaves_no_headers(db_session, monkeypatch):
    from backend.rate_limiter.middleware import RateLimitMiddleware

    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    RateLimitMiddleware.reset_for_tests()
    user = make_user(db_session)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        _login_as(c, user)
        resp = _create(c)
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert "ratelimit-limit" not in resp.headers
    assert "ratelimit-remaining" not in resp.headers


def test_fail_open_when_limiter_raises(db_session, monkeypatch):
    import backend.rate_limiter.middleware as mw_module
    from backend.rate_limiter.middleware import RateLimitMiddleware

    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_HOURLY", "30")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    RateLimitMiddleware.reset_for_tests()

    class BrokenLimiter:
        def check(self, key):
            raise RuntimeError("limiter exploded")

    monkeypatch.setattr(mw_module, "_create_limiter", BrokenLimiter())
    user = make_user(db_session)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        _login_as(c, user)
        resp = _create(c)
    app.dependency_overrides.clear()

    assert resp.status_code == 200


# ──────────────────────────────────────────────
# Slice 2: dual-window fairness tests
# ──────────────────────────────────────────────


def _dual_window_client(db_session, monkeypatch, *, hourly, daily, clock_list):
    """Build a TestClient logged in as one user, with the *create* limiter's two
    windows injected on a controllable clock — the create cap is per-user now,
    so these fairness assertions run against a single authenticated account.
    """
    import backend.rate_limiter.middleware as mw_module
    from backend.rate_limiter.limiter import RateLimiter
    from backend.rate_limiter.middleware import RateLimitMiddleware

    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_HOURLY", str(hourly))
    monkeypatch.setenv("RATE_LIMIT_DAILY", str(daily))
    monkeypatch.setenv("TRUSTED_PROXIES", "1")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    RateLimitMiddleware.reset_for_tests()

    limiter = RateLimiter(
        hourly_limit=hourly, daily_limit=daily, clock=lambda: clock_list[0]
    )
    monkeypatch.setattr(mw_module, "_create_limiter", limiter)

    user = make_user(db_session)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app, raise_server_exceptions=True)
    _login_as(client, user)
    return client


def test_hourly_exhausted_daily_has_slack_reports_hourly_retry_after(
    db_session, monkeypatch
):
    clock = [0.0]
    c = _dual_window_client(
        db_session, monkeypatch, hourly=3, daily=10, clock_list=clock
    )
    with c:
        for _ in range(3):
            assert _create(c).status_code == 200
        r = _create(c)
    app.dependency_overrides.clear()

    assert r.status_code == 429
    # hourly retry_after ≈ 1201s; daily would be >> 10 000s — confirm hourly bucket triggered
    assert int(r.headers["retry-after"]) < 2000


def test_daily_exhausted_hourly_has_slack_reports_daily_retry_after(
    db_session, monkeypatch
):
    clock = [0.0]
    c = _dual_window_client(
        db_session, monkeypatch, hourly=3, daily=4, clock_list=clock
    )
    with c:
        # exhaust hourly at t=0; daily still has 1 token
        for _ in range(3):
            assert _create(c).status_code == 200
        # advance clock: hourly fully refills, daily barely refills (~1.17 tokens)
        clock[0] = 3700.0
        assert _create(c).status_code == 200  # daily→0.17, hourly→2
        # daily < 1, hourly >= 1 → daily is the triggering bucket
        r = _create(c)
    app.dependency_overrides.clear()

    assert r.status_code == 429
    # daily retry_after >> hourly scale (~1200s)
    assert int(r.headers["retry-after"]) > 5000


def test_clock_advances_past_hourly_daily_still_exhausted_returns_daily_retry_after(
    db_session, monkeypatch
):
    clock = [0.0]
    # Equal limits are valid (daily >= hourly is satisfied)
    c = _dual_window_client(
        db_session, monkeypatch, hourly=3, daily=3, clock_list=clock
    )
    with c:
        for _ in range(3):
            assert _create(c).status_code == 200
        # first deny is hourly-triggered (both exhausted, hourly is first in list)
        assert _create(c).status_code == 429
        # advance past hourly refill: hourly ≈ 1 token, daily still tiny (<<1)
        clock[0] = 1201.0
        r = _create(c)
    app.dependency_overrides.clear()

    assert r.status_code == 429
    # daily triggers now (hourly allows); retry_after is daily-scale >> hourly scale
    assert int(r.headers["retry-after"]) > 5000


def test_ratelimit_remaining_reports_min_across_buckets(db_session, monkeypatch):
    clock = [0.0]
    c = _dual_window_client(
        db_session, monkeypatch, hourly=3, daily=5, clock_list=clock
    )
    with c:
        _create(c)  # after: hourly=2, daily=4  → min=2
        resp = _create(c)  # after: hourly=1, daily=3  → min=1
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.headers["ratelimit-remaining"] == "1"


def test_startup_validation_daily_less_than_hourly_aborts(monkeypatch):
    from backend.main import _validate_rate_limit_env

    monkeypatch.setenv("RATE_LIMIT_HOURLY", "30")
    monkeypatch.setenv("RATE_LIMIT_DAILY", "10")
    with pytest.raises(RuntimeError, match="RATE_LIMIT_DAILY"):
        _validate_rate_limit_env()


def test_startup_validation_auth_daily_less_than_hourly_aborts(monkeypatch):
    """The relocated per-IP auth limiter shares the create limiter's env-validation contract."""
    from backend.main import _validate_rate_limit_env

    monkeypatch.setenv("AUTH_RATE_LIMIT_HOURLY", "10")
    monkeypatch.setenv("AUTH_RATE_LIMIT_DAILY", "4")
    with pytest.raises(RuntimeError, match="AUTH_RATE_LIMIT_DAILY"):
        _validate_rate_limit_env()


def test_startup_validation_auth_non_integer_aborts(monkeypatch):
    from backend.main import _validate_rate_limit_env

    monkeypatch.setenv("AUTH_RATE_LIMIT_HOURLY", "lots")
    with pytest.raises(RuntimeError, match="AUTH_RATE_LIMIT_HOURLY"):
        _validate_rate_limit_env()


def test_startup_validation_trusted_proxies_negative_aborts(monkeypatch):
    from backend.main import _validate_trusted_proxies_env

    monkeypatch.setenv("TRUSTED_PROXIES", "-1")
    with pytest.raises(RuntimeError, match="TRUSTED_PROXIES"):
        _validate_trusted_proxies_env()


def test_startup_validation_trusted_proxies_non_integer_aborts(monkeypatch):
    from backend.main import _validate_trusted_proxies_env

    monkeypatch.setenv("TRUSTED_PROXIES", "two")
    with pytest.raises(RuntimeError, match="TRUSTED_PROXIES"):
        _validate_trusted_proxies_env()


def test_startup_validation_trusted_proxies_zero_is_valid(monkeypatch):
    from backend.main import _validate_trusted_proxies_env

    monkeypatch.setenv("TRUSTED_PROXIES", "0")
    _validate_trusted_proxies_env()  # must not raise


# ── Multi-worker startup warning (AC 5) ─────────────────────────────────────


def test_multi_worker_startup_warning_emitted_when_web_concurrency_gt_1(
    monkeypatch, caplog
):
    """WARNING is emitted at startup when WEB_CONCURRENCY > 1."""
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    monkeypatch.delenv("UVICORN_WORKERS", raising=False)

    with caplog.at_level(logging.WARNING):
        _maybe_warn_multi_worker()

    warning_msgs = [
        r.getMessage() for r in caplog.records if r.levelno == logging.WARNING
    ]
    assert any("worker" in m.lower() for m in warning_msgs)


def test_multi_worker_startup_warning_emitted_when_uvicorn_workers_gt_1(
    monkeypatch, caplog
):
    """WARNING is emitted at startup when UVICORN_WORKERS > 1."""
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    monkeypatch.setenv("UVICORN_WORKERS", "2")

    with caplog.at_level(logging.WARNING):
        _maybe_warn_multi_worker()

    warning_msgs = [
        r.getMessage() for r in caplog.records if r.levelno == logging.WARNING
    ]
    assert any("worker" in m.lower() for m in warning_msgs)


def test_no_multi_worker_warning_for_single_worker(monkeypatch, caplog):
    """No WARNING is emitted when no multi-worker env var is set."""
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    monkeypatch.delenv("UVICORN_WORKERS", raising=False)

    with caplog.at_level(logging.WARNING):
        _maybe_warn_multi_worker()

    worker_warnings = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "worker" in r.getMessage().lower()
    ]
    assert len(worker_warnings) == 0
