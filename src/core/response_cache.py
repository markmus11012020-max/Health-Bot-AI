"""In-memory LRU-кэш для AI-ответов.

Ключ — SHA-256 от анонимизированного ввода + параметров генерации.
Это безопасно: в кэше хранятся только анонимизированные данные и
уже-сгенерированные ответы LLM (они тоже не содержат ПД, т.к. LLM видит
только маскированный текст).
"""
from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from dataclasses import dataclass


@dataclass(frozen=True)
class CacheEntry:
    content: str
    provider: str
    model: str


class ResponseCache:
    """Thread-safe LRU-кэш фиксированного размера."""

    def __init__(self, maxsize: int = 64) -> None:
        self._maxsize = maxsize
        self._data: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def make_key(
        *,
        anonymized_input: str,
        prompt_variant: str,
        temperature: float,
        max_tokens: int,
        provider_name: str,
        model_name: str,
    ) -> str:
        """SHA-256 от всех факторов, влияющих на результат."""
        payload = (
            f"{anonymized_input}|{prompt_variant}|{temperature}|{max_tokens}|"
            f"{provider_name}|{model_name}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, key: str) -> CacheEntry | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is not None:
                self._data.move_to_end(key)  # LRU touch
            return entry

    def put(self, key: str, entry: CacheEntry) -> None:
        with self._lock:
            self._data[key] = entry
            self._data.move_to_end(key)
            if len(self._data) > self._maxsize:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"size": len(self._data), "maxsize": self._maxsize}