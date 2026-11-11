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

    def test_masks_snils_inn_passport_and_card(self) -> None:
        text = (
            "СНИЛС 123-456-789 00, ИНН 770123456789, "
            "паспорт 45 06 123456, карта 4111 1111 1111 1111"
        )
        out = self.anon.anonymize(text)
        self.assertIn("[СНИЛС]", out)
        self.assertIn("[ИНН]", out)
        self.assertIn("[Паспорт]", out)
        self.assertIn("[Карта]", out)

    def test_masks_ip_and_birth_date(self) -> None:
        text = "IP 192.168.1.10, дата рождения 01.01.1990"
        out = self.anon.anonymize(text)
        self.assertIn("[IP]", out)
        self.assertIn("[Дата рождения]", out)

    def test_detailed_counts(self) -> None:
        result = self.anon.anonymize_detailed("Мария, +79271234567")
        self.assertEqual(result.counts.get("name"), 1)
        self.assertEqual(result.counts.get("phone"), 1)
        self.assertEqual(result.total, 2)

    def test_does_not_mask_prices_or_product_names(self) -> None:
        text = "О-комплекс Детокс стоит 4500 руб."
        self.assertEqual(self.anon.anonymize(text), text)

    def test_masks_single_name_oleg(self) -> None:
        out = self.anon.anonymize("Олег оформляет комплекс за 4500 руб.")
        self.assertIn("[Клиент]", out)
        self.assertNotIn("Олег", out)


if __name__ == "__main__":
    unittest.main()