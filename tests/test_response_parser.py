"""Unit tests for the AI response parser."""
from __future__ import annotations

import unittest

from src.core.response_parser import ParsedResponse, ResponseParser, parse_ai_response


class ResponseParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = ResponseParser()

    def test_parses_well_formed_two_block_response(self) -> None:
        raw = (
            "=== БЛОК ДЛЯ КЛИЕНТА ===\n"
            "Здравствуйте! Доставка 300 руб.\n\n"
            "=== БЛОК ДЛЯ МЕНЕДЖЕРА (ВНУТРЕННИЙ) ===\n"
            "Предложите Витамин-Буст со скидкой 20%."
        )
        parsed = self.parser.parse(raw)
        self.assertIsInstance(parsed, ParsedResponse)
        self.assertIn("Доставка 300 руб.", parsed.client_answer)
        self.assertIn("Витамин-Буст", parsed.manager_tip)
        self.assertTrue(parsed.needs_upsell)

    def test_detects_no_upsell_marker(self) -> None:
        raw = (
            "=== БЛОК ДЛЯ КЛИЕНТА ===\n"
            "Спасибо за вопрос!\n\n"
            "=== БЛОК ДЛЯ МЕНЕДЖЕРА (ВНУТРЕННИЙ) ===\n"
            "Допродажа не требуется"
        )
        parsed = self.parser.parse(raw)
        self.assertFalse(parsed.needs_upsell)

    def test_fallback_when_no_markers(self) -> None:
        parsed = self.parser.parse("Просто текст без разделителей.")
        self.assertEqual(parsed.client_answer, "Просто текст без разделителей.")
        self.assertIn("не сформирована", parsed.manager_tip)

    def test_extract_copy_text(self) -> None:
        raw = (
            "=== БЛОК ДЛЯ КЛИЕНТА ===\n"
            "Здравствуйте!\n\n"
            "=== БЛОК ДЛЯ МЕНЕДЖЕРА (ВНУТРЕННИЙ) ===\n"
            "Предложите доп. товар."
        )
        copy_text = self.parser.extract_copy_text(raw)
        self.assertEqual(copy_text, "Здравствуйте!")

    def test_module_level_facade(self) -> None:
        parsed = parse_ai_response(
            "=== БЛОК ДЛЯ КЛИЕНТА ===\nОтвет\n\n=== БЛОК ДЛЯ МЕНЕДЖЕРА (ВНУТРЕННИЙ) ===\nСовет"
        )
        self.assertEqual(parsed.client_answer, "Ответ")
        self.assertEqual(parsed.manager_tip, "Совет")


if __name__ == "__main__":
    unittest.main()