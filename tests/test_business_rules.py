"""Deterministic upsell/delivery fallback rules."""
from __future__ import annotations

import unittest

from src.core.business_rules import UpsellAdvisor


class UpsellAdvisorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.advisor = UpsellAdvisor()

    def test_detox_context_offers_vitamin_boost(self) -> None:
        result = self.advisor.recommend(
            crm_context="Олег оформляет комплекс за 4500 руб.",
            client_message="Сколько доставка в Новосибирск?",
        )
        self.assertTrue(result.needs_upsell)
        self.assertIn("Витамин-Буст", result.text)
        self.assertIn("1 680", result.text)
        self.assertIn("6 180", result.text)

    def test_delivery_below_threshold(self) -> None:
        result = self.advisor.recommend(
            crm_context="Заказ на 3000 руб.",
            client_message="Сколько стоит доставка?",
        )
        self.assertTrue(result.needs_upsell)
        self.assertIn("300", result.text)

    def test_no_upsell_for_neutral_question(self) -> None:
        result = self.advisor.recommend(
            crm_context="Клиент спрашивает о графике работы.",
            client_message="Когда вы работаете?",
        )
        self.assertFalse(result.needs_upsell)
        self.assertIn("не требуется", result.text)

    def test_keeps_existing_manager_tip(self) -> None:
        result = self.advisor.recommend(
            crm_context="Детокс 4500",
            manager_tip="Предложите Витамин-Буст.",
        )
        self.assertEqual(result.text, "Предложите Витамин-Буст.")
        self.assertTrue(result.needs_upsell)


if __name__ == "__main__":
    unittest.main()
