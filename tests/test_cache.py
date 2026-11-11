"""Response cache TTL, LRU and key versioning."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from src.core.response_cache import CacheEntry, ResponseCache


class ResponseCacheTests(unittest.TestCase):
    def _entry(self, content: str = "answer") -> CacheEntry:
        return CacheEntry(content=content, provider="Test", model="model")

    def test_put_get_and_stats(self) -> None:
        cache = ResponseCache(maxsize=2, ttl_seconds=60)
        cache.put("a", self._entry("a"))
        self.assertEqual(cache.get("a").content, "a")  # type: ignore[union-attr]
        self.assertEqual(cache.stats()["hits"], 1)
        self.assertEqual(cache.stats()["size"], 1)

    def test_ttl_expires_entry(self) -> None:
        cache = ResponseCache(maxsize=2, ttl_seconds=10)
        with patch("src.core.response_cache.time.monotonic", side_effect=[0.0, 5.0, 20.0]):
            cache.put("a", self._entry())
            self.assertIsNotNone(cache.get("a"))
            self.assertIsNone(cache.get("a"))

    def test_lru_eviction(self) -> None:
        cache = ResponseCache(maxsize=2, ttl_seconds=60)
        cache.put("a", self._entry("a"))
        cache.put("b", self._entry("b"))
        cache.get("a")
        cache.put("c", self._entry("c"))
        self.assertIsNotNone(cache.get("a"))
        self.assertIsNone(cache.get("b"))
        self.assertIsNotNone(cache.get("c"))

    def test_key_changes_with_kb_and_prompt_version(self) -> None:
        base = dict(
            anonymized_input="x",
            prompt_variant="standard",
            temperature=0.2,
            max_tokens=800,
            provider_name="AITunnel",
            model_name="m",
        )
        k1 = ResponseCache.make_key(**base, kb_version="v1", prompt_version="p1")
        k2 = ResponseCache.make_key(**base, kb_version="v2", prompt_version="p1")
        k3 = ResponseCache.make_key(**base, kb_version="v1", prompt_version="p2")
        self.assertEqual(len({k1, k2, k3}), 3)

    def test_clear(self) -> None:
        cache = ResponseCache()
        cache.put("a", self._entry())
        cache.clear()
        self.assertEqual(cache.stats()["size"], 0)


if __name__ == "__main__":
    unittest.main()
