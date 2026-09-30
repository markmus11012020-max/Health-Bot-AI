"""Тесты FastAPI webhook без сетевых вызовов."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.ai.base import ChatResult
from src.ai.orchestrator import OrchestrationResult
from src.api.webhook import app
from src.services.consultation_service import ConsultationOutcome


class WebhookSchemaTests(unittest.TestCase):
    """Проверяем Pydantic-валидацию и 4xx-ответы без AI-вызовов."""

    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health(self) -> None:
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("aitunnel", body["providers"])
        self.assertIn("standard", body["prompt_variants"])

    def test_consult_requires_both_fields(self) -> None:
        r = self.client.post("/consult", json={})
        self.assertEqual(r.status_code, 422)

    def test_consult_rejects_empty_strings(self) -> None:
        r = self.client.post(
            "/consult",
            json={"crm_context": "", "client_message": "test"},
        )
        self.assertEqual(r.status_code, 422)


class WebhookConsultTests(unittest.TestCase):
    """С моком сервиса — без реальных запросов к LLM."""

    def setUp(self) -> None:
        self.client = TestClient(app)
        self._fake_outcome = ConsultationOutcome(
            result=OrchestrationResult(
                success=True,
                result=ChatResult(
                    content=(
                        "=== БЛОК ДЛЯ КЛИЕНТА ===\n"
                        "Здравствуйте! Доставка 300 руб.\n\n"
                        "=== БЛОК ДЛЯ МЕНЕДЖЕРА (ВНУТРЕННИЙ) ===\n"
                        "Предложите Витамин-Буст со скидкой 20%."
                    ),
                    provider="AITunnel",
                    model="minimax-m3",
                ),
                error=None,
                anonymized="...",
            ),
            anonymized_input="...",
            cache_hit=False,
        )

    def _patch_service(self) -> MagicMock:
        """Подменяем get_service() внутри модуля webhook на мок."""
        return patch("src.api.webhook.get_service")

    def test_consult_returns_two_blocks(self) -> None:
        fake_svc = MagicMock()
        fake_svc.run.return_value = self._fake_outcome
        with patch("src.api.webhook.get_service", return_value=fake_svc):
            r = self.client.post(
                "/consult",
                json={
                    "crm_context": "Мария оформляет Детокс за 4500р.",
                    "client_message": "Сколько доставка в Самару?",
                },
            )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("Доставка 300 руб", r.json()["client_answer"])
        self.assertIn("Витамин-Буст", r.json()["manager_tip"])
        self.assertTrue(r.json()["needs_upsell"])
        self.assertFalse(r.json()["cache_hit"])

    def test_consult_provider_override(self) -> None:
        fake_svc = MagicMock()
        fake_svc.run.return_value = self._fake_outcome
        # Патчим оба места: build_consultation_service (для override) и get_service (для fallback).
        with patch(
            "src.api.webhook.build_consultation_service", return_value=fake_svc
        ), patch("src.api.webhook.get_service", return_value=fake_svc):
            r = self.client.post(
                "/consult",
                json={
                    "crm_context": "Test",
                    "client_message": "Hello",
                    "provider": "yandex",
                },
            )
        self.assertEqual(r.status_code, 200, r.text)

    def test_consult_returns_502_on_failure(self) -> None:
        fake_svc = MagicMock()
        fake_svc.run.return_value = ConsultationOutcome(
            result=OrchestrationResult(
                success=False,
                result=None,
                error="AITunnel: Timeout",
                anonymized="...",
            ),
            anonymized_input="...",
        )
        with patch("src.api.webhook.get_service", return_value=fake_svc):
            r = self.client.post(
                "/consult",
                json={"crm_context": "x", "client_message": "y"},
            )
        self.assertEqual(r.status_code, 502)
        self.assertIn("Timeout", r.json()["detail"])


if __name__ == "__main__":
    unittest.main()