"""Knowledge base loader with versioning and lightweight retrieval.

The production target is pgvector/embeddings.  For the production MVP we use a
deterministic lexical retriever: it has no external dependencies, is easy to
test, and keeps the prompt small by selecting the most relevant sections.

The public ``retrieve()`` interface is intentionally compatible with a future
embedding-backed implementation.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_TOKEN_RE = re.compile(r"[А-ЯЁа-яёA-Za-z0-9]{3,}")
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class KnowledgeChunk:
    """A retrievable section of the knowledge base."""

    id: str
    title: str
    text: str
    score: float = 0.0


class KnowledgeBase:
    """Read-only knowledge base with versioning and lexical retrieval."""

    DEFAULT_PATH = "knowledge_base.txt"
    FALLBACK_TEXT = "База знаний не найдена. Используйте информацию по умолчанию."
    MAX_CHUNK_CHARS = 1400

    def __init__(
        self,
        path: str | Path = DEFAULT_PATH,
        *,
        top_k: int = 3,
        max_chars: int = 6000,
    ) -> None:
        self._path = Path(path)
        self._top_k = max(1, top_k)
        self._max_chars = max(500, max_chars)

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

    @property
    def version(self) -> str:
        """Stable content hash used in cache keys and audit records."""
        return hashlib.sha256(self.read().encode("utf-8")).hexdigest()[:16]

    def chunks(self) -> list[KnowledgeChunk]:
        """Split the KB into section-level chunks."""
        content = self.read()
        matches = list(_HEADING_RE.finditer(content))
        chunks: list[KnowledgeChunk] = []

        if not matches:
            return self._split_plain(content, title="База знаний")

        for index, match in enumerate(matches):
            title = match.group(1).strip()
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
            body = content[start:end].strip()
            chunks.extend(self._split_plain(body, title=title, prefix=str(index)))

        return chunks

    def _split_plain(
        self, text: str, *, title: str, prefix: str = "0"
    ) -> list[KnowledgeChunk]:
        text = text.strip()
        if not text:
            return []
        if len(text) <= self.MAX_CHUNK_CHARS:
            return [KnowledgeChunk(id=f"{prefix}-0", title=title, text=text)]

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        result: list[KnowledgeChunk] = []
        buffer = ""
        part = 0
        for paragraph in paragraphs:
            if buffer and len(buffer) + len(paragraph) + 2 > self.MAX_CHUNK_CHARS:
                result.append(
                    KnowledgeChunk(id=f"{prefix}-{part}", title=title, text=buffer.strip())
                )
                buffer = ""
                part += 1
            buffer = f"{buffer}\n\n{paragraph}".strip()
        if buffer:
            result.append(
                KnowledgeChunk(id=f"{prefix}-{part}", title=title, text=buffer.strip())
            )
        return result

    def retrieve(self, query: str, *, top_k: int | None = None) -> list[KnowledgeChunk]:
        """Return the most relevant chunks for a query.

        Lexical scoring is intentionally simple: term overlap plus a title
        bonus.  It is deterministic and good enough for the small OCX KB.
        """
        chunks = self.chunks()
        if not chunks:
            return []

        query_terms = {t.lower() for t in _TOKEN_RE.findall(query or "")}
        if not query_terms:
            return chunks[: (top_k or self._top_k)]

        scored: list[KnowledgeChunk] = []
        for chunk in chunks:
            haystack = f"{chunk.title}\n{chunk.text}".lower()
            score = sum(1.0 for term in query_terms if term in haystack)
            title_score = sum(1.0 for term in query_terms if term in chunk.title.lower())
            score += title_score * 2.0
            scored.append(
                KnowledgeChunk(
                    id=chunk.id,
                    title=chunk.title,
                    text=chunk.text,
                    score=round(score, 3),
                )
            )

        scored.sort(key=lambda c: (-c.score, c.id))
        selected = [c for c in scored if c.score > 0][: (top_k or self._top_k)]
        if not selected:
            selected = scored[: (top_k or self._top_k)]
        return selected

    def context_for(self, query: str) -> tuple[str, tuple[str, ...]]:
        """Build a prompt-ready context and a list of citations."""
        selected = self.retrieve(query)
        if not selected:
            text = self.read()[: self._max_chars]
            return text, ("База знаний",)

        parts: list[str] = []
        citations: list[str] = []
        for chunk in selected:
            parts.append(f"[Источник: {chunk.title}]\n{chunk.text}")
            citations.append(chunk.title)
        context = "\n\n".join(parts)
        if len(context) > self._max_chars:
            context = context[: self._max_chars].rsplit("\n", 1)[0]
        return context, tuple(dict.fromkeys(citations))


@lru_cache(maxsize=4)
def _cached_loader(path: str) -> KnowledgeBase:
    return KnowledgeBase(path)


def load_knowledge_base(path: str = KnowledgeBase.DEFAULT_PATH) -> str:
    """Functional facade — keeps backwards compatibility with `app.py`."""
    return _cached_loader(path).read()
