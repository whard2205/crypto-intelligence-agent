from __future__ import annotations
import asyncio
import time


class TokenBucketRateLimiter:
    """Async token-bucket rate limiter skeleton. One instance per API client."""

    def __init__(self, rate: float, capacity: float) -> None:
        self._rate = rate          # tokens per second
        self._capacity = capacity  # max burst
        self._tokens = capacity
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        async with self._lock:
            self._refill()
            if self._tokens < tokens:
                wait = (tokens - self._tokens) / self._rate
                await asyncio.sleep(wait)
                self._refill()
            self._tokens -= tokens

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now
