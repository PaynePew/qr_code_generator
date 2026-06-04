from backend.rate_limiter.token_bucket import TokenBucket


def _bucket(capacity=10, refill_rate=1.0, tokens=None):
    return TokenBucket(
        capacity=capacity,
        refill_rate=refill_rate,
        tokens=tokens if tokens is not None else float(capacity),
    )


def test_fresh_bucket_allows_first_request():
    bucket = _bucket(capacity=5)
    allowed, new_bucket = bucket.step(now=0.0, cost=1)
    assert allowed is True
    assert new_bucket.tokens == 4.0


def test_exhausted_bucket_denies_without_time():
    bucket = _bucket(capacity=3, tokens=0.0)
    allowed, _ = bucket.step(now=0.0, cost=1)
    assert allowed is False


def test_refill_after_elapsed_time():
    # 1 token/s rate, 0 tokens, advance 2s → 2 tokens refilled → allows
    bucket = _bucket(capacity=10, refill_rate=1.0, tokens=0.0)
    _, bucket = bucket.step(now=0.0, cost=0)  # anchor last_refill=0
    allowed, new_bucket = bucket.step(now=2.0, cost=1)
    assert allowed is True
    assert abs(new_bucket.tokens - 1.0) < 1e-9


def test_refill_capped_at_capacity():
    # 1 token/s, capacity=5, 0 tokens, advance 100s → still only 5 tokens
    bucket = _bucket(capacity=5, refill_rate=1.0, tokens=0.0)
    _, bucket = bucket.step(now=0.0, cost=0)
    _, new_bucket = bucket.step(now=100.0, cost=0)
    assert new_bucket.tokens == 5.0


def test_zero_cost_step_is_always_allowed():
    bucket = _bucket(capacity=3, tokens=0.0)
    allowed, new_bucket = bucket.step(now=0.0, cost=0)
    assert allowed is True
    assert new_bucket.tokens == 0.0
