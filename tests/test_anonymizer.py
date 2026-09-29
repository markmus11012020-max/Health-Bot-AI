"""Unit tests for PII anonymization (152-ФЗ compliance)."""
from __future__ import annotations

import unittest

from src.core.anonymizer import PIIAnonymizer, anonymize_text


class PIIAnonymizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.anon = PIIAnonymizer()

    def test_empty_input(self) -> None:
        self.assertEqual(self.anon.anonymize(""), "")

    def test_masks_russian_first_name(self) -> None:
        out = self.anon.anonymize("Мария оформляет заказ на Детокс.")
        self.assertIn("[Клиент]", out)
        self.assertNotIn("Мария", out)

    def test_masks_phone_various_formats(self) -> None:
        for phone in [
            "+7 (927) 123-45-67",
            "89271234567",
            "+79271234567",
            "927-123-45-67",
            "(927) 123-45-67",
        ]:
            with self.subTest(phone=phone):
                out = self.anon.anonymize(f"Позвоните {phone} завтра")
                self.assertIn("[Телефон]", out)

    def test_masks_email(self) -> None:
        out = self.anon.anonymize("Пишите на test@example.com")
        self.assertIn("[Email]", out)
        self.assertNotIn("test@example.com", out)

    def test_masks_address(self) -> None:
        out = self.anon.anonymize("Доставить по ул. Ленина, дом 5")
        self.assertIn("[Адрес]", out)

    def test_preserves_non_pii_text(self) -> None:
        text = "Детокс — бережное очищение организма"
        self.assertEqual(self.anon.anonymize(text), text)

    def test_module_level_facade(self) -> None:
        out = anonymize_text("Звоните +79271234567 или пишите")
        self.assertIn("[Телефон]", out)


if __name__ == "__main__":
    unittest.main()