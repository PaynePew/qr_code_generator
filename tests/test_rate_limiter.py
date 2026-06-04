import logging

from backend.rate_limiter.limiter import RateLimiter


def _deny_all(limiter, ip, count, path="/api/qr/create"):
    """Exhaust the limiter for ip then log count denials."""
    results = []
    for _ in range(count):
        result = limiter.check(ip)
        if not result.allowed:
            limiter.log_denied(
                ip, result.deny_bucket, result.limit, result.retry_after_seconds, path
            )
        results.append(result)
    return results


# ── TTL pruning (AC 1 & 2) ──────────────────────────────────────────────────


def test_idle_entry_pruned_on_next_access_by_same_ip():
    """IP makes a request; clock advances past 2×max_window TTL; entry is pruned on next access."""
    clock = [0.0]
    limiter = RateLimiter(hourly_limit=5, daily_limit=10, clock=lambda: clock[0])

    result = limiter.check("1.1.1.1")
    assert result.allowed
    assert "1.1.1.1" in limiter._ip_entries

    # Advance past TTL (2 × 86400 = 172800 s)
    clock[0] = 172_801.0

    # Same IP returns: old entry is pruned, fresh buckets assigned
    result2 = limiter.check("1.1.1.1")
    assert result2.allowed
    # Fresh: hourly=5-1=4, daily=10-1=9 → remaining = min = 4
    assert result2.remaining == 4


def test_idle_entry_pruned_by_sweep_on_different_ip_access():
    """Idle IP's entry is pruned during the bounded sweep triggered by a different IP's request."""
    clock = [0.0]
    limiter = RateLimiter(hourly_limit=5, daily_limit=10, clock=lambda: clock[0])

    limiter.check("idle-ip")
    assert "idle-ip" in limiter._ip_entries

    # Advance clock past TTL
    clock[0] = 172_801.0

    # A different IP arrives, triggering the sweep that should prune idle-ip
    limiter.check("active-ip")

    assert "idle-ip" not in limiter._ip_entries


def test_entry_not_pruned_before_ttl():
    """An entry that is still within TTL must NOT be pruned."""
    clock = [0.0]
    limiter = RateLimiter(hourly_limit=5, daily_limit=10, clock=lambda: clock[0])

    limiter.check("young-ip")
    clock[0] = 172_799.0  # one second before expiry

    limiter.check("other-ip")  # trigger sweep

    assert "young-ip" in limiter._ip_entries


# ── Deny-log anti-spam cap (AC 3 & 4) ──────────────────────────────────────


def test_attack_100_denies_produce_10_warn_and_90_debug(caplog):
    """100 denials in the same second produce exactly 10 WARN + 90 DEBUG log lines."""
    clock = [0.0]
    limiter = RateLimiter(hourly_limit=1, daily_limit=1, clock=lambda: clock[0])

    # Exhaust the single allowed token
    limiter.check("attacker")

    with caplog.at_level(logging.DEBUG, logger="backend.rate_limiter.limiter"):
        for _ in range(100):
            result = limiter.check("attacker")
            assert not result.allowed
            limiter.log_denied(
                "attacker",
                result.deny_bucket,
                result.limit,
                result.retry_after_seconds,
                "/api/qr/create",
            )

    records = [r for r in caplog.records if r.name == "backend.rate_limiter.limiter"]
    warn_count = sum(1 for r in records if r.levelno == logging.WARNING)
    debug_count = sum(1 for r in records if r.levelno == logging.DEBUG)
    assert warn_count == 10
    assert debug_count == 90


def test_anti_spam_cap_is_per_ip_not_global(caplog):
    """Two IPs each get their own 10-WARN cap; 10 denials per IP = 20 WARN total."""
    clock = [0.0]
    limiter = RateLimiter(hourly_limit=1, daily_limit=1, clock=lambda: clock[0])

    limiter.check("ip-a")
    limiter.check("ip-b")

    with caplog.at_level(logging.DEBUG, logger="backend.rate_limiter.limiter"):
        for ip in ("ip-a", "ip-b"):
            for _ in range(10):
                result = limiter.check(ip)
                assert not result.allowed
                limiter.log_denied(
                    ip,
                    result.deny_bucket,
                    result.limit,
                    result.retry_after_seconds,
                    "/api/qr/create",
                )

    records = [r for r in caplog.records if r.name == "backend.rate_limiter.limiter"]
    warn_count = sum(1 for r in records if r.levelno == logging.WARNING)
    # 10 per IP × 2 IPs = 20
    assert warn_count == 20


def test_deny_log_format_includes_all_required_fields(caplog):
    """The deny log line contains ip, bucket, limit, retry_after, and path fields."""
    clock = [0.0]
    limiter = RateLimiter(hourly_limit=1, daily_limit=1, clock=lambda: clock[0])

    limiter.check("log-test-ip")  # exhaust

    with caplog.at_level(logging.WARNING, logger="backend.rate_limiter.limiter"):
        result = limiter.check("log-test-ip")
        assert not result.allowed
        limiter.log_denied(
            "log-test-ip",
            result.deny_bucket,
            result.limit,
            result.retry_after_seconds,
            "/api/qr/create",
        )

    assert caplog.records, "Expected at least one log record"
    msg = caplog.records[0].getMessage()
    assert "ip=log-test-ip" in msg
    assert "bucket=" in msg
    assert "limit=" in msg
    assert "retry_after=" in msg
    assert "path=/api/qr/create" in msg
