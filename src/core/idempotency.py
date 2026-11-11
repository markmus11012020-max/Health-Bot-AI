"""In-process idempotency store for POST requests.

Redis is the production target; for a single-process MVP this TTL dictionary is
sufficient and keeps the demo dependency-free.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class _Entry:
    expires_at: float
    value: Any


class IdempotencyStore:
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._ttl = max(1, ttl_seconds)
        self._data: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                del self._data[key]
                return None
            return entry.value

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = _Entry(
                expires_at=time.monotonic() + self._ttl, value=value
            )
            # Opportunistic cleanup keeps the dict bounded.
            if len(self._data) > 2048:
                now = time.monotonic()
                self._data = {
                    k: v for k, v in self._data.items() if v.expires_at > now
                }

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
