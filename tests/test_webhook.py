"""Тесты FastAPI webhook без сетевых вызовов."""
from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.ai.base import ChatResult
from src.ai.orchestrator import OrchestrationResult
from src.api import webhook
from src.api.webhook import app
from src.core.rate_limit import RateLimiter
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


class WebhookProductionTests(unittest.TestCase):
    """Contract, security and streaming tests for the production API."""

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
            request_id="req-1",
            citations=("Условия доставки",),
            confidence=0.9,
        )
        webhook._idempotency.clear()

    def _fake_service(self) -> MagicMock:
        service = MagicMock()
        service.run.return_value = self._fake_outcome
        service.cache.stats.return_value = {"size": 0, "maxsize": 10, "ttl_seconds": 60}
        return service

    def test_prompt_variant_and_use_cache_are_honoured(self) -> None:
        service = self._fake_service()
        with patch("src.api.webhook.get_service", return_value=service) as get:
            response = self.client.post(
                "/v1/consult",
                json={
                    "crm_context": "Мария, Детокс 4500",
                    "client_message": "Сколько доставка?",
                    "prompt_variant": "warm",
                    "use_cache": False,
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        get.assert_called_once_with(None, "warm")
        kwargs = service.run.call_args.kwargs
        self.assertFalse(kwargs["use_cache"])
        self.assertIn("request_id", kwargs)
        self.assertEqual(response.json()["citations"], ["Условия доставки"])
        self.assertEqual(response.json()["confidence"], 0.9)

    def test_api_key_is_enforced_when_configured(self) -> None:
        secured = replace(webhook.settings, api_key="secret")
        with patch("src.api.webhook.settings", secured):
            response = self.client.post(
                "/v1/consult",
                json={"crm_context": "x", "client_message": "y"},
            )
            self.assertEqual(response.status_code, 401)

            service = self._fake_service()
            with patch("src.api.webhook.get_service", return_value=service):
                response = self.client.post(
                    "/v1/consult",
                    json={"crm_context": "x", "client_message": "y"},
                    headers={"X-API-Key": "secret"},
                )
            self.assertEqual(response.status_code, 200, response.text)

    def test_admin_cache_clear_is_protected(self) -> None:
        secured = replace(webhook.settings, admin_api_key="admin-secret")
        with patch("src.api.webhook.settings", secured):
            response = self.client.post("/v1/admin/cache/clear")
            self.assertEqual(response.status_code, 403)
            response = self.client.post(
                "/v1/admin/cache/clear", headers={"X-Admin-Key": "admin-secret"}
            )
            self.assertEqual(response.status_code, 200, response.text)

    def test_rate_limit_returns_429(self) -> None:
        service = self._fake_service()
        with patch("src.api.webhook.get_service", return_value=service), patch(
            "src.api.webhook._rate_limiter", RateLimiter(1, 60)
        ):
            first = self.client.post(
                "/v1/consult",
                json={"crm_context": "x", "client_message": "y"},
            )
            second = self.client.post(
                "/v1/consult",
                json={"crm_context": "x", "client_message": "y"},
            )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 429)
        self.assertIn("Retry-After", second.headers)

    def test_idempotency_key_prevents_duplicate_work(self) -> None:
        service = self._fake_service()
        headers = {"Idempotency-Key": "abc-123"}
        payload = {"crm_context": "x", "client_message": "y"}
        with patch("src.api.webhook.get_service", return_value=service):
            first = self.client.post("/v1/consult", json=payload, headers=headers)
            second = self.client.post("/v1/consult", json=payload, headers=headers)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(service.run.call_count, 1)

    def test_stream_returns_sse_events(self) -> None:
        service = self._fake_service()

        def stream():
            yield "Здравствуйте"
            return self._fake_outcome

        service.stream_run.return_value = stream()
        with patch("src.api.webhook.get_service", return_value=service):
            response = self.client.post(
                "/v1/consult/stream",
                json={"crm_context": "x", "client_message": "y"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("event: meta", response.text)
        self.assertIn("event: token", response.text)
        self.assertIn("event: done", response.text)
        self.assertIn("Здравствуйте", response.text)

    def test_feedback_is_saved(self) -> None:
        with patch.object(webhook._database, "record_feedback", return_value=7) as save:
            response = self.client.post(
                "/v1/feedback",
                json={"request_id": "req-1", "rating": 5, "correct": True},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["feedback_id"], 7)
        save.assert_called_once()

    def test_ready_reports_dependencies(self) -> None:
        with patch.object(webhook._database, "health", return_value=True):
            response = self.client.get("/ready")
        self.assertIn(response.status_code, (200, 503))
        body = response.json()
        self.assertIn("database", body)
        self.assertIn("cache", body)
        self.assertIn("providers", body)


if __name__ == "__main__":
    unittest.main()