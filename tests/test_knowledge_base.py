"""Knowledge base versioning and retrieval."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.core.knowledge_base import KnowledgeBase


class KnowledgeBaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "kb.txt"
        self.path.write_text(
            "## ПРОДУКТ: Детокс\nОчищение организма. Цена 4500 руб.\n\n"
            "## ДОСТАВКА\nБесплатно от 5000 руб., иначе 300 руб.\n\n"
            "## АКЦИЯ\nВитамин-Буст со скидкой 20%.\n",
            encoding="utf-8",
        )
        self.kb = KnowledgeBase(self.path, top_k=2)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_version_is_stable_and_changes_with_content(self) -> None:
        first = self.kb.version
        self.assertEqual(first, self.kb.version)
        self.path.write_text("## Новый раздел\nТекст", encoding="utf-8")
        self.assertNotEqual(first, self.kb.version)

    def test_retrieve_returns_relevant_section(self) -> None:
        chunks = self.kb.retrieve("Сколько стоит доставка?")
        self.assertTrue(chunks)
        self.assertIn("ДОСТАВКА", chunks[0].title)

    def test_context_contains_citation(self) -> None:
        context, citations = self.kb.context_for("доставка")
        self.assertIn("ДОСТАВКА", context)
        self.assertIn("ДОСТАВКА", citations)

    def test_chunks_are_not_empty(self) -> None:
        self.assertGreaterEqual(len(self.kb.chunks()), 3)

    def test_missing_file_falls_back(self) -> None:
        kb = KnowledgeBase(Path(self.tmp.name) / "missing.txt")
        self.assertIn("не найдена", kb.read())


if __name__ == "__main__":
    unittest.main()
