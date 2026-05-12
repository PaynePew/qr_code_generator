import time
from dataclasses import dataclass

from .token_bucket import TokenBucket


@dataclass(frozen=True)
class _Window:
    label: str
    period_seconds: int
    limit: int

    @property
    def refill_rate(self) -> float:
        return self.limit / self.period_seconds


@dataclass
class CheckResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int
    limit: int
    reset_seconds: int
    policy: str


class RateLimiter:
    def __init__(self, hourly_limit: int, daily_limit: int = 200, clock=None):
        self._hourly_limit = hourly_limit
        self._windows: list[_Window] = [
            _Window(label="hourly", period_seconds=3600, limit=hourly_limit),
            _Window(label="daily", period_seconds=86400, limit=daily_limit),
        ]
        self._ip_buckets: dict[str, list[TokenBucket]] = {}
        self._clock = clock or time.monotonic

    def _make_fresh_buckets(self, now: float) -> list[TokenBucket]:
        return [
            TokenBucket(
                capacity=float(w.limit),
                refill_rate=w.refill_rate,
                tokens=float(w.limit),
                last_refill=now,
            )
            for w in self._windows
        ]

    def check(self, ip: str) -> CheckResult:
        now = self._clock()
        buckets = self._ip_buckets.get(ip)
        if buckets is None:
            buckets = self._make_fresh_buckets(now)

        # Refill all buckets without consuming (cost=0)
        refilled = [b.step(now=now, cost=0)[1] for b in buckets]

        # Find first bucket that would deny
        deny_idx = next(
            (i for i, b in enumerate(refilled) if b.tokens < 1.0),
            None,
        )

        if deny_idx is None:
            # All allow — consume one token from each
            consumed = [b.step(now=now, cost=1)[1] for b in refilled]
            self._ip_buckets[ip] = consumed
            remaining = max(0, min(int(b.tokens) for b in consumed))
            hourly_rate = self._windows[0].refill_rate
            reset_seconds = int((1.0 / hourly_rate) + 0.5) if hourly_rate > 0 else 3600
            return CheckResult(
                allowed=True,
                remaining=remaining,
                retry_after_seconds=0,
                limit=self._hourly_limit,
                reset_seconds=reset_seconds,
                policy=self._policy(),
            )

        # Deny — store refilled state (no consumption), key Retry-After to triggering bucket
        self._ip_buckets[ip] = refilled
        triggering = self._windows[deny_idx]
        tokens_needed = 1.0 - refilled[deny_idx].tokens
        retry_after = (
            int(tokens_needed / triggering.refill_rate) + 1
            if triggering.refill_rate > 0
            else triggering.period_seconds
        )
        return CheckResult(
            allowed=False,
            remaining=0,
            retry_after_seconds=retry_after,
            limit=self._hourly_limit,
            reset_seconds=retry_after,
            policy=self._policy(),
        )

    def _policy(self) -> str:
        return ", ".join(f'"{w.limit};w={w.period_seconds}"' for w in self._windows)

    def reset(self):
        self._ip_buckets.clear()
