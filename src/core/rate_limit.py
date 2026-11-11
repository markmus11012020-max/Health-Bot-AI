"""Simple in-process sliding-window rate limiter.

For a multi-worker deployment replace the store with Redis (INCR + EXPIRE).
The interface is deliberately small so that swap is local.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self._max = max(0, max_requests)
        self._window = max(1, window_seconds)
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        if self._max == 0:
            return True
        now = time.monotonic()
        with self._lock:
            bucket = self._events[key]
            while bucket and now - bucket[0] > self._window:
                bucket.popleft()
            if len(bucket) >= self._max:
                return False
            bucket.append(now)
            return True

    def retry_after(self, key: str) -> int:
        with self._lock:
            bucket = self._events.get(key)
            if not bucket:
                return 0
            return max(1, int(self._window - (time.monotonic() - bucket[0])))

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
