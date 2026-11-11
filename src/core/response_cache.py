"""Response cache: in-process LRU with TTL, optional Redis backend.

Cache keys include the knowledge-base version and prompt fingerprint, so a
content update never serves stale answers.  Values contain only anonymized
input metadata and already-generated answers; raw PII is never stored.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)

# Bump when sanitization/parsing/business rules change in a way that makes old
# cached answers unsafe or misleading.
CACHE_SCHEMA_VERSION = "2026-11-11-2"


@dataclass(frozen=True)
class CacheEntry:
    content: str
    provider: str
    model: str
    citations: tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 0.8
    safety_flags: tuple[str, ...] = field(default_factory=tuple)


class CacheBackend(Protocol):
    def get(self, key: str) -> CacheEntry | None: ...
    def put(self, key: str, entry: CacheEntry) -> None: ...
    def clear(self) -> None: ...
    def stats(self) -> dict[str, int | float]: ...


class ResponseCache:
    """Thread-safe LRU cache with per-entry TTL."""

    def __init__(self, maxsize: int = 256, ttl_seconds: int = 86400) -> None:
        self._maxsize = max(1, maxsize)
        self._ttl = max(0, ttl_seconds)
        self._data: OrderedDict[str, tuple[float, CacheEntry]] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def make_key(
        *,
        anonymized_input: str,
        prompt_variant: str,
        temperature: float,
        max_tokens: int,
        provider_name: str,
        model_name: str,
        kb_version: str = "",
        prompt_version: str = "",
    ) -> str:
        """SHA-256 of every factor that can change the answer."""
        payload = (
            f"{CACHE_SCHEMA_VERSION}|{anonymized_input}|{prompt_variant}|"
            f"{temperature}|{max_tokens}|{provider_name}|{model_name}|"
            f"{kb_version}|{prompt_version}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, key: str) -> CacheEntry | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                self._misses += 1
                return None
            created_at, entry = item
            if self._ttl and (time.monotonic() - created_at) > self._ttl:
                del self._data[key]
                self._misses += 1
                return None
            self._data.move_to_end(key)  # LRU touch
            self._hits += 1
            return entry

    def put(self, key: str, entry: CacheEntry) -> None:
        with self._lock:
            self._data[key] = (time.monotonic(), entry)
            self._data.move_to_end(key)
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict[str, int | float]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._data),
                "maxsize": self._maxsize,
                "ttl_seconds": self._ttl,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total else 0.0,
            }


class RedisResponseCache:
    """Redis-backed cache for multi-worker deployments.

    Falls back to an in-process cache if Redis is unavailable at call time.
    """

    PREFIX = "hbai:answer:"

    def __init__(self, url: str, ttl_seconds: int = 86400, maxsize: int = 256) -> None:
        import redis  # local import keeps Redis optional

        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._ttl = max(0, ttl_seconds)
        self._maxsize = max(1, maxsize)
        self._fallback = ResponseCache(maxsize=maxsize, ttl_seconds=ttl_seconds)
        self._hits = 0
        self._misses = 0

    def _key(self, key: str) -> str:
        return f"{self.PREFIX}{key}"

    def get(self, key: str) -> CacheEntry | None:
        try:
            raw = self._client.get(self._key(key))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis GET failed, using fallback cache: %s", exc)
            return self._fallback.get(key)
        if not raw:
            self._misses += 1
            return None
        try:
            payload = json.loads(raw)
            self._hits += 1
            return CacheEntry(
                content=payload["content"],
                provider=payload["provider"],
                model=payload["model"],
                citations=tuple(payload.get("citations") or ()),
                confidence=float(payload.get("confidence", 0.8)),
                safety_flags=tuple(payload.get("safety_flags") or ()),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            logger.warning("Corrupted cache entry %s; ignoring", key)
            self._misses += 1
            return None

    def put(self, key: str, entry: CacheEntry) -> None:
        payload = json.dumps(asdict(entry), ensure_ascii=False)
        try:
            if self._ttl:
                self._client.setex(self._key(key), self._ttl, payload)
            else:
                self._client.set(self._key(key), payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis SET failed, using fallback cache: %s", exc)
            self._fallback.put(key, entry)

    def clear(self) -> None:
        try:
            for key in self._client.scan_iter(match=f"{self.PREFIX}*"):
                self._client.delete(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis CLEAR failed: %s", exc)
        self._fallback.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> dict[str, int | float]:
        try:
            size = sum(1 for _ in self._client.scan_iter(match=f"{self.PREFIX}*"))
        except Exception:  # noqa: BLE001
            size = int(self._fallback.stats()["size"])
        total = self._hits + self._misses
        return {
            "size": int(size),
            "maxsize": self._maxsize,
            "ttl_seconds": self._ttl,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 4) if total else 0.0,
        }


def build_cache(
    *,
    redis_url: str = "",
    maxsize: int = 256,
    ttl_seconds: int = 86400,
) -> CacheBackend:
    """Return Redis cache when configured and reachable, otherwise in-memory."""
    if redis_url:
        try:
            cache = RedisResponseCache(redis_url, ttl_seconds=ttl_seconds, maxsize=maxsize)
            cache._client.ping()  # type: ignore[attr-defined]
            logger.info("Using Redis response cache")
            return cache
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis is not reachable (%s); using in-memory cache", exc)
    return ResponseCache(maxsize=maxsize, ttl_seconds=ttl_seconds)
