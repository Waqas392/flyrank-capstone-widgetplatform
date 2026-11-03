"""In-memory token-bucket rate limiter (per key). Swap for Redis to scale past one process."""
from __future__ import annotations

import threading
import time
from typing import Callable


class TokenBucketLimiter:
    def __init__(self, capacity: float, refill_per_sec: float, clock: Callable[[], float] = time.monotonic):
        self.capacity = capacity
        self.refill = refill_per_sec
        self._clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_ts)
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, float]:
        """Returns (allowed, retry_after_seconds)."""
        now = self._clock()
        with self._lock:
            tokens, last = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.refill)
            if tokens >= 1:
                self._buckets[key] = (tokens - 1, now)
                allowed, retry = True, 0.0
            else:
                self._buckets[key] = (tokens, now)
                allowed, retry = False, (1 - tokens) / self.refill if self.refill > 0 else 60.0
            if len(self._buckets) > 20000:  # bound memory: drop buckets that are full again
                full_after = self.capacity / self.refill if self.refill > 0 else 3600
                self._buckets = {k: v for k, v in self._buckets.items() if now - v[1] < full_after}
        return allowed, retry
