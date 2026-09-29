"""Knowledge base loader (file-backed, cacheable)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path


class KnowledgeBase:
    """Read-only knowledge base with transparent caching."""

    DEFAULT_PATH = "knowledge_base.txt"
    FALLBACK_TEXT = "База знаний не найдена. Используйте информацию по умолчанию."

    def __init__(self, path: str | Path = DEFAULT_PATH) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> str:
        """Load KB content from disk; return placeholder on missing file."""
        try:
            return self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return self.FALLBACK_TEXT

    def refresh(self) -> str:
        """Re-read from disk bypassing any cache (used after edits)."""
        return self.read()


@lru_cache(maxsize=4)
def _cached_loader(path: str) -> KnowledgeBase:
    return KnowledgeBase(path)


def load_knowledge_base(path: str = KnowledgeBase.DEFAULT_PATH) -> str:
    """Functional facade — keeps backwards compatibility with `app.py`."""
    return _cached_loader(path).read()