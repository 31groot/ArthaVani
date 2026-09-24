"""Minimal in-memory rate limiting / lockout for auth endpoints.

This is intentionally dependency-free so it works without adding a Redis
or slowapi dependency. It tracks failed attempts per (client IP, email)
pair in-process and temporarily locks the pair out after too many
failures within a rolling window.

Caveats (documented rather than hidden): this is per-process state, so it
resets on restart and does not share state across multiple API workers or
replicas. For a multi-worker/multi-instance deployment, back this with a
shared store (e.g. Redis) keyed the same way.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock

from fastapi import HTTPException, Request, status

# Tunable limits.
MAX_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60
LOCKOUT_SECONDS = 15 * 60


@dataclass
class _Bucket:
    failures: list[float] = field(default_factory=list)
    locked_until: float = 0.0


class RateLimiter:
    """Tracks failed attempts per key (e.g. "ip:email") and locks out."""

    def __init__(
        self,
        max_attempts: int = MAX_ATTEMPTS,
        window_seconds: float = WINDOW_SECONDS,
        lockout_seconds: float = LOCKOUT_SECONDS,
    ) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._lockout_seconds = lockout_seconds
        self._buckets: dict[str, _Bucket] = defaultdict(_Bucket)
        self._lock = Lock()

    def check(self, key: str) -> None:
        """Raise HTTP 429 if `key` is currently locked out."""
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets[key]
            if bucket.locked_until > now:
                retry_after = int(bucket.locked_until - now) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many attempts. Please try again later.",
                    headers={"Retry-After": str(retry_after)},
                )

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets[key]
            bucket.failures = [
                ts for ts in bucket.failures if now - ts < self._window_seconds
            ]
            bucket.failures.append(now)
            if len(bucket.failures) >= self._max_attempts:
                bucket.locked_until = now + self._lockout_seconds
                bucket.failures = []

    def record_success(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)


# Shared limiters for the login and register endpoints.
login_limiter = RateLimiter()
register_limiter = RateLimiter(max_attempts=10, window_seconds=60 * 60, lockout_seconds=60 * 60)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"
