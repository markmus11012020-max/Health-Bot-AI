"""Тест: сырые ПД не должны попадать в запросы к AI-провайдеру.

Это критичное требование 152-ФЗ: даже если LLM «случайно» увидит
ФИО или телефон в системном или пользовательском промпте — это утечка.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from src.ai.orchestrator import OrchestrationResult
from src.core.anonymizer import PIIAnonymizer
from src.core.knowledge_base import KnowledgeBase
from src.services.consultation_service import (
    ConsultationInput,
    ConsultationService,
)


class _CaptureOrchestrator:
    """Сохраняет ChatRequest, который ему передали."""

    def __init__(self) -> None:
        self.captured_request = None

    def complete(self, request, *, anonymized: str = ""):  # noqa: ANN001
        self.captured_request = request
        return OrchestrationResult(
            success=True,
            result=MagicMock(content="ok", provider="Test", model="test"),
            error=None,
            anonymized=anonymized,
        )


class ConsultationServicePiiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.orch = _CaptureOrchestrator()
        self.svc = ConsultationService(
            settings=MagicMock(temperature=0.2, max_tokens=800),
            orchestrator=self.orch,
            knowledge_base=KnowledgeBase(),
            anonymizer=PIIAnonymizer(),
        )

    def test_raw_name_does_not_leak_to_llm(self) -> None:
        payload = ConsultationInput(
            crm_context="Мария оформляет заказ на Детокс за 4500р.",
            client_message="Здравствуйте, я Мария, хочу уточнить доставку.",
        )
        self.svc.run(payload)
        req = self.orch.captured_request
        joined = (req.system_prompt + "\n" + req.user_message).lower()
        self.assertNotIn("мария", joined, "Сырое имя клиента попало в LLM-промпт!")

    def test_raw_phone_does_not_leak_to_llm(self) -> None:
        payload = ConsultationInput(
            crm_context="Клиент: Мария, +79271234567",
            client_message="Перезвоните мне на +7 (927) 123-45-67",
        )
        self.svc.run(payload)
        req = self.orch.captured_request
        joined = req.system_prompt + "\n" + req.user_message
        # Телефон в любом из своих 5 форматов не должен «протечь»
        for needle in ("79271234567", "9271234567", "+7 (927) 123-45-67"):
            self.assertNotIn(needle, joined, f"Сырой телефон {needle} попал в LLM!")

    def test_raw_email_does_not_leak_to_llm(self) -> None:
        payload = ConsultationInput(
            crm_context="Email клиента: secret@example.com",
            client_message="Напишите мне на secret@example.com",
        )
        self.svc.run(payload)
        joined = (
            self.orch.captured_request.system_prompt
            + "\n"
            + self.orch.captured_request.user_message
        )
        self.assertNotIn("secret@example.com", joined)

    def test_placeholders_are_present(self) -> None:
        payload = ConsultationInput(
            crm_context="Мария, +79271234567",
            client_message="Мария звонит с +79271234567",
        )
        self.svc.run(payload)
        joined = (
            self.orch.captured_request.system_prompt
            + "\n"
            + self.orch.captured_request.user_message
        )
        self.assertIn("[Клиент]", joined)
        self.assertIn("[Телефон]", joined)

    def test_cache_hit_skips_orchestrator(self) -> None:
        """Повторный идентичный запрос должен вернуться из кэша, не дёргая AI."""
        payload = ConsultationInput(
            crm_context="Клиент оформляет Детокс.",
            client_message="Сколько стоит доставка?",
        )
        first = self.svc.run(payload)
        self.assertFalse(first.cache_hit, "первый запрос не должен быть cache hit")
        # Второй идентичный запрос — должен попасть в кэш
        captured_before = self.orch.captured_request
        self.orch.captured_request = None  # сбросим, чтобы поймать новый вызов
        second = self.svc.run(payload)
        self.assertTrue(second.cache_hit, "второй запрос должен быть cache hit")
        self.assertIsNone(
            self.orch.captured_request, "AI-оркестратор не должен был вызываться"
        )
        self.assertEqual(first.result.result.content, second.result.result.content)
        del captured_before  # silence unused


if __name__ == "__main__":
    unittest.main()