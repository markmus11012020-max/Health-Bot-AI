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

    def test_parses_json_fenced_response(self) -> None:
        raw = """```json
        {
          "client_answer": "Доставка 300 руб.",
          "manager_tip": "Предложите Витамин-Буст.",
          "needs_upsell": true,
          "citations": ["Условия доставки"],
          "confidence": 0.91
        }
        ```"""
        parsed = self.parser.parse(raw)
        self.assertEqual(parsed.client_answer, "Доставка 300 руб.")
        self.assertTrue(parsed.needs_upsell)
        self.assertEqual(parsed.citations, ("Условия доставки",))
        self.assertAlmostEqual(parsed.confidence, 0.91)

    def test_json_false_upsell(self) -> None:
        parsed = self.parser.parse(
            '{"client_answer":"ok","manager_tip":"Допродажа не требуется",'
            '"needs_upsell":false}'
        )
        self.assertFalse(parsed.needs_upsell)

    def test_salvages_truncated_json(self) -> None:
        raw = (
            '{"client_answer": "Олег, спасибо! Доставка 300 руб. '
            'Не является медицинской рекомендацией.", "confidence": 0.8'
        )
        parsed = self.parser.parse(raw)
        self.assertEqual(
            parsed.client_answer,
            "Олег, спасибо! Доставка 300 руб. Не является медицинской рекомендацией.",
        )
        self.assertNotIn('"client_answer"', parsed.client_answer)
        self.assertIn("не сформирована", parsed.manager_tip)

    def test_salvages_json_with_unescaped_quotes(self) -> None:
        raw = (
            '{"client_answer": "Ответ с "кавычками" внутри", '
            '"manager_tip": "Совет"}'
        )
        parsed = self.parser.parse(raw)
        self.assertIn("Ответ", parsed.client_answer)
        self.assertNotIn('"client_answer"', parsed.client_answer)

    def test_to_text_round_trip(self) -> None:
        parsed = self.parser.parse(
            '{"client_answer":"Ответ","manager_tip":"Совет","needs_upsell":true}'
        )
        text = parsed.to_text()
        self.assertIn("=== БЛОК ДЛЯ КЛИЕНТА ===", text)
        self.assertIn("Ответ", text)
        self.assertIn("Совет", text)


if __name__ == "__main__":
    unittest.main()