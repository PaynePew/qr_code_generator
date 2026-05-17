import logging
import time
from dataclasses import dataclass

from .token_bucket import TokenBucket

logger = logging.getLogger(__name__)

_SWEEP_SIZE = 10
_LOG_CAP_PER_SECOND = 10


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
    deny_bucket: str = ""


@dataclass
class _IpEntry:
    buckets: list[TokenBucket]
    last_access: float
    deny_count: int = 0
    # Wall-second (int(clock())) when deny_count was last reset; -1 = never.
    deny_second: int = -1


class RateLimiter:
    def __init__(self, hourly_limit: int, daily_limit: int = 200, clock=None):
        self._hourly_limit = hourly_limit
        self._windows: list[_Window] = [
            _Window(label="hourly", period_seconds=3600, limit=hourly_limit),
            _Window(label="daily", period_seconds=86400, limit=daily_limit),
        ]
        self._ip_entries: dict[str, _IpEntry] = {}
        self._clock = clock or time.monotonic
        self._ttl: float = 2.0 * max(w.period_seconds for w in self._windows)

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

    def _prune_entry(self, ip: str, now: float) -> None:
        """Remove this IP's entry if it has been inactive longer than TTL."""
        entry = self._ip_entries.get(ip)
        if entry is not None and (now - entry.last_access) > self._ttl:
            del self._ip_entries[ip]

    def _sweep(self, now: float) -> None:
        """Examine up to _SWEEP_SIZE entries and prune any that have expired."""
        expired = [
            ip
            for ip, entry in list(self._ip_entries.items())[:_SWEEP_SIZE]
            if (now - entry.last_access) > self._ttl
        ]
        for ip in expired:
            self._ip_entries.pop(ip, None)

    def _upsert(self, ip: str, buckets: list[TokenBucket], now: float) -> None:
        """Store buckets+last_access for ip, preserving any existing deny-log counters."""
        entry = self._ip_entries.get(ip)
        if entry is None:
            self._ip_entries[ip] = _IpEntry(buckets=buckets, last_access=now)
        else:
            entry.buckets = buckets
            entry.last_access = now

    def check(self, ip: str) -> CheckResult:
        now = self._clock()

        # Lazy prune: discard expired entry for this IP so it gets fresh buckets
        self._prune_entry(ip, now)

        # Bounded sweep: amortised cleanup of unreferenced expired entries
        self._sweep(now)

        entry = self._ip_entries.get(ip)
        buckets = entry.buckets if entry is not None else self._make_fresh_buckets(now)

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
            self._upsert(ip, consumed, now)
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
                deny_bucket="",
            )

        # Deny — store refilled state (no consumption), key Retry-After to triggering bucket
        triggering = self._windows[deny_idx]
        tokens_needed = 1.0 - refilled[deny_idx].tokens
        retry_after = (
            int(tokens_needed / triggering.refill_rate) + 1
            if triggering.refill_rate > 0
            else triggering.period_seconds
        )
        self._upsert(ip, refilled, now)
        return CheckResult(
            allowed=False,
            remaining=0,
            retry_after_seconds=retry_after,
            limit=self._hourly_limit,
            reset_seconds=retry_after,
            policy=self._policy(),
            deny_bucket=triggering.label,
        )

    def log_denied(self, ip: str, bucket: str, limit: int, retry_after: int, path: str) -> None:
        """Emit a structured deny log, capped at _LOG_CAP_PER_SECOND WARN per IP per second."""
        now = self._clock()
        current_second = int(now)

        entry = self._ip_entries.get(ip)
        if entry is not None:
            if entry.deny_second == current_second:
                entry.deny_count += 1
            else:
                entry.deny_count = 1
                entry.deny_second = current_second
            count = entry.deny_count
        else:
            count = 1

        msg = "rate_limiter.denied ip=%s bucket=%s limit=%d retry_after=%d path=%s"
        args = (ip, bucket, limit, retry_after, path)
        if count <= _LOG_CAP_PER_SECOND:
            logger.warning(msg, *args)
        else:
            logger.debug(msg, *args)

    def _policy(self) -> str:
        return ", ".join(f'"{w.limit};w={w.period_seconds}"' for w in self._windows)

    def reset(self):
        self._ip_entries.clear()
